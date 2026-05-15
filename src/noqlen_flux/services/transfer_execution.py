from __future__ import annotations

import uuid
from typing import Any

from noqlen_flux.providers.base import QueueExecutionProvider
from noqlen_flux.results import Artifact, FluxError, FluxResult, FluxWarning, PlannedChange, Severity, Status, StepResult
from noqlen_flux.services.base import FluxService
from noqlen_flux.transfers import (
    QueuePlan,
    QueueState,
    TransferExecutionMode,
    TransferExecutionPolicy,
    TransferExecutionRequest,
    TransferPriority,
    TransferSubmissionState,
)


class TransferExecutionService(FluxService):
    operation = "transfer-execution"

    def build_execution_request(
        self,
        queue_plan: QueuePlan,
        *,
        mode: TransferExecutionMode = TransferExecutionMode.DRY_RUN,
        allow_provider_queue: bool = False,
        allow_locked: bool = False,
        max_items: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TransferExecutionRequest:
        policy = TransferExecutionPolicy(
            allow_provider_queue=allow_provider_queue,
            allow_locked=allow_locked,
            max_items=max_items,
        )
        return TransferExecutionRequest(
            request_id=str(uuid.uuid4()),
            queue_plan=queue_plan,
            policy=policy,
            mode=mode,
            metadata=metadata or {},
        )

    def execute_queue(
        self,
        request: TransferExecutionRequest,
        provider: QueueExecutionProvider,
    ) -> FluxResult:
        warnings: list[FluxWarning] = []
        errors: list[FluxError] = []
        block_reasons: list[str] = []

        queue_plan = request.queue_plan

        if queue_plan.blocked:
            block_reasons.extend(queue_plan.block_reasons or ["queue plan is blocked"])
            return self._blocked_result(request, block_reasons, warnings, errors)

        if not queue_plan.items:
            block_reasons.append("queue plan has no items")
            return self._blocked_result(request, block_reasons, warnings, errors)

        has_locked = any(
            item.transfer_item and item.transfer_item.locked
            for item in queue_plan.items
        )
        if has_locked and not request.policy.allow_locked:
            block_reasons.append("queue plan contains locked items but allow_locked is False")
            return self._blocked_result(request, block_reasons, warnings, errors)

        max_items = request.policy.max_items
        if max_items is not None and len(queue_plan.items) > max_items:
            block_reasons.append(
                f"queue plan has {len(queue_plan.items)} items, max allowed is {max_items}"
            )
            return self._blocked_result(request, block_reasons, warnings, errors)

        if request.mode == TransferExecutionMode.APPLY and not request.policy.allow_provider_queue:
            block_reasons.append("provider queue execution not allowed by policy")
            return self._blocked_result(request, block_reasons, warnings, errors)

        submission = provider.submit_queue(request)

        if submission.blocked:
            block_reasons.extend(submission.block_reasons)
            return self._blocked_result(request, block_reasons, warnings, errors, submission)

        for item in submission.items:
            for w in item.warnings:
                warnings.append(
                    self.warning(
                        "item-warning",
                        w,
                        severity=Severity.WARNING,
                        context={"queue_item_id": item.queue_item_id},
                    )
                )
            for e in item.errors:
                errors.append(
                    self.error(
                        "item-error",
                        e,
                        context={"queue_item_id": item.queue_item_id},
                    )
                )

        if request.mode == TransferExecutionMode.DRY_RUN:
            return self._dry_run_result(request, submission, warnings, errors)

        return self._apply_result(request, submission, warnings, errors)

    def _dry_run_result(
        self,
        request: TransferExecutionRequest,
        submission: Any,
        warnings: list[FluxWarning],
        errors: list[FluxError],
    ) -> FluxResult:
        planned_changes = [
            PlannedChange(
                action="submit-queue-item",
                target=item.queue_item_id,
                reason=f"dry-run: would submit queue item {item.queue_item_id}",
                metadata={
                    "state": item.state.value,
                    "message": item.message,
                },
            )
            for item in submission.items
        ]

        artifact = Artifact(
            kind="transfer-execution-plan",
            description="Planned queue submission with no execution",
            metadata={
                "submission_id": submission.submission_id,
                "request_id": submission.request_id,
                "item_count": len(submission.items),
                "state": submission.state.value,
            },
        )

        step_status = Status.WARNING if warnings else Status.SUCCESS
        step = self.step(
            "execute-queue-dry-run",
            step_status,
            f"Planned submission of {len(submission.items)} queue item(s)",
            warnings=warnings,
            errors=errors,
            artifacts=[artifact],
        )

        result = FluxResult(
            operation=self.operation,
            status=step_status,
            steps=[step],
            warnings=warnings,
            errors=errors,
            artifacts=[artifact],
            planned_changes=planned_changes,
            summary={
                "submission_id": submission.submission_id,
                "request_id": submission.request_id,
                "item_count": len(submission.items),
                "state": submission.state.value,
                "blocked": submission.blocked,
                "block_reasons": submission.block_reasons,
            },
        )
        return result.finish()

    def _apply_result(
        self,
        request: TransferExecutionRequest,
        submission: Any,
        warnings: list[FluxWarning],
        errors: list[FluxError],
    ) -> FluxResult:
        applied_summary = {
            item.queue_item_id: item.state.value
            for item in submission.items
        }

        artifact = Artifact(
            kind="transfer-execution-applied",
            description="Queue submission executed via provider",
            metadata={
                "submission_id": submission.submission_id,
                "request_id": submission.request_id,
                "item_count": len(submission.items),
                "state": submission.state.value,
                "applied_summary": applied_summary,
            },
        )

        step_status = Status.FAILED if errors else (Status.WARNING if warnings else Status.SUCCESS)
        step = self.step(
            "execute-queue-apply",
            step_status,
            f"Submitted {len(submission.items)} queue item(s) to provider",
            warnings=warnings,
            errors=errors,
            artifacts=[artifact],
        )

        result = FluxResult(
            operation=self.operation,
            status=step_status,
            steps=[step],
            warnings=warnings,
            errors=errors,
            artifacts=[artifact],
            summary={
                "submission_id": submission.submission_id,
                "request_id": submission.request_id,
                "item_count": len(submission.items),
                "state": submission.state.value,
                "blocked": submission.blocked,
                "block_reasons": submission.block_reasons,
                "applied_summary": applied_summary,
            },
        )
        return result.finish()

    def _blocked_result(
        self,
        request: TransferExecutionRequest,
        block_reasons: list[str],
        warnings: list[FluxWarning],
        errors: list[FluxError],
        submission: Any | None = None,
    ) -> FluxResult:
        artifact = Artifact(
            kind="transfer-execution-blocked",
            description="Queue execution blocked by constraints or safety checks",
            metadata={
                "request_id": request.request_id,
                "blocked": True,
                "block_reasons": block_reasons,
            },
        )

        step = self.step(
            "execute-queue-blocked",
            Status.FAILED,
            f"Queue execution blocked for request {request.request_id}",
            warnings=warnings,
            errors=errors,
            artifacts=[artifact],
        )

        result = FluxResult(
            operation=self.operation,
            status=Status.FAILED,
            steps=[step],
            warnings=warnings,
            errors=errors,
            artifacts=[artifact],
            summary={
                "request_id": request.request_id,
                "blocked": True,
                "block_reasons": block_reasons,
            },
        )
        return result.finish()
