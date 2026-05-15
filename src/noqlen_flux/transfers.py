from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .results import _clean

SafeMetadata = dict[str, Any]


class TransferState(StrEnum):
    PLANNED = "planned"
    QUEUED = "queued"
    WAITING = "waiting"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class QueueState(StrEnum):
    EMPTY = "empty"
    READY = "ready"
    BLOCKED = "blocked"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class TransferPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class TransferExecutionMode(StrEnum):
    DRY_RUN = "dry-run"
    APPLY = "apply"


class TransferSubmissionState(StrEnum):
    PLANNED = "planned"
    SUBMITTED = "submitted"
    SUCCESS = "success"
    BLOCKED = "blocked"
    PROVIDER_ERROR = "provider-error"
    LOCKED_ITEM = "locked-item"
    DUPLICATE = "duplicate"
    UNAVAILABLE = "unavailable"


@dataclass(slots=True, frozen=True)
class TransferItem:
    item_id: str
    plan_id: str
    candidate_id: str
    filename: str
    target_relative_path: str
    size_bytes: int | None = None
    priority: TransferPriority = TransferPriority.NORMAL
    locked: bool = False
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.item_id.strip():
            raise ValueError("item_id is required")
        if not self.plan_id.strip():
            raise ValueError("plan_id is required")
        if not self.candidate_id.strip():
            raise ValueError("candidate_id is required")
        if not self.filename.strip():
            raise ValueError("filename is required")
        if not self.target_relative_path.strip():
            raise ValueError("target_relative_path is required")
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("size_bytes cannot be negative")
        self._validate_target_path()

    def _validate_target_path(self) -> None:
        normalized = self.target_relative_path.replace("\\", "/")
        parts = normalized.split("/")
        for part in parts:
            if part in ("", ".", ".."):
                raise ValueError(
                    f"target_relative_path contains unsafe segment: {part!r}"
                )
        if normalized.startswith("/") or normalized.startswith(".."):
            raise ValueError("target_relative_path must be a safe relative path")

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class TransferRequest:
    request_id: str
    plan_id: str
    candidate_id: str
    priority: TransferPriority = TransferPriority.NORMAL
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("request_id is required")
        if not self.plan_id.strip():
            raise ValueError("plan_id is required")
        if not self.candidate_id.strip():
            raise ValueError("candidate_id is required")

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class QueueItem:
    queue_item_id: str
    transfer_item: TransferItem
    state: TransferState = TransferState.PLANNED
    priority: TransferPriority = TransferPriority.NORMAL
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.queue_item_id.strip():
            raise ValueError("queue_item_id is required")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        data["priority"] = self.priority.value
        data["transfer_item"] = self.transfer_item.to_dict()
        return _clean(data)


@dataclass(slots=True, frozen=True)
class QueuePlan:
    queue_id: str
    request_id: str
    state: QueueState = QueueState.READY
    items: list[QueueItem] = field(default_factory=list)
    blocked: bool = False
    block_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.queue_id.strip():
            raise ValueError("queue_id is required")
        if not self.request_id.strip():
            raise ValueError("request_id is required")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        data["items"] = [item.to_dict() for item in self.items]
        return _clean(data)


@dataclass(slots=True, frozen=True)
class TransferStatus:
    transfer_id: str
    queue_item_id: str
    state: TransferState = TransferState.UNKNOWN
    progress_percent: float | None = None
    bytes_transferred: int | None = None
    total_bytes: int | None = None
    speed_bytes_per_second: float | None = None
    eta_seconds: float | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.transfer_id.strip():
            raise ValueError("transfer_id is required")
        if not self.queue_item_id.strip():
            raise ValueError("queue_item_id is required")
        if self.progress_percent is not None and (
            self.progress_percent < 0.0 or self.progress_percent > 100.0
        ):
            raise ValueError("progress_percent must be between 0 and 100")
        if self.bytes_transferred is not None and self.bytes_transferred < 0:
            raise ValueError("bytes_transferred cannot be negative")
        if self.total_bytes is not None and self.total_bytes < 0:
            raise ValueError("total_bytes cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        return _clean(data)


@dataclass(slots=True, frozen=True)
class TransferArtifact:
    artifact_id: str
    kind: str
    relative_path: str | None = None
    description: str = ""
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.artifact_id.strip():
            raise ValueError("artifact_id is required")
        if not self.kind.strip():
            raise ValueError("kind is required")

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class TransferExecutionPolicy:
    allow_provider_queue: bool = False
    allow_locked: bool = False
    max_items: int | None = None
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_items is not None and self.max_items < 1:
            raise ValueError("max_items must be >= 1")

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class TransferExecutionRequest:
    request_id: str
    queue_plan: QueuePlan
    policy: TransferExecutionPolicy
    mode: TransferExecutionMode = TransferExecutionMode.DRY_RUN
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("request_id is required")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mode"] = self.mode.value
        data["queue_plan"] = self.queue_plan.to_dict()
        data["policy"] = self.policy.to_dict()
        return _clean(data)


@dataclass(slots=True, frozen=True)
class TransferSubmissionItem:
    queue_item_id: str
    state: TransferSubmissionState
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.queue_item_id.strip():
            raise ValueError("queue_item_id is required")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        return _clean(data)


@dataclass(slots=True, frozen=True)
class TransferSubmissionResult:
    submission_id: str
    request_id: str
    state: TransferSubmissionState
    items: list[TransferSubmissionItem] = field(default_factory=list)
    blocked: bool = False
    block_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.submission_id.strip():
            raise ValueError("submission_id is required")
        if not self.request_id.strip():
            raise ValueError("request_id is required")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        data["items"] = [item.to_dict() for item in self.items]
        return _clean(data)
