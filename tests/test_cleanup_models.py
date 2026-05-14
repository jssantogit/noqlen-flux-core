import pytest

from noqlen_flux.cleanup import (
    DEFAULT_CLEANUP_POLICY,
    CleanupActionType,
    CleanupCandidate,
    CleanupCandidateKind,
    CleanupDecision,
    CleanupPlan,
    CleanupPolicy,
    CleanupRisk,
    build_fake_cleanup_candidates,
    default_cleanup_policy,
    validate_cleanup_relative_path,
)


def test_cleanup_candidate_kind_enum_values() -> None:
    assert CleanupCandidateKind.REJECTED.value == "rejected"
    assert CleanupCandidateKind.DELETE_ELIGIBLE.value == "delete_eligible"
    assert CleanupCandidateKind.TEMPORARY.value == "temporary"
    assert CleanupCandidateKind.ORPHANED.value == "orphaned"
    assert CleanupCandidateKind.STALE_REPORT.value == "stale_report"
    assert CleanupCandidateKind.STALE_MANIFEST.value == "stale_manifest"
    assert CleanupCandidateKind.UNKNOWN.value == "unknown"


def test_cleanup_action_type_enum_values() -> None:
    assert CleanupActionType.KEEP.value == "keep"
    assert CleanupActionType.REVIEW.value == "review"
    assert CleanupActionType.MARK_DELETE_ELIGIBLE.value == "mark_delete_eligible"
    assert CleanupActionType.PLAN_DELETE.value == "plan_delete"
    assert CleanupActionType.NONE.value == "none"


def test_cleanup_risk_enum_values() -> None:
    assert CleanupRisk.LOW.value == "low"
    assert CleanupRisk.MEDIUM.value == "medium"
    assert CleanupRisk.HIGH.value == "high"


def test_cleanup_candidate_serializes_correctly() -> None:
    candidate = CleanupCandidate(
        candidate_id="cand-1",
        kind=CleanupCandidateKind.REJECTED,
        relative_path="rejected/item.txt",
        size_bytes=1024,
        age_days=90,
        source="routing",
        reasons=["Routed to rejected."],
    )

    payload = candidate.to_dict()

    assert payload["candidate_id"] == "cand-1"
    assert payload["kind"] == "rejected"
    assert payload["relative_path"] == "rejected/item.txt"
    assert payload["size_bytes"] == 1024
    assert payload["age_days"] == 90
    assert payload["source"] == "routing"


def test_cleanup_candidate_serializes_safely() -> None:
    candidate = CleanupCandidate(
        candidate_id="cand-1",
        kind=CleanupCandidateKind.REJECTED,
        metadata={"token": "placeholder-secret"},
    )

    payload = candidate.to_dict()

    assert payload["metadata"]["token"] == "[redacted]"


def test_cleanup_policy_is_versioned() -> None:
    policy = CleanupPolicy(
        name="test_v1",
        version="1",
        description="Test policy",
    )

    assert policy.name == "test_v1"
    assert policy.version == "1"
    assert policy.description == "Test policy"
    assert policy.allow_delete_planning is False
    assert policy.auto_delete_enabled is False
    assert policy.delete_only_with_report is True
    assert policy.require_explicit_apply is True


def test_cleanup_policy_serializes_safely() -> None:
    policy = CleanupPolicy(
        name="test_v2",
        version="2",
        description="Test with secret",
        metadata={"secret": "hidden"},
    )

    payload = policy.to_dict()

    assert payload["name"] == "test_v2"
    assert payload["metadata"]["secret"] == "[redacted]"


def test_cleanup_decision_serializes_correctly() -> None:
    decision = CleanupDecision(
        candidate_id="cand-1",
        action_type=CleanupActionType.REVIEW,
        risk=CleanupRisk.MEDIUM,
        reasons=["Requires review."],
    )

    payload = decision.to_dict()

    assert payload["candidate_id"] == "cand-1"
    assert payload["action_type"] == "review"
    assert payload["risk"] == "medium"


def test_cleanup_decision_serializes_safely() -> None:
    decision = CleanupDecision(
        candidate_id="cand-1",
        action_type=CleanupActionType.REVIEW,
        risk=CleanupRisk.MEDIUM,
        metadata={"token": "placeholder-secret"},
    )

    payload = decision.to_dict()

    assert payload["metadata"]["token"] == "[redacted]"


def test_cleanup_plan_contains_planned_change_not_applied_change() -> None:
    plan = CleanupPlan(
        plan_id="plan-1",
        decisions=[],
        planned_changes=[{"action": "plan-review", "target": "cand-1"}],
        total_candidate_count=1,
    )

    payload = plan.to_dict()

    assert "planned_changes" in payload
    assert "applied_changes" not in payload


def test_cleanup_plan_serializes_safely() -> None:
    plan = CleanupPlan(
        plan_id="plan-1",
        metadata={"token": "placeholder-secret"},
    )

    payload = plan.to_dict()

    assert payload["metadata"]["token"] == "[redacted]"


def test_default_cleanup_policy_exists() -> None:
    policy = default_cleanup_policy()

    assert policy.name == "default_v1"
    assert policy.version == "1"
    assert "planning" in policy.metadata.get("stage", "")
    assert policy.allow_delete_planning is False
    assert policy.auto_delete_enabled is False


def test_cleanup_candidate_kind_is_not_quality_grade() -> None:
    from noqlen_flux.quality import QualityGrade

    kind_values = {k.value for k in CleanupCandidateKind}
    grade_values = {g.value for g in QualityGrade}

    assert "excellent" not in kind_values
    assert "medium" not in kind_values
    assert "bad" not in kind_values
    assert "delete_eligible" not in grade_values
    assert "temporary" not in grade_values
    assert "orphaned" not in grade_values


def test_cleanup_candidate_kind_is_not_routing_outcome() -> None:
    from noqlen_flux.routing import RoutingOutcome

    kind_values = {k.value for k in CleanupCandidateKind}
    outcome_values = {o.value for o in RoutingOutcome}

    assert "approved" not in kind_values
    assert "quarantine" not in kind_values
    assert "temporary" not in outcome_values
    assert "orphaned" not in outcome_values
    assert "stale_report" not in outcome_values
    assert "stale_manifest" not in outcome_values


def test_cleanup_candidate_kind_is_not_staging_area() -> None:
    from noqlen_flux.staging import StagingArea

    kind_values = {k.value for k in CleanupCandidateKind}
    area_values = {a.value for a in StagingArea}

    assert "incoming" not in kind_values
    assert "approved" not in kind_values
    assert "quarantine" not in kind_values
    assert "temporary" not in area_values
    assert "orphaned" not in area_values
    assert "stale_report" not in area_values
    assert "stale_manifest" not in area_values


def test_cleanup_risk_is_not_candidate_risk() -> None:
    from noqlen_flux.scoring import CandidateRisk

    risk_values = {r.value for r in CleanupRisk}
    scoring_risk_values = {r.value for r in CandidateRisk}

    assert "safe" not in risk_values
    assert "suspicious" not in risk_values
    assert "weak_match" not in risk_values
    assert "locked" not in risk_values


def test_cleanup_candidate_blocks_absolute_path() -> None:
    with pytest.raises(ValueError, match="Absolute paths"):
        CleanupCandidate(
            candidate_id="cand-1",
            kind=CleanupCandidateKind.REJECTED,
            relative_path="/etc/passwd",
        )


def test_cleanup_candidate_blocks_path_traversal() -> None:
    with pytest.raises(ValueError, match="Path traversal"):
        CleanupCandidate(
            candidate_id="cand-1",
            kind=CleanupCandidateKind.REJECTED,
            relative_path="../escape.txt",
        )


def test_cleanup_candidate_blocks_tilde_traversal() -> None:
    with pytest.raises(ValueError, match="Path traversal"):
        CleanupCandidate(
            candidate_id="cand-1",
            kind=CleanupCandidateKind.REJECTED,
            relative_path="~/escape.txt",
        )


def test_cleanup_candidate_blocks_dollar_traversal() -> None:
    with pytest.raises(ValueError, match="Path traversal"):
        CleanupCandidate(
            candidate_id="cand-1",
            kind=CleanupCandidateKind.REJECTED,
            relative_path="$HOME/escape.txt",
        )


def test_cleanup_candidate_blocks_brace_traversal() -> None:
    with pytest.raises(ValueError, match="Path traversal"):
        CleanupCandidate(
            candidate_id="cand-1",
            kind=CleanupCandidateKind.REJECTED,
            relative_path="{var}/escape.txt",
        )


def test_validate_cleanup_relative_path_returns_none_for_none() -> None:
    assert validate_cleanup_relative_path(None) is None


def test_validate_cleanup_relative_path_normalizes_backslashes() -> None:
    result = validate_cleanup_relative_path("foo\\bar.txt")
    assert result == "foo/bar.txt"


def test_cleanup_plan_total_candidate_count() -> None:
    plan = CleanupPlan(
        plan_id="plan-1",
        total_candidate_count=5,
    )

    assert plan.total_candidate_count == 5


def test_cleanup_plan_total_planned_bytes_optional() -> None:
    plan_with_bytes = CleanupPlan(
        plan_id="plan-1",
        total_planned_bytes=10240,
    )
    plan_without_bytes = CleanupPlan(
        plan_id="plan-2",
    )

    assert plan_with_bytes.total_planned_bytes == 10240
    assert plan_without_bytes.total_planned_bytes is None


def test_build_fake_cleanup_candidates_returns_list() -> None:
    candidates = build_fake_cleanup_candidates()

    assert isinstance(candidates, list)
    assert len(candidates) > 0
    for c in candidates:
        assert isinstance(c, CleanupCandidate)
        assert c.candidate_id
        assert c.kind


def test_fake_candidates_include_all_kinds() -> None:
    candidates = build_fake_cleanup_candidates()
    kinds = {c.kind for c in candidates}

    assert CleanupCandidateKind.REJECTED in kinds
    assert CleanupCandidateKind.DELETE_ELIGIBLE in kinds
    assert CleanupCandidateKind.TEMPORARY in kinds
    assert CleanupCandidateKind.ORPHANED in kinds
    assert CleanupCandidateKind.STALE_REPORT in kinds
    assert CleanupCandidateKind.STALE_MANIFEST in kinds


def test_cleanup_decision_enum_normalization() -> None:
    decision = CleanupDecision(
        candidate_id="cand-1",
        action_type="review",
        risk="medium",
    )

    assert decision.action_type == CleanupActionType.REVIEW
    assert decision.risk == CleanupRisk.MEDIUM


def test_cleanup_candidate_enum_normalization() -> None:
    candidate = CleanupCandidate(
        candidate_id="cand-1",
        kind="rejected",
    )

    assert candidate.kind == CleanupCandidateKind.REJECTED
