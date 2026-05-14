"""Slskd provider adapter with offline/injected-client search flow.

This module is an isolated external adapter for the slskd backend.
It does NOT perform network calls, real downloads, or import any
central Flux service. Core services must NOT import this module.

A future NativeSoulseekProvider can implement the same contracts
without rewriting the core.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from noqlen_flux.providers.base import SearchProvider
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

_logger = logging.getLogger(__name__)

_REDACTED = "[redacted]"

_DEFAULT_MAX_POLL_ATTEMPTS = 10


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
    """

    base_url: str | None = None
    api_key: str | None = None
    timeout_seconds: int = 30
    max_poll_attempts: int = _DEFAULT_MAX_POLL_ATTEMPTS

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
            }
        )

    def __repr__(self) -> str:
        return (
            f"SlskdProviderConfig("
            f"base_url={self.base_url!r}, "
            f"api_key={_REDACTED if self.api_key else None!r}, "
            f"timeout_seconds={self.timeout_seconds!r}, "
            f"max_poll_attempts={self.max_poll_attempts!r})"
        )


class SlskdClientProtocol(Protocol):
    """Injectable protocol for slskd-like client interactions.

    Implementations handle actual network communication.
    This commit provides only FakeSlskdClient for tests.

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

    @property
    def poll_count(self) -> int:
        return self._poll_count

    def was_search_stopped(self, search_id: str) -> bool:
        return self._active_searches.get(search_id, False)


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


class SlskdProvider(SearchProvider):
    """Slskd provider adapter for Flux with offline/injected-client search flow.

    Without an injected client, it returns controlled unavailable states
    and does NOT access the network.

    Core services must NOT import this module directly.
    They should depend on the generic SearchProvider contract only.

    Search flow:
    1. Convert SearchQuery to safe search text.
    2. Call client.start_search().
    3. Poll client.get_search_state() with bounded attempts.
    4. If timeout/poll limit reached, call stop_search() and return with timeout_reached.
    5. On completion, call client.get_search_responses().
    6. Map responses to SearchCandidate via SlskdPayloadMapper.
    7. Return SearchProviderResult.
    """

    _SEARCH_CAPABILITIES: list[ProviderCapability] = [
        ProviderCapability.SEARCH,
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
            return ProviderHealth(
                provider=self.name,
                kind=ProviderKind.EXTERNAL,
                availability=ProviderAvailability.UNAVAILABLE,
                status_message="slskd adapter has no active client",
                capabilities=self.capabilities(),
                warnings=["no slskd client configured; network access disabled"],
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
        if self._client is None:
            return SearchProviderResult(
                provider=self.name,
                query=query,
                errors=["slskd adapter has no active client; search unavailable"],
            )

        try:
            search_text = self._build_search_text(query)
            search_id = self._client.start_search(search_text)
        except Exception as exc:  # noqa: BLE001
            return SearchProviderResult(
                provider=self.name,
                query=query,
                errors=[f"slskd search start failed: {exc}"],
            )

        warnings: list[str] = []
        timeout_reached = False

        try:
            state, timeout_reached, warnings = self._poll_until_complete(search_id, warnings)
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
                self._client.stop_search(search_id)
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
            payload = self._client.get_search_responses(search_id)
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
        search_id: str,
        warnings: list[str],
    ) -> tuple[SearchState, bool, list[str]]:
        max_attempts = self._config.max_poll_attempts
        timeout_reached = False

        for attempt in range(1, max_attempts + 1):
            try:
                state_payload = self._client.get_search_state(search_id)
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
