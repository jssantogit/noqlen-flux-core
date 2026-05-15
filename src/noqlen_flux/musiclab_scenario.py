from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .results import _clean

SafeMetadata = dict[str, Any]


class ScenarioOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


class ScenarioCategory(StrEnum):
    GOOD = "good"
    BAD = "bad"
    SUSPICIOUS = "suspicious"
    FALSE_POSITIVE = "false_positive"
    CLEANUP = "cleanup"
    MVP_E2E = "mvp_e2e"


class ScenarioSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ScenarioKind(StrEnum):
    SINGLE_TRACK = "single_track"
    ALBUM = "album"
    FORMAT_VARIANT = "format_variant"
    CORRUPT = "corrupt"
    TRANSCODE = "transcode"
    UPSAMPLED = "upsampled"
    DOWNSAMPLED = "downsampled"
    FAKE_BIT_DEPTH = "fake_bit_depth"
    FAKE_SAMPLE_RATE = "fake_sample_rate"
    METADATA_VARIANT = "metadata_variant"
    EDGE_CASE = "edge_case"
    HANDOFF_READY = "handoff_ready"
    CLEANUP_CANDIDATE = "cleanup_candidate"
    REJECTED_RETENTION = "rejected_retention"
    QUARANTINE_RETENTION = "quarantine_retention"
    APPROVED_NEVER_CLEANUP = "approved_never_cleanup"
    NO_DESTRUCTIVE_ACTION = "no_destructive_action"


@dataclass(slots=True, frozen=True)
class MusicLabScenarioConfig:
    simulate_artifact: bool = True
    simulate_audio_probe: bool = True
    simulate_transfer: bool = True
    dry_run: bool = True
    run_scoring: bool = True
    run_quality: bool = True
    run_routing: bool = True
    run_staging: bool = True
    run_handoff: bool = True
    run_cleanup: bool = False
    run_e2e: bool = False
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class MusicLabScenario:
    scenario_id: str
    description: str
    category: ScenarioCategory
    kind: ScenarioKind
    severity: ScenarioSeverity = ScenarioSeverity.MEDIUM
    tags: list[str] = field(default_factory=list)
    config: MusicLabScenarioConfig = field(
        default_factory=MusicLabScenarioConfig
    )
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "category", ScenarioCategory(self.category))
        object.__setattr__(self, "kind", ScenarioKind(self.kind))
        object.__setattr__(self, "severity", ScenarioSeverity(self.severity))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class MusicLabScenarioPack:
    pack_id: str
    description: str
    version: str = "1"
    scenarios: list[MusicLabScenario] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class MusicLabScenarioStepResult:
    step_name: str
    status: str
    message: str = ""
    expected_value: str | None = None
    actual_value: str | None = None
    matched: bool = True
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class MusicLabScenarioResult:
    scenario_id: str
    outcome: ScenarioOutcome
    expected_grade: str | None = None
    actual_grade: str | None = None
    expected_routing_outcome: str | None = None
    actual_routing_outcome: str | None = None
    expected_staging_area: str | None = None
    actual_staging_area: str | None = None
    objective_failure_codes: list[str] = field(default_factory=list)
    heuristic_warning_codes: list[str] = field(default_factory=list)
    destructive_action_detected: bool = False
    steps: list[MusicLabScenarioStepResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    regression_notes: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "outcome", ScenarioOutcome(self.outcome)
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class MusicLabScenarioReport:
    report_id: str
    pack_id: str
    total_scenarios: int
    passed: int
    failed: int
    skipped: int
    errored: int
    scenario_results: list[MusicLabScenarioResult] = field(default_factory=list)
    critical_failures: list[str] = field(default_factory=list)
    regression_flags: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))
