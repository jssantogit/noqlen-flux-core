from noqlen_flux.routing import (
    DEFAULT_ROUTING_APPLY_POLICY,
    DEFAULT_ROUTING_POLICY,
    RoutingActionType,
    RoutingApplyPolicy,
    RoutingDecision,
    RoutingOutcome,
    RoutingPlan,
    RoutingPolicy,
    RoutingReason,
    RoutingReasonSource,
    default_routing_apply_policy,
    default_routing_policy,
)


def test_routing_outcome_enum_values() -> None:
    assert RoutingOutcome.APPROVED.value == "approved"
    assert RoutingOutcome.QUARANTINE.value == "quarantine"
    assert RoutingOutcome.REJECTED.value == "rejected"
    assert RoutingOutcome.DELETE_ELIGIBLE.value == "delete_eligible"
    assert RoutingOutcome.REVIEW.value == "review"
    assert RoutingOutcome.UNKNOWN.value == "unknown"


def test_routing_action_type_enum_values() -> None:
    assert RoutingActionType.PLAN_ONLY.value == "plan_only"
    assert RoutingActionType.MOVE_TO_APPROVED.value == "move_to_approved"
    assert RoutingActionType.MOVE_TO_QUARANTINE.value == "move_to_quarantine"
    assert RoutingActionType.MOVE_TO_REJECTED.value == "move_to_rejected"
    assert RoutingActionType.MARK_DELETE_ELIGIBLE.value == "mark_delete_eligible"
    assert RoutingActionType.NONE.value == "none"


def test_routing_reason_source_enum_values() -> None:
    assert RoutingReasonSource.QUALITY_GRADE.value == "quality_grade"
    assert RoutingReasonSource.QUALITY_FINDING.value == "quality_finding"
    assert RoutingReasonSource.POLICY_RULE.value == "policy_rule"
    assert RoutingReasonSource.UNKNOWN.value == "unknown"


def test_routing_decision_serializes_correctly() -> None:
    reason = RoutingReason(
        code="grade-excellent",
        message="Quality grade is excellent.",
        severity="info",
        source=RoutingReasonSource.QUALITY_GRADE,
    )
    decision = RoutingDecision(
        item_id="item-1",
        outcome=RoutingOutcome.APPROVED,
        action_type=RoutingActionType.PLAN_ONLY,
        reasons=[reason],
        confidence=0.95,
    )

    payload = decision.to_dict()

    assert payload["item_id"] == "item-1"
    assert payload["outcome"] == "approved"
    assert payload["action_type"] == "plan_only"
    assert payload["reasons"][0]["code"] == "grade-excellent"
    assert payload["confidence"] == 0.95


def test_routing_decision_serializes_safely() -> None:
    decision = RoutingDecision(
        item_id="item-1",
        outcome=RoutingOutcome.APPROVED,
        action_type=RoutingActionType.PLAN_ONLY,
        metadata={"token": "placeholder-secret"},
    )

    payload = decision.to_dict()

    assert payload["metadata"]["token"] == "[redacted]"


def test_routing_policy_is_versioned() -> None:
    policy = RoutingPolicy(
        name="test_v1",
        version="1",
        description="Test policy",
    )

    assert policy.name == "test_v1"
    assert policy.version == "1"
    assert policy.description == "Test policy"
    assert policy.allow_delete_eligible is False
    assert policy.heuristic_warnings_route_to_review_or_quarantine is True
    assert policy.objective_failures_route_to_rejected is True


def test_routing_policy_serializes_safely() -> None:
    policy = RoutingPolicy(
        name="test_v2",
        version="2",
        description="Test with secret",
        metadata={"secret": "hidden"},
    )

    payload = policy.to_dict()

    assert payload["name"] == "test_v2"
    assert payload["metadata"]["secret"] == "[redacted]"


def test_routing_plan_contains_planned_change_not_applied_change() -> None:
    plan = RoutingPlan(
        plan_id="plan-1",
        decisions=[],
        planned_changes=[{"action": "plan-approve", "target": "item-1"}],
    )

    payload = plan.to_dict()

    assert "planned_changes" in payload
    assert "applied_changes" not in payload


def test_routing_plan_serializes_safely() -> None:
    plan = RoutingPlan(
        plan_id="plan-1",
        metadata={"token": "placeholder-secret"},
    )

    payload = plan.to_dict()

    assert payload["metadata"]["token"] == "[redacted]"


def test_default_routing_policy_exists() -> None:
    policy = default_routing_policy()

    assert policy.name == "default_v1"
    assert policy.version == "1"
    assert "post-download" in policy.metadata.get("stage", "")
    assert policy.allow_delete_eligible is False


def test_routing_decision_is_not_quality_grade() -> None:
    from noqlen_flux.quality import QualityGrade

    outcome_values = {o.value for o in RoutingOutcome}
    grade_values = {g.value for g in QualityGrade}

    assert "approved" not in grade_values
    assert "quarantine" not in grade_values
    assert "rejected" not in grade_values
    assert "delete_eligible" not in grade_values
    assert "review" not in grade_values


def test_routing_decision_is_not_candidate_risk() -> None:
    from noqlen_flux.scoring import CandidateRisk

    outcome_values = {o.value for o in RoutingOutcome}
    risk_values = {r.value for r in CandidateRisk}

    assert "approved" not in risk_values
    assert "quarantine" not in risk_values
    assert "rejected" not in risk_values
    assert "delete_eligible" not in risk_values
    assert "review" not in risk_values


def test_routing_reason_serializes_safely() -> None:
    reason = RoutingReason(
        code="test-reason",
        message="Test reason",
        severity="info",
        source=RoutingReasonSource.QUALITY_GRADE,
        metadata={"token": "placeholder-secret"},
    )

    payload = reason.to_dict()

    assert payload["code"] == "test-reason"
    assert payload["source"] == "quality_grade"
    assert payload["metadata"]["token"] == "[redacted]"


class TestRoutingApplyPolicy:
    def test_default_policy_is_safe(self) -> None:
        policy = default_routing_apply_policy()
        assert policy.dry_run_default is True
        assert policy.apply_explicit is True
        assert policy.allow_delete_eligible is False
        assert policy.allow_mark_delete_eligible is False
        assert policy.workspace_only is True
        assert policy.block_absolute_path is True
        assert policy.block_traversal is True
        assert policy.block_symlink_escape is True
        assert policy.block_protected_roots is True
        assert policy.generate_safety_report is True

    def test_policy_allows_approved_quarantine_rejected(self) -> None:
        policy = default_routing_apply_policy()
        assert policy.allow_move_to_approved is True
        assert policy.allow_move_to_quarantine is True
        assert policy.allow_move_to_rejected is True

    def test_policy_forbids_delete_operations(self) -> None:
        policy = default_routing_apply_policy()
        assert policy.allow_delete_eligible is False
        assert policy.allow_mark_delete_eligible is False

    def test_policy_is_versioned(self) -> None:
        policy = RoutingApplyPolicy(
            name="test_apply_v1",
            version="1",
            description="Test apply policy",
        )
        assert policy.name == "test_apply_v1"
        assert policy.version == "1"

    def test_policy_serializes_safely(self) -> None:
        policy = RoutingApplyPolicy(
            name="test_v2",
            version="2",
            description="Test with secret",
            metadata={"secret": "hidden"},
        )
        payload = policy.to_dict()
        assert payload["name"] == "test_v2"
        assert payload["metadata"]["secret"] == "[redacted]"

    def test_policy_review_is_manual_only(self) -> None:
        policy = default_routing_apply_policy()
        assert policy.allow_review_manual_only is True
