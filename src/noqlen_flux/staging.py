from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .results import _clean
from .safety import validate_safe_relative_path as validate_relative_path

SafeMetadata = dict[str, Any]


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


@dataclass(slots=True, frozen=True)
class StagingExecutionPolicy:
    name: str
    version: str
    description: str
    allow_copy: bool = True
    allow_move: bool = False
    allow_delete: bool = False
    allow_overwrite: bool = False
    create_workspace_dirs: bool = True
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class StagingExecutionSummary:
    total_items: int = 0
    planned_count: int = 0
    applied_count: int = 0
    blocked_count: int = 0
    skipped_count: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


DEFAULT_STAGING_EXECUTION_POLICY = StagingExecutionPolicy(
    name="default_v1",
    version="1",
    description="Initial staging execution policy. Copy allowed within workspace. Move, delete, and overwrite are blocked by default.",
    allow_copy=True,
    allow_move=False,
    allow_delete=False,
    allow_overwrite=False,
    create_workspace_dirs=True,
    metadata={"stage": "post-download", "status": "execution-foundation"},
)


def default_staging_execution_policy() -> StagingExecutionPolicy:
    return DEFAULT_STAGING_EXECUTION_POLICY


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


@dataclass(slots=True, frozen=True)
class StagingApplyReport:
    report_id: str
    source_staging_plan_id: str
    mode: str
    timestamp: str
    policy_name: str
    total_items: int
    planned_count: int
    applied_count: int
    blocked_count: int
    skipped_count: int
    failed_count: int
    operations: list[dict[str, Any]] = field(default_factory=list)
    safety_checks: list[dict[str, Any]] = field(default_factory=list)
    blocked_operations: list[dict[str, Any]] = field(default_factory=list)
    skipped_operations: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))

    @classmethod
    def from_execution_result(
        cls,
        report_id: str,
        source_staging_plan_id: str,
        mode: str,
        timestamp: str,
        policy_name: str,
        total_items: int,
        planned_count: int,
        applied_count: int,
        blocked_count: int,
        skipped_count: int,
        failed_count: int,
        *,
        operations: list[dict[str, Any]] | None = None,
        safety_checks: list[dict[str, Any]] | None = None,
        blocked_operations: list[dict[str, Any]] | None = None,
        skipped_operations: list[dict[str, Any]] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        notes: list[str] | None = None,
        metadata: SafeMetadata | None = None,
    ) -> StagingApplyReport:
        return cls(
            report_id=report_id,
            source_staging_plan_id=source_staging_plan_id,
            mode=mode,
            timestamp=timestamp,
            policy_name=policy_name,
            total_items=total_items,
            planned_count=planned_count,
            applied_count=applied_count,
            blocked_count=blocked_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            operations=operations or [],
            safety_checks=safety_checks or [],
            blocked_operations=blocked_operations or [],
            skipped_operations=skipped_operations or [],
            warnings=warnings or [],
            errors=errors or [],
            notes=notes or [],
            metadata=metadata or {},
        )
