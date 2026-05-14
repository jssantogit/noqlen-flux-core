from __future__ import annotations

import uuid
from typing import Any

from noqlen_flux.quality import QualityGrade, QualityResult
from noqlen_flux.results import Artifact, FluxError, FluxResult, FluxWarning, PlannedChange, Severity, Status
from noqlen_flux.routing import (
    DEFAULT_ROUTING_POLICY,
    RoutingActionType,
    RoutingDecision,
    RoutingOutcome,
    RoutingPlan,
    RoutingPolicy,
    RoutingReason,
    RoutingReasonSource,
)
from noqlen_flux.services.base import FluxService


class RoutingDecisionService(FluxService):
    operation = "routing"

    def decide_quality_route(
        self,
        quality_result: QualityResult,
        policy: RoutingPolicy | None = None,
    ) -> RoutingDecision:
        selected_policy = policy or DEFAULT_ROUTING_POLICY
        reasons: list[RoutingReason] = []
        warnings: list[str] = []
        errors: list[str] = []

        grade = quality_result.grade
        objective_failures = quality_result.objective_failures
        heuristic_warnings_list = quality_result.heuristic_warnings

        outcome, action_type = _route_by_grade_and_findings(
            grade,
            objective_failures,
            heuristic_warnings_list,
            selected_policy,
            reasons,
            warnings,
            errors,
        )

        confidence = _compute_routing_confidence(outcome, reasons)

        return RoutingDecision(
            item_id=quality_result.item_id,
            outcome=outcome,
            action_type=action_type,
            reasons=reasons,
            warnings=warnings,
            errors=errors,
            confidence=confidence,
            policy=selected_policy,
            metadata={
                "stage": "post-download",
                "analysis": "planned-only",
                "quality_grade": grade.value,
            },
        )

    def plan_routing(
        self,
        quality_results: list[QualityResult],
        policy: RoutingPolicy | None = None,
    ) -> FluxResult:
        selected_policy = policy or DEFAULT_ROUTING_POLICY
        decisions: list[RoutingDecision] = []
        planned_changes: list[PlannedChange] = []
        all_warnings: list[FluxWarning] = []
        all_errors: list[FluxError] = []

        for qr in quality_results:
            decision = self.decide_quality_route(qr, selected_policy)
            decisions.append(decision)

            change = _decision_to_planned_change(decision)
            planned_changes.append(change)

            if decision.warnings:
                all_warnings.append(
                    self.warning(
                        "routing-warning",
                        f"Item {decision.item_id}: {', '.join(decision.warnings)}",
                        severity=Severity.WARNING,
                        item_id=decision.item_id,
                        outcome=decision.outcome.value,
                    )
                )
            if decision.errors:
                all_errors.append(
                    self.error(
                        "routing-error",
                        f"Item {decision.item_id}: {', '.join(decision.errors)}",
                        item_id=decision.item_id,
                        outcome=decision.outcome.value,
                    )
                )

        plan = RoutingPlan(
            plan_id=str(uuid.uuid4()),
            decisions=decisions,
            planned_changes=[c.to_dict() for c in planned_changes],
            warnings=[w.message for w in all_warnings],
            errors=[e.message for e in all_errors],
            metadata={"policy": selected_policy.name},
        )

        artifact = Artifact(
            kind="routing-plan",
            description="Logical post-download routing plan (planned-only, no execution)",
            metadata={
                "plan_id": plan.plan_id,
                "decision_count": len(decisions),
                "policy": selected_policy.name,
            },
        )

        step_status = Status.WARNING if (all_warnings or all_errors) else Status.SUCCESS
        step_message = f"Routing plan: {len(decisions)} item(s) evaluated with policy {selected_policy.name}"

        step = self.step(
            "plan-routing",
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
                "decision_count": len(decisions),
                "approved_count": sum(1 for d in decisions if d.outcome == RoutingOutcome.APPROVED),
                "quarantine_count": sum(1 for d in decisions if d.outcome == RoutingOutcome.QUARANTINE),
                "rejected_count": sum(1 for d in decisions if d.outcome == RoutingOutcome.REJECTED),
                "delete_eligible_count": sum(1 for d in decisions if d.outcome == RoutingOutcome.DELETE_ELIGIBLE),
                "review_count": sum(1 for d in decisions if d.outcome == RoutingOutcome.REVIEW),
                "unknown_count": sum(1 for d in decisions if d.outcome == RoutingOutcome.UNKNOWN),
                "policy": selected_policy.to_dict(),
                "routing_plan": plan.to_dict(),
            },
        ).finish()


def _route_by_grade_and_findings(
    grade: QualityGrade,
    objective_failures: list[Any],
    heuristic_warnings: list[Any],
    policy: RoutingPolicy,
    reasons: list[RoutingReason],
    warnings: list[str],
    errors: list[str],
) -> tuple[RoutingOutcome, RoutingActionType]:
    if grade == QualityGrade.EXCELLENT:
        reasons.append(
            RoutingReason(
                code="grade-excellent",
                message="Quality grade is excellent.",
                severity="info",
                source=RoutingReasonSource.QUALITY_GRADE,
            )
        )
        return RoutingOutcome.APPROVED, RoutingActionType.PLAN_ONLY

    if grade == QualityGrade.MEDIUM:
        if objective_failures:
            reasons.append(
                RoutingReason(
                    code="medium-with-objective-failure",
                    message="Medium grade with objective failure requires review.",
                    severity="warning",
                    source=RoutingReasonSource.QUALITY_FINDING,
                )
            )
            warnings.append("Medium grade includes objective failure.")
            return RoutingOutcome.REVIEW, RoutingActionType.PLAN_ONLY

        if heuristic_warnings:
            reasons.append(
                RoutingReason(
                    code="medium-with-heuristic-warning",
                    message="Medium grade with heuristic warning; approved with caution.",
                    severity="warning",
                    source=RoutingReasonSource.QUALITY_FINDING,
                )
            )
            if policy.heuristic_warnings_route_to_review_or_quarantine:
                return RoutingOutcome.REVIEW, RoutingActionType.PLAN_ONLY
            return RoutingOutcome.APPROVED, RoutingActionType.PLAN_ONLY

        reasons.append(
            RoutingReason(
                code="grade-medium-clean",
                message="Medium grade with no significant findings.",
                severity="info",
                source=RoutingReasonSource.QUALITY_GRADE,
            )
        )
        return RoutingOutcome.APPROVED, RoutingActionType.PLAN_ONLY

    if grade == QualityGrade.BAD:
        if objective_failures:
            reasons.append(
                RoutingReason(
                    code="bad-with-objective-failure",
                    message="Bad grade with objective failure.",
                    severity="error",
                    source=RoutingReasonSource.QUALITY_FINDING,
                )
            )
            errors.append("Objective failure detected for bad grade.")

            if policy.objective_failures_route_to_rejected:
                if policy.allow_delete_eligible:
                    reasons.append(
                        RoutingReason(
                            code="policy-allows-delete",
                            message="Policy allows delete_eligible for objective failures.",
                            severity="warning",
                            source=RoutingReasonSource.POLICY_RULE,
                        )
                    )
                    return RoutingOutcome.DELETE_ELIGIBLE, RoutingActionType.PLAN_ONLY
                return RoutingOutcome.REJECTED, RoutingActionType.PLAN_ONLY

            return RoutingOutcome.REJECTED, RoutingActionType.PLAN_ONLY

        if heuristic_warnings:
            reasons.append(
                RoutingReason(
                    code="bad-with-heuristic-only",
                    message="Bad grade with only heuristic warnings; routed to quarantine for review.",
                    severity="warning",
                    source=RoutingReasonSource.QUALITY_FINDING,
                )
            )
            warnings.append("Bad grade with only heuristic warnings routed to quarantine.")
            return RoutingOutcome.QUARANTINE, RoutingActionType.PLAN_ONLY

        reasons.append(
            RoutingReason(
                code="grade-bad-no-findings",
                message="Bad grade with no explicit findings; routed to review.",
                severity="warning",
                source=RoutingReasonSource.QUALITY_GRADE,
            )
        )
        return RoutingOutcome.REVIEW, RoutingActionType.PLAN_ONLY

    if grade == QualityGrade.UNKNOWN:
        reasons.append(
            RoutingReason(
                code="grade-unknown",
                message="Quality grade is unknown; routed to review.",
                severity="warning",
                source=RoutingReasonSource.QUALITY_GRADE,
            )
        )
        warnings.append("Unknown quality grade requires review.")
        return RoutingOutcome.REVIEW, RoutingActionType.PLAN_ONLY

    reasons.append(
        RoutingReason(
            code="unrecognized-grade",
            message="Unrecognized quality grade; no routing action.",
            severity="warning",
            source=RoutingReasonSource.UNKNOWN,
        )
    )
    return RoutingOutcome.UNKNOWN, RoutingActionType.NONE


def _compute_routing_confidence(outcome: RoutingOutcome, reasons: list[RoutingReason]) -> float:
    error_reasons = [r for r in reasons if r.severity == "error"]
    warning_reasons = [r for r in reasons if r.severity == "warning"]

    if outcome == RoutingOutcome.APPROVED and not warning_reasons:
        return 0.95
    if outcome == RoutingOutcome.APPROVED and warning_reasons:
        return 0.7
    if outcome == RoutingOutcome.REVIEW:
        return 0.5
    if outcome == RoutingOutcome.QUARANTINE:
        return 0.6
    if outcome == RoutingOutcome.REJECTED:
        return 0.85
    if outcome == RoutingOutcome.DELETE_ELIGIBLE:
        return 0.8
    return 0.1


def _decision_to_planned_change(decision: RoutingDecision) -> PlannedChange:
    action_map = {
        RoutingOutcome.APPROVED: "plan-approve",
        RoutingOutcome.QUARANTINE: "plan-quarantine",
        RoutingOutcome.REJECTED: "plan-reject",
        RoutingOutcome.DELETE_ELIGIBLE: "plan-mark-delete-eligible",
        RoutingOutcome.REVIEW: "plan-review",
        RoutingOutcome.UNKNOWN: "plan-no-action",
    }
    action = action_map.get(decision.outcome, "plan-no-action")
    reason_summary = "; ".join(r.message for r in decision.reasons) if decision.reasons else "No specific reason."
    return PlannedChange(
        action=action,
        target=decision.item_id,
        reason=reason_summary,
        metadata={
            "outcome": decision.outcome.value,
            "action_type": decision.action_type.value,
            "confidence": decision.confidence,
        },
    )
