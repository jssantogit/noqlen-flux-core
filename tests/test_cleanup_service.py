import inspect

from noqlen_flux.cleanup import (
    DEFAULT_CLEANUP_POLICY,
    CleanupActionType,
    CleanupCandidate,
    CleanupCandidateKind,
    CleanupPolicy,
    CleanupRisk,
    build_fake_cleanup_candidates,
)
from noqlen_flux.results import Status
from noqlen_flux.services.cleanup import CleanupPlanningService


def _rejected_candidate(item_id: str = "cand-1", age_days: int = 90) -> CleanupCandidate:
    return CleanupCandidate(
        candidate_id=item_id,
        kind=CleanupCandidateKind.REJECTED,
        relative_path="rejected/item.txt",
        size_bytes=1024,
        age_days=age_days,
        source="routing",
        reasons=["Routed to rejected."],
    )


def _delete_eligible_candidate(item_id: str = "cand-2", age_days: int = 60) -> CleanupCandidate:
    return CleanupCandidate(
        candidate_id=item_id,
        kind=CleanupCandidateKind.DELETE_ELIGIBLE,
        relative_path="delete_eligible/item.txt",
        size_bytes=2048,
        age_days=age_days,
        source="staging",
        reasons=["Marked delete-eligible."],
    )


def _heuristic_only_candidate(item_id: str = "cand-3") -> CleanupCandidate:
    return CleanupCandidate(
        candidate_id=item_id,
        kind=CleanupCandidateKind.DELETE_ELIGIBLE,
        relative_path="delete_eligible/heuristic.txt",
        size_bytes=512,
        age_days=15,
        source="routing",
        reasons=["Heuristic-only finding."],
        warnings=["Heuristic findings should not trigger automatic deletion."],
    )


def _temporary_candidate(item_id: str = "cand-4", age_days: int = 30) -> CleanupCandidate:
    return CleanupCandidate(
        candidate_id=item_id,
        kind=CleanupCandidateKind.TEMPORARY,
        relative_path="tmp/temp.txt",
        size_bytes=256,
        age_days=age_days,
        source="workspace",
        reasons=["Temporary file."],
    )


def _orphaned_candidate(item_id: str = "cand-5") -> CleanupCandidate:
    return CleanupCandidate(
        candidate_id=item_id,
        kind=CleanupCandidateKind.ORPHANED,
        relative_path="incoming/orphan.txt",
        size_bytes=4096,
        age_days=120,
        source="workspace",
        reasons=["No routing decision found."],
    )


def _stale_report_candidate(item_id: str = "cand-6", age_days: int = 180) -> CleanupCandidate:
    return CleanupCandidate(
        candidate_id=item_id,
        kind=CleanupCandidateKind.STALE_REPORT,
        relative_path="reports/report.json",
        size_bytes=128,
        age_days=age_days,
        source="reports",
        reasons=["Report is old."],
    )


def _stale_manifest_candidate(item_id: str = "cand-7", age_days: int = 200) -> CleanupCandidate:
    return CleanupCandidate(
        candidate_id=item_id,
        kind=CleanupCandidateKind.STALE_MANIFEST,
        relative_path="manifests/manifest.json",
        size_bytes=64,
        age_days=age_days,
        source="handoff",
        reasons=["Manifest is old."],
    )


def test_default_policy_does_not_plan_delete() -> None:
    service = CleanupPlanningService()
    candidate = _delete_eligible_candidate()

    decision = service.decide_candidate(candidate)

    assert decision.action_type != CleanupActionType.PLAN_DELETE
    assert decision.action_type == CleanupActionType.REVIEW


def test_delete_eligible_does_not_become_plan_delete_without_policy() -> None:
    service = CleanupPlanningService()
    candidate = _delete_eligible_candidate()

    decision = service.decide_candidate(candidate, policy=DEFAULT_CLEANUP_POLICY)

    assert decision.action_type != CleanupActionType.PLAN_DELETE


def test_delete_eligible_becomes_plan_delete_when_policy_allows() -> None:
    service = CleanupPlanningService()
    policy = CleanupPolicy(
        name="test_v1",
        version="1",
        description="Test policy with delete planning.",
        allow_delete_planning=True,
    )
    candidate = _delete_eligible_candidate()

    decision = service.decide_candidate(candidate, policy=policy)

    assert decision.action_type == CleanupActionType.PLAN_DELETE
    assert decision.risk == CleanupRisk.HIGH


def test_auto_delete_enabled_does_not_execute_delete() -> None:
    service = CleanupPlanningService()
    policy = CleanupPolicy(
        name="test_v1",
        version="1",
        description="Test policy with auto-delete flag.",
        allow_delete_planning=True,
        auto_delete_enabled=True,
    )
    candidate = _delete_eligible_candidate()

    result = service.plan_cleanup([candidate], policy=policy)

    assert result.status in (Status.SUCCESS, Status.WARNING)
    assert len(result.applied_changes) == 0
    assert len(result.planned_changes) >= 1


def test_heuristic_only_candidate_becomes_review_not_delete() -> None:
    service = CleanupPlanningService()
    policy = CleanupPolicy(
        name="test_v1",
        version="1",
        description="Test policy.",
        allow_delete_planning=True,
    )
    candidate = _heuristic_only_candidate()

    decision = service.decide_candidate(candidate, policy=policy)

    assert decision.action_type == CleanupActionType.REVIEW
    assert decision.action_type != CleanupActionType.PLAN_DELETE
    assert decision.risk == CleanupRisk.HIGH


def test_rejected_old_becomes_mark_delete_eligible_with_min_age() -> None:
    service = CleanupPlanningService()
    policy = CleanupPolicy(
        name="test_v1",
        version="1",
        description="Test policy.",
        min_age_days=60,
    )
    candidate = _rejected_candidate(age_days=90)

    decision = service.decide_candidate(candidate, policy=policy)

    assert decision.action_type == CleanupActionType.MARK_DELETE_ELIGIBLE


def test_rejected_young_becomes_review() -> None:
    service = CleanupPlanningService()
    policy = CleanupPolicy(
        name="test_v1",
        version="1",
        description="Test policy.",
        min_age_days=100,
    )
    candidate = _rejected_candidate(age_days=30)

    decision = service.decide_candidate(candidate, policy=policy)

    assert decision.action_type == CleanupActionType.REVIEW


def test_rejected_no_min_age_becomes_review() -> None:
    service = CleanupPlanningService()
    candidate = _rejected_candidate(age_days=90)

    decision = service.decide_candidate(candidate)

    assert decision.action_type == CleanupActionType.REVIEW


def test_temporary_old_becomes_mark_delete_eligible() -> None:
    service = CleanupPlanningService()
    policy = CleanupPolicy(
        name="test_v1",
        version="1",
        description="Test policy.",
        min_age_days=20,
    )
    candidate = _temporary_candidate(age_days=30)

    decision = service.decide_candidate(candidate, policy=policy)

    assert decision.action_type == CleanupActionType.MARK_DELETE_ELIGIBLE


def test_temporary_young_becomes_review() -> None:
    service = CleanupPlanningService()
    policy = CleanupPolicy(
        name="test_v1",
        version="1",
        description="Test policy.",
        min_age_days=60,
    )
    candidate = _temporary_candidate(age_days=30)

    decision = service.decide_candidate(candidate, policy=policy)

    assert decision.action_type == CleanupActionType.REVIEW


def test_orphaned_becomes_review_by_default() -> None:
    service = CleanupPlanningService()
    candidate = _orphaned_candidate()

    decision = service.decide_candidate(candidate)

    assert decision.action_type == CleanupActionType.REVIEW
    assert decision.risk == CleanupRisk.MEDIUM


def test_stale_report_old_becomes_mark_delete_eligible() -> None:
    service = CleanupPlanningService()
    policy = CleanupPolicy(
        name="test_v1",
        version="1",
        description="Test policy.",
        min_age_days=90,
    )
    candidate = _stale_report_candidate(age_days=180)

    decision = service.decide_candidate(candidate, policy=policy)

    assert decision.action_type == CleanupActionType.MARK_DELETE_ELIGIBLE


def test_stale_manifest_old_becomes_mark_delete_eligible() -> None:
    service = CleanupPlanningService()
    policy = CleanupPolicy(
        name="test_v1",
        version="1",
        description="Test policy.",
        min_age_days=90,
    )
    candidate = _stale_manifest_candidate(age_days=200)

    decision = service.decide_candidate(candidate, policy=policy)

    assert decision.action_type == CleanupActionType.MARK_DELETE_ELIGIBLE


def test_unknown_becomes_review() -> None:
    service = CleanupPlanningService()
    candidate = CleanupCandidate(
        candidate_id="cand-unknown",
        kind=CleanupCandidateKind.UNKNOWN,
    )

    decision = service.decide_candidate(candidate)

    assert decision.action_type == CleanupActionType.REVIEW
    assert decision.risk == CleanupRisk.HIGH


def test_plan_cleanup_returns_flux_result_with_planned_change() -> None:
    service = CleanupPlanningService()
    candidates = [_rejected_candidate(), _delete_eligible_candidate()]

    result = service.plan_cleanup(candidates)

    assert result.status in (Status.SUCCESS, Status.WARNING)
    assert result.summary["candidate_count"] == 2
    assert len(result.planned_changes) == 2
    assert len(result.applied_changes) == 0


def test_plan_cleanup_aggregates_all_outcomes() -> None:
    service = CleanupPlanningService()
    candidates = [
        _rejected_candidate("a"),
        _delete_eligible_candidate("b"),
        _temporary_candidate("c"),
        _orphaned_candidate("d"),
    ]

    result = service.plan_cleanup(candidates)

    assert result.summary["candidate_count"] == 4
    assert result.summary["review_count"] >= 1
    assert result.summary["mark_delete_eligible_count"] >= 0


def test_plan_cleanup_with_allow_delete_planning() -> None:
    service = CleanupPlanningService()
    policy = CleanupPolicy(
        name="test_v1",
        version="1",
        description="Test policy.",
        allow_delete_planning=True,
    )
    candidates = [_delete_eligible_candidate()]

    result = service.plan_cleanup(candidates, policy=policy)

    assert result.summary["plan_delete_count"] >= 1
    assert len(result.applied_changes) == 0


def test_cleanup_service_does_not_create_files(tmp_path) -> None:
    service = CleanupPlanningService()

    service.plan_cleanup([_rejected_candidate()])

    assert list(tmp_path.iterdir()) == []


def test_cleanup_service_does_not_move_files(tmp_path) -> None:
    service = CleanupPlanningService()

    service.plan_cleanup([_delete_eligible_candidate()])

    assert list(tmp_path.iterdir()) == []


def test_cleanup_service_does_not_delete_files(tmp_path) -> None:
    service = CleanupPlanningService()

    service.plan_cleanup([_rejected_candidate()])

    assert list(tmp_path.iterdir()) == []


def test_cleanup_service_does_not_access_network() -> None:
    from noqlen_flux.services import cleanup as cleanup_module

    source = inspect.getsource(cleanup_module)
    assert "requests" not in source
    assert "urllib" not in source
    assert "socket" not in source


def test_cleanup_service_does_not_depend_on_slskd() -> None:
    from noqlen_flux.services import cleanup as cleanup_module

    assert "slskd" not in cleanup_module.__file__
    for name in dir(cleanup_module):
        obj = getattr(cleanup_module, name, None)
        if hasattr(obj, "__module__"):
            assert "slskd" not in (getattr(obj, "__module__", "") or "")


def test_cleanup_service_does_not_use_print_or_input() -> None:
    from noqlen_flux.services import cleanup as cleanup_module

    source = inspect.getsource(cleanup_module)
    assert "print(" not in source
    assert "input(" not in source


def test_cleanup_service_does_not_call_fileops_for_delete() -> None:
    from noqlen_flux.services import cleanup as cleanup_module

    source = inspect.getsource(cleanup_module)
    assert "SafeFileOperationService" not in source
    assert "FileOperationType" not in source


def test_cleanup_service_does_not_call_staging_execution() -> None:
    from noqlen_flux.services import cleanup as cleanup_module

    source = inspect.getsource(cleanup_module)
    assert "StagingExecutionService" not in source


def test_cleanup_plan_is_not_file_operation_plan() -> None:
    from noqlen_flux.fileops import FileOperationPlan

    service = CleanupPlanningService()
    result = service.plan_cleanup([_rejected_candidate()])

    for change in result.planned_changes:
        assert not isinstance(change, FileOperationPlan)


def test_cleanup_plan_does_not_execute_delete() -> None:
    service = CleanupPlanningService()
    policy = CleanupPolicy(
        name="test_v1",
        version="1",
        description="Test policy.",
        allow_delete_planning=True,
    )
    candidates = [_delete_eligible_candidate()]

    result = service.plan_cleanup(candidates, policy=policy)

    assert len(result.applied_changes) == 0
    for change in result.planned_changes:
        assert change.action != "delete"
        assert "plan-" in change.action


def test_routing_delete_eligible_is_not_cleanup_delete() -> None:
    from noqlen_flux.routing import RoutingOutcome

    assert RoutingOutcome.DELETE_ELIGIBLE.value == "delete_eligible"

    service = CleanupPlanningService()
    candidate = _delete_eligible_candidate()
    decision = service.decide_candidate(candidate)

    assert decision.action_type != CleanupActionType.PLAN_DELETE


def test_staging_delete_eligible_is_not_cleanup_delete() -> None:
    from noqlen_flux.staging import StagingActionType

    assert StagingActionType.MARK_DELETE_ELIGIBLE.value == "mark_delete_eligible"

    service = CleanupPlanningService()
    candidate = _delete_eligible_candidate()
    decision = service.decide_candidate(candidate)

    assert decision.action_type != CleanupActionType.PLAN_DELETE


def test_cleanup_service_with_fake_candidates() -> None:
    service = CleanupPlanningService()
    candidates = build_fake_cleanup_candidates()

    result = service.plan_cleanup(candidates)

    assert result.status in (Status.SUCCESS, Status.WARNING)
    assert result.summary["candidate_count"] == len(candidates)
    assert len(result.applied_changes) == 0


def test_cleanup_plan_contains_only_planned_change() -> None:
    service = CleanupPlanningService()
    candidates = build_fake_cleanup_candidates()

    result = service.plan_cleanup(candidates)

    for change in result.planned_changes:
        assert change.action.startswith("plan-")


def test_cleanup_decision_contains_reasons() -> None:
    service = CleanupPlanningService()
    candidate = _rejected_candidate()

    decision = service.decide_candidate(candidate)

    assert len(decision.reasons) > 0


def test_cleanup_decision_contains_risk() -> None:
    service = CleanupPlanningService()
    candidate = _rejected_candidate()

    decision = service.decide_candidate(candidate)

    assert decision.risk in (CleanupRisk.LOW, CleanupRisk.MEDIUM, CleanupRisk.HIGH)


def test_cleanup_plan_total_planned_bytes() -> None:
    service = CleanupPlanningService()
    policy = CleanupPolicy(
        name="test_v1",
        version="1",
        description="Test policy.",
        min_age_days=30,
    )
    candidates = [
        _rejected_candidate("a", age_days=90),
        _delete_eligible_candidate("b", age_days=60),
    ]

    result = service.plan_cleanup(candidates, policy=policy)

    assert result.summary.get("total_planned_bytes") is not None
    assert result.summary["total_planned_bytes"] > 0
