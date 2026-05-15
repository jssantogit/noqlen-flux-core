import pytest

from noqlen_flux.providers.base import QueueExecutionProvider
from noqlen_flux.providers.fake_queue_execution import FakeQueueExecutionProvider
from noqlen_flux.providers.status import ProviderAvailability, ProviderCapability, ProviderKind
from noqlen_flux.transfers import (
    QueueItem,
    QueuePlan,
    QueueState,
    TransferExecutionMode,
    TransferExecutionPolicy,
    TransferExecutionRequest,
    TransferItem,
    TransferSubmissionState,
)


def _make_queue_plan(
    *,
    blocked: bool = False,
    block_reasons: list[str] | None = None,
    item_count: int = 1,
    locked: bool = False,
) -> QueuePlan:
    items = []
    for i in range(item_count):
        transfer_item = TransferItem(
            item_id=f"item-{i}",
            plan_id="plan-1",
            candidate_id="candidate-1",
            filename=f"Track {i}.flac",
            target_relative_path=f"candidate-1/Track {i}.flac",
            locked=locked,
        )
        items.append(
            QueueItem(
                queue_item_id=f"qi-{i}",
                transfer_item=transfer_item,
            )
        )
    return QueuePlan(
        queue_id="queue-1",
        request_id="req-1",
        state=QueueState.BLOCKED if blocked else QueueState.READY,
        items=items,
        blocked=blocked,
        block_reasons=block_reasons or [],
    )


def _make_request(
    queue_plan: QueuePlan,
    *,
    mode: TransferExecutionMode = TransferExecutionMode.DRY_RUN,
    allow_provider_queue: bool = False,
    allow_locked: bool = False,
    max_items: int | None = None,
) -> TransferExecutionRequest:
    return TransferExecutionRequest(
        request_id="exec-1",
        queue_plan=queue_plan,
        policy=TransferExecutionPolicy(
            allow_provider_queue=allow_provider_queue,
            allow_locked=allow_locked,
            max_items=max_items,
        ),
        mode=mode,
    )


def test_fake_queue_execution_is_queue_execution_provider() -> None:
    provider = FakeQueueExecutionProvider()
    assert isinstance(provider, QueueExecutionProvider)


def test_fake_queue_execution_contract_compliance() -> None:
    assert issubclass(FakeQueueExecutionProvider, QueueExecutionProvider)


def test_fake_queue_execution_name() -> None:
    provider = FakeQueueExecutionProvider()
    assert provider.name == "fake-queue-execution"

    custom = FakeQueueExecutionProvider(name="custom-name")
    assert custom.name == "custom-name"


def test_fake_queue_execution_capabilities() -> None:
    provider = FakeQueueExecutionProvider()
    caps = provider.capabilities()
    assert ProviderCapability.QUEUE_PLANNING in caps
    assert ProviderCapability.HEALTH in caps


def test_fake_queue_execution_health_available() -> None:
    provider = FakeQueueExecutionProvider()
    health = provider.health()
    assert health.availability == ProviderAvailability.AVAILABLE
    assert health.kind == ProviderKind.FAKE
    assert health.errors == []


def test_fake_queue_execution_health_unavailable() -> None:
    provider = FakeQueueExecutionProvider(availability=ProviderAvailability.UNAVAILABLE)
    health = provider.health()
    assert health.availability == ProviderAvailability.UNAVAILABLE
    assert len(health.errors) > 0


def test_dry_run_returns_planned_state() -> None:
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan()
    request = _make_request(plan, mode=TransferExecutionMode.DRY_RUN)
    result = provider.submit_queue(request)
    assert result.state == TransferSubmissionState.PLANNED
    assert len(result.items) == 1
    assert result.items[0].state == TransferSubmissionState.PLANNED


def test_dry_run_blocked_queue() -> None:
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan(blocked=True, block_reasons=["test blocked"])
    request = _make_request(plan, mode=TransferExecutionMode.DRY_RUN)
    result = provider.submit_queue(request)
    assert result.blocked is True
    assert result.state == TransferSubmissionState.BLOCKED


def test_dry_run_empty_queue() -> None:
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan(item_count=0)
    request = _make_request(plan, mode=TransferExecutionMode.DRY_RUN)
    result = provider.submit_queue(request)
    assert result.blocked is True
    assert result.state == TransferSubmissionState.BLOCKED


def test_dry_run_locked_item() -> None:
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan(locked=True)
    request = _make_request(plan, mode=TransferExecutionMode.DRY_RUN)
    result = provider.submit_queue(request)
    assert result.state == TransferSubmissionState.PLANNED
    assert result.items[0].state == TransferSubmissionState.LOCKED_ITEM


def test_apply_success() -> None:
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan()
    request = _make_request(plan, mode=TransferExecutionMode.APPLY, allow_provider_queue=True)
    result = provider.submit_queue(request)
    assert result.state == TransferSubmissionState.SUCCESS
    assert result.items[0].state == TransferSubmissionState.SUCCESS


def test_apply_blocked_without_policy() -> None:
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan()
    request = _make_request(plan, mode=TransferExecutionMode.APPLY, allow_provider_queue=False)
    result = provider.submit_queue(request)
    assert result.blocked is True
    assert result.state == TransferSubmissionState.BLOCKED


def test_apply_blocked_queue() -> None:
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan(blocked=True)
    request = _make_request(plan, mode=TransferExecutionMode.APPLY, allow_provider_queue=True)
    result = provider.submit_queue(request)
    assert result.blocked is True


def test_apply_empty_queue() -> None:
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan(item_count=0)
    request = _make_request(plan, mode=TransferExecutionMode.APPLY, allow_provider_queue=True)
    result = provider.submit_queue(request)
    assert result.blocked is True


def test_apply_max_items_exceeded() -> None:
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan(item_count=3)
    request = _make_request(plan, mode=TransferExecutionMode.APPLY, allow_provider_queue=True, max_items=2)
    result = provider.submit_queue(request)
    assert result.blocked is True
    assert "max allowed" in result.block_reasons[0]


def test_apply_simulate_failures() -> None:
    provider = FakeQueueExecutionProvider(simulate_failures=True)
    plan = _make_queue_plan()
    request = _make_request(plan, mode=TransferExecutionMode.APPLY, allow_provider_queue=True)
    result = provider.submit_queue(request)
    assert result.state == TransferSubmissionState.PROVIDER_ERROR
    assert result.items[0].state == TransferSubmissionState.PROVIDER_ERROR


def test_apply_simulate_blocked() -> None:
    provider = FakeQueueExecutionProvider(simulate_blocked=True)
    plan = _make_queue_plan()
    request = _make_request(plan, mode=TransferExecutionMode.APPLY, allow_provider_queue=True)
    result = provider.submit_queue(request)
    assert result.items[0].state == TransferSubmissionState.BLOCKED


def test_apply_simulate_locked() -> None:
    provider = FakeQueueExecutionProvider(simulate_locked=True)
    plan = _make_queue_plan(locked=True)
    request = _make_request(plan, mode=TransferExecutionMode.APPLY, allow_provider_queue=True, allow_locked=True)
    result = provider.submit_queue(request)
    assert result.items[0].state == TransferSubmissionState.LOCKED_ITEM


def test_apply_simulate_duplicate() -> None:
    provider = FakeQueueExecutionProvider(simulate_duplicate=True)
    plan = _make_queue_plan()
    request = _make_request(plan, mode=TransferExecutionMode.APPLY, allow_provider_queue=True)
    result = provider.submit_queue(request)
    assert result.items[0].state == TransferSubmissionState.DUPLICATE


def test_apply_simulate_unavailable() -> None:
    provider = FakeQueueExecutionProvider(simulate_unavailable=True)
    plan = _make_queue_plan()
    request = _make_request(plan, mode=TransferExecutionMode.APPLY, allow_provider_queue=True)
    result = provider.submit_queue(request)
    assert result.state == TransferSubmissionState.UNAVAILABLE
    assert result.blocked is True


def test_no_network_imports() -> None:
    import noqlen_flux.providers.fake_queue_execution as mod
    source = open(mod.__file__).read()
    assert "requests" not in source
    assert "urllib" not in source
    assert "socket" not in source
    assert "http" not in source.lower().split("import")[-1].split("\n")[0]


def test_no_slskd_imports() -> None:
    import noqlen_flux.providers.fake_queue_execution as mod
    source = open(mod.__file__).read()
    assert "slskd" not in source


def test_submission_stored_in_memory() -> None:
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan()
    request = _make_request(plan, mode=TransferExecutionMode.APPLY, allow_provider_queue=True)
    result = provider.submit_queue(request)
    health = provider.health()
    assert health.metadata["submission_count"] == 1
