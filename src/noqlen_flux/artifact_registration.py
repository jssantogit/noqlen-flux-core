from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from .results import _clean

SafeMetadata = dict[str, Any]


@dataclass(slots=True, frozen=True)
class DownloadArtifactRegistration:
    artifact_id: str
    candidate_id: str
    queue_item_id: str
    provider: str
    relative_path: str
    state: str
    size_bytes: int | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.artifact_id.strip():
            raise ValueError("artifact_id is required")
        if not self.candidate_id.strip():
            raise ValueError("candidate_id is required")
        if not self.queue_item_id.strip():
            raise ValueError("queue_item_id is required")
        if not self.provider.strip():
            raise ValueError("provider is required")
        if not self.relative_path.strip():
            raise ValueError("relative_path is required")
        if not self.state.strip():
            raise ValueError("state is required")
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("size_bytes cannot be negative")
        self._validate_relative_path()

    def _validate_relative_path(self) -> None:
        _TRAVERSAL_MARKERS = ("~", "$", "{", "}")
        for marker in _TRAVERSAL_MARKERS:
            if marker in self.relative_path:
                raise ValueError(
                    f"relative_path contains traversal marker: {marker!r}"
                )
        normalized = self.relative_path.replace("\\", "/")
        parts = normalized.split("/")
        for part in parts:
            if part in ("", ".", ".."):
                raise ValueError(
                    f"relative_path contains unsafe segment: {part!r}"
                )
        if normalized.startswith("/") or normalized.startswith("\\") or normalized.startswith(".."):
            raise ValueError("relative_path must be a safe relative path")

    @classmethod
    def from_transfer_status(
        cls,
        *,
        transfer_id: str,
        queue_item_id: str,
        candidate_id: str,
        provider: str,
        state: str,
        relative_path: str,
        size_bytes: int | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DownloadArtifactRegistration:
        return cls(
            artifact_id=transfer_id,
            candidate_id=candidate_id,
            queue_item_id=queue_item_id,
            provider=provider,
            relative_path=relative_path,
            state=state,
            size_bytes=size_bytes,
            warnings=list(warnings or []),
            errors=list(errors or []),
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_submission_result(
        cls,
        *,
        submission_id: str,
        queue_item_id: str,
        candidate_id: str,
        provider: str,
        state: str,
        relative_path: str,
        size_bytes: int | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DownloadArtifactRegistration:
        return cls(
            artifact_id=f"submit-{submission_id}",
            candidate_id=candidate_id,
            queue_item_id=queue_item_id,
            provider=provider,
            relative_path=relative_path,
            state=state,
            size_bytes=size_bytes,
            warnings=list(warnings or []),
            errors=list(errors or []),
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))
