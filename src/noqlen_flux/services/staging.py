from __future__ import annotations

import uuid
from typing import Any

from noqlen_flux.results import Artifact, FluxError, FluxResult, FluxWarning, PlannedChange, Severity, Status
from noqlen_flux.routing import RoutingDecision, RoutingOutcome, RoutingPlan
from noqlen_flux.services.base import FluxService
from noqlen_flux.staging import (
    DEFAULT_STAGING_POLICY,
    StagingActionType,
    StagingArea,
    StagingItem,
    StagingPlan,
    StagingPolicy,
)


class StagingPlanService(FluxService):
    operation = "staging"

    def plan_staging_item(
        self,
        routing_decision: RoutingDecision,
        config: Any = None,
        policy: StagingPolicy | None = None,
    ) -> StagingItem:
        selected_policy = policy or DEFAULT_STAGING_POLICY
        outcome = routing_decision.outcome
        warnings: list[str] = list(routing_decision.warnings)
        errors: list[str] = list(routing_decision.errors)

        target_area, action_type = _resolve_staging_target(outcome, selected_policy, warnings, errors)

        target_relative = _compute_target_relative(target_area, routing_decision.item_id)

        return StagingItem(
            item_id=routing_decision.item_id,
            routing_outcome=outcome.value,
            source_relative_path=None,
            target_area=target_area,
            target_relative_path=target_relative,
            action_type=action_type,
            warnings=warnings,
            errors=errors,
            metadata={
                "stage": "post-download",
                "analysis": "planned-only",
                "routing_outcome": outcome.value,
                "policy": selected_policy.name,
            },
        )

    def plan_staging(
        self,
        routing_plan: RoutingPlan,
        config: Any = None,
        policy: StagingPolicy | None = None,
    ) -> FluxResult:
        selected_policy = policy or DEFAULT_STAGING_POLICY
        items: list[StagingItem] = []
        planned_changes: list[PlannedChange] = []
        all_warnings: list[FluxWarning] = []
        all_errors: list[FluxError] = []

        for decision in routing_plan.decisions:
            staging_item = self.plan_staging_item(decision, config=config, policy=selected_policy)
            items.append(staging_item)

            change = _staging_item_to_planned_change(staging_item)
            planned_changes.append(change)

            if staging_item.warnings:
                all_warnings.append(
                    self.warning(
                        "staging-warning",
                        f"Item {staging_item.item_id}: {', '.join(staging_item.warnings)}",
                        severity=Severity.WARNING,
                        item_id=staging_item.item_id,
                        target_area=staging_item.target_area.value,
                    )
                )
            if staging_item.errors:
                all_errors.append(
                    self.error(
                        "staging-error",
                        f"Item {staging_item.item_id}: {', '.join(staging_item.errors)}",
                        item_id=staging_item.item_id,
                        target_area=staging_item.target_area.value,
                    )
                )

        plan = StagingPlan(
            plan_id=str(uuid.uuid4()),
            items=items,
            planned_changes=[c.to_dict() for c in planned_changes],
            warnings=[w.message for w in all_warnings],
            errors=[e.message for e in all_errors],
            metadata={"policy": selected_policy.name},
        )

        artifact = Artifact(
            kind="staging-plan",
            description="Logical post-download staging plan (planned-only, no execution)",
            metadata={
                "plan_id": plan.plan_id,
                "item_count": len(items),
                "policy": selected_policy.name,
            },
        )

        step_status = Status.WARNING if (all_warnings or all_errors) else Status.SUCCESS
        step_message = f"Staging plan: {len(items)} item(s) evaluated with policy {selected_policy.name}"

        step = self.step(
            "plan-staging",
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
                "item_count": len(items),
                "approved_count": sum(1 for i in items if i.target_area == StagingArea.APPROVED),
                "quarantine_count": sum(1 for i in items if i.target_area == StagingArea.QUARANTINE),
                "rejected_count": sum(1 for i in items if i.target_area == StagingArea.REJECTED),
                "delete_eligible_count": sum(1 for i in items if i.target_area == StagingArea.DELETE_ELIGIBLE),
                "review_count": sum(1 for i in items if i.target_area == StagingArea.REVIEW),
                "unknown_count": sum(1 for i in items if i.target_area == StagingArea.UNKNOWN),
                "policy": selected_policy.to_dict(),
                "staging_plan": plan.to_dict(),
            },
        ).finish()


def _resolve_staging_target(
    outcome: RoutingOutcome,
    policy: StagingPolicy,
    warnings: list[str],
    errors: list[str],
) -> tuple[StagingArea, StagingActionType]:
    if outcome == RoutingOutcome.APPROVED:
        return StagingArea.APPROVED, StagingActionType.PLAN_ONLY

    if outcome == RoutingOutcome.QUARANTINE:
        return StagingArea.QUARANTINE, StagingActionType.PLAN_ONLY

    if outcome == RoutingOutcome.REJECTED:
        return StagingArea.REJECTED, StagingActionType.PLAN_ONLY

    if outcome == RoutingOutcome.DELETE_ELIGIBLE:
        if policy.allow_delete_eligible:
            return StagingArea.DELETE_ELIGIBLE, StagingActionType.PLAN_ONLY
        warnings.append(
            "Policy does not allow delete_eligible; routing to rejected instead."
        )
        return StagingArea.REJECTED, StagingActionType.PLAN_ONLY

    if outcome == RoutingOutcome.REVIEW:
        if policy.quarantine_heuristic_warnings:
            return StagingArea.REVIEW, StagingActionType.PLAN_ONLY
        return StagingArea.QUARANTINE, StagingActionType.PLAN_ONLY

    warnings.append("Unrecognized routing outcome; no staging action.")
    return StagingArea.UNKNOWN, StagingActionType.NONE


def _compute_target_area_name(area: StagingArea) -> str:
    return area.value


def _compute_target_relative(area: StagingArea, item_id: str) -> str:
    area_name = _compute_target_area_name(area)
    return f"{area_name}/{item_id}"


def _staging_item_to_planned_change(item: StagingItem) -> PlannedChange:
    action_map = {
        StagingArea.APPROVED: "plan-stage-approved",
        StagingArea.QUARANTINE: "plan-stage-quarantine",
        StagingArea.REJECTED: "plan-stage-rejected",
        StagingArea.DELETE_ELIGIBLE: "plan-stage-delete-eligible",
        StagingArea.REVIEW: "plan-stage-review",
        StagingArea.UNKNOWN: "plan-stage-no-action",
        StagingArea.INCOMING: "plan-stage-incoming",
    }
    action = action_map.get(item.target_area, "plan-stage-no-action")
    return PlannedChange(
        action=action,
        target=item.target_relative_path or item.item_id,
        reason=f"Routing outcome: {item.routing_outcome}",
        metadata={
            "item_id": item.item_id,
            "routing_outcome": item.routing_outcome,
            "target_area": item.target_area.value,
            "action_type": item.action_type.value,
        },
    )
