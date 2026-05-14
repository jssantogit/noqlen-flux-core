from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .results import _clean

SafeMetadata = dict[str, Any]

_TRAVERSAL_MARKERS = ("..", "~", "$", "{", "}")


def _is_safe_relative_path(value: str | None) -> tuple[bool, str]:
    if value is None:
        return True, ""
    if not value:
        return False, "Empty path."
    if value.startswith("/") or value.startswith("\\"):
        return False, "Absolute paths are not allowed."
    for marker in _TRAVERSAL_MARKERS:
        if marker in value:
            return False, f"Path traversal marker '{marker}' is not allowed."
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if any(p in (".", "..", "") for p in parts if p):
        if ".." in parts:
            return False, "Parent directory traversal is not allowed."
    return True, ""


def validate_relative_path(value: str | None, *, field_name: str = "path") -> str | None:
    if value is None:
        return None
    safe, reason = _is_safe_relative_path(value)
    if not safe:
        raise ValueError(f"{field_name}: {reason}")
    return value.replace("\\", "/")


class StagingArea(StrEnum):
    INCOMING = "incoming"
    APPROVED = "approved"
    QUARANTINE = "quarantine"
    REJECTED = "rejected"
    DELETE_ELIGIBLE = "delete_eligible"
    REVIEW = "review"
    UNKNOWN = "unknown"


class StagingActionType(StrEnum):
    PLAN_ONLY = "plan_only"
    MOVE = "move"
    COPY = "copy"
    MARK_DELETE_ELIGIBLE = "mark_delete_eligible"
    NONE = "none"


@dataclass(slots=True, frozen=True)
class StagingItem:
    item_id: str
    routing_outcome: str
    source_relative_path: str | None = None
    target_area: StagingArea = StagingArea.UNKNOWN
    target_relative_path: str | None = None
    action_type: StagingActionType = StagingActionType.PLAN_ONLY
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_area", StagingArea(self.target_area))
        object.__setattr__(self, "action_type", StagingActionType(self.action_type))
        if self.source_relative_path is not None:
            validated = validate_relative_path(self.source_relative_path, field_name="source_relative_path")
            object.__setattr__(self, "source_relative_path", validated)
        if self.target_relative_path is not None:
            validated = validate_relative_path(self.target_relative_path, field_name="target_relative_path")
            object.__setattr__(self, "target_relative_path", validated)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class StagingPlan:
    plan_id: str
    items: list[StagingItem] = field(default_factory=list)
    planned_changes: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class StagingPolicy:
    name: str
    version: str
    description: str
    allow_delete_eligible: bool = False
    allow_real_moves: bool = False
    quarantine_heuristic_warnings: bool = True
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


DEFAULT_STAGING_POLICY = StagingPolicy(
    name="default_v1",
    version="1",
    description="Initial staging policy. No real moves, copies, or deletions are executed; all staging is planned only.",
    allow_delete_eligible=False,
    allow_real_moves=False,
    quarantine_heuristic_warnings=True,
    metadata={"stage": "post-download", "status": "contracts-only"},
)


def default_staging_policy() -> StagingPolicy:
    return DEFAULT_STAGING_POLICY
