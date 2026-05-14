from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .results import _clean

SafeMetadata = dict[str, Any]

_CLEANUP_TRAVERSAL_MARKERS = ("..", "~", "$", "{", "}")


def _is_safe_relative_path(value: str | None) -> tuple[bool, str]:
    if value is None:
        return True, ""
    if not value:
        return False, "Empty path."
    if value.startswith("/") or value.startswith("\\"):
        return False, "Absolute paths are not allowed."
    for marker in _CLEANUP_TRAVERSAL_MARKERS:
        if marker in value:
            return False, f"Path traversal marker '{marker}' is not allowed."
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if ".." in parts:
        return False, "Parent directory traversal is not allowed."
    return True, ""


def validate_cleanup_relative_path(value: str | None, *, field_name: str = "path") -> str | None:
    if value is None:
        return None
    safe, reason = _is_safe_relative_path(value)
    if not safe:
        raise ValueError(f"{field_name}: {reason}")
    return value.replace("\\", "/")


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
