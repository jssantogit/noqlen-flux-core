from __future__ import annotations

import uuid

from noqlen_flux.providers.base import QueueExecutionProvider
from noqlen_flux.providers.status import (
    ProviderAvailability,
    ProviderCapability,
    ProviderHealth,
    ProviderKind,
)
from noqlen_flux.transfers import (
    QueueState,
    TransferExecutionMode,
    TransferExecutionRequest,
    TransferSubmissionItem,
    TransferSubmissionResult,
    TransferSubmissionState,
)

_QUEUE_EXECUTION_CAPABILITIES: list[ProviderCapability] = [
    ProviderCapability.QUEUE_PLANNING,
    ProviderCapability.HEALTH,
]


class FakeQueueExecutionProvider(QueueExecutionProvider):
    """In-memory queue execution provider for offline tests and CLI demonstrations.

    Simulates queue submission without network, filesystem, or real transfers.

    Supports dry-run (returns planned/skipped) and apply (simulates submitted in memory).
    Simulates success, blocked, provider error, locked item, duplicate, and unavailable provider.
    """

    def __init__(
        self,
        *,
        name: str = "fake-queue-execution",
        kind: ProviderKind = ProviderKind.FAKE,
        availability: ProviderAvailability = ProviderAvailability.AVAILABLE,
        status_message: str | None = None,
        simulate_failures: bool = False,
        simulate_blocked: bool = False,
        simulate_locked: bool = False,
        simulate_duplicate: bool = False,
        simulate_unavailable: bool = False,
    ) -> None:
        self._name = name
        self._kind = kind
        self._availability = availability
        self._status_message = status_message
        self._simulate_failures = simulate_failures
        self._simulate_blocked = simulate_blocked
        self._simulate_locked = simulate_locked
        self._simulate_duplicate = simulate_duplicate
        self._simulate_unavailable = simulate_unavailable
        self._submissions: dict[str, TransferSubmissionResult] = {}

    @property
    def name(self) -> str:
        return self._name

    def capabilities(self) -> list[ProviderCapability]:
        return list(_QUEUE_EXECUTION_CAPABILITIES)

    def health(self) -> ProviderHealth:
        health_warnings: list[str] = []
        health_errors: list[str] = []
        status_msg = self._status_message

        if self._availability == ProviderAvailability.DEGRADED:
            health_warnings.append("provider operating in degraded mode")
        elif self._availability == ProviderAvailability.UNAVAILABLE:
            health_errors.append("provider is unavailable")
            status_msg = status_msg or "provider unreachable"

        return ProviderHealth(
            provider=self.name,
            kind=self._kind,
            availability=self._availability,
            status_message=status_msg,
            capabilities=self.capabilities(),
            warnings=health_warnings,
            errors=health_errors,
            metadata={"submission_count": len(self._submissions)},
        )

    def submit_queue(self, request: TransferExecutionRequest) -> TransferSubmissionResult:
        if request.mode == TransferExecutionMode.DRY_RUN:
            return self._dry_run_submit(request)
        return self._apply_submit(request)

    def _dry_run_submit(self, request: TransferExecutionRequest) -> TransferSubmissionResult:
        queue_plan = request.queue_plan
        items: list[TransferSubmissionItem] = []

        if queue_plan.blocked:
            return TransferSubmissionResult(
                submission_id=str(uuid.uuid4()),
                request_id=request.request_id,
                state=TransferSubmissionState.BLOCKED,
                items=[],
                blocked=True,
                block_reasons=queue_plan.block_reasons or ["queue plan is blocked"],
            )

        if not queue_plan.items:
            return TransferSubmissionResult(
                submission_id=str(uuid.uuid4()),
                request_id=request.request_id,
                state=TransferSubmissionState.BLOCKED,
                items=[],
                blocked=True,
                block_reasons=["queue plan has no items"],
            )

        for queue_item in queue_plan.items:
            if queue_item.transfer_item and queue_item.transfer_item.locked:
                items.append(TransferSubmissionItem(
                    queue_item_id=queue_item.queue_item_id,
                    state=TransferSubmissionState.LOCKED_ITEM,
                    message=f"locked item {queue_item.queue_item_id} would be skipped in apply",
                    warnings=["item is locked"],
                ))
            else:
                items.append(TransferSubmissionItem(
                    queue_item_id=queue_item.queue_item_id,
                    state=TransferSubmissionState.PLANNED,
                    message=f"would submit {queue_item.queue_item_id}",
                ))

        return TransferSubmissionResult(
            submission_id=str(uuid.uuid4()),
            request_id=request.request_id,
            state=TransferSubmissionState.PLANNED,
            items=items,
        )

    def _apply_submit(self, request: TransferExecutionRequest) -> TransferSubmissionResult:
        queue_plan = request.queue_plan
        items: list[TransferSubmissionItem] = []

        if not request.policy.allow_provider_queue:
            return TransferSubmissionResult(
                submission_id=str(uuid.uuid4()),
                request_id=request.request_id,
                state=TransferSubmissionState.BLOCKED,
                items=[],
                blocked=True,
                block_reasons=["provider queue execution not allowed by policy"],
            )

        if queue_plan.blocked:
            return TransferSubmissionResult(
                submission_id=str(uuid.uuid4()),
                request_id=request.request_id,
                state=TransferSubmissionState.BLOCKED,
                items=[],
                blocked=True,
                block_reasons=queue_plan.block_reasons or ["queue plan is blocked"],
            )

        if not queue_plan.items:
            return TransferSubmissionResult(
                submission_id=str(uuid.uuid4()),
                request_id=request.request_id,
                state=TransferSubmissionState.BLOCKED,
                items=[],
                blocked=True,
                block_reasons=["queue plan has no items"],
            )

        max_items = request.policy.max_items
        if max_items is not None and len(queue_plan.items) > max_items:
            return TransferSubmissionResult(
                submission_id=str(uuid.uuid4()),
                request_id=request.request_id,
                state=TransferSubmissionState.BLOCKED,
                items=[],
                blocked=True,
                block_reasons=[f"queue plan has {len(queue_plan.items)} items, max allowed is {max_items}"],
            )

        if self._simulate_unavailable:
            return TransferSubmissionResult(
                submission_id=str(uuid.uuid4()),
                request_id=request.request_id,
                state=TransferSubmissionState.UNAVAILABLE,
                items=[],
                blocked=True,
                block_reasons=["provider is unavailable"],
                errors=["provider unreachable"],
            )

        for queue_item in queue_plan.items:
            if self._simulate_locked and queue_item.transfer_item and queue_item.transfer_item.locked:
                items.append(TransferSubmissionItem(
                    queue_item_id=queue_item.queue_item_id,
                    state=TransferSubmissionState.LOCKED_ITEM,
                    message=f"locked item {queue_item.queue_item_id} skipped",
                    warnings=["item is locked"],
                ))
                continue

            if self._simulate_duplicate:
                items.append(TransferSubmissionItem(
                    queue_item_id=queue_item.queue_item_id,
                    state=TransferSubmissionState.DUPLICATE,
                    message=f"duplicate item {queue_item.queue_item_id}",
                    errors=["item already submitted"],
                ))
                continue

            if self._simulate_blocked:
                items.append(TransferSubmissionItem(
                    queue_item_id=queue_item.queue_item_id,
                    state=TransferSubmissionState.BLOCKED,
                    message=f"item {queue_item.queue_item_id} blocked",
                    errors=["simulated block"],
                ))
                continue

            if self._simulate_failures:
                items.append(TransferSubmissionItem(
                    queue_item_id=queue_item.queue_item_id,
                    state=TransferSubmissionState.PROVIDER_ERROR,
                    message=f"provider error for {queue_item.queue_item_id}",
                    errors=["simulated provider error"],
                ))
                continue

            items.append(TransferSubmissionItem(
                queue_item_id=queue_item.queue_item_id,
                state=TransferSubmissionState.SUCCESS,
                message=f"submitted {queue_item.queue_item_id}",
            ))

        has_errors = any(
            item.state in (
                TransferSubmissionState.PROVIDER_ERROR,
                TransferSubmissionState.UNAVAILABLE,
            )
            for item in items
        )
        all_blocked = all(
            item.state in (
                TransferSubmissionState.BLOCKED,
                TransferSubmissionState.LOCKED_ITEM,
                TransferSubmissionState.DUPLICATE,
            )
            for item in items
        )

        if has_errors:
            overall_state = TransferSubmissionState.PROVIDER_ERROR
        elif all_blocked and items:
            overall_state = TransferSubmissionState.BLOCKED
        else:
            overall_state = TransferSubmissionState.SUCCESS

        result = TransferSubmissionResult(
            submission_id=str(uuid.uuid4()),
            request_id=request.request_id,
            state=overall_state,
            items=items,
            blocked=overall_state in (TransferSubmissionState.BLOCKED, TransferSubmissionState.UNAVAILABLE),
            block_reasons=["simulated failures"] if self._simulate_failures else [],
            errors=[item_msg for item in items for item_msg in item.errors],
        )

        self._submissions[result.submission_id] = result
        return result
