from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any


class Status(StrEnum):
    SUCCESS = "success"
    WARNING = "warning"
    FAILED = "failed"
    SKIPPED = "skipped"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


SafeContext = dict[str, Any]


@dataclass(slots=True, frozen=True)
class FluxWarning:
    code: str
    message: str
    severity: Severity = Severity.WARNING
    context: SafeContext = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class FluxError:
    code: str
    message: str
    context: SafeContext = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class Artifact:
    kind: str
    description: str
    path: str | Path | None = None
    metadata: SafeContext = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class StepResult:
    name: str
    status: Status
    message: str = ""
    warnings: list[FluxWarning] = field(default_factory=list)
    errors: list[FluxError] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class PlannedChange:
    action: str
    target: str
    reason: str
    metadata: SafeContext = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class AppliedChange:
    action: str
    target: str
    result: str
    metadata: SafeContext = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class FluxResult:
    operation: str
    status: Status
    steps: list[StepResult] = field(default_factory=list)
    warnings: list[FluxWarning] = field(default_factory=list)
    errors: list[FluxError] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    planned_changes: list[PlannedChange] = field(default_factory=list)
    applied_changes: list[AppliedChange] = field(default_factory=list)
    summary: SafeContext = field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.started_at is None:
            self.started_at = datetime.now(timezone.utc)

    def finish(self, status: Status | None = None) -> FluxResult:
        if status is not None:
            self.status = status
        self.finished_at = datetime.now(timezone.utc)
        return self

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


_SENSITIVE_KEYS = (
    "authorization",
    "cookie",
    "fingerprint",
    "headers",
    "key",
    "lyrics",
    "password",
    "payload",
    "private",
    "secret",
    "set-cookie",
    "token",
)


def _clean(value: Any, *, key: str = "") -> Any:
    if _is_sensitive_key(key):
        return "[redacted]"
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return _clean(asdict(value), key=key)
    if isinstance(value, dict):
        return {str(item_key): _clean(item_value, key=str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item, key=key) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("_", "-")
    return any(part in normalized for part in _SENSITIVE_KEYS)
