from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .results import _clean

SafeMetadata = dict[str, Any]


class QualityGrade(StrEnum):
    EXCELLENT = "excellent"
    MEDIUM = "medium"
    BAD = "bad"
    UNKNOWN = "unknown"


class QualityFindingSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class QualityFindingKind(StrEnum):
    OBJECTIVE_FAILURE = "objective_failure"
    HEURISTIC_WARNING = "heuristic_warning"
    DIAGNOSTIC = "diagnostic"
    METADATA_SIGNAL = "metadata_signal"
    UNKNOWN = "unknown"


@dataclass(slots=True, frozen=True)
class QualityFinding:
    code: str
    message: str
    kind: QualityFindingKind
    severity: QualityFindingSeverity
    confidence: float | None = None
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", QualityFindingKind(self.kind))
        object.__setattr__(self, "severity", QualityFindingSeverity(self.severity))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class QualityProfile:
    name: str
    version: str
    description: str
    thresholds: dict[str, float] = field(default_factory=dict)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class QualityResult:
    item_id: str
    grade: QualityGrade
    relative_path: str | None = None
    findings: list[QualityFinding] = field(default_factory=list)
    objective_failures: list[QualityFinding] = field(default_factory=list)
    heuristic_warnings: list[QualityFinding] = field(default_factory=list)
    diagnostics: list[QualityFinding] = field(default_factory=list)
    confidence: float = 0.0
    profile: QualityProfile = field(default_factory=lambda: DEFAULT_QUALITY_PROFILE)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "grade", QualityGrade(self.grade))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class QualitySummary:
    total_items: int = 0
    excellent_count: int = 0
    medium_count: int = 0
    bad_count: int = 0
    unknown_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


DEFAULT_QUALITY_PROFILE = QualityProfile(
    name="default_v1",
    version="1",
    description="Initial post-download quality analysis profile. Thresholds will be calibrated by MusicLab.",
    thresholds={
        "excellent_min_confidence": 0.8,
        "medium_min_confidence": 0.4,
        "bad_max_confidence": 0.4,
    },
    metadata={"stage": "post-download", "status": "contracts-only"},
)


def default_quality_profile() -> QualityProfile:
    return DEFAULT_QUALITY_PROFILE
