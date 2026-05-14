from __future__ import annotations

import uuid
from typing import Any

from noqlen_flux.cleanup import (
    DEFAULT_CLEANUP_POLICY,
    CleanupActionType,
    CleanupCandidate,
    CleanupCandidateKind,
    CleanupDecision,
    CleanupPlan,
    CleanupPolicy,
    CleanupRisk,
)
from noqlen_flux.results import Artifact, FluxError, FluxResult, FluxWarning, PlannedChange, Severity, Status
from noqlen_flux.services.base import FluxService


class CleanupPlanningService(FluxService):
    operation = "cleanup"

    def plan_cleanup(
        self,
        candidates: list[CleanupCandidate],
        policy: CleanupPolicy | None = None,
    ) -> FluxResult:
        selected_policy = policy or DEFAULT_CLEANUP_POLICY
        decisions: list[CleanupDecision] = []
        planned_changes: list[PlannedChange] = []
        all_warnings: list[FluxWarning] = []
        all_errors: list[FluxError] = []
        total_planned_bytes: int | None = 0

        for candidate in candidates:
            decision = self.decide_candidate(candidate, selected_policy)
            decisions.append(decision)

            change = _decision_to_planned_change(decision, candidate)
            planned_changes.append(change)

            if decision.warnings:
                all_warnings.append(
                    self.warning(
                        "cleanup-warning",
                        f"Candidate {decision.candidate_id}: {', '.join(decision.warnings)}",
                        severity=Severity.WARNING,
                        candidate_id=decision.candidate_id,
                        action=decision.action_type.value,
                    )
                )
            if decision.errors:
                all_errors.append(
                    self.error(
                        "cleanup-error",
                        f"Candidate {decision.candidate_id}: {', '.join(decision.errors)}",
                        candidate_id=decision.candidate_id,
                        action=decision.action_type.value,
                    )
                )

            if candidate.size_bytes is not None and decision.action_type in (
                CleanupActionType.PLAN_DELETE,
                CleanupActionType.MARK_DELETE_ELIGIBLE,
            ):
                total_planned_bytes = (total_planned_bytes or 0) + candidate.size_bytes

        plan = CleanupPlan(
            plan_id=str(uuid.uuid4()),
            decisions=decisions,
            planned_changes=[c.to_dict() for c in planned_changes],
            total_candidate_count=len(candidates),
            total_planned_bytes=total_planned_bytes if total_planned_bytes and total_planned_bytes > 0 else None,
            warnings=[w.message for w in all_warnings],
            errors=[e.message for e in all_errors],
            metadata={"policy": selected_policy.name},
        )

        artifact = Artifact(
            kind="cleanup-plan",
            description="Logical cleanup planning result (planned-only, no execution)",
            metadata={
                "plan_id": plan.plan_id,
                "candidate_count": len(decisions),
                "policy": selected_policy.name,
            },
        )

        step_status = Status.WARNING if (all_warnings or all_errors) else Status.SUCCESS
        step_message = f"Cleanup plan: {len(decisions)} candidate(s) evaluated with policy {selected_policy.name}"

        step = self.step(
            "plan-cleanup",
            step_status,
            step_message,
            warnings=all_warnings,
            errors=all_errors,
            artifacts=[artifact],
        )

        return FluxResult(
            operation=self.operation,
            status=step_status,
            steps=[step],
            warnings=all_warnings,
            errors=all_errors,
            artifacts=[artifact],
            planned_changes=planned_changes,
            summary={
                "plan_id": plan.plan_id,
                "candidate_count": len(decisions),
                "keep_count": sum(1 for d in decisions if d.action_type == CleanupActionType.KEEP),
                "review_count": sum(1 for d in decisions if d.action_type == CleanupActionType.REVIEW),
                "mark_delete_eligible_count": sum(1 for d in decisions if d.action_type == CleanupActionType.MARK_DELETE_ELIGIBLE),
                "plan_delete_count": sum(1 for d in decisions if d.action_type == CleanupActionType.PLAN_DELETE),
                "none_count": sum(1 for d in decisions if d.action_type == CleanupActionType.NONE),
                "total_planned_bytes": total_planned_bytes if total_planned_bytes and total_planned_bytes > 0 else None,
                "policy": selected_policy.to_dict(),
                "cleanup_plan": plan.to_dict(),
            },
        ).finish()

    def decide_candidate(
        self,
        candidate: CleanupCandidate,
        policy: CleanupPolicy | None = None,
    ) -> CleanupDecision:
        selected_policy = policy or DEFAULT_CLEANUP_POLICY
        return _decide_for_candidate(candidate, selected_policy)


def _decide_for_candidate(candidate: CleanupCandidate, policy: CleanupPolicy) -> CleanupDecision:
    if candidate.kind == CleanupCandidateKind.REJECTED:
        return _decide_rejected(candidate, policy)
    if candidate.kind == CleanupCandidateKind.DELETE_ELIGIBLE:
        return _decide_delete_eligible(candidate, policy)
    if candidate.kind == CleanupCandidateKind.TEMPORARY:
        return _decide_temporary(candidate, policy)
    if candidate.kind == CleanupCandidateKind.ORPHANED:
        return _decide_orphaned(candidate, policy)
    if candidate.kind == CleanupCandidateKind.STALE_REPORT:
        return _decide_stale_report(candidate, policy)
    if candidate.kind == CleanupCandidateKind.STALE_MANIFEST:
        return _decide_stale_manifest(candidate, policy)
    return _decide_unknown(candidate, policy)


def _decide_rejected(candidate: CleanupCandidate, policy: CleanupPolicy) -> CleanupDecision:
    reasons: list[str] = []
    warnings: list[str] = []

    reasons.append("Item was routed to rejected.")

    if candidate.age_days is not None and policy.min_age_days is not None and candidate.age_days >= policy.min_age_days:
        return CleanupDecision(
            candidate_id=candidate.candidate_id,
            action_type=CleanupActionType.MARK_DELETE_ELIGIBLE,
            risk=CleanupRisk.MEDIUM,
            reasons=reasons + [f"Age {candidate.age_days} days meets minimum age threshold ({policy.min_age_days} days)."],
            warnings=warnings,
            metadata={"source_kind": candidate.kind.value, "age_days": candidate.age_days},
        )

    warnings.append("Rejected item requires manual review before any deletion planning.")
    return CleanupDecision(
        candidate_id=candidate.candidate_id,
        action_type=CleanupActionType.REVIEW,
        risk=CleanupRisk.MEDIUM,
        reasons=reasons,
        warnings=warnings,
        metadata={"source_kind": candidate.kind.value, "age_days": candidate.age_days},
    )


def _decide_delete_eligible(candidate: CleanupCandidate, policy: CleanupPolicy) -> CleanupDecision:
    reasons: list[str] = []
    warnings: list[str] = []

    reasons.append("Item is marked delete-eligible.")

    is_heuristic_only = any("heuristic" in r.lower() for r in candidate.reasons)

    if is_heuristic_only:
        warnings.append("Heuristic-only finding; must not trigger automatic deletion.")
        return CleanupDecision(
            candidate_id=candidate.candidate_id,
            action_type=CleanupActionType.REVIEW,
            risk=CleanupRisk.HIGH,
            reasons=reasons,
            warnings=warnings,
            metadata={"source_kind": candidate.kind.value, "heuristic_only": True},
        )

    if not policy.allow_delete_planning:
        warnings.append("Policy does not allow delete planning; candidate remains review-only.")
        return CleanupDecision(
            candidate_id=candidate.candidate_id,
            action_type=CleanupActionType.REVIEW,
            risk=CleanupRisk.MEDIUM,
            reasons=reasons,
            warnings=warnings,
            metadata={"source_kind": candidate.kind.value, "allow_delete_planning": False},
        )

    return CleanupDecision(
        candidate_id=candidate.candidate_id,
        action_type=CleanupActionType.PLAN_DELETE,
        risk=CleanupRisk.HIGH,
        reasons=reasons + ["Policy allows delete planning."],
        warnings=warnings,
        metadata={"source_kind": candidate.kind.value, "allow_delete_planning": True},
    )


def _decide_temporary(candidate: CleanupCandidate, policy: CleanupPolicy) -> CleanupDecision:
    reasons: list[str] = []
    warnings: list[str] = []

    reasons.append("Item is a temporary file.")

    if candidate.age_days is not None and policy.min_age_days is not None and candidate.age_days >= policy.min_age_days:
        return CleanupDecision(
            candidate_id=candidate.candidate_id,
            action_type=CleanupActionType.MARK_DELETE_ELIGIBLE,
            risk=CleanupRisk.LOW,
            reasons=reasons + [f"Age {candidate.age_days} days meets minimum age threshold ({policy.min_age_days} days)."],
            warnings=warnings,
            metadata={"source_kind": candidate.kind.value, "age_days": candidate.age_days},
        )

    warnings.append("Temporary file age is below threshold; review recommended.")
    return CleanupDecision(
        candidate_id=candidate.candidate_id,
        action_type=CleanupActionType.REVIEW,
        risk=CleanupRisk.LOW,
        reasons=reasons,
        warnings=warnings,
        metadata={"source_kind": candidate.kind.value, "age_days": candidate.age_days},
    )


def _decide_orphaned(candidate: CleanupCandidate, policy: CleanupPolicy) -> CleanupDecision:
    reasons: list[str] = []
    warnings: list[str] = []

    reasons.append("Item is orphaned with no known source decision.")
    warnings.append("Orphaned items require conservative handling.")

    return CleanupDecision(
        candidate_id=candidate.candidate_id,
        action_type=CleanupActionType.REVIEW,
        risk=CleanupRisk.MEDIUM,
        reasons=reasons,
        warnings=warnings,
        metadata={"source_kind": candidate.kind.value, "conservative": True},
    )


def _decide_stale_report(candidate: CleanupCandidate, policy: CleanupPolicy) -> CleanupDecision:
    reasons: list[str] = []
    warnings: list[str] = []

    reasons.append("Report is older than expected retention period.")

    if candidate.age_days is not None and policy.min_age_days is not None and candidate.age_days >= policy.min_age_days:
        return CleanupDecision(
            candidate_id=candidate.candidate_id,
            action_type=CleanupActionType.MARK_DELETE_ELIGIBLE,
            risk=CleanupRisk.LOW,
            reasons=reasons + [f"Age {candidate.age_days} days meets minimum age threshold ({policy.min_age_days} days)."],
            warnings=warnings,
            metadata={"source_kind": candidate.kind.value, "age_days": candidate.age_days},
        )

    return CleanupDecision(
        candidate_id=candidate.candidate_id,
        action_type=CleanupActionType.REVIEW,
        risk=CleanupRisk.LOW,
        reasons=reasons,
        warnings=warnings,
        metadata={"source_kind": candidate.kind.value, "age_days": candidate.age_days},
    )


def _decide_stale_manifest(candidate: CleanupCandidate, policy: CleanupPolicy) -> CleanupDecision:
    reasons: list[str] = []
    warnings: list[str] = []

    reasons.append("Manifest is older than expected retention period.")

    if candidate.age_days is not None and policy.min_age_days is not None and candidate.age_days >= policy.min_age_days:
        return CleanupDecision(
            candidate_id=candidate.candidate_id,
            action_type=CleanupActionType.MARK_DELETE_ELIGIBLE,
            risk=CleanupRisk.LOW,
            reasons=reasons + [f"Age {candidate.age_days} days meets minimum age threshold ({policy.min_age_days} days)."],
            warnings=warnings,
            metadata={"source_kind": candidate.kind.value, "age_days": candidate.age_days},
        )

    return CleanupDecision(
        candidate_id=candidate.candidate_id,
        action_type=CleanupActionType.REVIEW,
        risk=CleanupRisk.LOW,
        reasons=reasons,
        warnings=warnings,
        metadata={"source_kind": candidate.kind.value, "age_days": candidate.age_days},
    )


def _decide_unknown(candidate: CleanupCandidate, policy: CleanupPolicy) -> CleanupDecision:
    reasons: list[str] = []
    warnings: list[str] = []

    reasons.append("Candidate kind is unknown.")
    warnings.append("Unknown candidates require manual review.")

    return CleanupDecision(
        candidate_id=candidate.candidate_id,
        action_type=CleanupActionType.REVIEW,
        risk=CleanupRisk.HIGH,
        reasons=reasons,
        warnings=warnings,
        metadata={"source_kind": candidate.kind.value},
    )


def _decision_to_planned_change(decision: CleanupDecision, candidate: CleanupCandidate) -> PlannedChange:
    action_map = {
        CleanupActionType.KEEP: "plan-keep",
        CleanupActionType.REVIEW: "plan-review",
        CleanupActionType.MARK_DELETE_ELIGIBLE: "plan-mark-delete-eligible",
        CleanupActionType.PLAN_DELETE: "plan-delete",
        CleanupActionType.NONE: "plan-no-action",
    }
    action = action_map.get(decision.action_type, "plan-no-action")
    reason_summary = "; ".join(decision.reasons) if decision.reasons else "No specific reason."
    target = candidate.relative_path or decision.candidate_id
    meta: dict[str, Any] = {
        "candidate_id": decision.candidate_id,
        "action_type": decision.action_type.value,
        "risk": decision.risk.value,
        "kind": candidate.kind.value,
    }
    if candidate.size_bytes is not None:
        meta["size_bytes"] = candidate.size_bytes
    return PlannedChange(
        action=action,
        target=target,
        reason=reason_summary,
        metadata=meta,
    )
