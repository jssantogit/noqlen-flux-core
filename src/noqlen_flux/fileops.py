from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .results import _clean

SafeMetadata = dict[str, Any]


class FileOperationType(StrEnum):
    COPY = "copy"
    MOVE = "move"
    MARK = "mark"
    MKDIR = "mkdir"
    NONE = "none"


class FileOperationState(StrEnum):
    PLANNED = "planned"
    SKIPPED = "skipped"
    APPLIED = "applied"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass(slots=True, frozen=True)
class FileOperation:
    operation_id: str
    operation_type: FileOperationType
    source_relative_path: str | None = None
    target_relative_path: str | None = None
    reason: str = ""
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_type", FileOperationType(self.operation_type))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class FileOperationPlan:
    plan_id: str
    operations: list[FileOperation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class FileOperationResult:
    operation_id: str
    operation_type: FileOperationType
    state: FileOperationState
    source_relative_path: str | None = None
    target_relative_path: str | None = None
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_type", FileOperationType(self.operation_type))
        object.__setattr__(self, "state", FileOperationState(self.state))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class FileExecutionPolicy:
    name: str
    version: str
    description: str
    allow_move: bool = False
    allow_copy: bool = True
    allow_mkdir: bool = True
    allow_delete: bool = False
    allow_overwrite: bool = False
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


DEFAULT_FILE_EXECUTION_POLICY = FileExecutionPolicy(
    name="default_v1",
    version="1",
    description="Initial file execution policy. No delete, no move, no overwrite. Copy and mkdir are allowed within workspace boundary.",
    allow_move=False,
    allow_copy=True,
    allow_mkdir=True,
    allow_delete=False,
    allow_overwrite=False,
    metadata={"stage": "post-download", "status": "contracts-only"},
)


def default_file_execution_policy() -> FileExecutionPolicy:
    return DEFAULT_FILE_EXECUTION_POLICY
