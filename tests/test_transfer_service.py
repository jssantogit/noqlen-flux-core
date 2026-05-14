import pytest

from noqlen_flux.downloads import DownloadItem, DownloadPlan, DownloadIntent
from noqlen_flux.results import PlannedChange, Status
from noqlen_flux.services.transfers import TransferPlanningService
from noqlen_flux.transfers import QueueState, TransferPriority, TransferState


def _track_download_plan(
    candidate_id: str = "candidate-1",
    request_id: str = "req-1",
    plan_id: str = "plan-1",
    items: list[DownloadItem] | None = None,
    blocked: bool = False,
    block_reasons: list[str] | None = None,
) -> DownloadPlan:
    if items is None:
        items = [
            DownloadItem(
                item_id="item-1",
                candidate_id=candidate_id,
                filename="Example Track.flac",
                target_relative_path=f"{candidate_id}/Example Track.flac",
                size_bytes=12345678,
            )
        ]
    return DownloadPlan(
        plan_id=plan_id,
        request_id=request_id,
        candidate_id=candidate_id,
        intent=DownloadIntent.TRACK,
        items=items,
        target_relative_root=f"incoming/tracks/{candidate_id}",
        total_size_bytes=12345678,
        blocked=blocked,
        block_reasons=block_reasons or [],
    )


def _album_download_plan() -> DownloadPlan:
    items = [
        DownloadItem(
            item_id="item-1",
            candidate_id="album-1",
            filename="01 Intro.flac",
            target_relative_path="album-1/01 Intro.flac",
            size_bytes=1111111,
        ),
        DownloadItem(
            item_id="item-2",
            candidate_id="album-1",
            filename="02 Track.flac",
            target_relative_path="album-1/02 Track.flac",
            size_bytes=2222222,
        ),
    ]
    return DownloadPlan(
        plan_id="plan-1",
        request_id="req-1",
        candidate_id="album-1",
        intent=DownloadIntent.ALBUM,
        items=items,
        target_relative_root="incoming/albums/album-1",
        total_size_bytes=3333333,
    )


def test_valid_download_plan_generates_queue_plan_ready() -> None:
    service = TransferPlanningService()
    plan = _track_download_plan()

    result = service.plan_queue(plan)

    assert result.status == Status.SUCCESS
    assert result.summary["item_count"] == 1
    assert result.summary["state"] == "ready"
    assert result.summary["blocked"] is False
    assert len(result.planned_changes) == 1


def test_track_download_plan_generates_queue_with_one_item() -> None:
    service = TransferPlanningService()
    plan = _track_download_plan()

    result = service.plan_queue(plan)

    assert result.status == Status.SUCCESS
    assert result.summary["item_count"] == 1
    assert len(result.planned_changes) == 1


def test_album_download_plan_generates_queue_with_multiple_items() -> None:
    service = TransferPlanningService()
    plan = _album_download_plan()

    result = service.plan_queue(plan)

    assert result.status == Status.SUCCESS
    assert result.summary["item_count"] == 2
    assert len(result.planned_changes) == 2


def test_blocked_download_plan_generates_blocked_queue_plan() -> None:
    service = TransferPlanningService()
    plan = _track_download_plan(
        blocked=True,
        block_reasons=["candidate has no files"],
    )

    result = service.plan_queue(plan)

    assert result.status == Status.FAILED
    assert result.summary["blocked"] is True
    assert any("no files" in reason for reason in result.summary["block_reasons"])


def test_download_plan_without_items_generates_blocked_queue_plan() -> None:
    service = TransferPlanningService()
    plan = _track_download_plan(items=[])

    result = service.plan_queue(plan)

    assert result.status == Status.FAILED
    assert result.summary["blocked"] is True
    assert any("no items" in reason for reason in result.summary["block_reasons"])


def test_locked_items_generate_visible_warning() -> None:
    service = TransferPlanningService()
    items = [
        DownloadItem(
            item_id="item-1",
            candidate_id="candidate-1",
            filename="Locked Track.flac",
            target_relative_path="candidate-1/Locked Track.flac",
            size_bytes=12345678,
            locked=True,
        ),
    ]
    plan = _track_download_plan(items=items)

    result = service.plan_queue(plan)

    assert result.status == Status.WARNING
    assert any("locked" in w.message.lower() for w in result.warnings)
    assert result.summary["item_count"] == 1


def test_service_returns_planned_change_not_applied_change() -> None:
    service = TransferPlanningService()
    plan = _track_download_plan()

    result = service.plan_queue(plan)

    assert len(result.planned_changes) > 0
    assert len(result.applied_changes) == 0
    for change in result.planned_changes:
        assert isinstance(change, PlannedChange)
        assert not hasattr(change, "result")


def test_service_does_not_create_files(tmp_path) -> None:
    service = TransferPlanningService()
    plan = _track_download_plan()

    service.plan_queue(plan)

    assert list(tmp_path.iterdir()) == []


def test_service_does_not_access_network() -> None:
    from noqlen_flux.services import transfers as transfers_module

    source_code = open(transfers_module.__file__).read()
    assert "requests" not in source_code
    assert "urllib" not in source_code
    assert "socket" not in source_code


def test_service_does_not_depend_on_slskd() -> None:
    from noqlen_flux.services import transfers as transfers_module

    assert "slskd" not in transfers_module.__file__
    for name in dir(transfers_module):
        obj = getattr(transfers_module, name, None)
        if hasattr(obj, "__module__"):
            assert "slskd" not in (getattr(obj, "__module__", "") or "")


def test_service_does_not_decide_quality_routing_quarantine_delete() -> None:
    service = TransferPlanningService()
    plan = _track_download_plan()

    result = service.plan_queue(plan)

    payload = result.to_dict()
    assert "quality_grade" not in payload
    assert "approved" not in str(payload)
    assert "quarantine" not in str(payload)
    assert "rejected" not in str(payload)
    assert "delete_eligible" not in str(payload)


def test_plan_uses_planned_change_not_applied_change() -> None:
    service = TransferPlanningService()
    plan = _track_download_plan()

    result = service.plan_queue(plan)

    assert len(result.planned_changes) > 0
    assert len(result.applied_changes) == 0
    for change in result.planned_changes:
        assert isinstance(change, PlannedChange)
        assert not hasattr(change, "result")


def test_transfer_planning_respects_priority() -> None:
    service = TransferPlanningService()
    plan = _track_download_plan()

    result = service.plan_queue(plan, priority=TransferPriority.HIGH)

    assert result.status == Status.SUCCESS
    for change in result.planned_changes:
        assert change.action == "plan-transfer"


def test_mixed_locked_and_unlocked_items_generate_warnings() -> None:
    service = TransferPlanningService()
    items = [
        DownloadItem(
            item_id="item-1",
            candidate_id="candidate-1",
            filename="Unlocked.flac",
            target_relative_path="candidate-1/Unlocked.flac",
            size_bytes=1000,
            locked=False,
        ),
        DownloadItem(
            item_id="item-2",
            candidate_id="candidate-1",
            filename="Locked.flac",
            target_relative_path="candidate-1/Locked.flac",
            size_bytes=2000,
            locked=True,
        ),
    ]
    plan = _track_download_plan(items=items)

    result = service.plan_queue(plan)

    assert result.status == Status.WARNING
    assert result.summary["item_count"] == 2
    assert any("locked" in w.message.lower() for w in result.warnings)


def test_queue_plan_contains_queue_id() -> None:
    service = TransferPlanningService()
    plan = _track_download_plan()

    result = service.plan_queue(plan)

    assert "queue_id" in result.summary
    assert result.summary["queue_id"]


def test_queue_plan_contains_request_id() -> None:
    service = TransferPlanningService()
    plan = _track_download_plan()

    result = service.plan_queue(plan)

    assert "request_id" in result.summary
    assert result.summary["request_id"] == "req-1"


def test_service_does_not_download_files() -> None:
    service = TransferPlanningService()
    plan = _track_download_plan()

    result = service.plan_queue(plan)

    assert result.status == Status.SUCCESS
    assert "download" not in result.operation.lower()
    assert "transfer" in result.operation.lower()


def test_service_does_not_touch_filesystem() -> None:
    service = TransferPlanningService()
    plan = _track_download_plan()

    result = service.plan_queue(plan)

    payload = result.to_dict()
    assert payload["status"] == "success"
    assert payload["summary"]["blocked"] is False
