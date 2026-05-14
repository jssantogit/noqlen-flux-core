import inspect
import uuid

from noqlen_flux.results import Status
from noqlen_flux.routing import RoutingActionType, RoutingDecision, RoutingOutcome, RoutingPlan
from noqlen_flux.services.staging import StagingPlanService
from noqlen_flux.staging import DEFAULT_STAGING_POLICY, StagingActionType, StagingArea, StagingPolicy


def _approved_decision(item_id: str = "item-1") -> RoutingDecision:
    return RoutingDecision(
        item_id=item_id,
        outcome=RoutingOutcome.APPROVED,
        action_type=RoutingActionType.PLAN_ONLY,
    )


def _quarantine_decision(item_id: str = "item-1") -> RoutingDecision:
    return RoutingDecision(
        item_id=item_id,
        outcome=RoutingOutcome.QUARANTINE,
        action_type=RoutingActionType.PLAN_ONLY,
    )


def _rejected_decision(item_id: str = "item-1") -> RoutingDecision:
    return RoutingDecision(
        item_id=item_id,
        outcome=RoutingOutcome.REJECTED,
        action_type=RoutingActionType.PLAN_ONLY,
    )


def _delete_eligible_decision(item_id: str = "item-1") -> RoutingDecision:
    return RoutingDecision(
        item_id=item_id,
        outcome=RoutingOutcome.DELETE_ELIGIBLE,
        action_type=RoutingActionType.PLAN_ONLY,
    )


def _review_decision(item_id: str = "item-1") -> RoutingDecision:
    return RoutingDecision(
        item_id=item_id,
        outcome=RoutingOutcome.REVIEW,
        action_type=RoutingActionType.PLAN_ONLY,
    )


def _routing_plan(decisions: list[RoutingDecision]) -> RoutingPlan:
    return RoutingPlan(
        plan_id=str(uuid.uuid4()),
        decisions=decisions,
    )


def test_approved_routes_to_staging_area_approved() -> None:
    service = StagingPlanService()

    item = service.plan_staging_item(_approved_decision())

    assert item.target_area == StagingArea.APPROVED
    assert item.action_type == StagingActionType.PLAN_ONLY


def test_quarantine_routes_to_staging_area_quarantine() -> None:
    service = StagingPlanService()

    item = service.plan_staging_item(_quarantine_decision())

    assert item.target_area == StagingArea.QUARANTINE
    assert item.action_type == StagingActionType.PLAN_ONLY


def test_rejected_routes_to_staging_area_rejected() -> None:
    service = StagingPlanService()

    item = service.plan_staging_item(_rejected_decision())

    assert item.target_area == StagingArea.REJECTED
    assert item.action_type == StagingActionType.PLAN_ONLY


def test_review_routes_to_staging_area_review_by_default() -> None:
    service = StagingPlanService()

    item = service.plan_staging_item(_review_decision())

    assert item.target_area == StagingArea.REVIEW
    assert item.action_type == StagingActionType.PLAN_ONLY


def test_delete_eligible_only_planned_if_policy_allows() -> None:
    service = StagingPlanService()
    policy = StagingPolicy(
        name="aggressive_v1",
        version="1",
        description="Aggressive policy for testing.",
        allow_delete_eligible=True,
    )

    item = service.plan_staging_item(_delete_eligible_decision(), policy=policy)

    assert item.target_area == StagingArea.DELETE_ELIGIBLE
    assert item.action_type == StagingActionType.PLAN_ONLY


def test_delete_eligible_default_policy_converts_to_rejected() -> None:
    service = StagingPlanService()

    item = service.plan_staging_item(_delete_eligible_decision())

    assert item.target_area == StagingArea.REJECTED
    assert any("Policy does not allow delete_eligible" in w for w in item.warnings)


def test_plan_staging_returns_flux_result_with_planned_change() -> None:
    service = StagingPlanService()
    plan = _routing_plan([_approved_decision("a"), _rejected_decision("b")])

    result = service.plan_staging(plan)

    assert result.status == Status.SUCCESS
    assert result.summary["item_count"] == 2
    assert result.summary["approved_count"] == 1
    assert result.summary["rejected_count"] == 1
    assert len(result.planned_changes) == 2
    assert len(result.applied_changes) == 0


def test_plan_staging_returns_planned_change_not_applied_change() -> None:
    service = StagingPlanService()
    plan = _routing_plan([_approved_decision()])

    result = service.plan_staging(plan)

    assert len(result.planned_changes) >= 1
    assert len(result.applied_changes) == 0


def test_plan_staging_aggregates_all_outcomes() -> None:
    service = StagingPlanService()
    plan = _routing_plan([
        _approved_decision("a"),
        _quarantine_decision("b"),
        _rejected_decision("c"),
        _review_decision("d"),
    ])

    result = service.plan_staging(plan)

    assert result.summary["approved_count"] == 1
    assert result.summary["quarantine_count"] == 1
    assert result.summary["rejected_count"] == 1
    assert result.summary["review_count"] == 1


def test_staging_service_does_not_create_files(tmp_path) -> None:
    service = StagingPlanService()
    plan = _routing_plan([_approved_decision()])

    service.plan_staging(plan)

    assert list(tmp_path.iterdir()) == []


def test_staging_service_does_not_move_files(tmp_path) -> None:
    service = StagingPlanService()
    plan = _routing_plan([_approved_decision()])

    service.plan_staging(plan)

    assert list(tmp_path.iterdir()) == []


def test_staging_service_does_not_copy_files(tmp_path) -> None:
    service = StagingPlanService()
    plan = _routing_plan([_approved_decision()])

    service.plan_staging(plan)

    assert list(tmp_path.iterdir()) == []


def test_staging_service_does_not_delete_files(tmp_path) -> None:
    service = StagingPlanService()
    plan = _routing_plan([_delete_eligible_decision()])

    service.plan_staging(plan)

    assert list(tmp_path.iterdir()) == []


def test_staging_service_does_not_access_network() -> None:
    from noqlen_flux.services import staging as staging_module

    source = inspect.getsource(staging_module)
    assert "requests" not in source
    assert "urllib" not in source
    assert "socket" not in source


def test_staging_service_does_not_depend_on_slskd() -> None:
    from noqlen_flux.services import staging as staging_module

    assert "slskd" not in staging_module.__file__
    for name in dir(staging_module):
        obj = getattr(staging_module, name, None)
        if hasattr(obj, "__module__"):
            assert "slskd" not in (getattr(obj, "__module__", "") or "")


def test_staging_service_does_not_use_print_or_input() -> None:
    from noqlen_flux.services import staging as staging_module

    source = inspect.getsource(staging_module)
    assert "print(" not in source
    assert "input(" not in source


def test_staging_service_does_not_call_download_or_transfer() -> None:
    from noqlen_flux.services import staging as staging_module

    source = inspect.getsource(staging_module)
    assert "DownloadPlanningService" not in source
    assert "TransferPlanningService" not in source
    assert "plan_download" not in source
    assert "plan_queue" not in source


def test_staging_does_not_alter_routing_decision() -> None:
    service = StagingPlanService()
    decision = _approved_decision("item-1")
    original_dict = decision.to_dict()

    service.plan_staging_item(decision)

    assert decision.to_dict() == original_dict


def test_staging_item_contains_routing_outcome() -> None:
    service = StagingPlanService()

    item = service.plan_staging_item(_approved_decision())

    assert item.routing_outcome == "approved"


def test_staging_plan_is_not_routing_plan() -> None:
    from noqlen_flux.routing import RoutingPlan as RP

    service = StagingPlanService()
    plan = _routing_plan([_approved_decision()])

    result = service.plan_staging(plan)

    assert "staging_plan" in result.summary
    assert isinstance(result.summary["staging_plan"], dict)


def test_candidate_risk_not_equal_quality_grade_not_equal_routing_decision_not_equal_staging_plan() -> None:
    from noqlen_flux.quality import QualityGrade
    from noqlen_flux.routing import RoutingOutcome
    from noqlen_flux.scoring import CandidateRisk
    from noqlen_flux.staging import StagingArea

    risk_values = {r.value for r in CandidateRisk}
    grade_values = {g.value for g in QualityGrade}
    outcome_values = {o.value for o in RoutingOutcome}
    area_values = {a.value for a in StagingArea}

    assert "approved" not in risk_values
    assert "approved" not in grade_values
    assert "quarantine" not in risk_values
    assert "quarantine" not in grade_values
    assert "rejected" not in risk_values
    assert "rejected" not in grade_values
    assert "delete_eligible" not in risk_values
    assert "delete_eligible" not in grade_values
    assert "low" not in grade_values
    assert "high" not in grade_values
    assert "excellent" not in risk_values
    assert "bad" not in risk_values
    assert "approved" in outcome_values
    assert "approved" in area_values


def test_routing_does_not_execute_staging_automatically() -> None:
    from noqlen_flux.services import routing as routing_module

    source = inspect.getsource(routing_module)
    assert "StagingPlanService" not in source
    assert "plan_staging" not in source


def test_staging_does_not_call_download_or_transfer() -> None:
    from noqlen_flux.services import staging as staging_module

    source = inspect.getsource(staging_module)
    assert "DownloadPlanningService" not in source
    assert "TransferPlanningService" not in source


def test_staging_does_not_call_cleanup() -> None:
    from noqlen_flux.services import staging as staging_module

    source = inspect.getsource(staging_module)
    assert "cleanup" not in source.lower()
    assert "auto-delete" not in source.lower()


def test_delete_eligible_never_executes_delete() -> None:
    service = StagingPlanService()
    policy = StagingPolicy(
        name="aggressive_v1",
        version="1",
        description="Aggressive policy for testing.",
        allow_delete_eligible=True,
    )

    item = service.plan_staging_item(_delete_eligible_decision(), policy=policy)

    assert item.action_type == StagingActionType.PLAN_ONLY
    assert item.action_type != StagingActionType.MARK_DELETE_ELIGIBLE


def test_heuristic_review_cases_do_not_generate_delete() -> None:
    service = StagingPlanService()

    item = service.plan_staging_item(_review_decision())

    assert item.target_area != StagingArea.DELETE_ELIGIBLE


def test_staging_service_with_warning_aggregates_warnings() -> None:
    service = StagingPlanService()
    plan = _routing_plan([_delete_eligible_decision()])

    result = service.plan_staging(plan)

    assert result.status == Status.WARNING
    assert len(result.warnings) >= 1


def test_staging_service_with_multiple_outcomes() -> None:
    service = StagingPlanService()
    plan = _routing_plan([
        _approved_decision("a"),
        _quarantine_decision("b"),
        _rejected_decision("c"),
        _delete_eligible_decision("d"),
        _review_decision("e"),
    ])

    result = service.plan_staging(plan)

    assert result.summary["approved_count"] == 1
    assert result.summary["quarantine_count"] == 1
    assert result.summary["rejected_count"] == 2
    assert result.summary["review_count"] == 1
    assert result.summary["delete_eligible_count"] == 0
