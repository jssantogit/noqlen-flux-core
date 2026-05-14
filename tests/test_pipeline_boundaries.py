"""End-to-end pipeline boundary tests for Noqlen Flux Core.

All tests use fake/lab data only. No real provider, no slskd, no network,
no real download, no real audio analysis, no Forge, no real delete.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

from noqlen_flux.cleanup import CleanupCandidate, CleanupCandidateKind
from noqlen_flux.config import FluxConfig
from noqlen_flux.downloads import (
    DownloadConstraint,
    DownloadIntent,
    DownloadItem,
    DownloadPlan,
    DownloadRequest,
)
from noqlen_flux.fileops import FileOperationPlan
from noqlen_flux.handoff import HandoffItem, HandoffItemStatus, HandoffItemType, HandoffManifest, HandoffPathRef, HandoffSource
from noqlen_flux.providers.fake import FakeSearchProvider
from noqlen_flux.providers.status import ProviderKind
from noqlen_flux.quality import QualityGrade, QualityResult
from noqlen_flux.results import AppliedChange, PlannedChange, Status
from noqlen_flux.routing import RoutingDecision, RoutingOutcome, RoutingPlan
from noqlen_flux.scoring import CandidateRisk
from noqlen_flux.search import CandidateFile, SearchCandidate, SearchKind, SearchQuery
from noqlen_flux.services.cleanup import CleanupPlanningService
from noqlen_flux.services.downloads import DownloadPlanningService
from noqlen_flux.services.fileops import SafeFileOperationService
from noqlen_flux.services.handoff import HandoffManifestService
from noqlen_flux.services.providers import ProviderService
from noqlen_flux.services.quality import QualityService
from noqlen_flux.services.routing import RoutingDecisionService
from noqlen_flux.services.scoring import CandidateScoringService
from noqlen_flux.services.search import SearchService
from noqlen_flux.services.staging import StagingPlanService
from noqlen_flux.services.staging_execution import StagingExecutionService
from noqlen_flux.services.transfers import TransferPlanningService
from noqlen_flux.staging import StagingPlan
from noqlen_flux.transfers import TransferPriority


def _fake_candidate(candidate_id: str = "fake-1") -> SearchCandidate:
    return SearchCandidate(
        candidate_id=candidate_id,
        provider="fake",
        artist="Example Artist",
        title="Example Track",
        files=[CandidateFile(filename="Example Track.flac", extension="flac")],
    )


def _fake_config(tmp_path: Path) -> FluxConfig:
    return FluxConfig(workspace_root=tmp_path)


def _make_quality_result(item_id: str, grade: QualityGrade) -> QualityResult:
    return QualityResult(
        item_id=item_id,
        grade=grade,
        findings=[],
        objective_failures=[],
        heuristic_warnings=[],
        diagnostics=[],
        confidence=0.95 if grade == QualityGrade.EXCELLENT else 0.5,
        metadata={},
    )


def _fake_download_plan() -> DownloadPlan:
    return DownloadPlan(
        plan_id=str(uuid.uuid4()),
        request_id=str(uuid.uuid4()),
        candidate_id="cand-1",
        intent=DownloadIntent.TRACK,
        items=[
            DownloadItem(
                item_id=str(uuid.uuid4()),
                candidate_id="cand-1",
                filename="Example Track.flac",
                target_relative_path="cand-1/Example Track.flac",
            ),
        ],
    )


def test_fake_pipeline_boundary_dry_run_has_no_destructive_effects(tmp_path: Path) -> None:
    config = _fake_config(tmp_path)
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")

    search_service = SearchService()
    scoring_service = CandidateScoringService()
    provider = FakeSearchProvider([_fake_candidate()])

    search_result = search_service.search(query, provider, scoring_service)
    assert search_result.status == Status.SUCCESS

    candidate = _fake_candidate()
    score = scoring_service.score_candidate(query, candidate)

    download_service = DownloadPlanningService()
    request = DownloadRequest(
        request_id=str(uuid.uuid4()),
        intent=DownloadIntent.TRACK,
        query="Example Artist - Example Track",
        candidate_id=candidate.candidate_id,
        candidate_files=[f.to_dict() for f in candidate.files],
        score_total=score.total,
        score_max=score.max_score,
        score_risk=score.risk.value,
        constraints=DownloadConstraint(),
    )
    download_result = download_service.plan_download(request, config)
    assert download_result.status == Status.SUCCESS

    transfer_service = TransferPlanningService()
    download_plan_obj = _fake_download_plan()
    transfer_result = transfer_service.plan_queue(download_plan_obj, TransferPriority.NORMAL)
    assert transfer_result.status == Status.SUCCESS

    provider_service = ProviderService()
    provider_result = provider_service.inspect_provider(provider)
    assert provider_result.status == Status.SUCCESS

    quality_service = QualityService()
    quality_result = quality_service.evaluate_fake_quality(
        item_id=candidate.candidate_id,
        relative_path="incoming/fake-1/Example Track.flac",
        grade=QualityGrade.EXCELLENT,
    )
    assert quality_result.status == Status.SUCCESS

    quality_obj = _make_quality_result(candidate.candidate_id, QualityGrade.EXCELLENT)

    routing_service = RoutingDecisionService()
    routing_result = routing_service.plan_routing([quality_obj])
    assert routing_result.status == Status.SUCCESS

    decisions = [
        RoutingDecision(
            item_id=d["item_id"],
            outcome=RoutingOutcome(d["outcome"]),
            action_type=d["action_type"],
        )
        for d in routing_result.summary["routing_plan"]["decisions"]
    ]
    routing_plan_obj = RoutingPlan(
        plan_id=routing_result.summary["routing_plan"]["plan_id"],
        decisions=decisions,
    )

    staging_service = StagingPlanService()
    staging_result = staging_service.plan_staging(routing_plan_obj)
    assert staging_result.status == Status.SUCCESS

    staging_items = staging_result.summary.get("staging_plan", {}).get("items", [])
    from noqlen_flux.staging import StagingItem, StagingArea, StagingActionType

    si_list = [
        StagingItem(
            item_id=s["item_id"],
            routing_outcome=s["routing_outcome"],
            target_area=StagingArea(s["target_area"]),
            target_relative_path=s.get("target_relative_path"),
            action_type=StagingActionType(s.get("action_type", "plan_only")),
        )
        for s in staging_items
    ]
    staging_plan_obj = StagingPlan(
        plan_id=staging_result.summary["plan_id"],
        items=si_list,
    )

    fileops_service = SafeFileOperationService()
    fileops_plan = fileops_service.plan_from_staging(staging_plan_obj, config)
    assert fileops_plan.status in (Status.SUCCESS, Status.WARNING)

    fileops_result = fileops_service.execute_plan(
        FileOperationPlan(plan_id=fileops_plan.summary["plan_id"], operations=[]),
        config,
        dry_run=True,
    )
    assert fileops_result.status in (Status.SUCCESS, Status.WARNING)

    staging_exec_service = StagingExecutionService()
    staging_exec_result = staging_exec_service.execute_staging_plan(
        staging_plan_obj, config, dry_run=True,
    )
    assert staging_exec_result.status in (Status.SUCCESS, Status.WARNING)

    handoff_service = HandoffManifestService()
    manifest = handoff_service.build_manifest(
        items=[
            HandoffItem(
                item_id="item-1",
                item_type=HandoffItemType.TRACK,
                status=HandoffItemStatus.APPROVED,
                path=HandoffPathRef(relative_path="approved/item-1.flac"),
            ),
        ],
        source=HandoffSource(name="noqlen-flux", version="1"),
    )
    validation = handoff_service.validate_manifest(manifest)
    assert validation.valid is True

    cleanup_service = CleanupPlanningService()
    cleanup_result = cleanup_service.plan_cleanup([
        CleanupCandidate(
            candidate_id="cleanup-1",
            kind=CleanupCandidateKind.REJECTED,
            relative_path="rejected/item-1.txt",
            age_days=90,
        ),
    ])
    assert cleanup_result.status in (Status.SUCCESS, Status.WARNING)

    all_results = [
        search_result, download_result, transfer_result, provider_result,
        quality_result, routing_result, staging_result,
        fileops_plan, fileops_result, staging_exec_result,
        cleanup_result,
    ]
    for r in all_results:
        assert r.applied_changes == []

    assert validation.valid is True


def test_candidate_risk_quality_grade_and_routing_decision_remain_separate() -> None:
    risk_values = {r.value for r in CandidateRisk}
    grade_values = {g.value for g in QualityGrade}
    outcome_values = {o.value for o in RoutingOutcome}

    assert "low" in risk_values
    assert "medium" in risk_values
    assert "high" in risk_values

    assert "excellent" in grade_values
    assert "bad" in grade_values
    assert "unknown" in grade_values

    assert "approved" in outcome_values
    assert "rejected" in outcome_values
    assert "quarantine" in outcome_values

    assert risk_values != grade_values
    assert risk_values != outcome_values
    assert grade_values != outcome_values


def test_routing_staging_and_fileops_boundaries_remain_separate(tmp_path: Path) -> None:
    config = _fake_config(tmp_path)

    quality_obj = _make_quality_result("test-1", QualityGrade.EXCELLENT)

    routing_service = RoutingDecisionService()
    routing_result = routing_service.plan_routing([quality_obj])
    assert routing_result.status == Status.SUCCESS
    assert routing_result.planned_changes
    for change in routing_result.planned_changes:
        assert isinstance(change, PlannedChange)
        assert not isinstance(change, AppliedChange)

    decisions = [
        RoutingDecision(
            item_id=d["item_id"],
            outcome=RoutingOutcome(d["outcome"]),
            action_type=d["action_type"],
        )
        for d in routing_result.summary["routing_plan"]["decisions"]
    ]
    routing_plan_obj = RoutingPlan(
        plan_id=routing_result.summary["routing_plan"]["plan_id"],
        decisions=decisions,
    )

    staging_service = StagingPlanService()
    staging_result = staging_service.plan_staging(routing_plan_obj)
    assert staging_result.status == Status.SUCCESS
    for change in staging_result.planned_changes:
        assert isinstance(change, PlannedChange)

    from noqlen_flux.staging import StagingItem, StagingArea, StagingActionType

    staging_items = [
        StagingItem(
            item_id=s["item_id"],
            routing_outcome=s["routing_outcome"],
            target_area=StagingArea(s["target_area"]),
            action_type=StagingActionType(s.get("action_type", "plan_only")),
        )
        for s in staging_result.summary["staging_plan"]["items"]
    ]
    staging_plan_obj = StagingPlan(plan_id=staging_result.summary["plan_id"], items=staging_items)

    fileops_service = SafeFileOperationService()
    fileops_result = fileops_service.execute_plan(
        FileOperationPlan(plan_id="test-plan", operations=[]),
        config,
        dry_run=True,
    )
    assert fileops_result.applied_changes == []


def test_cleanup_planning_never_executes_delete(tmp_path: Path) -> None:
    cleanup_service = CleanupPlanningService()

    candidates = [
        CleanupCandidate(
            candidate_id="delete-1",
            kind=CleanupCandidateKind.DELETE_ELIGIBLE,
            relative_path="delete_eligible/item.txt",
            size_bytes=1024,
            age_days=60,
            reasons=["Marked delete-eligible by staging policy."],
        ),
    ]

    result = cleanup_service.plan_cleanup(candidates)
    assert result.status in (Status.SUCCESS, Status.WARNING)
    assert result.applied_changes == []

    for change in result.planned_changes:
        assert isinstance(change, PlannedChange)
        assert "applied-delete" not in change.action


def test_handoff_manifest_does_not_call_forge() -> None:
    handoff_service = HandoffManifestService()

    manifest = handoff_service.build_manifest(
        items=[
            HandoffItem(
                item_id="item-1",
                item_type=HandoffItemType.TRACK,
                status=HandoffItemStatus.APPROVED,
                path=HandoffPathRef(relative_path="approved/item-1.flac"),
            ),
        ],
    )

    assert manifest.to_dict()["handoff_version"] == 1
    assert "forge" not in str(manifest.to_dict()).lower()

    forge_modules = [m for m in sys.modules if "forge" in m.lower()]
    assert len(forge_modules) == 0


def test_core_services_do_not_import_slskd() -> None:
    service_modules = [
        "noqlen_flux.services.search",
        "noqlen_flux.services.scoring",
        "noqlen_flux.services.downloads",
        "noqlen_flux.services.transfers",
        "noqlen_flux.services.providers",
        "noqlen_flux.services.quality",
        "noqlen_flux.services.routing",
        "noqlen_flux.services.staging",
        "noqlen_flux.services.staging_execution",
        "noqlen_flux.services.fileops",
        "noqlen_flux.services.handoff",
        "noqlen_flux.services.cleanup",
    ]

    for mod_name in service_modules:
        if mod_name in sys.modules:
            mod = sys.modules[mod_name]
        else:
            import importlib
            mod = importlib.import_module(mod_name)

        assert "slskd" not in (getattr(mod, "__file__", "") or "")
        for attr_name in dir(mod):
            obj = getattr(mod, attr_name, None)
            if hasattr(obj, "__module__"):
                assert "slskd" not in (getattr(obj, "__module__", "") or "")


def test_planned_change_used_in_dry_run_not_applied_change(tmp_path: Path) -> None:
    config = _fake_config(tmp_path)

    download_service = DownloadPlanningService()
    request = DownloadRequest(
        request_id="req-1",
        intent=DownloadIntent.TRACK,
        query="test",
        candidate_id="cand-1",
        candidate_files=[{"filename": "Track.flac", "extension": "flac"}],
        constraints=DownloadConstraint(),
    )
    download_result = download_service.plan_download(request, config)
    assert download_result.status == Status.SUCCESS
    for change in download_result.planned_changes:
        assert isinstance(change, PlannedChange)
    assert download_result.applied_changes == []

    transfer_service = TransferPlanningService()
    dp = _fake_download_plan()
    transfer_result = transfer_service.plan_queue(dp)
    assert transfer_result.status == Status.SUCCESS
    assert transfer_result.applied_changes == []

    quality_obj = _make_quality_result("q-1", QualityGrade.EXCELLENT)

    routing_service = RoutingDecisionService()
    routing_result = routing_service.plan_routing([quality_obj])
    assert routing_result.status == Status.SUCCESS
    assert routing_result.applied_changes == []

    decisions = [
        RoutingDecision(
            item_id=d["item_id"],
            outcome=RoutingOutcome(d["outcome"]),
            action_type=d["action_type"],
        )
        for d in routing_result.summary["routing_plan"]["decisions"]
    ]
    rp = RoutingPlan(plan_id=routing_result.summary["routing_plan"]["plan_id"], decisions=decisions)

    staging_service = StagingPlanService()
    staging_result = staging_service.plan_staging(rp)
    assert staging_result.status == Status.SUCCESS
    assert staging_result.applied_changes == []

    cleanup_service = CleanupPlanningService()
    cleanup_result = cleanup_service.plan_cleanup([
        CleanupCandidate(candidate_id="c-1", kind=CleanupCandidateKind.REJECTED),
    ])
    assert cleanup_result.status in (Status.SUCCESS, Status.WARNING)
    assert cleanup_result.applied_changes == []


def test_path_safety_blocks_traversal_and_absolute_in_pipeline(tmp_path: Path) -> None:
    config = _fake_config(tmp_path)

    download_service = DownloadPlanningService()

    request_with_traversal = DownloadRequest(
        request_id="req-bad-1",
        intent=DownloadIntent.TRACK,
        query="test",
        candidate_id="cand-bad",
        candidate_files=[{"filename": "../../../etc/passwd", "extension": "flac"}],
        constraints=DownloadConstraint(),
    )
    result = download_service.plan_download(request_with_traversal, config)
    assert result.status == Status.FAILED
    assert result.summary["blocked"] is True

    with pytest.raises(ValueError, match="Absolute paths"):
        HandoffPathRef(relative_path="/etc/passwd")

    with pytest.raises(ValueError, match="Path traversal"):
        HandoffPathRef(relative_path="../../../escape.txt")

    with pytest.raises(ValueError, match="Absolute paths"):
        CleanupCandidate(
            candidate_id="bad-1",
            kind=CleanupCandidateKind.REJECTED,
            relative_path="/etc/passwd",
        )

    with pytest.raises(ValueError, match="Path traversal"):
        CleanupCandidate(
            candidate_id="bad-2",
            kind=CleanupCandidateKind.REJECTED,
            relative_path="../escape.txt",
        )


def test_no_real_paths_in_test_data() -> None:
    forbidden_prefixes = ("/Music", "/storage", "/sdcard", "/home/", "/Downloads")

    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    candidate = _fake_candidate()

    assert not any(query.artist.startswith(p) for p in forbidden_prefixes)
    assert not any(query.title.startswith(p) for p in forbidden_prefixes)
    for f in candidate.files:
        assert not any(f.filename.startswith(p) for p in forbidden_prefixes)

    request = DownloadRequest(
        request_id="req-1",
        intent=DownloadIntent.TRACK,
        query="test",
        candidate_id="cand-1",
        candidate_files=[f.to_dict() for f in candidate.files],
    )
    assert not any(request.query.startswith(p) for p in forbidden_prefixes)


def test_no_real_provider_is_instantiated() -> None:
    provider = FakeSearchProvider([_fake_candidate()])

    assert provider.name == "fake"
    assert "slskd" not in provider.name.lower()

    health = provider.health()
    assert health.provider == "fake"
    assert health.kind == ProviderKind.FAKE


def test_fileops_dry_run_does_not_alter_filesystem(tmp_path: Path) -> None:
    config = _fake_config(tmp_path)

    (tmp_path / "incoming").mkdir()
    source_file = tmp_path / "incoming" / "source.txt"
    source_file.write_text("test content")

    from noqlen_flux.fileops import FileOperation, FileOperationType

    plan = FileOperationPlan(
        plan_id="plan-1",
        operations=[
            FileOperation(
                operation_id="op-1",
                operation_type=FileOperationType.COPY,
                source_relative_path="incoming/source.txt",
                target_relative_path="approved/source.txt",
                reason="test copy",
            ),
        ],
    )

    fileops_service = SafeFileOperationService()
    result = fileops_service.execute_plan(plan, config, dry_run=True)

    assert result.status in (Status.SUCCESS, Status.WARNING)

    target_file = tmp_path / "approved" / "source.txt"
    assert not target_file.exists()


def test_staging_execution_dry_run_does_not_alter_filesystem(tmp_path: Path) -> None:
    config = _fake_config(tmp_path)

    from noqlen_flux.staging import StagingActionType, StagingArea, StagingItem

    staging_plan = StagingPlan(
        plan_id="plan-1",
        items=[
            StagingItem(
                item_id="item-1",
                routing_outcome="approved",
                source_relative_path="incoming/item-1.txt",
                target_area=StagingArea.APPROVED,
                target_relative_path="approved/item-1.txt",
                action_type=StagingActionType.PLAN_ONLY,
            ),
        ],
    )

    staging_exec_service = StagingExecutionService()
    result = staging_exec_service.execute_staging_plan(staging_plan, config, dry_run=True)

    assert result.status in (Status.SUCCESS, Status.WARNING)
    assert result.summary["applied_count"] == 0


def test_quality_service_does_not_decide_routing_automatically(tmp_path: Path) -> None:
    quality_service = QualityService()
    quality_result = quality_service.evaluate_fake_quality(
        item_id="test-1",
        grade=QualityGrade.BAD,
        findings=[{"code": "simulated", "message": "test failure", "kind": "objective_failure", "severity": "error"}],
    )

    assert quality_result.summary["grade"] == "bad"
    assert "routing" not in quality_result.summary
    assert "staging" not in quality_result.summary

    quality_obj = _make_quality_result("test-1", QualityGrade.BAD)

    routing_service = RoutingDecisionService()
    decision = routing_service.decide_quality_route(quality_obj)

    assert decision.outcome in (RoutingOutcome.REJECTED, RoutingOutcome.REVIEW)
    assert decision.action_type.value == "plan_only"
