from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from .results import _clean
from .safety import validate_safe_relative_path

SafeMetadata = dict[str, Any]


def validate_cleanup_relative_path(value: str | None, *, field_name: str = "path") -> str | None:
    return validate_safe_relative_path(value, field_name=field_name)


class CleanupCandidateKind(StrEnum):
    REJECTED = "rejected"
    DELETE_ELIGIBLE = "delete_eligible"
    TEMPORARY = "temporary"
    ORPHANED = "orphaned"
    STALE_REPORT = "stale_report"
    STALE_MANIFEST = "stale_manifest"
    UNKNOWN = "unknown"


class CleanupActionType(StrEnum):
    KEEP = "keep"
    REVIEW = "review"
    MARK_DELETE_ELIGIBLE = "mark_delete_eligible"
    PLAN_DELETE = "plan_delete"
    NONE = "none"


class CleanupRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(slots=True, frozen=True)
class CleanupCandidate:
    candidate_id: str
    kind: CleanupCandidateKind
    relative_path: str | None = None
    size_bytes: int | None = None
    age_days: int | None = None
    source: str | None = None
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", CleanupCandidateKind(self.kind))
        if self.relative_path is not None:
            validated = validate_cleanup_relative_path(self.relative_path, field_name="relative_path")
            object.__setattr__(self, "relative_path", validated)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class CleanupPolicy:
    name: str
    version: str
    description: str
    allow_delete_planning: bool = False
    auto_delete_enabled: bool = False
    min_age_days: int | None = None
    max_total_bytes: int | None = None
    delete_only_with_report: bool = True
    require_explicit_apply: bool = True
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class CleanupDecision:
    candidate_id: str
    action_type: CleanupActionType
    risk: CleanupRisk
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "action_type", CleanupActionType(self.action_type))
        object.__setattr__(self, "risk", CleanupRisk(self.risk))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class CleanupPlan:
    plan_id: str
    decisions: list[CleanupDecision] = field(default_factory=list)
    planned_changes: list[dict[str, Any]] = field(default_factory=list)
    total_candidate_count: int = 0
    total_planned_bytes: int | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


DEFAULT_CLEANUP_POLICY = CleanupPolicy(
    name="default_v1",
    version="1",
    description="Initial cleanup planning policy. No destructive actions are executed; all decisions are planned only.",
    allow_delete_planning=False,
    auto_delete_enabled=False,
    delete_only_with_report=True,
    require_explicit_apply=True,
    metadata={"stage": "planning", "status": "contracts-only"},
)


def default_cleanup_policy() -> CleanupPolicy:
    return DEFAULT_CLEANUP_POLICY


class CleanupExecutionAction(StrEnum):
    REMOVE_TEMP_REPORT = "remove_temp_report"
    REMOVE_STAGING_TEMP = "remove_staging_temp"
    MOVE_TO_TRASH = "move_to_trash"
    MOVE_TO_REJECTED_RETAINED = "move_to_rejected_retained"
    CLEAN_INVALID_MANIFEST = "clean_invalid_manifest"
    CLEAN_INCOMPLETE_ARTIFACT = "clean_incomplete_artifact"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class CleanupExecutionItemState(StrEnum):
    PENDING = "pending"
    EXECUTED = "executed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(slots=True, frozen=True)
class CleanupExecutionPolicy:
    name: str
    version: str
    description: str
    allow_remove_temp_reports: bool = True
    allow_remove_staging_temp: bool = True
    allow_move_to_trash: bool = True
    allow_move_to_rejected_retained: bool = True
    allow_clean_invalid_manifests: bool = True
    allow_clean_incomplete_artifacts: bool = True
    allow_delete: bool = False
    require_explicit_apply: bool = True
    workspace_only: bool = True
    block_absolute_path: bool = True
    block_traversal: bool = True
    block_symlink_escape: bool = True
    block_protected_roots: bool = True
    retention_days_rejected: int = 90
    retention_days_temp: int = 30
    retention_days_reports: int = 180
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class CleanupExecutionItem:
    item_id: str
    decision_id: str
    candidate_id: str
    kind: CleanupCandidateKind
    relative_path: str | None = None
    action: CleanupExecutionAction = CleanupExecutionAction.BLOCKED
    state: CleanupExecutionItemState = CleanupExecutionItemState.PENDING
    reason: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class CleanupExecutionRequest:
    request_id: str
    cleanup_plan_id: str
    workspace_root: str
    policy: CleanupExecutionPolicy
    decisions: list[CleanupDecision] = field(default_factory=list)
    candidates: list[CleanupCandidate] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class CleanupExecutionResult:
    result_id: str
    request_id: str
    items: list[CleanupExecutionItem] = field(default_factory=list)
    total_candidates: int = 0
    executed_count: int = 0
    blocked_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    total_bytes_removed: int = 0
    destructive_action_detected: bool = False
    safety_checks_passed: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str | None = None
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


class AutoCleanupPolicyPreset(StrEnum):
    CONSERVATIVE = "conservative"
    AGGRESSIVE = "aggressive"


class AutoCleanupTrigger(StrEnum):
    ON_HANDOFF = "on_handoff"
    ON_STAGING_COMPLETE = "on_staging_complete"
    ON_SCHEDULE = "on_schedule"
    MANUAL = "manual"


@dataclass(slots=True, frozen=True)
class AutoCleanupPolicy:
    name: str
    version: str
    description: str
    enabled: bool = False
    preset: AutoCleanupPolicyPreset = AutoCleanupPolicyPreset.CONSERVATIVE
    trigger_on_handoff: bool = False
    trigger_on_staging_complete: bool = False
    allowed_action_types: list[CleanupExecutionAction] = field(default_factory=lambda: [
        CleanupExecutionAction.REMOVE_TEMP_REPORT,
        CleanupExecutionAction.REMOVE_STAGING_TEMP,
        CleanupExecutionAction.CLEAN_INVALID_MANIFEST,
        CleanupExecutionAction.CLEAN_INCOMPLETE_ARTIFACT,
    ])
    workspace_only: bool = True
    block_approved: bool = True
    block_import_ready: bool = True
    require_report: bool = True
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))

    @classmethod
    def conservative_default(cls) -> AutoCleanupPolicy:
        return cls(
            name="auto-cleanup-conservative-v1",
            version="1",
            description="Conservative auto-cleanup policy. Opt-in only, workspace-scoped, never deletes library or approved items.",
            enabled=False,
            preset=AutoCleanupPolicyPreset.CONSERVATIVE,
            trigger_on_handoff=False,
            trigger_on_staging_complete=False,
            allowed_action_types=[
                CleanupExecutionAction.REMOVE_TEMP_REPORT,
                CleanupExecutionAction.REMOVE_STAGING_TEMP,
                CleanupExecutionAction.CLEAN_INVALID_MANIFEST,
                CleanupExecutionAction.CLEAN_INCOMPLETE_ARTIFACT,
            ],
            workspace_only=True,
            block_approved=True,
            block_import_ready=True,
            require_report=True,
        )


DEFAULT_CONSERVATIVE_EXECUTION_POLICY = CleanupExecutionPolicy(
    name="conservative-execution-v1",
    version="1",
    description="Conservative cleanup execution policy. No delete. Workspace-only. All destructive operations require explicit confirmation.",
    allow_delete=False,
    require_explicit_apply=True,
    workspace_only=True,
    block_absolute_path=True,
    block_traversal=True,
    block_symlink_escape=True,
    block_protected_roots=True,
    metadata={"stage": "execution", "status": "conservative"},
)


def build_default_execution_policy() -> CleanupExecutionPolicy:
    return DEFAULT_CONSERVATIVE_EXECUTION_POLICY


def build_fake_cleanup_candidates() -> list[CleanupCandidate]:
    return [
        CleanupCandidate(
            candidate_id=f"fake-rejected-{uuid.uuid4().hex[:8]}",
            kind=CleanupCandidateKind.REJECTED,
            relative_path="rejected/fake-item-1.txt",
            size_bytes=1024,
            age_days=90,
            source="routing",
            reasons=["Routed to rejected by quality evaluation."],
            warnings=["Candidate has been in rejected for 90 days."],
            metadata={"scenario": "old-rejected"},
        ),
        CleanupCandidate(
            candidate_id=f"fake-delete-eligible-{uuid.uuid4().hex[:8]}",
            kind=CleanupCandidateKind.DELETE_ELIGIBLE,
            relative_path="delete_eligible/fake-item-2.txt",
            size_bytes=2048,
            age_days=60,
            source="staging",
            reasons=["Marked delete-eligible by staging policy."],
            warnings=["Candidate is eligible for future deletion."],
            metadata={"scenario": "delete-eligible"},
        ),
        CleanupCandidate(
            candidate_id=f"fake-temporary-{uuid.uuid4().hex[:8]}",
            kind=CleanupCandidateKind.TEMPORARY,
            relative_path="tmp/fake-temp-3.txt",
            size_bytes=512,
            age_days=30,
            source="workspace",
            reasons=["Temporary file older than expected."],
            metadata={"scenario": "stale-temporary"},
        ),
        CleanupCandidate(
            candidate_id=f"fake-orphaned-{uuid.uuid4().hex[:8]}",
            kind=CleanupCandidateKind.ORPHANED,
            relative_path="incoming/fake-orphan-4.txt",
            size_bytes=4096,
            age_days=120,
            source="workspace",
            reasons=["No routing decision found for this item."],
            warnings=["Orphaned item has no known source."],
            metadata={"scenario": "orphaned"},
        ),
        CleanupCandidate(
            candidate_id=f"fake-stale-report-{uuid.uuid4().hex[:8]}",
            kind=CleanupCandidateKind.STALE_REPORT,
            relative_path="reports/fake-report-5.json",
            size_bytes=256,
            age_days=180,
            source="reports",
            reasons=["Report is older than retention period."],
            metadata={"scenario": "stale-report"},
        ),
        CleanupCandidate(
            candidate_id=f"fake-stale-manifest-{uuid.uuid4().hex[:8]}",
            kind=CleanupCandidateKind.STALE_MANIFEST,
            relative_path="manifests/fake-manifest-6.json",
            size_bytes=128,
            age_days=200,
            source="handoff",
            reasons=["Manifest is older than retention period."],
            metadata={"scenario": "stale-manifest"},
        ),
        CleanupCandidate(
            candidate_id=f"fake-heuristic-{uuid.uuid4().hex[:8]}",
            kind=CleanupCandidateKind.DELETE_ELIGIBLE,
            relative_path="delete_eligible/fake-heuristic-7.txt",
            size_bytes=3072,
            age_days=15,
            source="routing",
            reasons=["Heuristic-only finding suggested delete-eligible."],
            warnings=["Heuristic findings should not trigger automatic deletion."],
            metadata={"scenario": "heuristic-only"},
        ),
    ]
