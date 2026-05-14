from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .results import _clean
from .search import SearchQuery


SafeMetadata = dict[str, Any]


class CandidateRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(slots=True, frozen=True)
class ScoreReason:
    code: str
    message: str
    weight: float
    impact: float
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class ScorePenalty:
    code: str
    message: str
    value: float
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class ScoreComponent:
    name: str
    score: float
    max_score: float
    reasons: list[ScoreReason] = field(default_factory=list)
    penalties: list[ScorePenalty] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class CandidateScore:
    candidate_id: str
    total: float
    max_score: float
    risk: CandidateRisk
    confidence: float
    components: list[ScoreComponent] = field(default_factory=list)
    reasons: list[ScoreReason] = field(default_factory=list)
    penalties: list[ScorePenalty] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "risk", CandidateRisk(self.risk))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class ScoringProfile:
    name: str
    version: str
    description: str
    weights: dict[str, float] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class ScoringResult:
    query: SearchQuery
    provider: str
    scores: list[CandidateScore] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    profile: ScoringProfile = field(default_factory=lambda: DEFAULT_SCORING_PROFILE)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


DEFAULT_SCORING_PROFILE = ScoringProfile(
    name="default_v1",
    version="1",
    description="Initial explainable pre-download candidate risk scoring profile.",
    weights={
        "textual_match": 40.0,
        "artist_match": 20.0,
        "title_or_album_match": 20.0,
        "folder_consistency": 10.0,
        "declared_quality": 5.0,
        "availability": 5.0,
        "risk_penalties": 0.0,
    },
    thresholds={"medium_risk_penalty": 15.0, "high_risk_penalty": 35.0, "minimum_confidence": 0.1},
    metadata={"stage": "pre-download"},
)


def default_scoring_profile() -> ScoringProfile:
    return DEFAULT_SCORING_PROFILE
