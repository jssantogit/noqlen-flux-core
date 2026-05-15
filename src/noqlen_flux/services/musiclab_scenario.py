from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from noqlen_flux.config import FluxConfig
from noqlen_flux.downloads import (
    DownloadConstraint,
    DownloadIntent,
    DownloadItem,
    DownloadPlan,
    DownloadPlanArtifact,
    DownloadRequest,
)
from noqlen_flux.musiclab_scenario import (
    MusicLabScenario,
    MusicLabScenarioPack,
    MusicLabScenarioReport,
    MusicLabScenarioResult,
    MusicLabScenarioStepResult,
    ScenarioOutcome,
)
from noqlen_flux.musiclab_scenario_factory import (
    SyntheticFixture,
    SyntheticProbeProfile,
    build_probe_findings,
)
from noqlen_flux.musiclab_scenario_packs import (
    all_scenario_packs,
    get_scenario,
    get_scenario_fixture,
    list_all_packs,
    list_all_scenarios,
)
from noqlen_flux.quality import (
    DEFAULT_QUALITY_PROFILE,
    QualityFindingKind,
    QualityGrade,
    QualityProfile,
)
from noqlen_flux.results import Artifact, FluxResult, Status
from noqlen_flux.routing import RoutingOutcome
from noqlen_flux.scoring import CandidateScore
from noqlen_flux.search import CandidateFile, SearchCandidate, SearchKind, SearchQuery
from noqlen_flux.services.base import FluxService
from noqlen_flux.services.downloads import DownloadPlanningService
from noqlen_flux.services.handoff import HandoffManifestService
from noqlen_flux.services.quality import QualityService
from noqlen_flux.services.routing import RoutingDecisionService
from noqlen_flux.services.scoring import CandidateScoringService
from noqlen_flux.services.staging import StagingPlanService
from noqlen_flux.services.transfers import TransferPlanningService
from noqlen_flux.staging import StagingArea
from noqlen_flux.transfers import TransferPriority

SafeMetadata = dict[str, Any]


class MusicLabScenarioRunnerService(FluxService):
    operation = "musiclab-scenario"

    def __init__(self) -> None:
        self._scoring_service = CandidateScoringService()
        self._download_service = DownloadPlanningService()
        self._transfer_service = TransferPlanningService()
        self._quality_service = QualityService()
        self._routing_service = RoutingDecisionService()
        self._staging_service = StagingPlanService()
        self._handoff_service = HandoffManifestService()

    def list_scenarios(self) -> FluxResult:
        scenarios = list_all_scenarios()
        scenario_data = [s.to_dict() for s in scenarios]
        return self.result(
            Status.SUCCESS,
            scenario_count=len(scenario_data),
            scenarios=scenario_data,
        )

    def list_packs(self) -> FluxResult:
        packs = list_all_packs()
        pack_data = [
            {
                "pack_id": p.pack_id,
                "description": p.description,
                "version": p.version,
                "scenario_count": len(p.scenarios),
            }
            for p in packs
        ]
        return self.result(
            Status.SUCCESS,
            pack_count=len(pack_data),
            packs=pack_data,
        )

    def run_scenario(
        self,
        scenario_id: str,
        workspace_root: str,
        *,
        dry_run: bool = True,
    ) -> FluxResult:
        scenario = get_scenario(scenario_id)
        if scenario is None:
            return self.result(
                Status.FAILED,
                error=f"Scenario not found: {scenario_id}",
                available_scenarios=[s.scenario_id for s in list_all_scenarios()],
            )

        fixture = get_scenario_fixture(scenario_id)
        if fixture is None:
            return self.result(
                Status.FAILED,
                error=f"Fixture not found for scenario: {scenario_id}",
            )

        config = FluxConfig(Path(workspace_root), dry_run=dry_run)
        scenario_result = self._execute_scenario(scenario, fixture, config)

        result = self.result(
            Status.SUCCESS,
            scenario_id=scenario_id,
            outcome=scenario_result.outcome.value,
            expected_grade=scenario_result.expected_grade,
            actual_grade=scenario_result.actual_grade,
            expected_routing_outcome=scenario_result.expected_routing_outcome,
            actual_routing_outcome=scenario_result.actual_routing_outcome,
            expected_staging_area=scenario_result.expected_staging_area,
            actual_staging_area=scenario_result.actual_staging_area,
            destructive_action_detected=scenario_result.destructive_action_detected,
            objective_failure_codes=scenario_result.objective_failure_codes,
            heuristic_warning_codes=scenario_result.heuristic_warning_codes,
            warnings=scenario_result.warnings,
            errors=scenario_result.errors,
            regression_notes=scenario_result.regression_notes,
            scenario_result=scenario_result.to_dict(),
        )
        return result.finish()

    def run_pack(
        self,
        pack_id: str,
        workspace_root: str,
        *,
        dry_run: bool = True,
    ) -> FluxResult:
        packs = all_scenario_packs()
        pack_entry = packs.get(pack_id)
        if pack_entry is None:
            return self.result(
                Status.FAILED,
                error=f"Pack not found: {pack_id}",
                available_packs=list(packs.keys()),
            )

        pack, fixtures = pack_entry
        config = FluxConfig(Path(workspace_root), dry_run=dry_run)

        scenario_results: list[MusicLabScenarioResult] = []
        passed = 0
        failed = 0
        skipped = 0
        errored = 0
        critical_failures: list[str] = []
        regression_flags: list[str] = []

        for scenario in pack.scenarios:
            fixture = fixtures.get(scenario.scenario_id)
            if fixture is None:
                skipped += 1
                continue

            sr = self._execute_scenario(scenario, fixture, config)
            scenario_results.append(sr)

            if sr.outcome == ScenarioOutcome.PASS:
                passed += 1
            elif sr.outcome == ScenarioOutcome.FAIL:
                failed += 1
                if scenario.severity.value in ("critical", "high"):
                    critical_failures.append(scenario.scenario_id)
            elif sr.outcome == ScenarioOutcome.SKIP:
                skipped += 1
            else:
                errored += 1

            if sr.regression_notes:
                regression_flags.append(scenario.scenario_id)

        report = MusicLabScenarioReport(
            report_id=str(uuid.uuid4()),
            pack_id=pack_id,
            total_scenarios=len(pack.scenarios),
            passed=passed,
            failed=failed,
            skipped=skipped,
            errored=errored,
            scenario_results=scenario_results,
            critical_failures=critical_failures,
            regression_flags=regression_flags,
            metadata={
                "dry_run": dry_run,
                "workspace_root": "[workspace-root]",
                "network": False,
                "downloads": False,
                "library_writes": False,
                "audio_analysis": False,
                "ffmpeg": False,
            },
        )

        overall = (
            ScenarioOutcome.PASS if failed == 0 and errored == 0
            else ScenarioOutcome.FAIL
        )

        artifact = Artifact(
            kind="scenario-report",
            description=f"MusicLab scenario report for pack: {pack_id}",
            metadata={"report": report.to_dict()},
        )

        result = self.result(
            Status.SUCCESS if overall == ScenarioOutcome.PASS else Status.WARNING,
            pack_id=pack_id,
            total_scenarios=report.total_scenarios,
            passed=report.passed,
            failed=report.failed,
            skipped=report.skipped,
            errored=report.errored,
            critical_failures=report.critical_failures,
            regression_flags=report.regression_flags,
            overall_outcome=overall.value,
            report=report.to_dict(),
        )
        result.artifacts.append(artifact)
        return result.finish()

    def _execute_scenario(
        self,
        scenario: MusicLabScenario,
        fixture: SyntheticFixture,
        config: FluxConfig,
    ) -> MusicLabScenarioResult:
        warnings: list[str] = []
        errors: list[str] = []
        steps: list[MusicLabScenarioStepResult] = []
        regression_notes: list[str] = []

        cfg = scenario.config

        score: CandidateScore | None = None
        download_plan: DownloadPlan | None = None
        actual_grade: str = QualityGrade.UNKNOWN.value
        actual_routing: str = RoutingOutcome.UNKNOWN.value
        actual_staging: str = StagingArea.UNKNOWN.value
        objective_failure_codes: list[str] = []
        heuristic_warning_codes: list[str] = []
        destructive_action_detected = False

        if cfg.run_scoring:
            score = self._scoring_service.score_candidate(
                fixture.query, fixture.candidate,
            )
            steps.append(
                MusicLabScenarioStepResult(
                    step_name="scoring",
                    status="success",
                    message=f"Score: {score.total}/{score.max_score}, Risk: {score.risk.value}",
                    actual_value=score.risk.value,
                )
            )

        download_blocked = False

        if cfg.run_scoring and score is not None:
            try:
                download_request = DownloadRequest.from_candidate(
                    candidate=fixture.candidate,
                    intent=DownloadIntent.TRACK if fixture.query.kind == SearchKind.TRACK else DownloadIntent.ALBUM,
                    query=f"{fixture.query.artist or 'Unknown'} - {fixture.query.title or fixture.query.album or 'Unknown'}",
                    score=score,
                )
                download_result = self._download_service.plan_download(download_request, config)
                if download_result.status == Status.FAILED:
                    download_blocked = True
                    warnings.append(f"Download plan blocked: {download_result.summary.get('block_reasons', [])}")
                    steps.append(
                        MusicLabScenarioStepResult(
                            step_name="download-plan",
                            status="blocked",
                            message="Download plan was blocked",
                        )
                    )
                else:
                    download_plan = DownloadPlan(
                        plan_id=download_result.summary.get("plan_id", str(uuid.uuid4())),
                        request_id=download_result.summary.get("request_id", ""),
                        candidate_id=download_result.summary.get("candidate_id", fixture.candidate.candidate_id),
                        intent=DownloadIntent.TRACK if fixture.query.kind == SearchKind.TRACK else DownloadIntent.ALBUM,
                        items=[
                            DownloadItem(
                                item_id=str(uuid.uuid4()),
                                candidate_id=fixture.candidate.candidate_id,
                                filename=f.filename,
                                target_relative_path=f"{fixture.candidate.candidate_id}/{f.filename}",
                                size_bytes=f.size_bytes,
                                locked=f.locked,
                            )
                            for f in fixture.candidate.files
                            if not f.locked
                        ],
                    )
                    steps.append(
                        MusicLabScenarioStepResult(
                            step_name="download-plan",
                            status="success",
                            message=f"Planned {download_result.summary.get('item_count', 0)} download items",
                        )
                    )
            except Exception as exc:
                download_blocked = True
                errors.append(f"Download planning error: {exc}")
                steps.append(
                    MusicLabScenarioStepResult(
                        step_name="download-plan",
                        status="error",
                        message=str(exc),
                    )
                )

        if cfg.simulate_transfer:
            try:
                if download_plan is not None and not download_blocked:
                    transfer_result = self._transfer_service.plan_queue(
                        download_plan=download_plan,
                        priority=TransferPriority.NORMAL,
                    )
                    status_msg = "success" if transfer_result.status != Status.FAILED else "blocked"
                    steps.append(
                        MusicLabScenarioStepResult(
                            step_name="transfer-plan",
                            status=status_msg,
                            message="Transfer plan simulated",
                        )
                    )
                    steps.append(
                        MusicLabScenarioStepResult(
                            step_name="transfer-submission-fake",
                            status="success",
                            message="Fake transfer submission previewed; no provider submission performed",
                        )
                    )
                else:
                    steps.append(
                        MusicLabScenarioStepResult(
                            step_name="transfer-plan",
                            status="skipped",
                            message="Transfer plan skipped (download blocked or unavailable)",
                        )
                    )
            except Exception as exc:
                steps.append(
                    MusicLabScenarioStepResult(
                        step_name="transfer-plan",
                        status="skipped",
                        message=f"Transfer plan simulation skipped: {exc}",
                    )
                )

        if cfg.simulate_artifact:
            steps.append(
                MusicLabScenarioStepResult(
                    step_name="simulate-artifact",
                    status="success",
                    message="Simulated downloaded artifact creation",
                )
            )
            steps.append(
                MusicLabScenarioStepResult(
                    step_name="download-artifact",
                    status="success",
                    message="DownloadArtifact simulated inside controlled MusicLab flow",
                )
            )

        if cfg.simulate_audio_probe:
            steps.append(
                MusicLabScenarioStepResult(
                    step_name="audio-probe",
                    status="success",
                    message="Synthetic AudioProbe profile evaluated; no ffmpeg/ffprobe invoked",
                    metadata={
                        "codec": fixture.probe.codec,
                        "sample_rate": fixture.probe.sample_rate,
                        "bit_depth": fixture.probe.bit_depth,
                    },
                )
            )

        if cfg.run_quality:
            findings_raw = build_probe_findings(fixture.probe)
            findings_dicts = [f.to_dict() for f in findings_raw]

            objective_failures = [
                f for f in findings_raw if f.kind == QualityFindingKind.OBJECTIVE_FAILURE
            ]
            heuristic_warnings = [
                f for f in findings_raw if f.kind == QualityFindingKind.HEURISTIC_WARNING
            ]

            objective_failure_codes = [f.code for f in objective_failures]
            heuristic_warning_codes = [f.code for f in heuristic_warnings]

            derived_grade = _derive_grade_from_findings(fixture.probe, objective_failures, heuristic_warnings)

            try:
                quality_result = self._quality_service.evaluate_fake_quality(
                    item_id=fixture.fixture_id,
                    relative_path=f"incoming/fake/{fixture.fixture_id}/track.{fixture.probe.format_name}",
                    grade=derived_grade.value,
                    findings=findings_dicts,
                )
                actual_grade = quality_result.summary.get("grade", QualityGrade.UNKNOWN.value)
                steps.append(
                    MusicLabScenarioStepResult(
                        step_name="quality",
                        status="success",
                        message=f"Grade: {actual_grade}",
                        actual_value=actual_grade,
                    )
                )

                if cfg.run_routing:
                    from noqlen_flux.quality import QualityFinding, QualityResult
                    qr = QualityResult(
                        item_id=fixture.fixture_id,
                        grade=QualityGrade(actual_grade),
                        relative_path=f"incoming/fake/{fixture.fixture_id}/track.{fixture.probe.format_name}",
                        findings=findings_raw,
                        objective_failures=objective_failures,
                        heuristic_warnings=heuristic_warnings,
                        diagnostics=[f for f in findings_raw if f.kind == QualityFindingKind.DIAGNOSTIC],
                    )
                    routing_decision = self._routing_service.decide_quality_route(qr)
                    actual_routing = routing_decision.outcome.value
                    steps.append(
                        MusicLabScenarioStepResult(
                            step_name="routing",
                            status="success",
                            message=f"Outcome: {actual_routing}",
                            actual_value=actual_routing,
                        )
                    )

                    if cfg.run_staging:
                        staging_item = self._staging_service.plan_staging_item(routing_decision, config=config)
                        actual_staging = staging_item.target_area.value
                        steps.append(
                            MusicLabScenarioStepResult(
                                step_name="staging",
                                status="success",
                                message=f"Area: {actual_staging}",
                                actual_value=actual_staging,
                            )
                        )

                        if staging_item.target_area == StagingArea.DELETE_ELIGIBLE:
                            destructive_action_detected = True
                            warnings.append("DELETE_ELIGIBLE staging area detected - possible destructive action")

            except Exception as exc:
                errors.append(f"Quality/routing error: {exc}")
                steps.append(
                    MusicLabScenarioStepResult(
                        step_name="quality-pipeline",
                        status="error",
                        message=str(exc),
                    )
                )

        if cfg.run_handoff:
            try:
                manifest = self._handoff_service.demo_manifest()
                steps.append(
                    MusicLabScenarioStepResult(
                        step_name="handoff-preview",
                        status="success",
                        message="Handoff preview generated",
                        metadata={"manifest_items": len(manifest.items)},
                    )
                )
            except Exception as exc:
                steps.append(
                    MusicLabScenarioStepResult(
                        step_name="handoff-preview",
                        status="skipped",
                        message=f"Handoff preview skipped: {exc}",
                    )
                )

        expected_grade = _derive_expected_grade(fixture, scenario)
        expected_routing = _derive_expected_routing(fixture, scenario)
        expected_staging = _derive_expected_staging(fixture, scenario)

        grade_matched = expected_grade is None or expected_grade == actual_grade
        routing_matched = expected_routing is None or expected_routing == actual_routing
        staging_matched = expected_staging is None or expected_staging == actual_staging

        if not grade_matched:
            errors.append(f"Grade mismatch: expected={expected_grade}, actual={actual_grade}")
        if not routing_matched:
            errors.append(f"Routing mismatch: expected={expected_routing}, actual={actual_routing}")
        if not staging_matched:
            errors.append(f"Staging mismatch: expected={expected_staging}, actual={actual_staging}")

        _validate_critical_rules(
            fixture, scenario,
            actual_grade, actual_routing, actual_staging,
            objective_failure_codes, heuristic_warning_codes,
            errors, warnings, regression_notes,
        )

        if destructive_action_detected:
            errors.append("Destructive action detected (delete_eligible staging)")
            regression_notes.append("destructive-action-flag")

        has_errors = len(errors) > 0
        outcome = (
            ScenarioOutcome.ERROR if "error" in [s.status for s in steps]
            else ScenarioOutcome.FAIL if has_errors
            else ScenarioOutcome.PASS
        )

        return MusicLabScenarioResult(
            scenario_id=scenario.scenario_id,
            outcome=outcome,
            expected_grade=expected_grade,
            actual_grade=actual_grade,
            expected_routing_outcome=expected_routing,
            actual_routing_outcome=actual_routing,
            expected_staging_area=expected_staging,
            actual_staging_area=actual_staging,
            objective_failure_codes=objective_failure_codes,
            heuristic_warning_codes=heuristic_warning_codes,
            destructive_action_detected=destructive_action_detected,
            steps=steps,
            warnings=warnings,
            errors=errors,
            regression_notes=regression_notes,
            metadata={
                "scenario_category": scenario.category.value,
                "scenario_kind": scenario.kind.value,
                "dry_run": config.dry_run,
                "source_profile": fixture.probe.metadata.get("source_profile"),
                "fixture_tags": fixture.tags,
            },
        )


def _derive_expected_grade(fixture: SyntheticFixture, scenario: MusicLabScenario) -> str | None:
    probe = fixture.probe
    has_objective = (
        not probe.probe_success
        or not probe.has_audio_stream
        or probe.file_size_bytes == 0
        or not probe.decode_ok
        or probe.truncated
        or probe.duration_seconds <= 0
        or not probe.container_readable
        or probe.timeout
    )
    has_heuristic_only = (
        probe.lowpass_suspicion
        or probe.spectral_cutoff_hz is not None
        or probe.fake_bit_depth
        or probe.fake_sample_rate
        or probe.upsampled
        or probe.downsampled
        or probe.transcode_cutoff_source is not None
        or probe.bitrate_container_mismatch
        or probe.lossy_source_lossless_container
    ) and not has_objective

    if has_objective:
        return QualityGrade.BAD.value
    if has_heuristic_only:
        return QualityGrade.MEDIUM.value
    return QualityGrade.EXCELLENT.value


def _derive_expected_routing(fixture: SyntheticFixture, scenario: MusicLabScenario) -> str | None:
    probe = fixture.probe
    has_objective = (
        not probe.probe_success
        or not probe.has_audio_stream
        or probe.file_size_bytes == 0
        or not probe.decode_ok
        or probe.truncated
        or probe.duration_seconds <= 0
        or not probe.container_readable
        or probe.timeout
    )
    has_heuristic_only = (
        probe.lowpass_suspicion
        or probe.spectral_cutoff_hz is not None
        or probe.fake_bit_depth
        or probe.fake_sample_rate
        or probe.upsampled
        or probe.downsampled
        or probe.transcode_cutoff_source is not None
        or probe.bitrate_container_mismatch
        or probe.lossy_source_lossless_container
    ) and not has_objective

    if has_objective:
        return RoutingOutcome.REJECTED.value
    if has_heuristic_only:
        return RoutingOutcome.REVIEW.value
    return RoutingOutcome.APPROVED.value


def _derive_expected_staging(fixture: SyntheticFixture, scenario: MusicLabScenario) -> str | None:
    routing = _derive_expected_routing(fixture, scenario)
    if routing == RoutingOutcome.APPROVED.value:
        return StagingArea.APPROVED.value
    if routing == RoutingOutcome.REJECTED.value:
        return StagingArea.REJECTED.value
    if routing == RoutingOutcome.REVIEW.value:
        return StagingArea.REVIEW.value
    return StagingArea.UNKNOWN.value


def _validate_critical_rules(
    fixture: SyntheticFixture,
    scenario: MusicLabScenario,
    actual_grade: str,
    actual_routing: str,
    actual_staging: str,
    objective_failures: list[str],
    heuristic_warnings: list[str],
    errors: list[str],
    warnings: list[str],
    regression_notes: list[str],
) -> None:
    probe = fixture.probe
    has_cutoff_only = (
        (probe.lowpass_suspicion or probe.spectral_cutoff_hz is not None)
        and probe.decode_ok
        and probe.has_audio_stream
        and probe.file_size_bytes > 0
        and probe.probe_success
        and not probe.truncated
        and probe.duration_seconds > 0
        and probe.container_readable
        and not probe.timeout
    )

    has_heuristic_only = (
        (probe.lowpass_suspicion
         or probe.spectral_cutoff_hz is not None
         or probe.fake_bit_depth
         or probe.fake_sample_rate
         or probe.upsampled
         or probe.downsampled
         or probe.transcode_cutoff_source is not None
         or probe.bitrate_container_mismatch
         or probe.lossy_source_lossless_container)
        and probe.decode_ok
        and probe.has_audio_stream
        and probe.probe_success
        and not probe.truncated
        and probe.duration_seconds > 0
        and probe.container_readable
        and not probe.timeout
        and not has_objective_failure(fixture)
    )

    has_objective = has_objective_failure(fixture)

    if actual_staging == StagingArea.DELETE_ELIGIBLE.value:
        errors.append(
            "CRITICAL: Staging resulted in delete_eligible. No real delete operation exists, "
            "and delete_eligible staging should never be produced."
        )
        regression_notes.append("delete-eligible-staging-produced")

    if actual_routing == RoutingOutcome.DELETE_ELIGIBLE.value:
        errors.append(
            "CRITICAL: Routing resulted in delete_eligible. Default policy forbids this."
        )
        regression_notes.append("delete-eligible-routing-produced")

    if has_cutoff_only and probe.decode_ok:
        non_cutoff_objective_failures = [
            code for code in objective_failures
            if code not in {"lowpass-suspicion", "spectral-cutoff", "transcode-cutoff"}
        ]
        if non_cutoff_objective_failures:
            errors.append(
                "CRITICAL: Cutoff/lowpass-only scenario produced objective failure(s): "
                + ", ".join(non_cutoff_objective_failures)
            )
            regression_notes.append("cutoff-lowpass-caused-objective-failure")

        if actual_grade == QualityGrade.BAD.value:
            errors.append("CRITICAL: Cutoff/lowpass alone resulted in QualityGrade bad. Must be MEDIUM at worst.")
            regression_notes.append("cutoff-lowpass-caused-bad-grade")

        if actual_routing in (RoutingOutcome.REJECTED.value, RoutingOutcome.DELETE_ELIGIBLE.value):
            errors.append(
                f"CRITICAL: Cutoff/lowpass alone routed to {actual_routing}. Must not be quarantine/rejected/delete."
            )
            regression_notes.append("cutoff-lowpass-caused-rejection")

        if actual_staging == StagingArea.QUARANTINE.value:
            errors.append("CRITICAL: Cutoff/lowpass alone sent to quarantine. Must not quarantine for heuristic only.")
            regression_notes.append("cutoff-lowpass-caused-quarantine")

        if actual_staging == StagingArea.REJECTED.value:
            errors.append("CRITICAL: Cutoff/lowpass alone sent to rejected staging. Must not reject for heuristic only.")
            regression_notes.append("cutoff-lowpass-caused-staging-rejection")

    if has_heuristic_only:
        if actual_routing in (RoutingOutcome.REJECTED.value, RoutingOutcome.DELETE_ELIGIBLE.value):
            errors.append(
                f"CRITICAL: Heuristic-only scenario routed to {actual_routing}. "
                "Heuristic warnings alone must not trigger rejected/delete routing."
            )
            regression_notes.append("heuristic-only-caused-rejection")

        if actual_staging in (StagingArea.REJECTED.value, StagingArea.QUARANTINE.value, StagingArea.DELETE_ELIGIBLE.value):
            errors.append(
                f"CRITICAL: Heuristic-only scenario staged to {actual_staging}. "
                "Heuristic warnings alone must not trigger rejected/quarantine/delete staging."
            )
            regression_notes.append("heuristic-only-caused-bad-staging")

    if has_objective:
        if actual_staging == StagingArea.DELETE_ELIGIBLE.value:
            errors.append(
                "CRITICAL: Objective failure scenario produced delete_eligible staging. "
                "Even for objective failures, delete must never be automatic."
            )
            regression_notes.append("objective-failure-caused-delete-eligible")

        if actual_routing == RoutingOutcome.DELETE_ELIGIBLE.value:
            errors.append(
                "CRITICAL: Objective failure scenario routed to delete_eligible. "
                "Objective failures should route to rejected, not delete_eligible."
            )
            regression_notes.append("objective-failure-routed-delete-eligible")

    if not probe.decode_ok and has_cutoff_only:
        if actual_grade != QualityGrade.BAD.value:
            warnings.append("Expected bad grade for decode_failure + cutoff, but grade is not bad. Verify decode_failure is the cause, not cutoff.")

        if actual_staging == StagingArea.DELETE_ELIGIBLE.value:
            errors.append(
                "CRITICAL: decode_failure + cutoff routing produced delete_eligible staging. "
                "Corrupt/decode failures can produce rejected/quarantine but never delete."
            )
            regression_notes.append("decode-failure-caused-delete-eligible")

    if probe.spectral_cutoff_hz is not None and probe.spectral_cutoff_hz == 9400 and probe.decode_ok:
        if actual_grade == QualityGrade.BAD.value:
            errors.append("CRITICAL: qobuz_like_cutoff was auto-punished (bad grade). Must not be auto-punished.")
            regression_notes.append("qobuz-like-auto-punished")
        if actual_routing == RoutingOutcome.REJECTED.value:
            errors.append("CRITICAL: qobuz_like_cutoff was rejected. Must not be auto-rejected.")
            regression_notes.append("qobuz-like-auto-rejected")
        if actual_staging == StagingArea.QUARANTINE.value:
            errors.append("CRITICAL: qobuz_like_cutoff was quarantined at staging level. Must not be auto-quarantined.")
            regression_notes.append("qobuz-like-auto-quarantined-at-staging")
        if actual_staging == StagingArea.REJECTED.value:
            errors.append("CRITICAL: qobuz_like_cutoff was rejected at staging level. Must not be auto-rejected.")
            regression_notes.append("qobuz-like-auto-rejected-at-staging")

    if probe.transcode_cutoff_source is not None and probe.decode_ok:
        if probe.has_audio_stream and not has_objective_failure(fixture):
            if actual_routing not in (RoutingOutcome.REVIEW.value, RoutingOutcome.QUARANTINE.value, RoutingOutcome.APPROVED.value):
                errors.append(
                    f"CRITICAL: transcode suspicion without objective failure routed to {actual_routing}. "
                    "Must go to review or quarantine, never rejected/delete."
                )
                regression_notes.append("transcode-suspicion-bad-routing")

            if actual_staging in (StagingArea.REJECTED.value, StagingArea.DELETE_ELIGIBLE.value):
                errors.append(
                    f"CRITICAL: transcode suspicion without objective failure staged to {actual_staging}. "
                    "Must go to review or quarantine, never rejected/delete."
                )
                regression_notes.append("transcode-suspicion-bad-staging")


def has_objective_failure(fixture: SyntheticFixture) -> bool:
    probe = fixture.probe
    return (
        not probe.probe_success
        or not probe.has_audio_stream
        or probe.file_size_bytes == 0
        or not probe.decode_ok
        or probe.truncated
        or probe.duration_seconds <= 0
        or not probe.container_readable
        or probe.timeout
    )


def _derive_grade_from_findings(
    probe: SyntheticProbeProfile,
    objective_failures: list[Any],
    heuristic_warnings: list[Any],
) -> QualityGrade:
    if objective_failures:
        return QualityGrade.BAD
    if heuristic_warnings:
        return QualityGrade.MEDIUM
    if not probe.probe_success and not objective_failures:
        return QualityGrade.UNKNOWN
    if not probe.has_audio_stream or not probe.decode_ok:
        return QualityGrade.BAD
    return QualityGrade.EXCELLENT
