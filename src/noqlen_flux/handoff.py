from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from .results import _clean
from .safety import validate_safe_relative_path as validate_relative_path

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


class HandoffApplyMode(StrEnum):
    DRY_RUN = "dry_run"
    APPLY = "apply"


class HandoffApplyItemOutcome(StrEnum):
    APPLIED = "applied"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


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
    "raw_payload_dump",
    "api_response_body",
    "set_cookie",
    "session_token",
    "refresh_token",
    "access_key",
    "api_secret",
    "credential",
    "signing_key",
)


def _contains_forbidden_field(data: Any) -> tuple[bool, str | None]:
    if isinstance(data, dict):
        for key, value in data.items():
            normalized_key = str(key).lower().replace("_", "-")
            for forbidden in _FORBIDDEN_FIELDS:
                normalized_forbidden = forbidden.lower().replace("_", "-")
                if normalized_forbidden in normalized_key:
                    return True, str(key)
            found, found_key = _contains_forbidden_field(value)
            if found:
                return True, found_key
    elif isinstance(data, (list, tuple)):
        for item in data:
            found, found_key = _contains_forbidden_field(item)
            if found:
                return True, found_key
    return False, None


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
    forge_ready: bool = False
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


@dataclass(slots=True, frozen=True)
class HandoffApplyItemResult:
    item_id: str
    outcome: HandoffApplyItemOutcome
    reason: str = ""
    forge_ready: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class HandoffApplyResult:
    mode: HandoffApplyMode
    manifest_version: int
    total_items: int
    applied: int = 0
    blocked: int = 0
    skipped: int = 0
    item_results: list[HandoffApplyItemResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class HandoffApplyReport:
    report_id: str
    manifest_path: str
    mode: HandoffApplyMode
    valid: bool
    total_items: int
    applied: int
    blocked: int
    skipped: int
    item_results: list[HandoffApplyItemResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))
