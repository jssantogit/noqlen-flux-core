from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .results import _clean

SafeMetadata = dict[str, Any]


@dataclass(slots=True, frozen=True)
class QualityCalibrationExpectation:
    expected_grade: str | None = None
    expected_min_confidence: float | None = None
    expected_finding_codes: list[str] = field(default_factory=list)
    expected_objective_failure_codes: list[str] = field(default_factory=list)
    expected_heuristic_warning_codes: list[str] = field(default_factory=list)
    expected_no_routing_decision: bool = True
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class QualityCalibrationCase:
    case_id: str
    description: str
    item_id: str
    relative_path: str | None = None
    findings: list[dict[str, Any]] = field(default_factory=list)
    expectation: QualityCalibrationExpectation = field(default_factory=QualityCalibrationExpectation)
    tags: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class QualityCalibrationDataset:
    dataset_id: str
    version: str
    description: str
    cases: list[QualityCalibrationCase] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class QualityCalibrationCaseResult:
    case_id: str
    passed: bool
    expected_grade: str | None = None
    actual_grade: str | None = None
    expected_confidence: float | None = None
    actual_confidence: float | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class QualityCalibrationReport:
    dataset_id: str
    profile_name: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    case_results: list[QualityCalibrationCaseResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))
