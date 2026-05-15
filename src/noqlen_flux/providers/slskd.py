"""Slskd provider adapter with offline/injected-client search flow.

This module is an isolated external adapter for the slskd backend.
It does NOT perform network calls, real downloads, or import any
central Flux service. Core services must NOT import this module.

A future NativeSoulseekProvider can implement the same contracts
without rewriting the core.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen

from noqlen_flux.providers.base import QueueExecutionProvider, SearchProvider
from noqlen_flux.providers.status import (
    ProviderAvailability,
    ProviderCapability,
    ProviderHealth,
    ProviderKind,
)
from noqlen_flux.results import _clean
from noqlen_flux.search import (
    CandidateFile,
    SearchCandidate,
    SearchKind,
    SearchProviderResult,
    SearchQuery,
)
from noqlen_flux.transfers import (
    QueueItem,
    QueuePlan,
    TransferExecutionMode,
    TransferExecutionRequest,
    TransferItem,
    TransferSubmissionItem,
    TransferSubmissionResult,
    TransferSubmissionState,
)

_logger = logging.getLogger(__name__)

_REDACTED = "[redacted]"

_DEFAULT_MAX_POLL_ATTEMPTS = 10
_DEFAULT_HTTP_TIMEOUT = 5


class SearchState(StrEnum):
    """Conceptual search lifecycle states."""

    IN_PROGRESS = "InProgress"
    COMPLETED = "Completed"
    FAILED = "Failed"
    STOPPED = "Stopped"
    UNKNOWN = "Unknown"


@dataclass(slots=True)
class SlskdProviderConfig:
    """Configuration for the slskd provider adapter.

    Sensitive fields are redacted in to_dict/repr.
    Network access is disabled by default.
    """

    base_url: str | None = None
    api_key: str | None = None
    timeout_seconds: int = _DEFAULT_HTTP_TIMEOUT
    max_poll_attempts: int = _DEFAULT_MAX_POLL_ATTEMPTS
    allow_network: bool = False

    def __post_init__(self) -> None:
        if self.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive")
        if self.max_poll_attempts < 1:
            raise ValueError("max_poll_attempts must be positive")

    def to_dict(self) -> dict[str, Any]:
        return _clean(
            {
                "base_url": self.base_url,
                "api_key": self.api_key,
                "timeout_seconds": self.timeout_seconds,
                "max_poll_attempts": self.max_poll_attempts,
                "allow_network": self.allow_network,
            }
        )

    def __repr__(self) -> str:
        return (
            f"SlskdProviderConfig("
            f"base_url={self.base_url!r}, "
            f"api_key={_REDACTED if self.api_key else None!r}, "
            f"timeout_seconds={self.timeout_seconds!r}, "
            f"max_poll_attempts={self.max_poll_attempts!r}, "
            f"allow_network={self.allow_network!r})"
        )


class SlskdClientProtocol(Protocol):
    """Injectable protocol for slskd-like client interactions.

    Implementations handle actual network communication.
    This commit provides FakeSlskdClient for tests and
    SlskdHttpClient for optional real network access.

    The protocol follows a lifecycle:
    1. start_search(query_text) -> search_id
    2. get_search_state(search_id) -> state payload
    3. (poll bounded) repeat step 2 until Completed/Failed
    4. get_search_responses(search_id) -> response payload
    5. stop_search(search_id) -> None (cleanup, especially on timeout)
    """

    def start_search(self, query_text: str) -> str:
        """Start a search and return a search identifier."""
        ...

    def get_search_state(self, search_id: str) -> dict[str, Any]:
        """Return the current state of a search."""
        ...

    def get_search_responses(self, search_id: str) -> dict[str, Any]:
        """Return the collected search responses."""
        ...

    def stop_search(self, search_id: str) -> None:
        """Stop/cancel an ongoing search."""
        ...

    def health_check(self) -> dict[str, Any]:
        """Return a raw slskd-like health status dict."""
        ...


class FakeSlskdClient:
    """Fake slskd client for offline tests.

    Simulates a polling-based search lifecycle with configurable behavior:
    - immediate completion
    - delayed completion (polls InProgress first)
    - timeout (never completes within poll limit)
    - failure
    - empty responses
    - controlled errors
    - locked files
    - multi-file album responses

    Queue submission (offline/fake):
    - success, failed, duplicate, locked, user_offline, invalid_item,
      provider_unavailable
    """

    def __init__(
        self,
        *,
        responses: list[dict[str, Any]] | None = None,
        healthy: bool = True,
        poll_delay: int = 0,
        fail_after_polls: int | None = None,
        raise_on_start: bool = False,
        raise_on_state: bool = False,
        raise_on_responses: bool = False,
        queue_simulate_failures: bool = False,
        queue_simulate_duplicate: bool = False,
        queue_simulate_locked: bool = False,
        queue_simulate_user_offline: bool = False,
        queue_simulate_invalid_item: bool = False,
        queue_simulate_provider_unavailable: bool = False,
    ) -> None:
        self._responses = list(responses or [])
        self._healthy = healthy
        self._poll_delay = poll_delay
        self._fail_after_polls = fail_after_polls
        self._raise_on_start = raise_on_start
        self._raise_on_state = raise_on_state
        self._raise_on_responses = raise_on_start if raise_on_responses is None else raise_on_responses
        self._poll_count: int = 0
        self._active_searches: dict[str, bool] = {}
        self._queue_simulate_failures = queue_simulate_failures
        self._queue_simulate_duplicate = queue_simulate_duplicate
        self._queue_simulate_locked = queue_simulate_locked
        self._queue_simulate_user_offline = queue_simulate_user_offline
        self._queue_simulate_invalid_item = queue_simulate_invalid_item
        self._queue_simulate_provider_unavailable = queue_simulate_provider_unavailable
        self._queue_submissions: list[dict[str, Any]] = []

    def start_search(self, query_text: str) -> str:
        if self._raise_on_start:
            raise RuntimeError("fake client: start_search error")
        search_id = f"fake-search-{uuid.uuid4().hex[:8]}"
        self._active_searches[search_id] = False
        self._poll_count = 0
        return search_id

    def get_search_state(self, search_id: str) -> dict[str, Any]:
        if self._raise_on_state:
            raise RuntimeError("fake client: get_search_state error")
        self._poll_count += 1

        if self._fail_after_polls is not None and self._poll_count > self._fail_after_polls:
            return {"state": SearchState.FAILED.value, "message": "fake search failed after polls"}

        if self._poll_delay > 0 and self._poll_count <= self._poll_delay:
            return {"state": SearchState.IN_PROGRESS.value}

        return {"state": SearchState.COMPLETED.value}

    def get_search_responses(self, search_id: str) -> dict[str, Any]:
        if self._raise_on_responses:
            raise RuntimeError("fake client: get_search_responses error")
        if not self._responses:
            return {"responses": [], "response_count": 0}
        return self._responses[0]

    def stop_search(self, search_id: str) -> None:
        if search_id in self._active_searches:
            self._active_searches[search_id] = True

    def health_check(self) -> dict[str, Any]:
        if self._healthy:
            return {"status": "ok", "version": "0.0.0-fake"}
        return {"status": "error", "message": "fake client unavailable"}

    def submit_queue(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Simulate a queue submission response."""
        result = _simulate_slskd_queue_submission(
            payload,
            simulate_failures=self._queue_simulate_failures,
            simulate_duplicate=self._queue_simulate_duplicate,
            simulate_locked=self._queue_simulate_locked,
            simulate_user_offline=self._queue_simulate_user_offline,
            simulate_invalid_item=self._queue_simulate_invalid_item,
            simulate_provider_unavailable=self._queue_simulate_provider_unavailable,
        )
        self._queue_submissions.append(result)
        return result

    @property
    def poll_count(self) -> int:
        return self._poll_count

    def was_search_stopped(self, search_id: str) -> bool:
        return self._active_searches.get(search_id, False)

    @property
    def queue_submissions(self) -> list[dict[str, Any]]:
        return list(self._queue_submissions)


class SlskdHttpClient:
    """Optional real HTTP client for slskd search and health.

    Uses only the Python standard library (urllib.request).
    Network access must be explicitly allowed via config.
    API keys are never exposed in error messages or metadata.

    NOTE: The exact slskd API endpoint paths below are based on
    common slskd API patterns and must be confirmed against the
    actual slskd version in use before production deployment.
    The client structure is isolated and testable via fake transport.
    """

    def __init__(self, config: SlskdProviderConfig) -> None:
        self._config = config

    def health_check(self) -> dict[str, Any]:
        """Perform a real health check against the slskd API."""
        base_url = self._config.base_url
        if not base_url:
            return {"status": "error", "message": "no base_url configured"}

        url = f"{base_url.rstrip('/')}/api/server/version"
        headers: dict[str, str] = {}
        if self._config.api_key:
            headers["X-Api-Key"] = self._config.api_key

        req = Request(url, headers=headers, method="GET")

        try:
            with urlopen(req, timeout=self._config.timeout_seconds) as resp:
                raw = resp.read()
                try:
                    data = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return {"status": "error", "message": "invalid response from slskd"}
                return {"status": "ok", "version": data.get("version", "unknown")}
        except URLError as exc:
            reason = str(exc.reason) if hasattr(exc, "reason") else str(exc)
            return {"status": "error", "message": f"slskd unreachable: {reason}"}
        except TimeoutError:
            return {"status": "error", "message": "slskd health check timed out"}
        except OSError:
            return {"status": "error", "message": "slskd network error"}

    def start_search(self, query_text: str) -> str:
        """Start a search and return the search ID.

        Endpoint path must be confirmed against actual slskd API.
        """
        base_url = self._config.base_url
        if not base_url:
            raise RuntimeError("slskd client: no base_url configured")

        url = f"{base_url.rstrip('/')}/api/v1/searches"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["X-Api-Key"] = self._config.api_key

        body = json.dumps({"text": query_text}).encode("utf-8")
        req = Request(url, data=body, headers=headers, method="POST")

        try:
            with urlopen(req, timeout=self._config.timeout_seconds) as resp:
                raw = resp.read()
                data = json.loads(raw)
                search_id = data.get("id") or data.get("searchId")
                if not search_id:
                    raise RuntimeError("slskd client: search started but no ID returned")
                return str(search_id)
        except URLError as exc:
            reason = str(exc.reason) if hasattr(exc, "reason") else str(exc)
            raise RuntimeError(f"slskd client: search start failed: {reason}") from exc
        except TimeoutError:
            raise RuntimeError("slskd client: search start timed out") from None
        except OSError as exc:
            raise RuntimeError("slskd client: search start network error") from exc

    def get_search_state(self, search_id: str) -> dict[str, Any]:
        """Return the current state of a search.

        Endpoint path must be confirmed against actual slskd API.
        """
        base_url = self._config.base_url
        if not base_url:
            raise RuntimeError("slskd client: no base_url configured")

        url = f"{base_url.rstrip('/')}/api/v1/searches/{_url_quote(search_id)}"
        headers: dict[str, str] = {}
        if self._config.api_key:
            headers["X-Api-Key"] = self._config.api_key

        req = Request(url, headers=headers, method="GET")

        try:
            with urlopen(req, timeout=self._config.timeout_seconds) as resp:
                raw = resp.read()
                data = json.loads(raw)
                state = data.get("state") or data.get("status")
                if not state:
                    return {"state": SearchState.UNKNOWN.value, "raw": _safe_summary(data)}
                return {"state": str(state)}
        except URLError as exc:
            reason = str(exc.reason) if hasattr(exc, "reason") else str(exc)
            raise RuntimeError(f"slskd client: state check failed: {reason}") from exc
        except TimeoutError:
            raise RuntimeError("slskd client: state check timed out") from None
        except OSError as exc:
            raise RuntimeError("slskd client: state check network error") from exc

    def get_search_responses(self, search_id: str) -> dict[str, Any]:
        """Return the collected search responses.

        Endpoint path must be confirmed against actual slskd API.
        """
        base_url = self._config.base_url
        if not base_url:
            raise RuntimeError("slskd client: no base_url configured")

        url = f"{base_url.rstrip('/')}/api/v1/searches/{_url_quote(search_id)}/responses"
        headers: dict[str, str] = {}
        if self._config.api_key:
            headers["X-Api-Key"] = self._config.api_key

        req = Request(url, headers=headers, method="GET")

        try:
            with urlopen(req, timeout=self._config.timeout_seconds) as resp:
                raw = resp.read()
                data = json.loads(raw)
                return _normalize_search_responses(data)
        except URLError as exc:
            reason = str(exc.reason) if hasattr(exc, "reason") else str(exc)
            raise RuntimeError(f"slskd client: response retrieval failed: {reason}") from exc
        except TimeoutError:
            raise RuntimeError("slskd client: response retrieval timed out") from None
        except OSError as exc:
            raise RuntimeError("slskd client: response retrieval network error") from exc

    def stop_search(self, search_id: str) -> None:
        """Stop/cancel an ongoing search.

        Endpoint path must be confirmed against actual slskd API.
        """
        base_url = self._config.base_url
        if not base_url:
            return

        url = f"{base_url.rstrip('/')}/api/v1/searches/{_url_quote(search_id)}"
        headers: dict[str, str] = {}
        if self._config.api_key:
            headers["X-Api-Key"] = self._config.api_key

        req = Request(url, headers=headers, method="DELETE")

        try:
            with urlopen(req, timeout=self._config.timeout_seconds):
                pass
        except (URLError, TimeoutError, OSError):
            pass


def _url_quote(value: str) -> str:
    """URL-safe quote for search IDs."""
    from urllib.parse import quote
    return quote(value, safe="")


def _safe_summary(data: dict[str, Any], max_keys: int = 5) -> dict[str, Any]:
    """Return a safe summary of a dict without exposing sensitive data."""
    summary: dict[str, Any] = {}
    for i, (k, v) in enumerate(data.items()):
        if i >= max_keys:
            break
        if _is_sensitive_key(k):
            summary[k] = "[redacted]"
        elif isinstance(v, (str, int, float, bool)):
            summary[k] = v
        elif isinstance(v, list):
            summary[k] = f"[{len(v)} items]"
        elif isinstance(v, dict):
            summary[k] = "{...}"
        else:
            summary[k] = str(v)
    return summary


def _is_sensitive_key(key: str) -> bool:
    """Check if a key looks sensitive."""
    sensitive_parts = ("key", "token", "secret", "password", "auth", "credential")
    normalized = key.lower().replace("_", "-")
    return any(part in normalized for part in sensitive_parts)


def _normalize_search_responses(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize raw slskd search response data to Flux-expected format."""
    if isinstance(data, list):
        responses = data
        response_count = len(responses)
    elif isinstance(data, dict):
        responses = data.get("responses") or data.get("files") or data.get("results") or []
        if not isinstance(responses, list):
            responses = [responses] if responses else []
        response_count = data.get("responseCount") or data.get("response_count") or len(responses)
    else:
        responses = []
        response_count = 0

    if not isinstance(response_count, int) or response_count < 0:
        response_count = len(responses)

    normalized_responses = []
    for r in responses:
        if not isinstance(r, dict):
            continue
        normalized_responses.append(_normalize_single_response(r))

    return {
        "responses": normalized_responses,
        "response_count": response_count,
    }


def _normalize_single_response(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a single search response dict."""
    username = raw.get("username") or raw.get("user") or ""
    directory = raw.get("directory") or raw.get("path") or raw.get("folder")
    files = raw.get("files") or raw.get("fileList") or raw.get("file_list") or []
    locked_files = raw.get("lockedFiles") or raw.get("locked_files") or raw.get("locked") or []

    if not isinstance(files, list):
        files = [files] if files else []
    if not isinstance(locked_files, list):
        locked_files = [locked_files] if locked_files else []

    return {
        "username": str(username) if username else "",
        "directory": str(directory) if isinstance(directory, str) else None,
        "files": [_normalize_file(f) for f in files if isinstance(f, dict)],
        "locked_files": [_normalize_file(f) for f in locked_files if isinstance(f, dict)],
    }


def _normalize_file(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a single file dict from slskd response."""
    filename = raw.get("filename") or raw.get("name") or raw.get("file") or ""
    size = raw.get("size") or raw.get("filesize") or raw.get("file_size")
    bitrate = raw.get("bitrate") or raw.get("bitRate")
    extension = raw.get("extension") or raw.get("ext")
    duration = raw.get("duration") or raw.get("length") or raw.get("time")

    safe_ext = None
    if isinstance(extension, str) and extension.strip():
        safe_ext = extension.strip().lstrip(".")
    elif isinstance(filename, str) and "." in filename:
        safe_ext = filename.rsplit(".", 1)[-1].lower()

    return {
        "filename": str(filename) if filename else "",
        "size": int(size) if isinstance(size, (int, float)) and size >= 0 else None,
        "bitrate": int(bitrate) if isinstance(bitrate, (int, float)) and bitrate > 0 else None,
        "extension": safe_ext,
        "duration": int(duration) if isinstance(duration, (int, float)) and duration >= 0 else None,
    }


class SlskdPayloadMapper:
    """Pure mapping functions from slskd-like payloads to Flux models.

    No network access, no side effects, no raw payload leakage.
    """

    @staticmethod
    def map_search_response_to_candidates(
        payload: dict[str, Any],
        query: SearchQuery,
    ) -> list[SearchCandidate]:
        """Convert a slskd-like search response into Flux SearchCandidate list."""
        raw_responses = payload.get("responses", [])
        if not isinstance(raw_responses, list):
            _logger.warning("slskd payload: 'responses' is not a list")
            return []

        candidates: list[SearchCandidate] = []
        for idx, response in enumerate(raw_responses):
            if not isinstance(response, dict):
                _logger.warning("slskd payload: response %d is not a dict", idx)
                continue

            candidate = SlskdPayloadMapper._map_single_response(response, query, idx)
            if candidate is not None:
                candidates.append(candidate)

        return candidates

    @staticmethod
    def map_file_payload_to_candidate_file(
        file_payload: dict[str, Any],
        *,
        locked: bool = False,
    ) -> CandidateFile | None:
        """Convert a single file dict from slskd payload to CandidateFile."""
        if not isinstance(file_payload, dict):
            return None

        filename = file_payload.get("filename")
        if not filename or not isinstance(filename, str) or not filename.strip():
            return None

        size = file_payload.get("size")
        bitrate = file_payload.get("bitrate")
        extension = file_payload.get("extension")
        duration = file_payload.get("duration")

        safe_size = int(size) if isinstance(size, (int, float)) and size >= 0 else None
        safe_bitrate = int(bitrate) if isinstance(bitrate, (int, float)) and bitrate > 0 else None
        safe_duration = int(duration) if isinstance(duration, (int, float)) and duration >= 0 else None
        safe_ext = extension if isinstance(extension, str) and extension.strip() else None

        try:
            return CandidateFile(
                filename=filename.strip(),
                size_bytes=safe_size,
                declared_bitrate=safe_bitrate,
                extension=safe_ext,
                duration_seconds=safe_duration,
                locked=locked,
            )
        except ValueError:
            _logger.warning("slskd payload: invalid CandidateFile fields for %r", filename)
            return None

    @staticmethod
    def map_provider_health(
        config: SlskdProviderConfig,
        health_payload: dict[str, Any] | None = None,
    ) -> ProviderHealth:
        """Map slskd health payload to Flux ProviderHealth."""
        if health_payload is None:
            return ProviderHealth(
                provider="slskd",
                kind=ProviderKind.EXTERNAL,
                availability=ProviderAvailability.UNAVAILABLE,
                status_message="no client configured",
                capabilities=[ProviderCapability.SEARCH],
                warnings=["slskd adapter has no active client"],
            )

        status = health_payload.get("status", "")
        if status == "ok":
            availability = ProviderAvailability.AVAILABLE
            status_message = "slskd backend reports ok"
        else:
            availability = ProviderAvailability.DEGRADED
            status_message = health_payload.get("message", "slskd backend reports unknown status")

        return ProviderHealth(
            provider="slskd",
            kind=ProviderKind.EXTERNAL,
            availability=availability,
            status_message=status_message,
            capabilities=[ProviderCapability.SEARCH],
        )

    @staticmethod
    def _map_single_response(
        response: dict[str, Any],
        query: SearchQuery,
        index: int,
    ) -> SearchCandidate | None:
        username = response.get("username", "")
        if not isinstance(username, str) or not username.strip():
            _logger.warning("slskd payload: response %d missing username", index)
            return None

        directory = response.get("directory")
        if not isinstance(directory, (str, type(None))):
            directory = None

        files_payload = response.get("files", [])
        locked_payload = response.get("locked_files", [])

        if not isinstance(files_payload, list):
            files_payload = []
        if not isinstance(locked_payload, list):
            locked_payload = []

        files: list[CandidateFile] = []
        for fp in files_payload:
            cf = SlskdPayloadMapper.map_file_payload_to_candidate_file(fp, locked=False)
            if cf is not None:
                files.append(cf)

        for lp in locked_payload:
            cf = SlskdPayloadMapper.map_file_payload_to_candidate_file(lp, locked=True)
            if cf is not None:
                files.append(cf)

        if not files:
            _logger.warning("slskd payload: response %d from %r has no valid files", index, username)
            return None

        candidate_id = f"slskd-{username.strip()}-{index}-{uuid.uuid4().hex[:8]}"

        artist = query.artist
        title = query.title if query.kind == SearchKind.TRACK else None
        album = query.album if query.kind == SearchKind.ALBUM else None

        return SearchCandidate(
            candidate_id=candidate_id,
            provider="slskd",
            username=username.strip(),
            directory=directory,
            artist=artist,
            title=title,
            album=album,
            files=files,
        )


class SlskdProvider(SearchProvider, QueueExecutionProvider):
    """Slskd provider adapter for Flux with offline/injected-client search flow.

    Without an injected client, it returns controlled unavailable states
    and does NOT access the network.

    Core services must NOT import this module directly.
    They should depend on the generic SearchProvider and QueueExecutionProvider
    contracts only.

    Search flow:
    1. Convert SearchQuery to safe search text.
    2. Call client.start_search().
    3. Poll client.get_search_state() with bounded attempts.
    4. If timeout/poll limit reached, call stop_search() and return with timeout_reached.
    5. On completion, call client.get_search_responses().
    6. Map responses to SearchCandidate via SlskdPayloadMapper.
    7. Return SearchProviderResult.

    Queue execution flow (offline/fake only in this commit):
    1. Convert TransferExecutionRequest to slskd-like payload.
    2. Call client.submit_queue() (fake/injected only).
    3. Map response to TransferSubmissionResult.
    4. Return TransferSubmissionResult.
    """

    _SEARCH_CAPABILITIES: list[ProviderCapability] = [
        ProviderCapability.SEARCH,
        ProviderCapability.HEALTH,
    ]

    _QUEUE_CAPABILITIES: list[ProviderCapability] = [
        ProviderCapability.QUEUE_PLANNING,
        ProviderCapability.HEALTH,
    ]

    def __init__(
        self,
        config: SlskdProviderConfig | None = None,
        *,
        client: SlskdClientProtocol | None = None,
    ) -> None:
        self._config = config or SlskdProviderConfig()
        self._client = client

    @property
    def name(self) -> str:
        return "slskd"

    def capabilities(self) -> list[ProviderCapability]:
        return list(self._SEARCH_CAPABILITIES)

    def health(self) -> ProviderHealth:
        if self._client is None:
            if self._config.allow_network and self._config.base_url:
                real_client = SlskdHttpClient(self._config)
                try:
                    payload = real_client.health_check()
                    return SlskdPayloadMapper.map_provider_health(self._config, payload)
                except Exception as exc:  # noqa: BLE001
                    return ProviderHealth(
                        provider=self.name,
                        kind=ProviderKind.EXTERNAL,
                        availability=ProviderAvailability.UNAVAILABLE,
                        status_message="slskd health check failed",
                        capabilities=self.capabilities(),
                        errors=["health check exception"],
                    )
            return ProviderHealth(
                provider=self.name,
                kind=ProviderKind.EXTERNAL,
                availability=ProviderAvailability.UNAVAILABLE,
                status_message="network access disabled",
                capabilities=self.capabilities(),
                warnings=["slskd network access is disabled by default; use allow_network=true to enable"],
            )

        try:
            payload = self._client.health_check()
            return SlskdPayloadMapper.map_provider_health(self._config, payload)
        except Exception as exc:  # noqa: BLE001
            return ProviderHealth(
                provider=self.name,
                kind=ProviderKind.EXTERNAL,
                availability=ProviderAvailability.UNAVAILABLE,
                status_message=f"slskd health check failed: {exc}",
                capabilities=self.capabilities(),
                errors=["health check exception"],
            )

    def search(self, query: SearchQuery) -> SearchProviderResult:
        client = self._resolve_client()
        if client is None:
            return SearchProviderResult(
                provider=self.name,
                query=query,
                errors=["slskd adapter has no active client; search unavailable"],
            )

        try:
            search_text = self._build_search_text(query)
            search_id = client.start_search(search_text)
        except Exception as exc:  # noqa: BLE001
            return SearchProviderResult(
                provider=self.name,
                query=query,
                errors=[f"slskd search start failed: {exc}"],
            )

        warnings: list[str] = []
        timeout_reached = False

        try:
            state, timeout_reached, warnings = self._poll_until_complete(client, search_id, warnings)
        except Exception as exc:  # noqa: BLE001
            return SearchProviderResult(
                provider=self.name,
                query=query,
                errors=[f"slskd search polling failed: {exc}"],
                warnings=warnings,
            )

        if state == SearchState.FAILED:
            return SearchProviderResult(
                provider=self.name,
                query=query,
                errors=["slskd search completed with failure state"],
                warnings=warnings,
            )

        if timeout_reached:
            try:
                client.stop_search(search_id)
            except Exception:  # noqa: BLE001
                pass
            warnings.append("slskd search reached poll limit; results may be incomplete")
            return SearchProviderResult(
                provider=self.name,
                query=query,
                warnings=warnings,
                timeout_reached=True,
            )

        try:
            payload = client.get_search_responses(search_id)
        except Exception as exc:  # noqa: BLE001
            return SearchProviderResult(
                provider=self.name,
                query=query,
                errors=[f"slskd search response retrieval failed: {exc}"],
                warnings=warnings,
            )

        candidates = SlskdPayloadMapper.map_search_response_to_candidates(payload, query)
        response_count = payload.get("response_count", 0)
        if not isinstance(response_count, int) or response_count < 0:
            response_count = len(candidates)

        if not candidates:
            warnings.append("slskd search returned no candidates")

        return SearchProviderResult(
            provider=self.name,
            query=query,
            candidates=candidates,
            response_count=response_count,
            warnings=warnings,
            timeout_reached=timeout_reached,
        )

    def _resolve_client(self) -> SlskdClientProtocol | None:
        """Resolve the client to use: injected client first, then real HTTP client if allowed."""
        if self._client is not None:
            return self._client

        if self._config.allow_network and self._config.base_url:
            return SlskdHttpClient(self._config)

        return None

    def _build_search_text(self, query: SearchQuery) -> str:
        if query.kind == SearchKind.TRACK:
            parts = [query.artist]
            if query.title:
                parts.append(query.title)
            parts.extend(query.extra_terms)
            return " ".join(p for p in parts if p and p.strip())
        parts = [query.artist]
        if query.album:
            parts.append(query.album)
        parts.extend(query.extra_terms)
        return " ".join(p for p in parts if p and p.strip())

    def _poll_until_complete(
        self,
        client: SlskdClientProtocol,
        search_id: str,
        warnings: list[str],
    ) -> tuple[SearchState, bool, list[str]]:
        max_attempts = self._config.max_poll_attempts
        timeout_reached = False

        for attempt in range(1, max_attempts + 1):
            try:
                state_payload = client.get_search_state(search_id)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"slskd poll attempt {attempt} failed: {exc}")
                if attempt == max_attempts:
                    timeout_reached = True
                    return SearchState.UNKNOWN, timeout_reached, warnings
                continue

            state_str = state_payload.get("state", SearchState.UNKNOWN.value)
            try:
                state = SearchState(state_str)
            except ValueError:
                state = SearchState.UNKNOWN
                warnings.append(f"slskd unknown state: {state_str}")

            if state in (SearchState.COMPLETED, SearchState.FAILED):
                return state, False, warnings

            if state == SearchState.STOPPED:
                warnings.append("slskd search was stopped externally")
                return SearchState.STOPPED, False, warnings

        timeout_reached = True
        return SearchState.IN_PROGRESS, timeout_reached, warnings

    def submit_queue(self, request: TransferExecutionRequest) -> TransferSubmissionResult:
        """Submit a queue transfer request via the slskd adapter.

        This is offline/fake only in this commit. No real network calls,
        no real downloads, no real queue operations.

        Without an injected client that supports submit_queue, returns
        a controlled unavailable state.
        """
        client = self._resolve_client()
        if client is None:
            return TransferSubmissionResult(
                submission_id=str(uuid.uuid4()),
                request_id=request.request_id,
                state=TransferSubmissionState.UNAVAILABLE,
                blocked=True,
                block_reasons=["slskd adapter has no active client; queue submission unavailable"],
                errors=["no client configured"],
            )

        if request.mode == TransferExecutionMode.APPLY and not request.policy.allow_provider_queue:
            return TransferSubmissionResult(
                submission_id=str(uuid.uuid4()),
                request_id=request.request_id,
                state=TransferSubmissionState.BLOCKED,
                blocked=True,
                block_reasons=["provider queue execution not allowed by policy"],
            )

        if request.queue_plan.blocked:
            return TransferSubmissionResult(
                submission_id=str(uuid.uuid4()),
                request_id=request.request_id,
                state=TransferSubmissionState.BLOCKED,
                blocked=True,
                block_reasons=list(request.queue_plan.block_reasons) or ["queue plan is blocked"],
            )

        if not request.queue_plan.items:
            return TransferSubmissionResult(
                submission_id=str(uuid.uuid4()),
                request_id=request.request_id,
                state=TransferSubmissionState.BLOCKED,
                blocked=True,
                block_reasons=["queue plan has no items"],
            )

        payload = SlskdQueuePayloadMapper.map_execution_request_to_slskd_payload(request)

        try:
            response = client.submit_queue(payload)
        except Exception as exc:  # noqa: BLE001
            return TransferSubmissionResult(
                submission_id=str(uuid.uuid4()),
                request_id=request.request_id,
                state=TransferSubmissionState.PROVIDER_ERROR,
                blocked=True,
                block_reasons=[f"slskd queue submission failed: {exc}"],
                errors=["queue submission exception"],
            )

        return SlskdQueuePayloadMapper.map_slskd_queue_response_to_submission_result(
            response, request.request_id,
        )


# ---------------------------------------------------------------------------
# Queue execution (offline/fake mapping only)
# ---------------------------------------------------------------------------


class SlskdQueueSubmissionState(StrEnum):
    """Internal slskd-like queue submission states.

    These map to Flux TransferSubmissionState but are kept separate
    to avoid leaking slskd-specific details into the core.
    """

    QUEUED = "queued"
    DOWNLOADING = "downloading"
    COMPLETE = "complete"
    FAILED = "failed"
    DUPLICATE = "duplicate"
    LOCKED = "locked"
    USER_OFFLINE = "user_offline"
    INVALID_ITEM = "invalid_item"
    PROVIDER_UNAVAILABLE = "provider_unavailable"


class SlskdQueuePayloadMapper:
    """Pure mapping functions between Flux transfer execution models and
    slskd-like queue payloads.

    No network access, no side effects, no raw payload leakage.
    """

    @staticmethod
    def map_execution_request_to_slskd_payload(
        request: TransferExecutionRequest,
    ) -> dict[str, Any]:
        """Convert a TransferExecutionRequest into a slskd-like queue payload.

        The result is a safe dict suitable for a fake slskd client.
        No sensitive data, no raw provider payloads, no api_key.
        """
        queue_plan = request.queue_plan
        items: list[dict[str, Any]] = []

        for queue_item in queue_plan.items:
            transfer_item = queue_item.transfer_item
            if transfer_item is None:
                continue
            items.append({
                "username": transfer_item.candidate_id,
                "filename": transfer_item.filename,
                "directory": transfer_item.target_relative_path.rsplit("/", 1)[0]
                if "/" in transfer_item.target_relative_path
                else ".",
                "size": transfer_item.size_bytes,
                "locked": transfer_item.locked,
                "priority": transfer_item.priority.value,
            })

        return {
            "queue_id": queue_plan.queue_id,
            "request_id": request.request_id,
            "items": items,
            "item_count": len(items),
            "blocked": queue_plan.blocked,
            "block_reasons": list(queue_plan.block_reasons),
        }

    @staticmethod
    def map_slskd_queue_response_to_submission_result(
        response: dict[str, Any],
        request_id: str,
    ) -> TransferSubmissionResult:
        """Convert a fake slskd queue response into a TransferSubmissionResult.

        Handles: success, failed, duplicate, locked, user_offline,
        invalid_item, provider_unavailable.
        """
        submission_id = response.get("submission_id", str(uuid.uuid4()))
        raw_items = response.get("items", [])
        raw_state = response.get("state", SlskdQueueSubmissionState.FAILED.value)

        items: list[TransferSubmissionItem] = []
        has_errors = False
        all_blocked = True
        has_locked = False
        has_duplicate = False

        for raw_item in raw_items:
            item_state = SlskdQueuePayloadMapper._map_item_state(raw_item)
            message = raw_item.get("message", "")
            warnings = list(raw_item.get("warnings", []))
            errors = list(raw_item.get("errors", []))

            if item_state in (
                TransferSubmissionState.PROVIDER_ERROR,
                TransferSubmissionState.UNAVAILABLE,
            ):
                has_errors = True
            if item_state == TransferSubmissionState.LOCKED_ITEM:
                has_locked = True
            if item_state == TransferSubmissionState.DUPLICATE:
                has_duplicate = True
            if item_state not in (
                TransferSubmissionState.BLOCKED,
            ):
                all_blocked = False

            items.append(TransferSubmissionItem(
                queue_item_id=raw_item.get("queue_item_id", ""),
                state=item_state,
                message=message,
                warnings=warnings,
                errors=errors,
            ))

        response_errors = response.get("errors", [])

        if has_errors:
            overall_state = TransferSubmissionState.PROVIDER_ERROR
            blocked = True
        elif not items and raw_state in (
            SlskdQueueSubmissionState.PROVIDER_UNAVAILABLE.value,
            SlskdQueueSubmissionState.USER_OFFLINE.value,
        ):
            overall_state = TransferSubmissionState.UNAVAILABLE
            blocked = True
        elif response.get("blocked", False):
            overall_state = TransferSubmissionState.BLOCKED
            blocked = True
        elif all_blocked and items:
            overall_state = TransferSubmissionState.BLOCKED
            blocked = True
        elif (has_locked or has_duplicate) and not has_errors:
            overall_state = TransferSubmissionState.SUCCESS
            blocked = False
        else:
            overall_state = TransferSubmissionState.SUCCESS
            blocked = False

        return TransferSubmissionResult(
            submission_id=submission_id,
            request_id=request_id,
            state=overall_state,
            items=items,
            blocked=blocked,
            block_reasons=list(response.get("block_reasons", [])),
            warnings=list(response.get("warnings", [])),
            errors=list(response.get("errors", [])),
        )

    @staticmethod
    def _map_item_state(raw_item: dict[str, Any]) -> TransferSubmissionState:
        """Map a single raw item state to TransferSubmissionState."""
        slskd_state = raw_item.get("state", SlskdQueueSubmissionState.FAILED.value)
        mapping = {
            SlskdQueueSubmissionState.QUEUED.value: TransferSubmissionState.SUBMITTED,
            SlskdQueueSubmissionState.DOWNLOADING.value: TransferSubmissionState.SUBMITTED,
            SlskdQueueSubmissionState.COMPLETE.value: TransferSubmissionState.SUCCESS,
            SlskdQueueSubmissionState.FAILED.value: TransferSubmissionState.PROVIDER_ERROR,
            SlskdQueueSubmissionState.DUPLICATE.value: TransferSubmissionState.DUPLICATE,
            SlskdQueueSubmissionState.LOCKED.value: TransferSubmissionState.LOCKED_ITEM,
            SlskdQueueSubmissionState.USER_OFFLINE.value: TransferSubmissionState.UNAVAILABLE,
            SlskdQueueSubmissionState.INVALID_ITEM.value: TransferSubmissionState.PROVIDER_ERROR,
            SlskdQueueSubmissionState.PROVIDER_UNAVAILABLE.value: TransferSubmissionState.UNAVAILABLE,
        }
        return mapping.get(slskd_state, TransferSubmissionState.PROVIDER_ERROR)


def _simulate_slskd_queue_submission(
    payload: dict[str, Any],
    *,
    simulate_failures: bool = False,
    simulate_duplicate: bool = False,
    simulate_locked: bool = False,
    simulate_user_offline: bool = False,
    simulate_invalid_item: bool = False,
    simulate_provider_unavailable: bool = False,
) -> dict[str, Any]:
    """Simulate a slskd queue submission response.

    Pure function. No network, no side effects.
    """
    if simulate_provider_unavailable:
        return {
            "submission_id": str(uuid.uuid4()),
            "state": SlskdQueueSubmissionState.PROVIDER_UNAVAILABLE.value,
            "items": [],
            "blocked": True,
            "block_reasons": ["slskd provider unavailable"],
            "errors": ["provider unreachable"],
        }

    items = payload.get("items", [])
    result_items: list[dict[str, Any]] = []

    for idx, item in enumerate(items):
        queue_item_id = f"slskd-qi-{uuid.uuid4().hex[:8]}"

        if simulate_locked and item.get("locked", False):
            result_items.append({
                "queue_item_id": queue_item_id,
                "state": SlskdQueueSubmissionState.LOCKED.value,
                "message": f"locked file {item.get('filename', 'unknown')}",
                "warnings": ["item is locked"],
            })
            continue

        if simulate_duplicate:
            result_items.append({
                "queue_item_id": queue_item_id,
                "state": SlskdQueueSubmissionState.DUPLICATE.value,
                "message": f"duplicate {item.get('filename', 'unknown')}",
                "warnings": ["item already in queue"],
            })
            continue

        if simulate_user_offline:
            result_items.append({
                "queue_item_id": queue_item_id,
                "state": SlskdQueueSubmissionState.USER_OFFLINE.value,
                "message": f"user offline for {item.get('filename', 'unknown')}",
                "errors": ["user is offline"],
            })
            continue

        if simulate_invalid_item:
            result_items.append({
                "queue_item_id": queue_item_id,
                "state": SlskdQueueSubmissionState.INVALID_ITEM.value,
                "message": f"invalid item {item.get('filename', 'unknown')}",
                "errors": ["invalid file specification"],
            })
            continue

        if simulate_failures:
            result_items.append({
                "queue_item_id": queue_item_id,
                "state": SlskdQueueSubmissionState.FAILED.value,
                "message": f"failed {item.get('filename', 'unknown')}",
                "errors": ["simulated transfer failure"],
            })
            continue

        result_items.append({
            "queue_item_id": queue_item_id,
            "state": SlskdQueueSubmissionState.QUEUED.value,
            "message": f"queued {item.get('filename', 'unknown')}",
        })

    has_errors = any(
        i["state"] in (
            SlskdQueueSubmissionState.FAILED.value,
            SlskdQueueSubmissionState.USER_OFFLINE.value,
            SlskdQueueSubmissionState.INVALID_ITEM.value,
            SlskdQueueSubmissionState.PROVIDER_UNAVAILABLE.value,
        )
        for i in result_items
    )

    return {
        "submission_id": str(uuid.uuid4()),
        "state": (
            SlskdQueueSubmissionState.FAILED.value
            if has_errors
            else SlskdQueueSubmissionState.QUEUED.value
        ),
        "items": result_items,
        "blocked": has_errors or payload.get("blocked", False),
        "block_reasons": list(payload.get("block_reasons", [])),
        "warnings": [],
        "errors": [
            e for item in result_items for e in item.get("errors", [])
        ],
    }


# Extend the SlskdClientProtocol with queue methods
class SlskdClientProtocol(Protocol):
    """Injectable protocol for slskd-like client interactions.

    Implementations handle actual network communication.
    This commit provides FakeSlskdClient for tests and
    SlskdHttpClient for optional real network access.

    The protocol follows a lifecycle:
    1. start_search(query_text) -> search_id
    2. get_search_state(search_id) -> state payload
    3. (poll bounded) repeat step 2 until Completed/ Failed
    4. get_search_responses(search_id) -> response payload
    5. stop_search(search_id) -> None (cleanup, especially on timeout)

    Queue execution (offline/fake):
    6. submit_queue(payload) -> submission response
    """

    def start_search(self, query_text: str) -> str:
        """Start a search and return a search identifier."""
        ...

    def get_search_state(self, search_id: str) -> dict[str, Any]:
        """Return the current state of a search."""
        ...

    def get_search_responses(self, search_id: str) -> dict[str, Any]:
        """Return the collected search responses."""
        ...

    def stop_search(self, search_id: str) -> None:
        """Stop/cancel an ongoing search."""
        ...

    def health_check(self) -> dict[str, Any]:
        """Return a raw slskd-like health status dict."""
        ...

    def submit_queue(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Submit a queue transfer request and return a submission response.

        Offline/fake implementations simulate the response.
        Real implementations would call the slskd downloads API.
        """
        ...

