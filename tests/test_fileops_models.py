import pytest

from noqlen_flux.fileops import (
    DEFAULT_FILE_EXECUTION_POLICY,
    FileExecutionPolicy,
    FileOperation,
    FileOperationPlan,
    FileOperationResult,
    FileOperationState,
    FileOperationType,
    default_file_execution_policy,
)


def test_file_operation_type_enum_values() -> None:
    assert FileOperationType.COPY.value == "copy"
    assert FileOperationType.MOVE.value == "move"
    assert FileOperationType.MARK.value == "mark"
    assert FileOperationType.MKDIR.value == "mkdir"
    assert FileOperationType.NONE.value == "none"


def test_file_operation_state_enum_values() -> None:
    assert FileOperationState.PLANNED.value == "planned"
    assert FileOperationState.SKIPPED.value == "skipped"
    assert FileOperationState.APPLIED.value == "applied"
    assert FileOperationState.FAILED.value == "failed"
    assert FileOperationState.BLOCKED.value == "blocked"


def test_file_execution_policy_default_blocks_move_delete_overwrite() -> None:
    policy = DEFAULT_FILE_EXECUTION_POLICY

    assert policy.allow_move is False
    assert policy.allow_delete is False
    assert policy.allow_overwrite is False
    assert policy.allow_copy is True
    assert policy.allow_mkdir is True


def test_file_execution_policy_serializes_safely() -> None:
    policy = FileExecutionPolicy(
        name="test_v1",
        version="1",
        description="Test policy",
        metadata={"token": "placeholder-secret"},
    )

    payload = policy.to_dict()

    assert payload["name"] == "test_v1"
    assert payload["metadata"]["token"] == "[redacted]"


def test_file_operation_serializes_correctly() -> None:
    op = FileOperation(
        operation_id="op-1",
        operation_type=FileOperationType.COPY,
        source_relative_path="incoming/file.flac",
        target_relative_path="approved/file.flac",
        reason="Test copy",
    )

    payload = op.to_dict()

    assert payload["operation_id"] == "op-1"
    assert payload["operation_type"] == "copy"
    assert payload["source_relative_path"] == "incoming/file.flac"
    assert payload["target_relative_path"] == "approved/file.flac"
    assert payload["reason"] == "Test copy"


def test_file_operation_serializes_safely() -> None:
    op = FileOperation(
        operation_id="op-1",
        operation_type=FileOperationType.COPY,
        metadata={"token": "placeholder-secret"},
    )

    payload = op.to_dict()

    assert payload["metadata"]["token"] == "[redacted]"


def test_file_operation_plan_serializes_correctly() -> None:
    plan = FileOperationPlan(
        plan_id="plan-1",
        operations=[],
        warnings=["test warning"],
        errors=[],
    )

    payload = plan.to_dict()

    assert payload["plan_id"] == "plan-1"
    assert payload["warnings"] == ["test warning"]
    assert payload["operations"] == []


def test_file_operation_plan_serializes_safely() -> None:
    plan = FileOperationPlan(
        plan_id="plan-1",
        metadata={"token": "placeholder-secret"},
    )

    payload = plan.to_dict()

    assert payload["metadata"]["token"] == "[redacted]"


def test_file_operation_result_planned() -> None:
    result = FileOperationResult(
        operation_id="op-1",
        operation_type=FileOperationType.COPY,
        state=FileOperationState.PLANNED,
        source_relative_path="incoming/file.flac",
        target_relative_path="approved/file.flac",
        message="Would copy file.",
    )

    payload = result.to_dict()

    assert payload["state"] == "planned"
    assert payload["operation_type"] == "copy"
    assert payload["message"] == "Would copy file."


def test_file_operation_result_applied() -> None:
    result = FileOperationResult(
        operation_id="op-1",
        operation_type=FileOperationType.MKDIR,
        state=FileOperationState.APPLIED,
        target_relative_path="approved",
        message="Created directory.",
    )

    payload = result.to_dict()

    assert payload["state"] == "applied"
    assert payload["operation_type"] == "mkdir"


def test_file_operation_result_blocked() -> None:
    result = FileOperationResult(
        operation_id="op-1",
        operation_type=FileOperationType.MOVE,
        state=FileOperationState.BLOCKED,
        message="Move blocked by policy.",
    )

    payload = result.to_dict()

    assert payload["state"] == "blocked"


def test_file_operation_result_failed() -> None:
    result = FileOperationResult(
        operation_id="op-1",
        operation_type=FileOperationType.COPY,
        state=FileOperationState.FAILED,
        errors=["Source not found"],
    )

    payload = result.to_dict()

    assert payload["state"] == "failed"
    assert payload["errors"] == ["Source not found"]


def test_file_operation_result_serializes_safely() -> None:
    result = FileOperationResult(
        operation_id="op-1",
        operation_type=FileOperationType.COPY,
        state=FileOperationState.PLANNED,
        metadata={"token": "placeholder-secret"},
    )

    payload = result.to_dict()

    assert payload["metadata"]["token"] == "[redacted]"


def test_default_file_execution_policy_exists() -> None:
    policy = default_file_execution_policy()

    assert policy.name == "default_v1"
    assert policy.version == "1"
    assert "post-download" in policy.metadata.get("stage", "")
    assert policy.allow_move is False
    assert policy.allow_delete is False
    assert policy.allow_overwrite is False


def test_file_operation_type_is_not_staging_action_type() -> None:
    from noqlen_flux.staging import StagingActionType

    op_values = {o.value for o in FileOperationType}
    staging_values = {s.value for s in StagingActionType}

    assert "plan_only" not in op_values
    assert "mark_delete_eligible" not in op_values


def test_file_operation_state_is_not_routing_outcome() -> None:
    from noqlen_flux.routing import RoutingOutcome

    state_values = {s.value for s in FileOperationState}
    outcome_values = {o.value for o in RoutingOutcome}

    assert "planned" not in outcome_values
    assert "applied" not in outcome_values
    assert "approved" not in state_values
