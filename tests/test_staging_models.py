import pytest

from noqlen_flux.staging import (
    DEFAULT_STAGING_EXECUTION_POLICY,
    DEFAULT_STAGING_POLICY,
    StagingActionType,
    StagingApplyReport,
    StagingArea,
    StagingExecutionPolicy,
    StagingExecutionSummary,
    StagingItem,
    StagingPlan,
    StagingPolicy,
    default_staging_execution_policy,
    default_staging_policy,
    validate_relative_path,
)


def test_staging_area_enum_values() -> None:
    assert StagingArea.INCOMING.value == "incoming"
    assert StagingArea.APPROVED.value == "approved"
    assert StagingArea.QUARANTINE.value == "quarantine"
    assert StagingArea.REJECTED.value == "rejected"
    assert StagingArea.DELETE_ELIGIBLE.value == "delete_eligible"
    assert StagingArea.REVIEW.value == "review"
    assert StagingArea.UNKNOWN.value == "unknown"


def test_staging_action_type_enum_values() -> None:
    assert StagingActionType.PLAN_ONLY.value == "plan_only"
    assert StagingActionType.MOVE.value == "move"
    assert StagingActionType.COPY.value == "copy"
    assert StagingActionType.MARK_DELETE_ELIGIBLE.value == "mark_delete_eligible"
    assert StagingActionType.NONE.value == "none"


def test_staging_item_serializes_target_area_and_action_type() -> None:
    item = StagingItem(
        item_id="item-1",
        routing_outcome="approved",
        target_area=StagingArea.APPROVED,
        action_type=StagingActionType.PLAN_ONLY,
    )

    payload = item.to_dict()

    assert payload["item_id"] == "item-1"
    assert payload["target_area"] == "approved"
    assert payload["action_type"] == "plan_only"
    assert payload["routing_outcome"] == "approved"


def test_staging_item_serializes_safely() -> None:
    item = StagingItem(
        item_id="item-1",
        routing_outcome="approved",
        target_area=StagingArea.APPROVED,
        action_type=StagingActionType.PLAN_ONLY,
        metadata={"token": "placeholder-secret"},
    )

    payload = item.to_dict()

    assert payload["metadata"]["token"] == "[redacted]"


def test_staging_policy_is_versioned() -> None:
    policy = StagingPolicy(
        name="test_v1",
        version="1",
        description="Test policy",
    )

    assert policy.name == "test_v1"
    assert policy.version == "1"
    assert policy.description == "Test policy"
    assert policy.allow_delete_eligible is False
    assert policy.allow_real_moves is False
    assert policy.quarantine_heuristic_warnings is True


def test_staging_policy_serializes_safely() -> None:
    policy = StagingPolicy(
        name="test_v2",
        version="2",
        description="Test with secret",
        metadata={"secret": "hidden"},
    )

    payload = policy.to_dict()

    assert payload["name"] == "test_v2"
    assert payload["metadata"]["secret"] == "[redacted]"


def test_staging_plan_contains_planned_change_not_applied_change() -> None:
    plan = StagingPlan(
        plan_id="plan-1",
        items=[],
        planned_changes=[{"action": "plan-stage-approved", "target": "item-1"}],
    )

    payload = plan.to_dict()

    assert "planned_changes" in payload
    assert "applied_changes" not in payload


def test_staging_plan_serializes_safely() -> None:
    plan = StagingPlan(
        plan_id="plan-1",
        metadata={"token": "placeholder-secret"},
    )

    payload = plan.to_dict()

    assert payload["metadata"]["token"] == "[redacted]"


def test_default_staging_policy_exists() -> None:
    policy = default_staging_policy()

    assert policy.name == "default_v1"
    assert policy.version == "1"
    assert "post-download" in policy.metadata.get("stage", "")
    assert policy.allow_delete_eligible is False
    assert policy.allow_real_moves is False


def test_staging_item_is_not_routing_decision() -> None:
    from noqlen_flux.routing import RoutingOutcome

    area_values = {a.value for a in StagingArea}
    outcome_values = {o.value for o in RoutingOutcome}

    assert "incoming" not in outcome_values
    assert "review" in outcome_values
    assert "review" in area_values


def test_staging_item_is_not_quality_grade() -> None:
    from noqlen_flux.quality import QualityGrade

    area_values = {a.value for a in StagingArea}
    grade_values = {g.value for g in QualityGrade}

    assert "approved" not in grade_values
    assert "quarantine" not in grade_values
    assert "rejected" not in grade_values
    assert "delete_eligible" not in grade_values


def test_staging_item_is_not_candidate_risk() -> None:
    from noqlen_flux.scoring import CandidateRisk

    area_values = {a.value for a in StagingArea}
    risk_values = {r.value for r in CandidateRisk}

    assert "approved" not in risk_values
    assert "quarantine" not in risk_values
    assert "rejected" not in risk_values
    assert "delete_eligible" not in risk_values


def test_validate_relative_path_accepts_none() -> None:
    assert validate_relative_path(None) is None


def test_validate_relative_path_accepts_safe_path() -> None:
    result = validate_relative_path("approved/item-1.flac")
    assert result == "approved/item-1.flac"


def test_validate_relative_path_blocks_absolute_path() -> None:
    with pytest.raises(ValueError, match="Absolute paths"):
        validate_relative_path("/etc/passwd")


def test_validate_relative_path_blocks_traversal() -> None:
    with pytest.raises(ValueError, match="Path traversal marker"):
        validate_relative_path("../../../etc/passwd")


def test_validate_relative_path_blocks_traversal_marker() -> None:
    with pytest.raises(ValueError, match="Path traversal marker"):
        validate_relative_path("foo/../bar")


def test_validate_relative_path_normalizes_backslashes() -> None:
    result = validate_relative_path("approved\\item-1.flac")
    assert result == "approved/item-1.flac"


def test_staging_item_blocks_absolute_source_path() -> None:
    with pytest.raises(ValueError, match="Absolute paths"):
        StagingItem(
            item_id="item-1",
            routing_outcome="approved",
            source_relative_path="/etc/passwd",
            target_area=StagingArea.APPROVED,
        )


def test_staging_item_blocks_absolute_target_path() -> None:
    with pytest.raises(ValueError, match="Absolute paths"):
        StagingItem(
            item_id="item-1",
            routing_outcome="approved",
            source_relative_path="incoming/item.flac",
            target_area=StagingArea.APPROVED,
            target_relative_path="/tmp/evil",
        )


def test_staging_item_blocks_traversal_in_source() -> None:
    with pytest.raises(ValueError, match="Path traversal marker"):
        StagingItem(
            item_id="item-1",
            routing_outcome="approved",
            source_relative_path="../../../etc/passwd",
            target_area=StagingArea.APPROVED,
        )


def test_staging_item_blocks_traversal_in_target() -> None:
    with pytest.raises(ValueError, match="Path traversal marker"):
        StagingItem(
            item_id="item-1",
            routing_outcome="approved",
            target_area=StagingArea.APPROVED,
            target_relative_path="../../../tmp/evil",
        )


def test_staging_execution_policy_defaults() -> None:
    policy = StagingExecutionPolicy(
        name="test_v1",
        version="1",
        description="Test policy",
    )

    assert policy.allow_copy is True
    assert policy.allow_move is False
    assert policy.allow_delete is False
    assert policy.allow_overwrite is False
    assert policy.create_workspace_dirs is True


def test_staging_execution_policy_serializes_safely() -> None:
    policy = StagingExecutionPolicy(
        name="test_v1",
        version="1",
        description="Test with secret",
        metadata={"secret": "hidden"},
    )

    payload = policy.to_dict()

    assert payload["name"] == "test_v1"
    assert payload["metadata"]["secret"] == "[redacted]"


def test_staging_execution_summary_defaults() -> None:
    summary = StagingExecutionSummary()

    assert summary.total_items == 0
    assert summary.planned_count == 0
    assert summary.applied_count == 0
    assert summary.blocked_count == 0
    assert summary.skipped_count == 0
    assert summary.warnings == []
    assert summary.errors == []


def test_staging_execution_summary_serializes_safely() -> None:
    summary = StagingExecutionSummary(
        total_items=5,
        applied_count=3,
        blocked_count=1,
        skipped_count=1,
        warnings=["test warning"],
        metadata={"secret": "hidden"},
    )

    payload = summary.to_dict()

    assert payload["total_items"] == 5
    assert payload["applied_count"] == 3
    assert payload["blocked_count"] == 1
    assert payload["skipped_count"] == 1
    assert payload["metadata"]["secret"] == "[redacted]"


def test_default_staging_execution_policy_exists() -> None:
    policy = default_staging_execution_policy()

    assert policy.name == "default_v1"
    assert policy.version == "1"
    assert policy.allow_copy is True
    assert policy.allow_move is False
    assert policy.allow_delete is False
    assert policy.allow_overwrite is False
    assert policy.create_workspace_dirs is True


class TestStagingApplyReport:
    def test_report_serializes_safely(self) -> None:
        report = StagingApplyReport.from_execution_result(
            report_id="rpt-1",
            source_staging_plan_id="plan-1",
            mode="dry-run",
            timestamp="2025-01-01T00:00:00Z",
            policy_name="default_apply_v1",
            total_items=1,
            planned_count=1,
            applied_count=0,
            blocked_count=0,
            skipped_count=0,
            failed_count=0,
            metadata={"secret": "hidden"},
        )
        payload = report.to_dict()
        assert payload["report_id"] == "rpt-1"
        assert payload["mode"] == "dry-run"
        assert payload["metadata"]["secret"] == "[redacted]"

    def test_report_includes_safety_checks(self) -> None:
        report = StagingApplyReport.from_execution_result(
            report_id="rpt-2",
            source_staging_plan_id="plan-2",
            mode="apply",
            timestamp="2025-01-01T00:00:00Z",
            policy_name="default_apply_v1",
            total_items=3,
            planned_count=2,
            applied_count=2,
            blocked_count=1,
            skipped_count=0,
            failed_count=0,
            safety_checks=[
                {"check": "dry_run_default", "passed": True},
                {"check": "workspace_only", "passed": True},
                {"check": "no_delete", "passed": True},
            ],
            notes=["Workspace-only operations applied", "No delete operations"],
        )
        payload = report.to_dict()
        assert len(payload["safety_checks"]) == 3
        assert payload["safety_checks"][0]["check"] == "dry_run_default"
        assert payload["mode"] == "apply"
        assert payload["blocked_count"] == 1

    def test_report_blocks_delete_eligible(self) -> None:
        report = StagingApplyReport.from_execution_result(
            report_id="rpt-3",
            source_staging_plan_id="plan-3",
            mode="dry-run",
            timestamp="2025-01-01T00:00:00Z",
            policy_name="default_apply_v1",
            total_items=1,
            planned_count=0,
            applied_count=0,
            blocked_count=1,
            skipped_count=0,
            failed_count=0,
            blocked_operations=[
                {"item_id": "item-1", "reason": "delete_eligible blocked by policy"},
            ],
        )
        payload = report.to_dict()
        assert len(payload["blocked_operations"]) == 1
        assert payload["blocked_operations"][0]["item_id"] == "item-1"

    def test_factory_creates_complete_report(self) -> None:
        report = StagingApplyReport.from_execution_result(
            report_id="rpt-factory",
            source_staging_plan_id="plan-src",
            mode="apply",
            timestamp="2025-06-15T12:00:00Z",
            policy_name="test_policy",
            total_items=5,
            planned_count=4,
            applied_count=3,
            blocked_count=1,
            skipped_count=0,
            failed_count=1,
            operations=[{"action": "copy", "target": "approved/item.flac"}],
            safety_checks=[{"check": "no_delete", "passed": True}],
            blocked_operations=[],
            skipped_operations=[],
            warnings=["test warning"],
            errors=[],
            notes=["test note"],
            metadata={"source": "test"},
        )
        payload = report.to_dict()
        assert payload["report_id"] == "rpt-factory"
        assert payload["source_staging_plan_id"] == "plan-src"
        assert payload["total_items"] == 5
        assert payload["applied_count"] == 3
        assert payload["failed_count"] == 1
        assert len(payload["operations"]) == 1
        assert len(payload["safety_checks"]) == 1
        assert payload["warnings"] == ["test warning"]
        assert payload["notes"] == ["test note"]
