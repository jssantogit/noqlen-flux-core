from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .results import _clean


SafeMetadata = dict[str, Any]


class DownloadIntent(StrEnum):
    TRACK = "track"
    ALBUM = "album"


@dataclass(slots=True, frozen=True)
class DownloadItem:
    item_id: str
    candidate_id: str
    filename: str
    target_relative_path: str
    size_bytes: int | None = None
    locked: bool = False
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.item_id.strip():
            raise ValueError("item_id is required")
        if not self.candidate_id.strip():
            raise ValueError("candidate_id is required")
        if not self.filename.strip():
            raise ValueError("filename is required")
        if not self.target_relative_path.strip():
            raise ValueError("target_relative_path is required")
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("size_bytes cannot be negative")
        self._validate_target_path()

    def _validate_target_path(self) -> None:
        normalized = self.target_relative_path.replace("\\", "/")
        parts = normalized.split("/")
        for part in parts:
            if part in ("", ".", ".."):
                raise ValueError(
                    f"target_relative_path contains unsafe segment: {part!r}"
                )
        if normalized.startswith("/") or normalized.startswith(".."):
            raise ValueError("target_relative_path must be a safe relative path")

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class DownloadConstraint:
    max_files: int | None = None
    max_total_bytes: int | None = None
    allow_locked: bool = False
    require_score_min: float | None = None
    allowed_extensions: set[str] | None = None
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_files is not None and self.max_files < 1:
            raise ValueError("max_files must be positive")
        if self.max_total_bytes is not None and self.max_total_bytes < 1:
            raise ValueError("max_total_bytes must be positive")
        if self.require_score_min is not None and (
            self.require_score_min < 0.0 or self.require_score_min > 100.0
        ):
            raise ValueError("require_score_min must be between 0 and 100")
        object.__setattr__(
            self,
            "allowed_extensions",
            {ext.casefold() for ext in (self.allowed_extensions or set())},
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["allowed_extensions"] = list(self.allowed_extensions) if self.allowed_extensions else []
        return _clean(data)


@dataclass(slots=True, frozen=True)
class DownloadRequest:
    request_id: str
    intent: DownloadIntent
    query: str
    candidate_id: str
    candidate_files: list[dict[str, Any]]
    score_total: float | None = None
    score_max: float | None = None
    score_risk: str | None = None
    constraints: DownloadConstraint = field(default_factory=DownloadConstraint)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("request_id is required")
        object.__setattr__(self, "intent", DownloadIntent(self.intent))
        if not self.query.strip():
            raise ValueError("query is required")
        if not self.candidate_id.strip():
            raise ValueError("candidate_id is required")

    @classmethod
    def from_candidate(
        cls,
        candidate,
        intent: DownloadIntent | str,
        query: str,
        score=None,
        constraints: DownloadConstraint | None = None,
    ) -> DownloadRequest:
        intent_value = DownloadIntent(intent) if isinstance(intent, str) else intent
        candidate_files = [f.to_dict() for f in candidate.files]
        score_total = score.total if score else None
        score_max = score.max_score if score else None
        score_risk = score.risk.value if score else None
        return cls(
            request_id=str(uuid.uuid4()),
            intent=intent_value,
            query=query,
            candidate_id=candidate.candidate_id,
            candidate_files=candidate_files,
            score_total=score_total,
            score_max=score_max,
            score_risk=score_risk,
            constraints=constraints or DownloadConstraint(),
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class DownloadPlan:
    plan_id: str
    request_id: str
    candidate_id: str
    intent: DownloadIntent
    items: list[DownloadItem]
    target_relative_root: str | None = None
    total_size_bytes: int | None = None
    warnings: list[str] = field(default_factory=list)
    blocked: bool = False
    block_reasons: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.plan_id.strip():
            raise ValueError("plan_id is required")
        if not self.request_id.strip():
            raise ValueError("request_id is required")
        if not self.candidate_id.strip():
            raise ValueError("candidate_id is required")
        object.__setattr__(self, "intent", DownloadIntent(self.intent))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class DownloadPlanArtifact:
    artifact_id: str
    kind: str
    relative_path: str | None = None
    description: str = ""
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.artifact_id.strip():
            raise ValueError("artifact_id is required")
        if not self.kind.strip():
            raise ValueError("kind is required")

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))
