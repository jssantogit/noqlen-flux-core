from __future__ import annotations

import uuid
from typing import Any

from noqlen_flux.downloads import DownloadItem, DownloadPlan, DownloadPlanArtifact
from noqlen_flux.results import Artifact, FluxError, FluxResult, FluxWarning, PlannedChange, Severity, Status, StepResult
from noqlen_flux.services.base import FluxService
from noqlen_flux.transfers import (
    QueueItem,
    QueuePlan,
    QueueState,
    TransferArtifact,
    TransferItem,
    TransferPriority,
    TransferRequest,
    TransferState,
)


class TransferPlanningService(FluxService):
    operation = "transfer-planning"

    def plan_queue(
        self,
        download_plan: DownloadPlan,
        priority: TransferPriority = TransferPriority.NORMAL,
    ) -> FluxResult:
        warnings: list[FluxWarning] = []
        errors: list[FluxError] = []
        block_reasons: list[str] = []
        queue_items: list[QueueItem] = []
        plan_warnings: list[str] = []

        if download_plan.blocked:
            block_reasons.extend(download_plan.block_reasons)
            return self._blocked_result(download_plan, block_reasons, warnings, errors)

        if not download_plan.items:
            block_reasons.append("download plan has no items")
            return self._blocked_result(download_plan, block_reasons, warnings, errors)

        for download_item in download_plan.items:
            if download_item.locked:
                plan_warnings.append(f"file {download_item.filename!r} is locked")
                warnings.append(
                    self.warning(
                        "locked-transfer-item",
                        f"Locked file {download_item.filename!r} is included in the transfer plan.",
                        severity=Severity.WARNING,
                    )
                )

            transfer_item = TransferItem(
                item_id=str(uuid.uuid4()),
                plan_id=download_plan.plan_id,
                candidate_id=download_plan.candidate_id,
                filename=download_item.filename,
                target_relative_path=download_item.target_relative_path,
                size_bytes=download_item.size_bytes,
                priority=priority,
                locked=download_item.locked,
            )

            queue_item = QueueItem(
                queue_item_id=str(uuid.uuid4()),
                transfer_item=transfer_item,
                state=TransferState.PLANNED,
                priority=priority,
            )
            queue_items.append(queue_item)

        if not queue_items:
            block_reasons.append("no queue items after processing")
            return self._blocked_result(download_plan, block_reasons, warnings, errors)

        queue_plan = QueuePlan(
            queue_id=str(uuid.uuid4()),
            request_id=download_plan.request_id,
            state=QueueState.READY,
            items=queue_items,
            blocked=False,
            block_reasons=[],
            warnings=plan_warnings,
        )

        planned_changes = [
            PlannedChange(
                action="plan-transfer",
                target=item.transfer_item.target_relative_path,
                reason=f"planned transfer item from download plan {download_plan.plan_id}",
                metadata={
                    "queue_item_id": item.queue_item_id,
                    "transfer_item_id": item.transfer_item.item_id,
                    "filename": item.transfer_item.filename,
                },
            )
            for item in queue_items
        ]

        artifact = Artifact(
            kind="transfer-plan",
            description="Logical transfer/queue plan with no execution",
            metadata={
                "queue_id": queue_plan.queue_id,
                "request_id": queue_plan.request_id,
                "item_count": len(queue_plan.items),
                "state": queue_plan.state.value,
            },
        )

        step_status = Status.WARNING if (warnings or plan_warnings) else Status.SUCCESS
        step = self.step(
            "plan-transfer",
            step_status,
            f"Planned {len(queue_items)} transfer item(s) for candidate {download_plan.candidate_id}",
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
                "queue_id": queue_plan.queue_id,
                "request_id": queue_plan.request_id,
                "candidate_id": download_plan.candidate_id,
                "item_count": len(queue_plan.items),
                "state": queue_plan.state.value,
                "blocked": queue_plan.blocked,
                "block_reasons": queue_plan.block_reasons,
                "warnings": queue_plan.warnings,
            },
        )
        return result.finish()

    def _blocked_result(
        self,
        download_plan: DownloadPlan,
        block_reasons: list[str],
        warnings: list[FluxWarning],
        errors: list[FluxError],
    ) -> FluxResult:
        queue_plan = QueuePlan(
            queue_id=str(uuid.uuid4()),
            request_id=download_plan.request_id,
            state=QueueState.BLOCKED,
            items=[],
            blocked=True,
            block_reasons=block_reasons,
        )

        artifact = Artifact(
            kind="transfer-plan-blocked",
            description="Transfer/queue plan was blocked by constraints or safety checks",
            metadata={
                "queue_id": queue_plan.queue_id,
                "candidate_id": download_plan.candidate_id,
                "blocked": True,
                "block_reasons": queue_plan.block_reasons,
            },
        )

        step = self.step(
            "plan-transfer",
            Status.FAILED,
            f"Transfer plan blocked for candidate {download_plan.candidate_id}",
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
                "queue_id": queue_plan.queue_id,
                "request_id": queue_plan.request_id,
                "candidate_id": download_plan.candidate_id,
                "item_count": 0,
                "blocked": True,
                "block_reasons": queue_plan.block_reasons,
            },
        )
        return result.finish()
