from noqlen_flux.scoring import (
    CandidateRisk,
    CandidateScore,
    ScoreComponent,
    ScorePenalty,
    ScoreReason,
    default_scoring_profile,
)


def test_candidate_risk_serializes_as_flux_value() -> None:
    assert CandidateRisk.LOW.value == "low"
    assert CandidateRisk.MEDIUM.value == "medium"
    assert CandidateRisk.HIGH.value == "high"


def test_candidate_score_serializes_components_reasons_and_penalties() -> None:
    reason = ScoreReason("exact", "Exact match.", 10.0, 10.0, metadata={"token": "placeholder-secret"})
    penalty = ScorePenalty("locked", "Locked file.", 5.0)
    component = ScoreComponent("availability", 5.0, 10.0, reasons=[reason], penalties=[penalty])
    score = CandidateScore(
        candidate_id="candidate-1",
        total=5.0,
        max_score=10.0,
        risk=CandidateRisk.MEDIUM,
        confidence=0.5,
        components=[component],
        reasons=[reason],
        penalties=[penalty],
    )

    payload = score.to_dict()

    assert payload["risk"] == "medium"
    assert payload["components"][0]["name"] == "availability"
    assert payload["reasons"][0]["metadata"]["token"] == "[redacted]"
    assert payload["penalties"][0]["code"] == "locked"


def test_default_scoring_profile_exists() -> None:
    profile = default_scoring_profile()

    assert profile.name == "default_v1"
    assert profile.weights["textual_match"] > 0
    assert profile.thresholds["high_risk_penalty"] > profile.thresholds["medium_risk_penalty"]


def test_score_reason_and_penalty_do_not_require_real_paths() -> None:
    reason = ScoreReason("safe", "Safe reason.", 1.0, 1.0)
    penalty = ScorePenalty("safe-penalty", "Safe penalty.", 1.0)

    assert reason.to_dict()["metadata"] == {}
    assert penalty.to_dict()["metadata"] == {}
