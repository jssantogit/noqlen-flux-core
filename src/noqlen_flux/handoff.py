from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from .results import _clean

SafeMetadata = dict[str, Any]

HANDOFF_MANIFEST_VERSION = 1


class HandoffManifestVersion(StrEnum):
    V1 = "1"


class HandoffItemType(StrEnum):
    TRACK = "track"
    ALBUM = "album"
    UNKNOWN = "unknown"


class HandoffItemStatus(StrEnum):
    APPROVED = "approved"
    QUARANTINE = "quarantine"
    REJECTED = "rejected"
    REVIEW = "review"
    DELETE_ELIGIBLE = "delete_eligible"
    UNKNOWN = "unknown"


_TRAVERSAL_MARKERS = ("..", "~", "$", "{", "}")

_FORBIDDEN_FIELDS = (
    "full_lyrics",
    "lyrics",
    "fingerprint",
    "raw_fingerprint",
    "raw_provider_payload",
    "provider_payload",
    "secret",
    "token",
    "password",
    "authorization",
    "cookie",
    "private",
)


def _is_safe_relative_path(value: str) -> bool:
    if not value:
        return False
    if value.startswith("/") or value.startswith("\\"):
        return False
    for marker in _TRAVERSAL_MARKERS:
        if marker in value:
            return False
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if ".." in parts:
        return False
    return True


def _contains_forbidden_field(data: dict[str, Any]) -> tuple[bool, str | None]:
    for key, value in data.items():
        normalized_key = key.lower().replace("_", "-")
        for forbidden in _FORBIDDEN_FIELDS:
            normalized_forbidden = forbidden.lower().replace("_", "-")
            if normalized_forbidden in normalized_key:
                return True, key
        if isinstance(value, dict):
            found, found_key = _contains_forbidden_field(value)
            if found:
                return True, found_key
    return False, None


def validate_relative_path(value: str | None, *, field_name: str = "path") -> str | None:
    if value is None:
        return None
    if not value:
        raise ValueError(f"{field_name}: Empty path.")
    if value.startswith("/") or value.startswith("\\"):
        raise ValueError(f"{field_name}: Absolute paths are not allowed.")
    for marker in _TRAVERSAL_MARKERS:
        if marker in value:
            raise ValueError(f"{field_name}: Path traversal marker '{marker}' is not allowed.")
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if ".." in parts:
        raise ValueError(f"{field_name}: Parent directory traversal is not allowed.")
    return normalized


def validate_safe_metadata(data: SafeMetadata) -> SafeMetadata:
    if not data:
        return {}
    found, key = _contains_forbidden_field(data)
    if found:
        raise ValueError(f"Forbidden field in metadata: {key}")
    return data


@dataclass(slots=True, frozen=True)
class HandoffSource:
    name: str
    version: str | None = None
    job_id: str | None = None
    created_at: str | None = None
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now(timezone.utc).isoformat())
        if self.metadata:
            object.__setattr__(self, "metadata", validate_safe_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class HandoffPathRef:
    relative_path: str
    workspace_area: str | None = None
    description: str | None = None
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        validated = validate_relative_path(self.relative_path, field_name="relative_path")
        object.__setattr__(self, "relative_path", validated)
        if self.metadata:
            object.__setattr__(self, "metadata", validate_safe_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class HandoffReportRef:
    kind: str
    relative_path: str | None = None
    description: str = ""
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.relative_path is not None:
            validated = validate_relative_path(self.relative_path, field_name="relative_path")
            object.__setattr__(self, "relative_path", validated)
        if self.metadata:
            object.__setattr__(self, "metadata", validate_safe_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class HandoffQualityRef:
    grade: str
    confidence: float | None = None
    finding_count: int = 0
    objective_failure_count: int = 0
    heuristic_warning_count: int = 0
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.metadata:
            object.__setattr__(self, "metadata", validate_safe_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class HandoffRoutingRef:
    outcome: str
    action_type: str
    reason_count: int = 0
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.metadata:
            object.__setattr__(self, "metadata", validate_safe_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class HandoffCandidateRef:
    candidate_id: str | None = None
    provider: str | None = None
    risk: str | None = None
    score: float | None = None
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.metadata:
            object.__setattr__(self, "metadata", validate_safe_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class HandoffItem:
    item_id: str
    item_type: HandoffItemType
    status: HandoffItemStatus
    path: HandoffPathRef
    query_metadata: SafeMetadata | None = None
    candidate: HandoffCandidateRef | None = None
    quality: HandoffQualityRef | None = None
    routing: HandoffRoutingRef | None = None
    reports: list[HandoffReportRef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "item_type", HandoffItemType(self.item_type))
        object.__setattr__(self, "status", HandoffItemStatus(self.status))
        if self.metadata:
            object.__setattr__(self, "metadata", validate_safe_metadata(self.metadata))
        if self.query_metadata:
            object.__setattr__(self, "query_metadata", validate_safe_metadata(self.query_metadata))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class HandoffManifest:
    handoff_version: int = HANDOFF_MANIFEST_VERSION
    source: HandoffSource | None = None
    items: list[HandoffItem] = field(default_factory=list)
    reports: list[HandoffReportRef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.metadata:
            object.__setattr__(self, "metadata", validate_safe_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


@dataclass(slots=True, frozen=True)
class HandoffValidationIssue:
    code: str
    message: str
    severity: str = "error"
    item_id: str | None = None
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class HandoffValidationResult:
    valid: bool
    issues: list[HandoffValidationIssue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))
