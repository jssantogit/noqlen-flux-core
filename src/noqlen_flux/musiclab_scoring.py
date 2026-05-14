from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from noqlen_flux.results import _clean
from noqlen_flux.scoring import CandidateRisk
from noqlen_flux.search import SearchCandidate, SearchQuery


SafeMetadata = dict[str, Any]


@dataclass(slots=True, frozen=True)
class ScoringCalibrationExpectation:
    expected_min_score: float | None = None
    expected_max_score: float | None = None
    expected_risk: CandidateRisk | None = None
    expected_higher_than: float | None = None
    expected_lower_than: float | None = None
    expected_warning_codes: list[str] = field(default_factory=list)
    expected_penalty_codes: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.expected_risk is not None:
            object.__setattr__(self, "expected_risk", CandidateRisk(self.expected_risk))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class ScoringCalibrationCase:
    case_id: str
    description: str
    query: SearchQuery
    candidate: SearchCandidate
    expectation: ScoringCalibrationExpectation
    tags: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id is required")

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class ScoringCalibrationDataset:
    dataset_id: str
    version: str
    description: str
    cases: list[ScoringCalibrationCase] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.dataset_id.strip():
            raise ValueError("dataset_id is required")
        if not self.version.strip():
            raise ValueError("version is required")

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class ScoringCalibrationCaseResult:
    case_id: str
    passed: bool
    score: float
    expected_risk: str | None
    actual_risk: str
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class ScoringCalibrationReport:
    dataset_id: str
    profile_name: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    case_results: list[ScoringCalibrationCaseResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))
