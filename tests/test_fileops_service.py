import inspect
import uuid

import pytest

from noqlen_flux.config import FluxConfig
from noqlen_flux.fileops import (
    DEFAULT_FILE_EXECUTION_POLICY,
    FileExecutionPolicy,
    FileOperation,
    FileOperationPlan,
    FileOperationResult,
    FileOperationState,
    FileOperationType,
)
from noqlen_flux.results import Status
from noqlen_flux.safety import PathSafetyError
from noqlen_flux.services.fileops import SafeFileOperationService
from noqlen_flux.staging import StagingActionType, StagingArea, StagingItem, StagingPlan


def _config(tmp_path) -> FluxConfig:
    return FluxConfig(workspace_root=tmp_path)


def _mkdir_op(op_id: str | None = None, target: str = "test-dir") -> FileOperation:
    return FileOperation(
        operation_id=op_id or f"op-{uuid.uuid4().hex[:8]}",
        operation_type=FileOperationType.MKDIR,
        target_relative_path=target,
        reason="Test mkdir",
    )


def _copy_op(op_id: str | None = None, source: str = "incoming/file.txt", target: str = "approved/file.txt") -> FileOperation:
    return FileOperation(
        operation_id=op_id or f"op-{uuid.uuid4().hex[:8]}",
        operation_type=FileOperationType.COPY,
        source_relative_path=source,
        target_relative_path=target,
        reason="Test copy",
    )


def _move_op(op_id: str | None = None, source: str = "incoming/file.txt", target: str = "approved/file.txt") -> FileOperation:
    return FileOperation(
        operation_id=op_id or f"op-{uuid.uuid4().hex[:8]}",
        operation_type=FileOperationType.MOVE,
        source_relative_path=source,
        target_relative_path=target,
        reason="Test move",
    )


def _mark_op(op_id: str | None = None, target: str = "rejected/file.txt") -> FileOperation:
    return FileOperation(
        operation_id=op_id or f"op-{uuid.uuid4().hex[:8]}",
        operation_type=FileOperationType.MARK,
        target_relative_path=target,
        reason="Test mark",
    )


def _plan(operations: list[FileOperation]) -> FileOperationPlan:
    return FileOperationPlan(
        plan_id=f"plan-{uuid.uuid4().hex[:8]}",
        operations=operations,
    )


def test_dry_run_does_not_create_directories(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)
    plan = _plan([_mkdir_op(target="new-dir")])

    result = service.execute_plan(plan, config, dry_run=True)

    assert not (tmp_path / "new-dir").exists()


def test_dry_run_does_not_copy_files(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    (tmp_path / "incoming" / "file.txt").write_text("test")

    plan = _plan([_copy_op()])
    result = service.execute_plan(plan, config, dry_run=True)

    assert not (tmp_path / "approved" / "file.txt").exists()


def test_dry_run_does_not_move_files(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    (tmp_path / "incoming" / "file.txt").write_text("test")

    policy = FileExecutionPolicy(name="test", version="1", description="test", allow_move=True)
    plan = _plan([_move_op()])
    result = service.execute_plan(plan, config, dry_run=True, policy=policy)

    assert (tmp_path / "incoming" / "file.txt").exists()
    assert not (tmp_path / "approved" / "file.txt").exists()


def test_dry_run_returns_planned_change_not_applied_change(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)
    plan = _plan([_mkdir_op(target="new-dir")])

    result = service.execute_plan(plan, config, dry_run=True)

    assert len(result.planned_changes) >= 1
    assert len(result.applied_changes) == 0


def test_apply_mkdir_within_workspace_works(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)
    plan = _plan([_mkdir_op(target="new-dir")])

    result = service.execute_plan(plan, config, dry_run=False)

    assert (tmp_path / "new-dir").is_dir()
    assert result.status == Status.SUCCESS


def test_apply_copy_within_workspace_works(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    source_file = tmp_path / "incoming" / "file.txt"
    source_file.write_text("test content")

    plan = _plan([_copy_op()])
    result = service.execute_plan(plan, config, dry_run=False)

    assert (tmp_path / "approved" / "file.txt").exists()
    assert (tmp_path / "approved" / "file.txt").read_text() == "test content"
    assert result.status == Status.SUCCESS


def test_apply_move_within_workspace_works_if_policy_allows(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    source_file = tmp_path / "incoming" / "file.txt"
    source_file.write_text("test content")

    policy = FileExecutionPolicy(name="test", version="1", description="test", allow_move=True)
    plan = _plan([_move_op()])
    result = service.execute_plan(plan, config, dry_run=False, policy=policy)

    assert not (tmp_path / "incoming" / "file.txt").exists()
    assert (tmp_path / "approved" / "file.txt").exists()
    assert (tmp_path / "approved" / "file.txt").read_text() == "test content"
    assert result.status == Status.SUCCESS


def test_apply_move_blocked_if_policy_disallows(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    (tmp_path / "incoming" / "file.txt").write_text("test")

    plan = _plan([_move_op()])
    result = service.execute_plan(plan, config, dry_run=False)

    assert result.status == Status.WARNING
    assert (tmp_path / "incoming" / "file.txt").exists()
    assert not (tmp_path / "approved" / "file.txt").exists()


def test_overwrite_blocked_by_default(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    (tmp_path / "approved").mkdir()
    (tmp_path / "incoming" / "file.txt").write_text("source")
    (tmp_path / "approved" / "file.txt").write_text("existing")

    plan = _plan([_copy_op()])
    result = service.execute_plan(plan, config, dry_run=False)

    assert (tmp_path / "approved" / "file.txt").read_text() == "existing"
    assert result.status == Status.WARNING


def test_source_not_found_blocks_copy(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)

    plan = _plan([_copy_op(source="incoming/missing.txt")])
    result = service.execute_plan(plan, config, dry_run=False)

    assert result.status == Status.FAILED


def test_source_not_found_blocks_move(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)
    policy = FileExecutionPolicy(name="test", version="1", description="test", allow_move=True)

    plan = _plan([_move_op(source="incoming/missing.txt")])
    result = service.execute_plan(plan, config, dry_run=False, policy=policy)

    assert result.status == Status.FAILED


def test_delete_never_executed(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)

    assert "delete" not in [op.value for op in FileOperationType]


def test_mark_delete_eligible_does_not_delete(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)
    (tmp_path / "rejected").mkdir()
    target_file = tmp_path / "rejected" / "file.txt"
    target_file.write_text("test")

    plan = _plan([_mark_op(target="rejected/file.txt")])
    result = service.execute_plan(plan, config, dry_run=False)

    assert target_file.exists()
    assert target_file.read_text() == "test"
    assert result.status == Status.SUCCESS


def test_path_traversal_blocked(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)

    plan = _plan([_mkdir_op(target="../../../etc/evil")])
    result = service.execute_plan(plan, config, dry_run=False)

    assert result.status in (Status.FAILED, Status.WARNING)


def test_absolute_path_blocked(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)

    plan = _plan([_mkdir_op(target="/etc/passwd")])
    result = service.execute_plan(plan, config, dry_run=False)

    assert result.status in (Status.FAILED, Status.WARNING)


def test_symlink_escape_source_blocked(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    outside = tmp_path.parent / "outside-file.txt"
    outside.write_text("outside")
    symlink = tmp_path / "incoming" / "escape"
    symlink.symlink_to(outside)

    plan = _plan([_copy_op(source="incoming/escape", target="approved/escape")])
    result = service.execute_plan(plan, config, dry_run=False)

    assert result.status in (Status.FAILED, Status.WARNING)


def test_protected_roots_blocked(tmp_path) -> None:
    service = SafeFileOperationService()
    protected = tmp_path / "protected"
    protected.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = FluxConfig(workspace_root=workspace, protected_roots=(protected,))

    plan = _plan([_mkdir_op(target="../protected/evil")])
    result = service.execute_plan(plan, config, dry_run=False)

    assert result.status in (Status.FAILED, Status.WARNING)


def test_no_operation_exits_workspace(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)

    plan = _plan([
        FileOperation(
            operation_id=f"op-{uuid.uuid4().hex[:8]}",
            operation_type=FileOperationType.NONE,
            reason="No operation",
        ),
    ])
    result = service.execute_plan(plan, config, dry_run=False)

    assert list(tmp_path.iterdir()) == []


def test_staging_approved_generates_file_operation_plan(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)

    item = StagingItem(
        item_id="item-1",
        routing_outcome="approved",
        source_relative_path="incoming/item-1.flac",
        target_area=StagingArea.APPROVED,
        target_relative_path="approved/item-1.flac",
        action_type=StagingActionType.COPY,
    )
    staging_plan = StagingPlan(plan_id="sp-1", items=[item])

    result = service.plan_from_staging(staging_plan, config)

    assert result.status == Status.SUCCESS
    assert result.summary["operation_count"] == 1


def test_staging_quarantine_generates_file_operation_plan(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)

    item = StagingItem(
        item_id="item-1",
        routing_outcome="quarantine",
        source_relative_path="incoming/item-1.flac",
        target_area=StagingArea.QUARANTINE,
        target_relative_path="quarantine/item-1.flac",
        action_type=StagingActionType.COPY,
    )
    staging_plan = StagingPlan(plan_id="sp-1", items=[item])

    result = service.plan_from_staging(staging_plan, config)

    assert result.status == Status.SUCCESS
    assert result.summary["operation_count"] == 1


def test_staging_rejected_generates_file_operation_plan(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)

    item = StagingItem(
        item_id="item-1",
        routing_outcome="rejected",
        source_relative_path="incoming/item-1.flac",
        target_area=StagingArea.REJECTED,
        target_relative_path="rejected/item-1.flac",
        action_type=StagingActionType.COPY,
    )
    staging_plan = StagingPlan(plan_id="sp-1", items=[item])

    result = service.plan_from_staging(staging_plan, config)

    assert result.status == Status.SUCCESS
    assert result.summary["operation_count"] == 1


def test_staging_delete_eligible_generates_mark_not_delete(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)

    item = StagingItem(
        item_id="item-1",
        routing_outcome="delete_eligible",
        source_relative_path="incoming/item-1.flac",
        target_area=StagingArea.DELETE_ELIGIBLE,
        target_relative_path="delete_eligible/item-1.flac",
        action_type=StagingActionType.MARK_DELETE_ELIGIBLE,
    )
    staging_plan = StagingPlan(plan_id="sp-1", items=[item])

    result = service.plan_from_staging(staging_plan, config)

    assert result.status == Status.SUCCESS
    plan_data = result.summary["file_operation_plan"]
    ops = plan_data["operations"]
    assert len(ops) == 1
    assert ops[0]["operation_type"] == "mark"


def test_staging_review_does_not_generate_destruction(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)

    item = StagingItem(
        item_id="item-1",
        routing_outcome="review",
        source_relative_path="incoming/item-1.flac",
        target_area=StagingArea.REVIEW,
        target_relative_path="review/item-1.flac",
        action_type=StagingActionType.PLAN_ONLY,
    )
    staging_plan = StagingPlan(plan_id="sp-1", items=[item])

    result = service.plan_from_staging(staging_plan, config)

    assert result.status in (Status.SUCCESS, Status.WARNING)
    plan_data = result.summary["file_operation_plan"]
    ops = plan_data["operations"]
    assert len(ops) == 1
    assert ops[0]["operation_type"] == "none"


def test_service_does_not_access_network() -> None:
    from noqlen_flux.services import fileops as fileops_module

    source = inspect.getsource(fileops_module)
    assert "requests" not in source
    assert "urllib" not in source
    assert "socket" not in source


def test_service_does_not_depend_on_slskd() -> None:
    from noqlen_flux.services import fileops as fileops_module

    assert "slskd" not in fileops_module.__file__
    for name in dir(fileops_module):
        obj = getattr(fileops_module, name, None)
        if hasattr(obj, "__module__"):
            assert "slskd" not in (getattr(obj, "__module__", "") or "")


def test_service_does_not_use_print_or_input() -> None:
    from noqlen_flux.services import fileops as fileops_module

    source = inspect.getsource(fileops_module)
    assert "print(" not in source
    assert "input(" not in source


def test_service_does_not_delete_files(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    test_file = tmp_path / "incoming" / "file.txt"
    test_file.write_text("test")

    plan = _plan([_mkdir_op(target="approved")])
    service.execute_plan(plan, config, dry_run=False)

    assert test_file.exists()


def test_apply_copy_with_overwrite_allowed(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)
    (tmp_path / "incoming").mkdir()
    (tmp_path / "approved").mkdir()
    (tmp_path / "incoming" / "file.txt").write_text("new content")
    (tmp_path / "approved" / "file.txt").write_text("old content")

    policy = FileExecutionPolicy(name="test", version="1", description="test", allow_overwrite=True)
    plan = _plan([_copy_op()])
    result = service.execute_plan(plan, config, dry_run=False, policy=policy)

    assert (tmp_path / "approved" / "file.txt").read_text() == "new content"
    assert result.status == Status.SUCCESS


def test_apply_returns_applied_change_for_real_operation(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)
    plan = _plan([_mkdir_op(target="new-dir")])

    result = service.execute_plan(plan, config, dry_run=False)

    assert len(result.applied_changes) >= 1
    assert result.applied_changes[0].action.startswith("applied-")


def test_staging_move_blocked_if_policy_disallows_move(tmp_path) -> None:
    service = SafeFileOperationService()
    config = _config(tmp_path)

    item = StagingItem(
        item_id="item-1",
        routing_outcome="approved",
        source_relative_path="incoming/item-1.flac",
        target_area=StagingArea.APPROVED,
        target_relative_path="approved/item-1.flac",
        action_type=StagingActionType.MOVE,
    )
    staging_plan = StagingPlan(plan_id="sp-1", items=[item])

    result = service.plan_from_staging(staging_plan, config)

    assert result.status in (Status.SUCCESS, Status.WARNING)
    plan_data = result.summary["file_operation_plan"]
    ops = plan_data["operations"]
    assert len(ops) == 1
    assert ops[0]["operation_type"] == "none"
