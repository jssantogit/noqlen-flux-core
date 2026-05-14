"""Slskd provider adapter skeleton.

This module is an isolated external adapter for the slskd backend.
It does NOT perform network calls, real downloads, or import any
central Flux service. Core services must NOT import this module.

A future NativeSoulseekProvider can implement the same contracts
without rewriting the core.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass, field
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


@dataclass(slots=True)
class SlskdProviderConfig:
    """Configuration for the slskd provider adapter.

    Sensitive fields are redacted in to_dict/repr.
    """

    base_url: str | None = None
    api_key: str | None = None
    timeout_seconds: int = 30

    def __post_init__(self) -> None:
        if self.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive")

    def to_dict(self) -> dict[str, Any]:
        return _clean(
            {
                "base_url": self.base_url,
                "api_key": self.api_key,
                "timeout_seconds": self.timeout_seconds,
            }
        )

    def __repr__(self) -> str:
        return (
            f"SlskdProviderConfig("
            f"base_url={self.base_url!r}, "
            f"api_key={_REDACTED if self.api_key else None!r}, "
            f"timeout_seconds={self.timeout_seconds!r})"
        )


class SlskdClientProtocol(Protocol):
    """Injectable protocol for slskd-like client interactions.

    Implementations handle actual network communication.
    This commit provides only FakeSlskdClient for tests.
    """

    def search(self, query: SearchQuery) -> dict[str, Any]:
        """Return a raw slskd-like search response dict."""
        ...

    def health_check(self) -> dict[str, Any]:
        """Return a raw slskd-like health status dict."""
        ...


class FakeSlskdClient:
    """Fake slskd client for offline tests.

    Returns controlled fake payloads that mimic conceptual
    slskd search responses. No network access.
    """

    def __init__(
        self,
        *,
        responses: list[dict[str, Any]] | None = None,
        healthy: bool = True,
    ) -> None:
        self._responses = list(responses or [])
        self._healthy = healthy

    def search(self, query: SearchQuery) -> dict[str, Any]:
        if not self._responses:
            return {"responses": [], "response_count": 0}
        return self._responses[0]

    def health_check(self) -> dict[str, Any]:
        if self._healthy:
            return {"status": "ok", "version": "0.0.0-fake"}
        return {"status": "error", "message": "fake client unavailable"}


class SlskdPayloadMapper:
    """Pure mapping functions from slskd-like payloads to Flux models.

    No network access, no side effects, no raw payload leakage.
    """

    @staticmethod
    def map_search_response_to_candidates(
        payload: dict[str, Any],
        query: SearchQuery,
    ) -> list[SearchCandidate]:
        """Convert a slskd-like search response into Flux SearchCandidate list.

        Expected payload shape (conceptual):
        {
            "responses": [
                {
                    "username": "user1",
                    "directory": "Music/Artist/Album",
                    "files": [
                        {"filename": "track.flac", "size": 12345, "bitrate": 1000,
                         "extension": "flac", "duration": 240}
                    ],
                    "locked_files": [
                        {"filename": "locked.flac", "size": 54321}
                    ]
                }
            ],
            "response_count": 1
        }
        """
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

        artist = query.artist if query.kind == SearchKind.TRACK else query.artist
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
    """Slskd provider adapter for Flux.

    This is an external adapter skeleton. Without an injected client,
    it returns controlled unavailable states and does NOT access the network.

    Core services must NOT import this module directly.
    They should depend on the generic SearchProvider contract only.
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
            payload = self._client.search(query)
            candidates = SlskdPayloadMapper.map_search_response_to_candidates(payload, query)
            response_count = payload.get("response_count", 0)
            if not isinstance(response_count, int) or response_count < 0:
                response_count = len(candidates)

            return SearchProviderResult(
                provider=self.name,
                query=query,
                candidates=candidates,
                response_count=response_count,
            )
        except Exception as exc:  # noqa: BLE001
            return SearchProviderResult(
                provider=self.name,
                query=query,
                errors=[f"slskd search failed: {exc}"],
            )
