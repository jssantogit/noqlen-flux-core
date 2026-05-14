import inspect
import uuid

import pytest

from noqlen_flux.config import FluxConfig
from noqlen_flux.results import Status
from noqlen_flux.safety import PathSafetyError
from noqlen_flux.services.staging_execution import StagingExecutionService
from noqlen_flux.staging import (
    DEFAULT_STAGING_EXECUTION_POLICY,
    StagingActionType,
    StagingArea,
    StagingExecutionPolicy,
    StagingItem,
    StagingPlan,
)


def _config(tmp_path) -> FluxConfig:
    return FluxConfig(workspace_root=tmp_path)


def _staging_item(
    item_id: str = "item-1",
    area: StagingArea = StagingArea.APPROVED,
    action_type: StagingActionType = StagingActionType.COPY,
    source: str | None = "incoming/item-1.txt",
    target: str | None = None,
) -> StagingItem:
    target_path = target or f"{area.value}/{item_id}.txt"
    return StagingItem(
        item_id=item_id,
        routing_outcome=area.value,
        source_relative_path=source,
        target_area=area,
        target_relative_path=target_path,
        action_type=action_type,
    )


def _staging_plan(items: list[StagingItem]) -> StagingPlan:
    return StagingPlan(
        plan_id=f"sp-{uuid.uuid4().hex[:8]}",
        items=items,
    )


def test_dry_run_does_not_create_directories(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)
    item = _staging_item(area=StagingArea.APPROVED)
    plan = _staging_plan([item])

    result = service.execute_staging_plan(plan, config, dry_run=True)

    assert not (tmp_path / "approved").exists()
    assert not (tmp_path / "incoming").exists()


def test_dry_run_does_not_create_files(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    (tmp_path / "incoming" / "item-1.txt").write_text("test")

    item = _staging_item(area=StagingArea.APPROVED)
    plan = _staging_plan([item])

    result = service.execute_staging_plan(plan, config, dry_run=True)

    assert not (tmp_path / "approved" / "item-1.txt").exists()


def test_dry_run_does_not_copy_files(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    source_file = tmp_path / "incoming" / "item-1.txt"
    source_file.write_text("test content")

    item = _staging_item(area=StagingArea.APPROVED)
    plan = _staging_plan([item])

    result = service.execute_staging_plan(plan, config, dry_run=True)

    assert not (tmp_path / "approved" / "item-1.txt").exists()
    assert source_file.exists()


def test_dry_run_does_not_move_files(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    source_file = tmp_path / "incoming" / "item-1.txt"
    source_file.write_text("test content")

    policy = StagingExecutionPolicy(name="test", version="1", description="test", allow_move=True)
    item = _staging_item(area=StagingArea.APPROVED, action_type=StagingActionType.MOVE)
    plan = _staging_plan([item])

    result = service.execute_staging_plan(plan, config, dry_run=True, policy=policy)

    assert source_file.exists()
    assert not (tmp_path / "approved" / "item-1.txt").exists()


def test_dry_run_does_not_delete_anything(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    source_file = tmp_path / "incoming" / "item-1.txt"
    source_file.write_text("test content")

    item = _staging_item(area=StagingArea.DELETE_ELIGIBLE, action_type=StagingActionType.MARK_DELETE_ELIGIBLE)
    plan = _staging_plan([item])

    result = service.execute_staging_plan(plan, config, dry_run=True)

    assert source_file.exists()


def test_dry_run_returns_planned_change_not_applied_change(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)
    item = _staging_item(area=StagingArea.APPROVED)
    plan = _staging_plan([item])

    result = service.execute_staging_plan(plan, config, dry_run=True)

    assert len(result.planned_changes) >= 1
    assert len(result.applied_changes) == 0


def test_apply_copy_approved_within_workspace_works(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    source_file = tmp_path / "incoming" / "item-1.txt"
    source_file.write_text("test content")

    item = _staging_item(area=StagingArea.APPROVED)
    plan = _staging_plan([item])

    result = service.execute_staging_plan(plan, config, dry_run=False)

    assert (tmp_path / "approved" / "item-1.txt").exists()
    assert (tmp_path / "approved" / "item-1.txt").read_text() == "test content"
    assert result.status == Status.SUCCESS


def test_apply_copy_quarantine_within_workspace_works(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    source_file = tmp_path / "incoming" / "item-1.txt"
    source_file.write_text("test content")

    item = _staging_item(area=StagingArea.QUARANTINE)
    plan = _staging_plan([item])

    result = service.execute_staging_plan(plan, config, dry_run=False)

    assert (tmp_path / "quarantine" / "item-1.txt").exists()
    assert result.status == Status.SUCCESS


def test_apply_copy_rejected_within_workspace_works(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    source_file = tmp_path / "incoming" / "item-1.txt"
    source_file.write_text("test content")

    item = _staging_item(area=StagingArea.REJECTED)
    plan = _staging_plan([item])

    result = service.execute_staging_plan(plan, config, dry_run=False)

    assert (tmp_path / "rejected" / "item-1.txt").exists()
    assert result.status == Status.SUCCESS


def test_apply_move_blocked_by_default(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    (tmp_path / "incoming" / "item-1.txt").write_text("test")

    item = _staging_item(area=StagingArea.APPROVED, action_type=StagingActionType.MOVE)
    plan = _staging_plan([item])

    result = service.execute_staging_plan(plan, config, dry_run=False)

    assert result.status in (Status.WARNING, Status.SUCCESS)
    assert (tmp_path / "incoming" / "item-1.txt").exists()
    assert not (tmp_path / "approved" / "item-1.txt").exists()


def test_apply_move_works_if_policy_allows(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    source_file = tmp_path / "incoming" / "item-1.txt"
    source_file.write_text("test content")

    policy = StagingExecutionPolicy(name="test", version="1", description="test", allow_move=True)
    item = _staging_item(area=StagingArea.APPROVED, action_type=StagingActionType.MOVE)
    plan = _staging_plan([item])

    result = service.execute_staging_plan(plan, config, dry_run=False, policy=policy)

    assert not source_file.exists()
    assert (tmp_path / "approved" / "item-1.txt").exists()
    assert (tmp_path / "approved" / "item-1.txt").read_text() == "test content"
    assert result.status == Status.SUCCESS


def test_mark_delete_eligible_does_not_delete(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    source_file = tmp_path / "incoming" / "item-1.txt"
    source_file.write_text("test content")

    item = _staging_item(area=StagingArea.DELETE_ELIGIBLE, action_type=StagingActionType.MARK_DELETE_ELIGIBLE)
    plan = _staging_plan([item])

    result = service.execute_staging_plan(plan, config, dry_run=False)

    assert source_file.exists()
    assert source_file.read_text() == "test content"
    assert result.status == Status.SUCCESS


def test_delete_eligible_generates_mark_not_delete(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)

    item = _staging_item(area=StagingArea.DELETE_ELIGIBLE, action_type=StagingActionType.MARK_DELETE_ELIGIBLE)
    plan = _staging_plan([item])

    result = service.build_file_operation_plan(plan, config)

    assert result.status == Status.SUCCESS
    plan_data = result.summary["file_operation_plan"]
    ops = plan_data["operations"]
    assert len(ops) >= 1
    copy_ops = [o for o in ops if o["operation_type"] == "mark"]
    assert len(copy_ops) >= 1


def test_overwrite_blocked_by_default(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    (tmp_path / "approved").mkdir()
    (tmp_path / "incoming" / "item-1.txt").write_text("source")
    (tmp_path / "approved" / "item-1.txt").write_text("existing")

    item = _staging_item(area=StagingArea.APPROVED)
    plan = _staging_plan([item])

    result = service.execute_staging_plan(plan, config, dry_run=False)

    assert (tmp_path / "approved" / "item-1.txt").read_text() == "existing"
    assert result.status in (Status.WARNING, Status.FAILED)


def test_source_not_found_blocks(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)

    item = _staging_item(source="incoming/missing.txt")
    plan = _staging_plan([item])

    result = service.execute_staging_plan(plan, config, dry_run=False)

    assert result.status in (Status.FAILED, Status.WARNING)


def test_absolute_path_blocked(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)

    with pytest.raises(ValueError, match="Absolute paths"):
        StagingItem(
            item_id="item-1",
            routing_outcome="approved",
            source_relative_path="/etc/passwd",
            target_area=StagingArea.APPROVED,
            target_relative_path="approved/item-1.txt",
            action_type=StagingActionType.COPY,
        )


def test_path_traversal_blocked(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)

    with pytest.raises(ValueError, match="Path traversal marker"):
        StagingItem(
            item_id="item-1",
            routing_outcome="approved",
            source_relative_path="incoming/../../../etc/passwd",
            target_area=StagingArea.APPROVED,
            target_relative_path="approved/item-1.txt",
            action_type=StagingActionType.COPY,
        )


def test_symlink_escape_blocked(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    outside = tmp_path.parent / "outside-file.txt"
    outside.write_text("outside")
    symlink = tmp_path / "incoming" / "escape"
    symlink.symlink_to(outside)

    item = StagingItem(
        item_id="item-1",
        routing_outcome="approved",
        source_relative_path="incoming/escape",
        target_area=StagingArea.APPROVED,
        target_relative_path="approved/item-1.txt",
        action_type=StagingActionType.COPY,
    )
    plan = _staging_plan([item])

    result = service.execute_staging_plan(plan, config, dry_run=False)

    assert result.status in (Status.FAILED, Status.WARNING)


def test_protected_roots_blocked(tmp_path) -> None:
    service = StagingExecutionService()
    protected = tmp_path / "protected"
    protected.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = FluxConfig(workspace_root=workspace, protected_roots=(protected,))

    (workspace / "incoming").mkdir()
    (workspace / "incoming" / "item-1.txt").write_text("test")

    item = _staging_item(area=StagingArea.APPROVED)
    plan = _staging_plan([item])

    result = service.execute_staging_plan(plan, config, dry_run=False)

    assert not (protected / "approved").exists()
    assert not (protected / "item-1.txt").exists()
    assert (workspace / "approved" / "item-1.txt").exists()


def test_no_operation_exits_workspace(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)

    item = _staging_item(area=StagingArea.UNKNOWN, action_type=StagingActionType.NONE, source=None)
    plan = _staging_plan([item])

    result = service.execute_staging_plan(plan, config, dry_run=False)

    assert list(tmp_path.iterdir()) == []


def test_staging_approved_converts_to_file_operation_plan(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)

    item = _staging_item(area=StagingArea.APPROVED)
    plan = _staging_plan([item])

    result = service.build_file_operation_plan(plan, config)

    assert result.status == Status.SUCCESS
    assert result.summary["operation_count"] >= 1


def test_staging_quarantine_converts_to_file_operation_plan(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)

    item = _staging_item(area=StagingArea.QUARANTINE)
    plan = _staging_plan([item])

    result = service.build_file_operation_plan(plan, config)

    assert result.status == Status.SUCCESS
    assert result.summary["operation_count"] >= 1


def test_staging_rejected_converts_to_file_operation_plan(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)

    item = _staging_item(area=StagingArea.REJECTED)
    plan = _staging_plan([item])

    result = service.build_file_operation_plan(plan, config)

    assert result.status == Status.SUCCESS
    assert result.summary["operation_count"] >= 1


def test_staging_delete_eligible_converts_to_mark_not_delete(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)

    item = _staging_item(area=StagingArea.DELETE_ELIGIBLE, action_type=StagingActionType.MARK_DELETE_ELIGIBLE)
    plan = _staging_plan([item])

    result = service.build_file_operation_plan(plan, config)

    assert result.status == Status.SUCCESS
    plan_data = result.summary["file_operation_plan"]
    ops = plan_data["operations"]
    assert len(ops) >= 1
    assert ops[0]["operation_type"] == "mark"


def test_staging_execution_uses_safe_file_operation_service(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    (tmp_path / "incoming" / "item-1.txt").write_text("test")

    item = _staging_item(area=StagingArea.APPROVED)
    plan = _staging_plan([item])

    result = service.execute_staging_plan(plan, config, dry_run=False)

    assert (tmp_path / "approved" / "item-1.txt").exists()
    assert len(result.applied_changes) >= 1


def test_staging_plan_service_does_not_execute_automatically(tmp_path) -> None:
    from noqlen_flux.services import staging as staging_module

    source = inspect.getsource(staging_module)
    assert "StagingExecutionService" not in source
    assert "execute_staging_plan" not in source


def test_routing_service_does_not_execute_staging_automatically(tmp_path) -> None:
    from noqlen_flux.services import routing as routing_module

    source = inspect.getsource(routing_module)
    assert "StagingExecutionService" not in source
    assert "execute_staging_plan" not in source


def test_service_does_not_access_network() -> None:
    from noqlen_flux.services import staging_execution as module

    source = inspect.getsource(module)
    assert "requests" not in source
    assert "urllib" not in source
    assert "socket" not in source


def test_service_does_not_depend_on_slskd() -> None:
    from noqlen_flux.services import staging_execution as module

    assert "slskd" not in module.__file__
    for name in dir(module):
        obj = getattr(module, name, None)
        if hasattr(obj, "__module__"):
            assert "slskd" not in (getattr(obj, "__module__", "") or "")


def test_service_does_not_use_print_or_input() -> None:
    from noqlen_flux.services import staging_execution as module

    source = inspect.getsource(module)
    assert "print(" not in source
    assert "input(" not in source


def test_apply_returns_applied_change_for_real_operation(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    (tmp_path / "incoming" / "item-1.txt").write_text("test")

    item = _staging_item(area=StagingArea.APPROVED)
    plan = _staging_plan([item])

    result = service.execute_staging_plan(plan, config, dry_run=False)

    assert len(result.applied_changes) >= 1
    assert any(c.action.startswith("applied-") for c in result.applied_changes)


def test_copy_blocked_if_policy_disallows(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    (tmp_path / "incoming" / "item-1.txt").write_text("test")

    policy = StagingExecutionPolicy(name="test", version="1", description="test", allow_copy=False)
    item = _staging_item(area=StagingArea.APPROVED)
    plan = _staging_plan([item])

    result = service.execute_staging_plan(plan, config, dry_run=False, policy=policy)

    assert result.status in (Status.WARNING, Status.FAILED)
    assert not (tmp_path / "approved" / "item-1.txt").exists()


def test_apply_copy_with_overwrite_allowed(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    (tmp_path / "approved").mkdir()
    (tmp_path / "incoming" / "item-1.txt").write_text("new content")
    (tmp_path / "approved" / "item-1.txt").write_text("old content")

    policy = StagingExecutionPolicy(name="test", version="1", description="test", allow_overwrite=True)
    item = _staging_item(area=StagingArea.APPROVED)
    plan = _staging_plan([item])

    result = service.execute_staging_plan(plan, config, dry_run=False, policy=policy)

    assert (tmp_path / "approved" / "item-1.txt").read_text() == "new content"
    assert result.status in (Status.SUCCESS, Status.WARNING)


def test_build_file_operation_plan_returns_planned_change(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)

    item = _staging_item(area=StagingArea.APPROVED)
    plan = _staging_plan([item])

    result = service.build_file_operation_plan(plan, config)

    assert len(result.planned_changes) >= 1
    assert len(result.applied_changes) == 0


def test_staging_review_generates_plan_only(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)

    item = _staging_item(area=StagingArea.REVIEW, action_type=StagingActionType.PLAN_ONLY, source=None)
    plan = _staging_plan([item])

    result = service.build_file_operation_plan(plan, config)

    assert result.status in (Status.SUCCESS, Status.WARNING)
    plan_data = result.summary["file_operation_plan"]
    ops = plan_data["operations"]
    assert len(ops) >= 1
    assert ops[0]["operation_type"] == "none"


def test_multiple_items_processed(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    (tmp_path / "incoming" / "item-1.txt").write_text("test1")
    (tmp_path / "incoming" / "item-2.txt").write_text("test2")

    items = [
        _staging_item(item_id="item-1", area=StagingArea.APPROVED),
        _staging_item(item_id="item-2", area=StagingArea.QUARANTINE),
    ]
    plan = _staging_plan(items)

    result = service.execute_staging_plan(plan, config, dry_run=False)

    assert (tmp_path / "approved" / "item-1.txt").exists()
    assert (tmp_path / "quarantine" / "item-2.txt").exists()
    assert result.status == Status.SUCCESS


def test_execution_summary_in_result(tmp_path) -> None:
    service = StagingExecutionService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    (tmp_path / "incoming" / "item-1.txt").write_text("test")

    item = _staging_item(area=StagingArea.APPROVED)
    plan = _staging_plan([item])

    result = service.execute_staging_plan(plan, config, dry_run=False)

    assert "execution_summary" in result.summary
    summary = result.summary["execution_summary"]
    assert summary["total_items"] == 1
    assert "applied_count" in summary
    assert "planned_count" in summary
    assert "blocked_count" in summary
    assert "skipped_count" in summary
