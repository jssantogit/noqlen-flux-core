import inspect

from noqlen_flux.quality import QualityFinding, QualityFindingKind, QualityFindingSeverity, QualityGrade, QualityResult
from noqlen_flux.results import Status
from noqlen_flux.routing import (
    DEFAULT_ROUTING_POLICY,
    RoutingActionType,
    RoutingDecision,
    RoutingOutcome,
    RoutingPolicy,
)
from noqlen_flux.services.routing import RoutingDecisionService


def _excellent_result(item_id: str = "item-1") -> QualityResult:
    return QualityResult(item_id=item_id, grade=QualityGrade.EXCELLENT)


def _medium_result(item_id: str = "item-1") -> QualityResult:
    return QualityResult(item_id=item_id, grade=QualityGrade.MEDIUM)


def _medium_with_heuristic(item_id: str = "item-1") -> QualityResult:
    return QualityResult(
        item_id=item_id,
        grade=QualityGrade.MEDIUM,
        heuristic_warnings=[
            QualityFinding(
                code="clipping-suspicion",
                message="Possible clipping detected.",
                kind=QualityFindingKind.HEURISTIC_WARNING,
                severity=QualityFindingSeverity.WARNING,
            )
        ],
    )


def _bad_with_objective(item_id: str = "item-1") -> QualityResult:
    return QualityResult(
        item_id=item_id,
        grade=QualityGrade.BAD,
        objective_failures=[
            QualityFinding(
                code="decode-fail",
                message="File fails decode validation.",
                kind=QualityFindingKind.OBJECTIVE_FAILURE,
                severity=QualityFindingSeverity.ERROR,
            )
        ],
    )


def _bad_with_heuristic(item_id: str = "item-1") -> QualityResult:
    return QualityResult(
        item_id=item_id,
        grade=QualityGrade.BAD,
        heuristic_warnings=[
            QualityFinding(
                code="low-pass-suspicion",
                message="Low-pass filter suggests transcode.",
                kind=QualityFindingKind.HEURISTIC_WARNING,
                severity=QualityFindingSeverity.WARNING,
            )
        ],
    )


def _unknown_result(item_id: str = "item-1") -> QualityResult:
    return QualityResult(item_id=item_id, grade=QualityGrade.UNKNOWN)


def test_excellent_routes_to_approved() -> None:
    service = RoutingDecisionService()

    decision = service.decide_quality_route(_excellent_result())

    assert decision.outcome == RoutingOutcome.APPROVED
    assert decision.action_type == RoutingActionType.PLAN_ONLY
    assert decision.confidence > 0.8


def test_medium_clean_routes_to_approved() -> None:
    service = RoutingDecisionService()

    decision = service.decide_quality_route(_medium_result())

    assert decision.outcome == RoutingOutcome.APPROVED
    assert decision.action_type == RoutingActionType.PLAN_ONLY


def test_medium_with_heuristic_routes_to_review() -> None:
    service = RoutingDecisionService()

    decision = service.decide_quality_route(_medium_with_heuristic())

    assert decision.outcome == RoutingOutcome.REVIEW
    assert decision.action_type == RoutingActionType.PLAN_ONLY


def test_medium_with_objective_routes_to_review() -> None:
    service = RoutingDecisionService()
    qr = QualityResult(
        item_id="item-1",
        grade=QualityGrade.MEDIUM,
        objective_failures=[
            QualityFinding(
                code="decode-fail",
                message="File fails decode validation.",
                kind=QualityFindingKind.OBJECTIVE_FAILURE,
                severity=QualityFindingSeverity.ERROR,
            )
        ],
    )

    decision = service.decide_quality_route(qr)

    assert decision.outcome == RoutingOutcome.REVIEW
    assert decision.action_type == RoutingActionType.PLAN_ONLY


def test_bad_with_objective_routes_to_rejected() -> None:
    service = RoutingDecisionService()

    decision = service.decide_quality_route(_bad_with_objective())

    assert decision.outcome == RoutingOutcome.REJECTED
    assert decision.action_type == RoutingActionType.PLAN_ONLY


def test_bad_with_objective_only_becomes_delete_eligible_if_policy_allows() -> None:
    service = RoutingDecisionService()
    policy = RoutingPolicy(
        name="aggressive_v1",
        version="1",
        description="Aggressive policy for testing.",
        allow_delete_eligible=True,
    )

    decision = service.decide_quality_route(_bad_with_objective(), policy=policy)

    assert decision.outcome == RoutingOutcome.DELETE_ELIGIBLE
    assert decision.action_type == RoutingActionType.PLAN_ONLY


def test_bad_with_objective_default_policy_does_not_allow_delete() -> None:
    service = RoutingDecisionService()

    decision = service.decide_quality_route(_bad_with_objective())

    assert decision.outcome == RoutingOutcome.REJECTED
    assert decision.outcome != RoutingOutcome.DELETE_ELIGIBLE


def test_bad_with_heuristic_routes_to_quarantine() -> None:
    service = RoutingDecisionService()

    decision = service.decide_quality_route(_bad_with_heuristic())

    assert decision.outcome == RoutingOutcome.QUARANTINE
    assert decision.action_type == RoutingActionType.PLAN_ONLY


def test_bad_with_heuristic_never_delete_eligible() -> None:
    service = RoutingDecisionService()

    decision = service.decide_quality_route(_bad_with_heuristic())

    assert decision.outcome != RoutingOutcome.DELETE_ELIGIBLE


def test_unknown_routes_to_review() -> None:
    service = RoutingDecisionService()

    decision = service.decide_quality_route(_unknown_result())

    assert decision.outcome == RoutingOutcome.REVIEW
    assert decision.action_type == RoutingActionType.PLAN_ONLY


def test_heuristic_warning_does_not_cause_destructive_action() -> None:
    service = RoutingDecisionService()

    decision = service.decide_quality_route(_bad_with_heuristic())

    assert decision.outcome != RoutingOutcome.DELETE_ELIGIBLE
    assert decision.action_type == RoutingActionType.PLAN_ONLY


def test_objective_failure_does_not_execute_delete() -> None:
    service = RoutingDecisionService()

    decision = service.decide_quality_route(_bad_with_objective())

    assert decision.action_type == RoutingActionType.PLAN_ONLY
    assert decision.action_type != RoutingActionType.MARK_DELETE_ELIGIBLE


def test_plan_routing_returns_flux_result_with_planned_change() -> None:
    service = RoutingDecisionService()
    results = [_excellent_result("a"), _bad_with_objective("b")]

    result = service.plan_routing(results)

    assert result.status == Status.WARNING
    assert result.summary["decision_count"] == 2
    assert result.summary["approved_count"] == 1
    assert result.summary["rejected_count"] == 1
    assert len(result.planned_changes) == 2
    assert len(result.applied_changes) == 0


def test_plan_routing_returns_planned_change_not_applied_change() -> None:
    service = RoutingDecisionService()

    result = service.plan_routing([_excellent_result()])

    assert len(result.planned_changes) >= 1
    assert len(result.applied_changes) == 0


def test_plan_routing_aggregates_all_outcomes() -> None:
    service = RoutingDecisionService()
    results = [
        _excellent_result("a"),
        _medium_result("b"),
        _bad_with_objective("c"),
        _bad_with_heuristic("d"),
        _unknown_result("e"),
    ]

    result = service.plan_routing(results)

    assert result.summary["approved_count"] == 2
    assert result.summary["rejected_count"] == 1
    assert result.summary["quarantine_count"] == 1
    assert result.summary["review_count"] == 1


def test_routing_service_does_not_create_files(tmp_path) -> None:
    service = RoutingDecisionService()

    service.plan_routing([_excellent_result()])

    assert list(tmp_path.iterdir()) == []


def test_routing_service_does_not_move_files(tmp_path) -> None:
    service = RoutingDecisionService()

    service.plan_routing([_excellent_result()])

    assert list(tmp_path.iterdir()) == []


def test_routing_service_does_not_delete_files(tmp_path) -> None:
    service = RoutingDecisionService()

    service.plan_routing([_bad_with_objective()])

    assert list(tmp_path.iterdir()) == []


def test_routing_service_does_not_access_network() -> None:
    from noqlen_flux.services import routing as routing_module

    source = inspect.getsource(routing_module)
    assert "requests" not in source
    assert "urllib" not in source
    assert "socket" not in source


def test_routing_service_does_not_depend_on_slskd() -> None:
    from noqlen_flux.services import routing as routing_module

    assert "slskd" not in routing_module.__file__
    for name in dir(routing_module):
        obj = getattr(routing_module, name, None)
        if hasattr(obj, "__module__"):
            assert "slskd" not in (getattr(obj, "__module__", "") or "")


def test_routing_service_does_not_use_print_or_input() -> None:
    from noqlen_flux.services import routing as routing_module

    source = inspect.getsource(routing_module)
    assert "print(" not in source
    assert "input(" not in source


def test_routing_service_does_not_call_download_or_transfer() -> None:
    from noqlen_flux.services import routing as routing_module

    source = inspect.getsource(routing_module)
    assert "DownloadPlanningService" not in source
    assert "TransferPlanningService" not in source
    assert "plan_download" not in source
    assert "plan_queue" not in source


def test_scoring_does_not_import_routing() -> None:
    from noqlen_flux.services import routing as routing_module
    from noqlen_flux.services import scoring as scoring_module

    source = inspect.getsource(scoring_module)
    assert "RoutingDecisionService" not in source
    assert "RoutingOutcome" not in source
    assert "RoutingDecision" not in source


def test_quality_does_not_execute_routing_automatically() -> None:
    from noqlen_flux.services import quality as quality_module

    source = inspect.getsource(quality_module)
    assert "RoutingDecisionService" not in source
    assert "RoutingOutcome" not in source
    assert "routing" not in source.lower()


def test_routing_does_not_alter_quality_result() -> None:
    service = RoutingDecisionService()
    qr = _excellent_result("item-1")
    original_dict = qr.to_dict()

    service.decide_quality_route(qr)

    assert qr.to_dict() == original_dict


def test_routing_decision_contains_reasons() -> None:
    service = RoutingDecisionService()

    decision = service.decide_quality_route(_excellent_result())

    assert len(decision.reasons) > 0
    assert decision.reasons[0].code == "grade-excellent"


def test_routing_decision_with_policy_override() -> None:
    service = RoutingDecisionService()
    policy = RoutingPolicy(
        name="strict_v1",
        version="1",
        description="Strict policy.",
        heuristic_warnings_route_to_review_or_quarantine=False,
    )

    decision = service.decide_quality_route(_medium_with_heuristic(), policy=policy)

    assert decision.outcome == RoutingOutcome.APPROVED
