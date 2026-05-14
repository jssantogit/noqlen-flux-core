from __future__ import annotations

import uuid

from noqlen_flux.providers.base import TransferProvider
from noqlen_flux.providers.status import (
    ProviderAvailability,
    ProviderCapability,
    ProviderHealth,
    ProviderKind,
)
from noqlen_flux.transfers import (
    QueueItem,
    QueuePlan,
    QueueState,
    TransferRequest,
    TransferState,
    TransferStatus,
)


class FakeTransferProvider(TransferProvider):
    """In-memory transfer provider for offline tests and CLI demonstrations.

    Simulates queue planning and status without network, filesystem, or real downloads.
    """

    _TRANSFER_CAPABILITIES: list[ProviderCapability] = [
        ProviderCapability.DOWNLOAD_PLANNING,
        ProviderCapability.QUEUE_PLANNING,
        ProviderCapability.TRANSFER_STATUS,
        ProviderCapability.HEALTH,
    ]

    def __init__(
        self,
        *,
        name: str = "fake-transfer",
        kind: ProviderKind = ProviderKind.FAKE,
        availability: ProviderAvailability = ProviderAvailability.AVAILABLE,
        status_message: str | None = None,
        simulate_failures: bool = False,
    ) -> None:
        self._name = name
        self._kind = kind
        self._availability = availability
        self._status_message = status_message
        self._simulate_failures = simulate_failures
        self._plans: dict[str, QueuePlan] = {}

    @property
    def name(self) -> str:
        return self._name

    def capabilities(self) -> list[ProviderCapability]:
        return list(self._TRANSFER_CAPABILITIES)

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
            metadata={"plan_count": len(self._plans)},
        )

    def plan_queue(self, request: TransferRequest) -> QueuePlan:
        queue_item_id = str(uuid.uuid4())
        state = TransferState.FAILED if self._simulate_failures else TransferState.PLANNED
        queue_state = QueueState.FAILED if self._simulate_failures else QueueState.READY

        queue_item = QueueItem(
            queue_item_id=queue_item_id,
            transfer_item=None,  # type: ignore[arg-type]
            state=state,
            priority=request.priority,
        )

        plan = QueuePlan(
            queue_id=str(uuid.uuid4()),
            request_id=request.request_id,
            state=queue_state,
            items=[queue_item],
            blocked=self._simulate_failures,
            block_reasons=["simulated failure"] if self._simulate_failures else [],
        )

        self._plans[request.request_id] = plan
        return plan

    def get_status(self, queue_item_id: str) -> TransferStatus:
        for plan in self._plans.values():
            for item in plan.items:
                if item.queue_item_id == queue_item_id:
                    return TransferStatus(
                        transfer_id=str(uuid.uuid4()),
                        queue_item_id=queue_item_id,
                        state=item.state,
                        warnings=item.warnings,
                        errors=item.errors,
                    )

        return TransferStatus(
            transfer_id=str(uuid.uuid4()),
            queue_item_id=queue_item_id,
            state=TransferState.UNKNOWN,
            errors=["queue item not found"],
        )
