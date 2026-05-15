import pytest

from noqlen_flux.providers.fake_queue_execution import FakeQueueExecutionProvider
from noqlen_flux.results import PlannedChange, Status
from noqlen_flux.services.transfer_execution import TransferExecutionService
from noqlen_flux.transfers import (
    QueueItem,
    QueuePlan,
    QueueState,
    TransferExecutionMode,
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


def test_build_execution_request_defaults() -> None:
    service = TransferExecutionService()
    plan = _make_queue_plan()
    request = service.build_execution_request(plan)
    assert request.mode == TransferExecutionMode.DRY_RUN
    assert request.policy.allow_provider_queue is False
    assert request.policy.allow_locked is False
    assert request.policy.max_items is None
    assert request.queue_plan is plan


def test_build_execution_request_custom() -> None:
    service = TransferExecutionService()
    plan = _make_queue_plan()
    request = service.build_execution_request(
        plan,
        mode=TransferExecutionMode.APPLY,
        allow_provider_queue=True,
        allow_locked=True,
        max_items=5,
        metadata={"key": "value"},
    )
    assert request.mode == TransferExecutionMode.APPLY
    assert request.policy.allow_provider_queue is True
    assert request.policy.allow_locked is True
    assert request.policy.max_items == 5
    assert request.metadata["key"] == "value"


def test_dry_run_success() -> None:
    service = TransferExecutionService()
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan()
    request = service.build_execution_request(plan, mode=TransferExecutionMode.DRY_RUN)
    result = service.execute_queue(request, provider)
    assert result.status == Status.SUCCESS
    assert len(result.planned_changes) == 1
    assert len(result.applied_changes) == 0


def test_dry_run_blocked_queue() -> None:
    service = TransferExecutionService()
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan(blocked=True, block_reasons=["test blocked"])
    request = service.build_execution_request(plan, mode=TransferExecutionMode.DRY_RUN)
    result = service.execute_queue(request, provider)
    assert result.status == Status.FAILED
    assert result.summary["blocked"] is True


def test_dry_run_empty_queue() -> None:
    service = TransferExecutionService()
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan(item_count=0)
    request = service.build_execution_request(plan, mode=TransferExecutionMode.DRY_RUN)
    result = service.execute_queue(request, provider)
    assert result.status == Status.FAILED
    assert "no items" in result.summary["block_reasons"][0]


def test_dry_run_locked_items_blocked() -> None:
    service = TransferExecutionService()
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan(locked=True)
    request = service.build_execution_request(plan, mode=TransferExecutionMode.DRY_RUN)
    result = service.execute_queue(request, provider)
    assert result.status == Status.FAILED
    assert "locked" in result.summary["block_reasons"][0].lower()


def test_dry_run_locked_items_allowed() -> None:
    service = TransferExecutionService()
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan(locked=True)
    request = service.build_execution_request(
        plan, mode=TransferExecutionMode.DRY_RUN, allow_locked=True,
    )
    result = service.execute_queue(request, provider)
    assert result.status in (Status.SUCCESS, Status.WARNING)


def test_dry_run_max_items_exceeded() -> None:
    service = TransferExecutionService()
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan(item_count=3)
    request = service.build_execution_request(plan, mode=TransferExecutionMode.DRY_RUN, max_items=2)
    result = service.execute_queue(request, provider)
    assert result.status == Status.FAILED
    assert "max allowed" in result.summary["block_reasons"][0]


def test_apply_without_policy_blocked() -> None:
    service = TransferExecutionService()
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan()
    request = service.build_execution_request(
        plan, mode=TransferExecutionMode.APPLY, allow_provider_queue=False,
    )
    result = service.execute_queue(request, provider)
    assert result.status == Status.FAILED
    assert "not allowed" in result.summary["block_reasons"][0].lower()


def test_apply_success() -> None:
    service = TransferExecutionService()
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan()
    request = service.build_execution_request(
        plan, mode=TransferExecutionMode.APPLY, allow_provider_queue=True,
    )
    result = service.execute_queue(request, provider)
    assert result.status == Status.SUCCESS
    assert len(result.planned_changes) == 0
    assert result.summary["state"] == "success"


def test_apply_blocked_queue() -> None:
    service = TransferExecutionService()
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan(blocked=True)
    request = service.build_execution_request(
        plan, mode=TransferExecutionMode.APPLY, allow_provider_queue=True,
    )
    result = service.execute_queue(request, provider)
    assert result.status == Status.FAILED


def test_apply_empty_queue() -> None:
    service = TransferExecutionService()
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan(item_count=0)
    request = service.build_execution_request(
        plan, mode=TransferExecutionMode.APPLY, allow_provider_queue=True,
    )
    result = service.execute_queue(request, provider)
    assert result.status == Status.FAILED


def test_apply_locked_without_allow_locked() -> None:
    service = TransferExecutionService()
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan(locked=True)
    request = service.build_execution_request(
        plan, mode=TransferExecutionMode.APPLY, allow_provider_queue=True, allow_locked=False,
    )
    result = service.execute_queue(request, provider)
    assert result.status == Status.FAILED
    assert "locked" in result.summary["block_reasons"][0].lower()


def test_apply_locked_with_allow_locked() -> None:
    service = TransferExecutionService()
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan(locked=True)
    request = service.build_execution_request(
        plan, mode=TransferExecutionMode.APPLY, allow_provider_queue=True, allow_locked=True,
    )
    result = service.execute_queue(request, provider)
    assert result.status == Status.SUCCESS


def test_apply_max_items_exceeded() -> None:
    service = TransferExecutionService()
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan(item_count=3)
    request = service.build_execution_request(
        plan, mode=TransferExecutionMode.APPLY, allow_provider_queue=True, max_items=2,
    )
    result = service.execute_queue(request, provider)
    assert result.status == Status.FAILED


def test_apply_simulate_failures() -> None:
    service = TransferExecutionService()
    provider = FakeQueueExecutionProvider(simulate_failures=True)
    plan = _make_queue_plan()
    request = service.build_execution_request(
        plan, mode=TransferExecutionMode.APPLY, allow_provider_queue=True,
    )
    result = service.execute_queue(request, provider)
    assert result.status == Status.FAILED
    assert len(result.errors) > 0


def test_service_returns_planned_change_not_applied_change_in_dry_run() -> None:
    service = TransferExecutionService()
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan()
    request = service.build_execution_request(plan, mode=TransferExecutionMode.DRY_RUN)
    result = service.execute_queue(request, provider)
    assert len(result.planned_changes) > 0
    assert len(result.applied_changes) == 0
    for change in result.planned_changes:
        assert isinstance(change, PlannedChange)


def test_service_does_not_create_files(tmp_path) -> None:
    service = TransferExecutionService()
    provider = FakeQueueExecutionProvider()
    plan = _make_queue_plan()
    request = service.build_execution_request(plan, mode=TransferExecutionMode.DRY_RUN)
    service.execute_queue(request, provider)
    assert list(tmp_path.iterdir()) == []


def test_service_does_not_access_network() -> None:
    from noqlen_flux.services import transfer_execution as mod
    source = open(mod.__file__).read()
    assert "requests" not in source
    assert "urllib" not in source
    assert "socket" not in source


def test_service_does_not_depend_on_slskd() -> None:
    from noqlen_flux.services import transfer_execution as mod
    assert "slskd" not in mod.__file__
    for name in dir(mod):
        obj = getattr(mod, name, None)
        if hasattr(obj, "__module__"):
            assert "slskd" not in (getattr(obj, "__module__", "") or "")
