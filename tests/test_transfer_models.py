import pytest

from noqlen_flux.results import PlannedChange
from noqlen_flux.transfers import (
    QueueItem,
    QueuePlan,
    QueueState,
    TransferArtifact,
    TransferItem,
    TransferPriority,
    TransferRequest,
    TransferState,
    TransferStatus,
)


def test_transfer_state_values() -> None:
    assert TransferState.PLANNED.value == "planned"
    assert TransferState.QUEUED.value == "queued"
    assert TransferState.WAITING.value == "waiting"
    assert TransferState.RUNNING.value == "running"
    assert TransferState.PAUSED.value == "paused"
    assert TransferState.COMPLETED.value == "completed"
    assert TransferState.FAILED.value == "failed"
    assert TransferState.CANCELLED.value == "cancelled"
    assert TransferState.UNKNOWN.value == "unknown"


def test_queue_state_values() -> None:
    assert QueueState.EMPTY.value == "empty"
    assert QueueState.READY.value == "ready"
    assert QueueState.BLOCKED.value == "blocked"
    assert QueueState.ACTIVE.value == "active"
    assert QueueState.COMPLETED.value == "completed"
    assert QueueState.FAILED.value == "failed"


def test_transfer_priority_values() -> None:
    assert TransferPriority.LOW.value == "low"
    assert TransferPriority.NORMAL.value == "normal"
    assert TransferPriority.HIGH.value == "high"


def test_transfer_priority_default_normal() -> None:
    item = TransferItem(
        item_id="item-1",
        plan_id="plan-1",
        candidate_id="candidate-1",
        filename="Track.flac",
        target_relative_path="candidate-1/Track.flac",
    )
    assert item.priority == TransferPriority.NORMAL


def test_transfer_item_valid() -> None:
    item = TransferItem(
        item_id="item-1",
        plan_id="plan-1",
        candidate_id="candidate-1",
        filename="Track.flac",
        target_relative_path="candidate-1/Track.flac",
        size_bytes=12345678,
        priority=TransferPriority.HIGH,
        locked=False,
    )

    assert item.item_id == "item-1"
    assert item.plan_id == "plan-1"
    assert item.candidate_id == "candidate-1"
    assert item.filename == "Track.flac"
    assert item.size_bytes == 12345678
    assert item.priority == TransferPriority.HIGH
    assert item.locked is False


def test_transfer_item_requires_item_id() -> None:
    with pytest.raises(ValueError):
        TransferItem(
            item_id="",
            plan_id="plan-1",
            candidate_id="candidate-1",
            filename="Track.flac",
            target_relative_path="candidate-1/Track.flac",
        )


def test_transfer_item_requires_plan_id() -> None:
    with pytest.raises(ValueError):
        TransferItem(
            item_id="item-1",
            plan_id="",
            candidate_id="candidate-1",
            filename="Track.flac",
            target_relative_path="candidate-1/Track.flac",
        )


def test_transfer_item_requires_candidate_id() -> None:
    with pytest.raises(ValueError):
        TransferItem(
            item_id="item-1",
            plan_id="plan-1",
            candidate_id="",
            filename="Track.flac",
            target_relative_path="candidate-1/Track.flac",
        )


def test_transfer_item_requires_filename() -> None:
    with pytest.raises(ValueError):
        TransferItem(
            item_id="item-1",
            plan_id="plan-1",
            candidate_id="candidate-1",
            filename="",
            target_relative_path="candidate-1/Track.flac",
        )


def test_transfer_item_requires_target_relative_path() -> None:
    with pytest.raises(ValueError):
        TransferItem(
            item_id="item-1",
            plan_id="plan-1",
            candidate_id="candidate-1",
            filename="Track.flac",
            target_relative_path="",
        )


def test_transfer_item_blocks_path_traversal() -> None:
    with pytest.raises(ValueError):
        TransferItem(
            item_id="item-1",
            plan_id="plan-1",
            candidate_id="candidate-1",
            filename="Track.flac",
            target_relative_path="../escape/Track.flac",
        )


def test_transfer_item_blocks_absolute_path() -> None:
    with pytest.raises(ValueError):
        TransferItem(
            item_id="item-1",
            plan_id="plan-1",
            candidate_id="candidate-1",
            filename="Track.flac",
            target_relative_path="/etc/passwd",
        )


def test_transfer_item_blocks_dot_segments() -> None:
    with pytest.raises(ValueError):
        TransferItem(
            item_id="item-1",
            plan_id="plan-1",
            candidate_id="candidate-1",
            filename="Track.flac",
            target_relative_path="candidate-1/./Track.flac",
        )


def test_transfer_item_serializes_safely() -> None:
    item = TransferItem(
        item_id="item-1",
        plan_id="plan-1",
        candidate_id="candidate-1",
        filename="Track.flac",
        target_relative_path="candidate-1/Track.flac",
        metadata={"token": "placeholder-secret"},
    )

    payload = item.to_dict()

    assert payload["item_id"] == "item-1"
    assert payload["metadata"]["token"] == "[redacted]"
    assert payload["priority"] == "normal"


def test_transfer_request_valid() -> None:
    request = TransferRequest(
        request_id="req-1",
        plan_id="plan-1",
        candidate_id="candidate-1",
        priority=TransferPriority.HIGH,
    )

    assert request.request_id == "req-1"
    assert request.plan_id == "plan-1"
    assert request.candidate_id == "candidate-1"
    assert request.priority == TransferPriority.HIGH


def test_transfer_request_requires_request_id() -> None:
    with pytest.raises(ValueError):
        TransferRequest(
            request_id="",
            plan_id="plan-1",
            candidate_id="candidate-1",
        )


def test_transfer_request_serializes_safely() -> None:
    request = TransferRequest(
        request_id="req-1",
        plan_id="plan-1",
        candidate_id="candidate-1",
        metadata={"token": "request-secret"},
    )

    payload = request.to_dict()
    assert payload["metadata"]["token"] == "[redacted]"


def test_queue_item_valid() -> None:
    transfer_item = TransferItem(
        item_id="item-1",
        plan_id="plan-1",
        candidate_id="candidate-1",
        filename="Track.flac",
        target_relative_path="candidate-1/Track.flac",
    )

    queue_item = QueueItem(
        queue_item_id="qi-1",
        transfer_item=transfer_item,
        state=TransferState.PLANNED,
        priority=TransferPriority.NORMAL,
    )

    assert queue_item.queue_item_id == "qi-1"
    assert queue_item.state == TransferState.PLANNED
    assert queue_item.priority == TransferPriority.NORMAL
    assert queue_item.warnings == []
    assert queue_item.errors == []


def test_queue_item_requires_queue_item_id() -> None:
    transfer_item = TransferItem(
        item_id="item-1",
        plan_id="plan-1",
        candidate_id="candidate-1",
        filename="Track.flac",
        target_relative_path="candidate-1/Track.flac",
    )

    with pytest.raises(ValueError):
        QueueItem(
            queue_item_id="",
            transfer_item=transfer_item,
        )


def test_queue_item_serializes_safely() -> None:
    transfer_item = TransferItem(
        item_id="item-1",
        plan_id="plan-1",
        candidate_id="candidate-1",
        filename="Track.flac",
        target_relative_path="candidate-1/Track.flac",
    )

    queue_item = QueueItem(
        queue_item_id="qi-1",
        transfer_item=transfer_item,
        metadata={"token": "queue-secret"},
    )

    payload = queue_item.to_dict()
    assert payload["metadata"]["token"] == "[redacted]"
    assert payload["state"] == "planned"
    assert payload["priority"] == "normal"


def test_queue_plan_valid() -> None:
    transfer_item = TransferItem(
        item_id="item-1",
        plan_id="plan-1",
        candidate_id="candidate-1",
        filename="Track.flac",
        target_relative_path="candidate-1/Track.flac",
    )

    queue_item = QueueItem(
        queue_item_id="qi-1",
        transfer_item=transfer_item,
    )

    plan = QueuePlan(
        queue_id="queue-1",
        request_id="req-1",
        state=QueueState.READY,
        items=[queue_item],
    )

    assert plan.queue_id == "queue-1"
    assert plan.request_id == "req-1"
    assert plan.state == QueueState.READY
    assert len(plan.items) == 1
    assert plan.blocked is False
    assert plan.block_reasons == []


def test_queue_plan_blocked() -> None:
    plan = QueuePlan(
        queue_id="queue-1",
        request_id="req-1",
        state=QueueState.BLOCKED,
        items=[],
        blocked=True,
        block_reasons=["download plan has no items"],
    )

    assert plan.blocked is True
    assert len(plan.block_reasons) == 1
    assert plan.state == QueueState.BLOCKED


def test_queue_plan_serializes_safely() -> None:
    plan = QueuePlan(
        queue_id="queue-1",
        request_id="req-1",
        metadata={"token": "plan-secret"},
    )

    payload = plan.to_dict()
    assert payload["metadata"]["token"] == "[redacted]"
    assert payload["state"] == "ready"


def test_transfer_status_valid() -> None:
    status = TransferStatus(
        transfer_id="transfer-1",
        queue_item_id="qi-1",
        state=TransferState.RUNNING,
        progress_percent=50.0,
        bytes_transferred=5000,
        total_bytes=10000,
    )

    assert status.transfer_id == "transfer-1"
    assert status.queue_item_id == "qi-1"
    assert status.state == TransferState.RUNNING
    assert status.progress_percent == 50.0


def test_transfer_status_requires_transfer_id() -> None:
    with pytest.raises(ValueError):
        TransferStatus(
            transfer_id="",
            queue_item_id="qi-1",
        )


def test_transfer_status_requires_queue_item_id() -> None:
    with pytest.raises(ValueError):
        TransferStatus(
            transfer_id="transfer-1",
            queue_item_id="",
        )


def test_transfer_status_validates_progress_percent() -> None:
    with pytest.raises(ValueError):
        TransferStatus(
            transfer_id="transfer-1",
            queue_item_id="qi-1",
            progress_percent=-1.0,
        )

    with pytest.raises(ValueError):
        TransferStatus(
            transfer_id="transfer-1",
            queue_item_id="qi-1",
            progress_percent=101.0,
        )


def test_transfer_status_serializes_safely() -> None:
    status = TransferStatus(
        transfer_id="transfer-1",
        queue_item_id="qi-1",
        state=TransferState.COMPLETED,
        metadata={"token": "status-secret"},
    )

    payload = status.to_dict()
    assert payload["metadata"]["token"] == "[redacted]"
    assert payload["state"] == "completed"


def test_transfer_artifact_valid() -> None:
    artifact = TransferArtifact(
        artifact_id="artifact-1",
        kind="transfer-plan",
        relative_path="plans/plan-1.json",
        description="Logical transfer plan",
    )

    assert artifact.artifact_id == "artifact-1"
    assert artifact.kind == "transfer-plan"
    assert artifact.relative_path == "plans/plan-1.json"


def test_transfer_artifact_does_not_require_absolute_path() -> None:
    artifact = TransferArtifact(
        artifact_id="artifact-1",
        kind="transfer-plan",
        description="Logical transfer plan without path",
    )

    assert artifact.relative_path is None


def test_transfer_artifact_serializes_safely() -> None:
    artifact = TransferArtifact(
        artifact_id="artifact-1",
        kind="transfer-plan",
        metadata={"token": "artifact-secret"},
    )

    payload = artifact.to_dict()
    assert payload["metadata"]["token"] == "[redacted]"


def test_transfer_artifact_requires_artifact_id() -> None:
    with pytest.raises(ValueError):
        TransferArtifact(
            artifact_id="",
            kind="transfer-plan",
        )


def test_transfer_artifact_requires_kind() -> None:
    with pytest.raises(ValueError):
        TransferArtifact(
            artifact_id="artifact-1",
            kind="",
        )
