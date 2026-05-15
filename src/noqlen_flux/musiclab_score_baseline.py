from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .results import _clean

SafeMetadata = dict[str, Any]


class ScoreBaselineRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(slots=True, frozen=True)
class MusicLabScoreTolerance:
    score_absolute: float = 5.0
    score_relative_pct: float = 10.0
    risk_must_match: bool = True
    confidence_range: tuple[float, float] = (0.0, 1.0)
    allow_extra_warnings: bool = False
    allow_extra_penalties: bool = False
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class MusicLabScoreExpectation:
    expected_min_score: float
    expected_max_score: float | None = None
    expected_risk: ScoreBaselineRisk | None = None
    expected_confidence_min: float | None = None
    expected_confidence_max: float | None = None
    expected_reason_codes: list[str] = field(default_factory=list)
    expected_penalty_codes: list[str] = field(default_factory=list)
    expected_warning_codes: list[str] = field(default_factory=list)
    forbidden_reason_codes: list[str] = field(default_factory=list)
    forbidden_penalty_codes: list[str] = field(default_factory=list)
    forbidden_warning_codes: list[str] = field(default_factory=list)
    description: str = ""
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.expected_risk is not None:
            object.__setattr__(self, "expected_risk", ScoreBaselineRisk(self.expected_risk))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class MusicLabScoreBaseline:
    baseline_id: str
    category: str
    description: str
    expectation: MusicLabScoreExpectation
    tolerance: MusicLabScoreTolerance = field(default_factory=MusicLabScoreTolerance)
    profile_version: str = "1"
    priority: str = "medium"
    tags: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class MusicLabScoreBaselineResult:
    baseline_id: str
    passed: bool
    actual_score: float
    actual_max_score: float
    actual_risk: str
    actual_confidence: float
    expected_min_score: float
    expected_max_score: float | None
    expected_risk: str | None
    score_drift: float = 0.0
    risk_matched: bool = False
    confidence_in_range: bool = False
    missing_expected_reasons: list[str] = field(default_factory=list)
    missing_expected_penalties: list[str] = field(default_factory=list)
    missing_expected_warnings: list[str] = field(default_factory=list)
    unexpected_reasons: list[str] = field(default_factory=list)
    unexpected_penalties: list[str] = field(default_factory=list)
    unexpected_warnings: list[str] = field(default_factory=list)
    forbidden_detected: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class MusicLabScoreBaselinePack:
    pack_id: str
    description: str
    version: str = "1"
    baselines: list[MusicLabScoreBaseline] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class MusicLabScoreCalibrationReport:
    report_id: str
    pack_id: str
    total_baselines: int
    passed: int
    failed: int
    score_drift_avg: float = 0.0
    score_drift_max: float = 0.0
    risk_mismatch_count: int = 0
    confidence_out_of_range_count: int = 0
    missing_expected_reasons_count: int = 0
    unexpected_penalties_count: int = 0
    forbidden_detected_count: int = 0
    threshold_pressure_notes: list[str] = field(default_factory=list)
    suggested_review_notes: list[str] = field(default_factory=list)
    baseline_results: list[MusicLabScoreBaselineResult] = field(default_factory=list)
    calibration_profile_version: str = "1"
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


DEFAULT_SCORE_TOLERANCE = MusicLabScoreTolerance(
    score_absolute=5.0,
    score_relative_pct=10.0,
    risk_must_match=True,
    confidence_range=(0.0, 1.0),
    allow_extra_warnings=False,
    allow_extra_penalties=False,
)
