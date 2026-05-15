import pytest

from noqlen_flux.transfers import (
    QueueItem,
    QueuePlan,
    QueueState,
    TransferExecutionMode,
    TransferExecutionPolicy,
    TransferExecutionRequest,
    TransferItem,
    TransferPriority,
    TransferState,
    TransferSubmissionItem,
    TransferSubmissionResult,
    TransferSubmissionState,
)


def test_execution_mode_values() -> None:
    assert TransferExecutionMode.DRY_RUN.value == "dry-run"
    assert TransferExecutionMode.APPLY.value == "apply"


def test_submission_state_values() -> None:
    assert TransferSubmissionState.PLANNED.value == "planned"
    assert TransferSubmissionState.SUBMITTED.value == "submitted"
    assert TransferSubmissionState.SUCCESS.value == "success"
    assert TransferSubmissionState.BLOCKED.value == "blocked"
    assert TransferSubmissionState.PROVIDER_ERROR.value == "provider-error"
    assert TransferSubmissionState.LOCKED_ITEM.value == "locked-item"
    assert TransferSubmissionState.DUPLICATE.value == "duplicate"
    assert TransferSubmissionState.UNAVAILABLE.value == "unavailable"


def test_execution_policy_default() -> None:
    policy = TransferExecutionPolicy()
    assert policy.allow_provider_queue is False
    assert policy.allow_locked is False
    assert policy.max_items is None


def test_execution_policy_custom() -> None:
    policy = TransferExecutionPolicy(
        allow_provider_queue=True,
        allow_locked=True,
        max_items=5,
    )
    assert policy.allow_provider_queue is True
    assert policy.allow_locked is True
    assert policy.max_items == 5


def test_execution_policy_rejects_zero_max_items() -> None:
    with pytest.raises(ValueError):
        TransferExecutionPolicy(max_items=0)

    with pytest.raises(ValueError):
        TransferExecutionPolicy(max_items=-1)


def test_execution_policy_serializes_safely() -> None:
    policy = TransferExecutionPolicy(
        allow_provider_queue=True,
        metadata={"token": "policy-secret"},
    )
    payload = policy.to_dict()
    assert payload["allow_provider_queue"] is True
    assert payload["metadata"]["token"] == "[redacted]"


def test_execution_request_valid() -> None:
    queue_plan = QueuePlan(
        queue_id="queue-1",
        request_id="req-1",
        state=QueueState.READY,
    )
    policy = TransferExecutionPolicy(allow_provider_queue=True)
    request = TransferExecutionRequest(
        request_id="exec-1",
        queue_plan=queue_plan,
        policy=policy,
        mode=TransferExecutionMode.DRY_RUN,
    )
    assert request.request_id == "exec-1"
    assert request.mode == TransferExecutionMode.DRY_RUN
    assert request.policy.allow_provider_queue is True


def test_execution_request_requires_request_id() -> None:
    queue_plan = QueuePlan(
        queue_id="queue-1",
        request_id="req-1",
    )
    policy = TransferExecutionPolicy()
    with pytest.raises(ValueError):
        TransferExecutionRequest(
            request_id="",
            queue_plan=queue_plan,
            policy=policy,
        )


def test_execution_request_default_mode_is_dry_run() -> None:
    queue_plan = QueuePlan(
        queue_id="queue-1",
        request_id="req-1",
    )
    policy = TransferExecutionPolicy()
    request = TransferExecutionRequest(
        request_id="exec-1",
        queue_plan=queue_plan,
        policy=policy,
    )
    assert request.mode == TransferExecutionMode.DRY_RUN


def test_execution_request_serializes_safely() -> None:
    queue_plan = QueuePlan(
        queue_id="queue-1",
        request_id="req-1",
    )
    policy = TransferExecutionPolicy()
    request = TransferExecutionRequest(
        request_id="exec-1",
        queue_plan=queue_plan,
        policy=policy,
        metadata={"token": "exec-secret"},
    )
    payload = request.to_dict()
    assert payload["metadata"]["token"] == "[redacted]"
    assert payload["mode"] == "dry-run"


def test_submission_item_valid() -> None:
    item = TransferSubmissionItem(
        queue_item_id="qi-1",
        state=TransferSubmissionState.SUCCESS,
        message="submitted successfully",
    )
    assert item.queue_item_id == "qi-1"
    assert item.state == TransferSubmissionState.SUCCESS
    assert item.message == "submitted successfully"
    assert item.warnings == []
    assert item.errors == []


def test_submission_item_requires_queue_item_id() -> None:
    with pytest.raises(ValueError):
        TransferSubmissionItem(
            queue_item_id="",
            state=TransferSubmissionState.SUCCESS,
        )


def test_submission_item_serializes_safely() -> None:
    item = TransferSubmissionItem(
        queue_item_id="qi-1",
        state=TransferSubmissionState.SUCCESS,
        metadata={"token": "item-secret"},
    )
    payload = item.to_dict()
    assert payload["metadata"]["token"] == "[redacted]"
    assert payload["state"] == "success"


def test_submission_result_valid() -> None:
    result = TransferSubmissionResult(
        submission_id="sub-1",
        request_id="exec-1",
        state=TransferSubmissionState.SUCCESS,
    )
    assert result.submission_id == "sub-1"
    assert result.request_id == "exec-1"
    assert result.state == TransferSubmissionState.SUCCESS
    assert result.blocked is False


def test_submission_result_requires_submission_id() -> None:
    with pytest.raises(ValueError):
        TransferSubmissionResult(
            submission_id="",
            request_id="exec-1",
            state=TransferSubmissionState.SUCCESS,
        )


def test_submission_result_requires_request_id() -> None:
    with pytest.raises(ValueError):
        TransferSubmissionResult(
            submission_id="sub-1",
            request_id="",
            state=TransferSubmissionState.SUCCESS,
        )


def test_submission_result_blocked() -> None:
    result = TransferSubmissionResult(
        submission_id="sub-1",
        request_id="exec-1",
        state=TransferSubmissionState.BLOCKED,
        blocked=True,
        block_reasons=["policy violation"],
    )
    assert result.blocked is True
    assert len(result.block_reasons) == 1


def test_submission_result_serializes_safely() -> None:
    result = TransferSubmissionResult(
        submission_id="sub-1",
        request_id="exec-1",
        state=TransferSubmissionState.SUCCESS,
        metadata={"token": "result-secret"},
    )
    payload = result.to_dict()
    assert payload["metadata"]["token"] == "[redacted]"
    assert payload["state"] == "success"
