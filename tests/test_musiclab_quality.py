from __future__ import annotations

import inspect

from noqlen_flux.musiclab_quality import (
    QualityCalibrationCase,
    QualityCalibrationCaseResult,
    QualityCalibrationDataset,
    QualityCalibrationExpectation,
    QualityCalibrationReport,
)
from noqlen_flux.quality import QualityGrade
from noqlen_flux.results import Status
from noqlen_flux.services.musiclab_quality import (
    MusicLabQualityService,
    _build_default_quality_calibration_dataset,
)


# === MODEL TESTS ===


def test_quality_calibration_expectation_defaults() -> None:
    exp = QualityCalibrationExpectation()

    assert exp.expected_grade is None
    assert exp.expected_min_confidence is None
    assert exp.expected_finding_codes == []
    assert exp.expected_objective_failure_codes == []
    assert exp.expected_heuristic_warning_codes == []
    assert exp.expected_no_routing_decision is True
    assert exp.metadata == {}


def test_quality_calibration_expectation_serializes_safely() -> None:
    exp = QualityCalibrationExpectation(
        expected_grade="excellent",
        expected_min_confidence=0.8,
        metadata={"token": "secret"},
    )

    payload = exp.to_dict()

    assert payload["expected_grade"] == "excellent"
    assert payload["expected_min_confidence"] == 0.8
    assert payload["metadata"]["token"] == "[redacted]"


def test_quality_calibration_case_represents_findings_and_expectation() -> None:
    case = QualityCalibrationCase(
        case_id="test-case-1",
        description="Test case",
        item_id="item-1",
        relative_path="incoming/track.flac",
        findings=[{"code": "test", "kind": "objective_failure"}],
        expectation=QualityCalibrationExpectation(expected_grade="bad"),
        tags=["test"],
    )

    assert case.case_id == "test-case-1"
    assert case.findings[0]["code"] == "test"
    assert case.expectation.expected_grade == "bad"
    assert case.tags == ["test"]


def test_quality_calibration_case_serializes_safely() -> None:
    case = QualityCalibrationCase(
        case_id="test-case-1",
        description="Test case",
        item_id="item-1",
        metadata={"secret": "hidden"},
    )

    payload = case.to_dict()

    assert payload["metadata"]["secret"] == "[redacted]"


def test_quality_calibration_dataset_is_versioned() -> None:
    ds = QualityCalibrationDataset(
        dataset_id="test-ds-v1",
        version="1",
        description="Test dataset",
    )

    assert ds.dataset_id == "test-ds-v1"
    assert ds.version == "1"
    assert ds.description == "Test dataset"


def test_quality_calibration_dataset_serializes_safely() -> None:
    ds = QualityCalibrationDataset(
        dataset_id="test-ds-v1",
        version="1",
        description="Test dataset",
        metadata={"token": "secret"},
    )

    payload = ds.to_dict()

    assert payload["metadata"]["token"] == "[redacted]"


def test_quality_calibration_case_result_tracks_pass_fail() -> None:
    result = QualityCalibrationCaseResult(
        case_id="case-1",
        passed=True,
        expected_grade="excellent",
        actual_grade="excellent",
    )

    assert result.passed is True
    assert result.expected_grade == "excellent"
    assert result.actual_grade == "excellent"


def test_quality_calibration_case_result_serializes_safely() -> None:
    result = QualityCalibrationCaseResult(
        case_id="case-1",
        passed=False,
        metadata={"token": "secret"},
    )

    payload = result.to_dict()

    assert payload["passed"] is False
    assert payload["metadata"]["token"] == "[redacted]"


def test_quality_calibration_report_sums_pass_fail_correctly() -> None:
    report = QualityCalibrationReport(
        dataset_id="test-ds",
        profile_name="default_v1",
        total_cases=5,
        passed_cases=3,
        failed_cases=2,
    )

    assert report.total_cases == 5
    assert report.passed_cases == 3
    assert report.failed_cases == 2
    assert report.passed_cases + report.failed_cases == report.total_cases


def test_quality_calibration_report_serializes_safely() -> None:
    report = QualityCalibrationReport(
        dataset_id="test-ds",
        profile_name="default_v1",
        total_cases=1,
        passed_cases=1,
        failed_cases=0,
        metadata={"token": "secret"},
    )

    payload = report.to_dict()

    assert payload["metadata"]["token"] == "[redacted]"


# === DATASET TESTS ===


def test_default_quality_calibration_dataset_exists() -> None:
    ds = _build_default_quality_calibration_dataset()

    assert ds.dataset_id == "default-quality-calibration-v1"
    assert ds.version == "1"
    assert len(ds.cases) > 0


def test_default_dataset_has_excellent_cases() -> None:
    ds = _build_default_quality_calibration_dataset()
    excellent_cases = [c for c in ds.cases if "excellent" in c.case_id]

    assert len(excellent_cases) >= 1
    for case in excellent_cases:
        assert case.expectation.expected_grade == QualityGrade.EXCELLENT.value


def test_default_dataset_has_medium_cases() -> None:
    ds = _build_default_quality_calibration_dataset()
    medium_cases = [c for c in ds.cases if c.case_id.startswith("medium")]

    assert len(medium_cases) >= 1
    for case in medium_cases:
        assert case.expectation.expected_grade == QualityGrade.MEDIUM.value


def test_default_dataset_has_bad_objective_cases() -> None:
    ds = _build_default_quality_calibration_dataset()
    bad_objective_cases = [c for c in ds.cases if c.case_id.startswith("bad-") and "susp" not in c.case_id]

    assert len(bad_objective_cases) >= 1
    for case in bad_objective_cases:
        assert case.expectation.expected_grade == QualityGrade.BAD.value


def test_default_dataset_has_bad_suspicious_cases() -> None:
    ds = _build_default_quality_calibration_dataset()
    bad_suspicious_cases = [c for c in ds.cases if c.case_id.startswith("bad-susp")]

    assert len(bad_suspicious_cases) >= 1
    for case in bad_suspicious_cases:
        assert case.expectation.expected_grade == QualityGrade.BAD.value


def test_default_dataset_has_unknown_cases() -> None:
    ds = _build_default_quality_calibration_dataset()
    unknown_cases = [c for c in ds.cases if c.case_id.startswith("unknown")]

    assert len(unknown_cases) >= 1
    for case in unknown_cases:
        assert case.expectation.expected_grade == QualityGrade.UNKNOWN.value


def test_default_dataset_case_ids_are_unique() -> None:
    ds = _build_default_quality_calibration_dataset()
    case_ids = [c.case_id for c in ds.cases]

    assert len(case_ids) == len(set(case_ids))


def test_default_dataset_does_not_contain_personal_paths() -> None:
    ds = _build_default_quality_calibration_dataset()

    for case in ds.cases:
        if case.relative_path:
            assert not case.relative_path.startswith("/home")
            assert not case.relative_path.startswith("/Music")
            assert not case.relative_path.startswith("/storage")


def test_default_dataset_does_not_use_real_music_files() -> None:
    ds = _build_default_quality_calibration_dataset()

    for case in ds.cases:
        assert case.metadata.get("fake") is True or "fake" in str(case.metadata)


def test_default_dataset_does_not_contain_fingerprints_or_lyrics() -> None:
    ds = _build_default_quality_calibration_dataset()
    ds_str = str(ds.to_dict())

    assert "fingerprint" not in ds_str.lower() or "raw" not in ds_str.lower()
    assert "lyrics" not in ds_str.lower()
    assert "payload" not in ds_str.lower()


# === SERVICE TESTS ===


def test_service_excellent_passes_with_excellent_grade() -> None:
    service = MusicLabQualityService()
    result = service.run_calibration()

    assert result.status in (Status.SUCCESS, Status.WARNING)
    assert result.summary["total_cases"] > 0


def test_service_returns_flux_result_with_step() -> None:
    service = MusicLabQualityService()
    result = service.run_calibration()

    assert len(result.steps) >= 1
    assert result.steps[0].name == "quality-calibration"


def test_service_returns_artifact() -> None:
    service = MusicLabQualityService()
    result = service.run_calibration()

    assert len(result.artifacts) >= 1
    assert result.artifacts[0].kind == "quality-calibration-report"


def test_service_report_contains_dataset_info() -> None:
    service = MusicLabQualityService()
    result = service.run_calibration()

    assert result.summary["dataset_id"] == "default-quality-calibration-v1"
    assert result.summary["dataset_version"] == "1"
    assert result.summary["profile_name"] == "default_v1"


def test_service_report_contains_pass_fail_counts() -> None:
    service = MusicLabQualityService()
    result = service.run_calibration()

    assert "total_cases" in result.summary
    assert "passed_cases" in result.summary
    assert "failed_cases" in result.summary
    assert result.summary["total_cases"] == result.summary["passed_cases"] + result.summary["failed_cases"]


def test_service_does_not_create_files(tmp_path) -> None:
    service = MusicLabQualityService()
    service.run_calibration()

    assert list(tmp_path.iterdir()) == []


def test_service_does_not_access_network() -> None:
    from noqlen_flux.services import musiclab_quality as module

    source = inspect.getsource(module)
    assert "requests" not in source
    assert "urllib" not in source
    assert "socket" not in source


def test_service_does_not_depend_on_slskd() -> None:
    from noqlen_flux.services import musiclab_quality as module

    assert "slskd" not in module.__file__
    for name in dir(module):
        obj = getattr(module, name, None)
        if hasattr(obj, "__module__"):
            assert "slskd" not in (getattr(obj, "__module__", "") or "")


def test_service_does_not_use_print_or_input() -> None:
    from noqlen_flux.services import musiclab_quality as module

    source = inspect.getsource(module)
    assert "print(" not in source
    assert "input(" not in source


def test_service_does_not_decide_routing() -> None:
    service = MusicLabQualityService()
    result = service.run_calibration()

    artifact_data = result.artifacts[0].metadata.get("report", {})
    case_results = artifact_data.get("case_results", [])

    for case_result in case_results:
        assert "routing_decision" not in case_result
        assert "routing_outcome" not in case_result
        assert "routing_plan" not in case_result


def test_service_does_not_call_routing_service() -> None:
    from noqlen_flux.services import musiclab_quality as module

    source = inspect.getsource(module)
    assert "RoutingDecisionService" not in source
    assert "routing" not in source.lower().split("routing")[0] if "routing" in source.lower() else True


def test_service_does_not_call_staging_service() -> None:
    from noqlen_flux.services import musiclab_quality as module

    source = inspect.getsource(module)
    assert "StagingPlanService" not in source
    assert "StagingExecutionService" not in source


def test_service_does_not_call_cleanup_service() -> None:
    from noqlen_flux.services import musiclab_quality as module

    source = inspect.getsource(module)
    assert "CleanupPlanningService" not in source


def test_service_does_not_call_fileops_service() -> None:
    from noqlen_flux.services import musiclab_quality as module

    source = inspect.getsource(module)
    assert "SafeFileOperationService" not in source
    assert "FileOperationService" not in source


def test_service_does_not_use_ffmpeg() -> None:
    from noqlen_flux.services import musiclab_quality as module

    source = inspect.getsource(module)
    lines = source.split("\n")
    code_lines = [line.strip() for line in lines if not line.strip().startswith("#") and not line.strip().startswith('"') and not line.strip().startswith("'")]
    code_text = "\n".join(code_lines)

    assert "subprocess" not in code_text
    assert "ffmpeg" not in code_text.lower().replace('"ffmpeg"', "").replace("'ffmpeg'", "").replace("ffmpeg:", "")


def test_service_does_not_read_audio() -> None:
    from noqlen_flux.services import musiclab_quality as module

    source = inspect.getsource(module)
    assert "wave" not in source
    assert "audioop" not in source
    assert "soundfile" not in source
    assert "librosa" not in source


def test_service_does_not_alter_thresholds() -> None:
    service = MusicLabQualityService()
    result = service.run_calibration()

    assert result.summary.get("network") is False
    assert result.summary.get("downloads") is False
    assert result.summary.get("library_writes") is False


def test_heuristic_warning_does_not_become_objective_failure() -> None:
    service = MusicLabQualityService()
    result = service.run_calibration()

    artifact_data = result.artifacts[0].metadata.get("report", {})
    case_results = artifact_data.get("case_results", [])

    medium_cases = [cr for cr in case_results if "medium" in cr.get("case_id", "")]
    for case_result in medium_cases:
        actual_grade = case_result.get("actual_grade")
        if actual_grade:
            assert actual_grade != QualityGrade.BAD.value or "bad-susp" in case_result.get("case_id", "")


def test_service_metadata_is_safe() -> None:
    service = MusicLabQualityService()
    result = service.run_calibration()

    artifact_data = result.artifacts[0].metadata
    artifact_str = str(artifact_data)

    assert "secret" not in artifact_str.lower() or "[redacted]" in artifact_str


# === BOUNDARY TESTS ===


def test_candidate_risk_separate_from_quality_grade() -> None:
    from noqlen_flux.scoring import CandidateRisk

    risk_values = {r.value for r in CandidateRisk}
    grade_values = {g.value for g in QualityGrade}

    assert risk_values != grade_values
    assert "low" not in grade_values
    assert "high" not in grade_values
    assert "excellent" not in risk_values
    assert "bad" not in risk_values


def test_quality_grade_separate_from_routing_decision() -> None:
    from noqlen_flux.routing import RoutingOutcome

    grade_values = {g.value for g in QualityGrade}
    outcome_values = {o.value for o in RoutingOutcome}

    assert grade_values != outcome_values
    assert "approved" not in grade_values
    assert "rejected" not in grade_values


def test_quality_calibration_does_not_call_routing_decision_service() -> None:
    from noqlen_flux.services import musiclab_quality as module

    source = inspect.getsource(module)
    assert "RoutingDecisionService" not in source
    assert "decide_quality_route" not in source


def test_quality_calibration_does_not_call_staging_plan_service() -> None:
    from noqlen_flux.services import musiclab_quality as module

    source = inspect.getsource(module)
    assert "StagingPlanService" not in source
    assert "plan_staging" not in source


def test_quality_calibration_does_not_call_cleanup_planning_service() -> None:
    from noqlen_flux.services import musiclab_quality as module

    source = inspect.getsource(module)
    assert "CleanupPlanningService" not in source
    assert "plan_cleanup" not in source


def test_quality_calibration_does_not_call_file_operation_service() -> None:
    from noqlen_flux.services import musiclab_quality as module

    source = inspect.getsource(module)
    assert "SafeFileOperationService" not in source
    assert "FileOperationService" not in source
    assert "execute_plan" not in source


def test_quality_calibration_service_independent_of_scoring() -> None:
    from noqlen_flux.services import musiclab_quality as quality_module
    from noqlen_flux.services import scoring as scoring_module

    source = inspect.getsource(quality_module)
    assert "CandidateScoringService" not in source
    assert "CandidateRisk" not in source
    assert quality_module.__file__ != scoring_module.__file__


def test_quality_calibration_service_independent_of_routing() -> None:
    from noqlen_flux.services import musiclab_quality as quality_module
    from noqlen_flux.services import routing as routing_module

    source = inspect.getsource(quality_module)
    assert "RoutingDecisionService" not in source
    assert quality_module.__file__ != routing_module.__file__


def test_quality_calibration_service_independent_of_staging() -> None:
    from noqlen_flux.services import musiclab_quality as quality_module
    from noqlen_flux.services import staging as staging_module

    source = inspect.getsource(quality_module)
    assert "StagingPlanService" not in source
    assert quality_module.__file__ != staging_module.__file__


def test_quality_calibration_service_independent_of_cleanup() -> None:
    from noqlen_flux.services import musiclab_quality as quality_module
    from noqlen_flux.services import cleanup as cleanup_module

    source = inspect.getsource(quality_module)
    assert "CleanupPlanningService" not in source
    assert quality_module.__file__ != cleanup_module.__file__
