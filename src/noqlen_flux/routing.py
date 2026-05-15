from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .results import _clean

SafeMetadata = dict[str, Any]


class RoutingOutcome(StrEnum):
    APPROVED = "approved"
    QUARANTINE = "quarantine"
    REJECTED = "rejected"
    DELETE_ELIGIBLE = "delete_eligible"
    REVIEW = "review"
    UNKNOWN = "unknown"


class RoutingActionType(StrEnum):
    PLAN_ONLY = "plan_only"
    MOVE_TO_APPROVED = "move_to_approved"
    MOVE_TO_QUARANTINE = "move_to_quarantine"
    MOVE_TO_REJECTED = "move_to_rejected"
    MARK_DELETE_ELIGIBLE = "mark_delete_eligible"
    NONE = "none"


class RoutingReasonSource(StrEnum):
    QUALITY_GRADE = "quality_grade"
    QUALITY_FINDING = "quality_finding"
    POLICY_RULE = "policy_rule"
    UNKNOWN = "unknown"


@dataclass(slots=True, frozen=True)
class RoutingReason:
    code: str
    message: str
    severity: str
    source: RoutingReasonSource
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", RoutingReasonSource(self.source))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class RoutingPolicy:
    name: str
    version: str
    description: str
    allow_delete_eligible: bool = False
    heuristic_warnings_route_to_review_or_quarantine: bool = True
    objective_failures_route_to_rejected: bool = True
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class RoutingDecision:
    item_id: str
    outcome: RoutingOutcome
    action_type: RoutingActionType
    reasons: list[RoutingReason] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    confidence: float = 0.0
    policy: RoutingPolicy = field(default_factory=lambda: DEFAULT_ROUTING_POLICY)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome", RoutingOutcome(self.outcome))
        object.__setattr__(self, "action_type", RoutingActionType(self.action_type))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class RoutingPlan:
    plan_id: str
    decisions: list[RoutingDecision] = field(default_factory=list)
    planned_changes: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


DEFAULT_ROUTING_POLICY = RoutingPolicy(
    name="default_v1",
    version="1",
    description="Initial post-download routing policy. No destructive actions are executed; all decisions are planned only.",
    allow_delete_eligible=False,
    heuristic_warnings_route_to_review_or_quarantine=True,
    objective_failures_route_to_rejected=True,
    metadata={"stage": "post-download", "status": "contracts-only"},
)


def default_routing_policy() -> RoutingPolicy:
    return DEFAULT_ROUTING_POLICY


@dataclass(slots=True, frozen=True)
class RoutingApplyPolicy:
    name: str
    version: str
    description: str
    dry_run_default: bool = True
    apply_explicit: bool = True
    allow_move_to_approved: bool = True
    allow_move_to_quarantine: bool = True
    allow_move_to_rejected: bool = True
    allow_delete_eligible: bool = False
    allow_mark_delete_eligible: bool = False
    allow_review_manual_only: bool = True
    workspace_only: bool = True
    block_absolute_path: bool = True
    block_traversal: bool = True
    block_symlink_escape: bool = True
    block_protected_roots: bool = True
    generate_safety_report: bool = True
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


DEFAULT_ROUTING_APPLY_POLICY = RoutingApplyPolicy(
    name="default_apply_v1",
    version="1",
    description="Default routing apply policy. Dry-run by default, apply must be explicit. No delete. Workspace-only. All path safety enforced.",
    dry_run_default=True,
    apply_explicit=True,
    allow_move_to_approved=True,
    allow_move_to_quarantine=True,
    allow_move_to_rejected=True,
    allow_delete_eligible=False,
    allow_mark_delete_eligible=False,
    allow_review_manual_only=True,
    workspace_only=True,
    block_absolute_path=True,
    block_traversal=True,
    block_symlink_escape=True,
    block_protected_roots=True,
    generate_safety_report=True,
    metadata={"stage": "post-download", "status": "apply-foundation"},
)


def default_routing_apply_policy() -> RoutingApplyPolicy:
    return DEFAULT_ROUTING_APPLY_POLICY
