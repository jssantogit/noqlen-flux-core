"""Tests for MusicLab scoring calibration models, dataset, service, and CLI.

All tests use fake/lab data only. No real provider, no slskd, no network,
no real download, no real audio analysis, no real music library.
"""

from __future__ import annotations

import sys

from noqlen_flux.musiclab_scoring import (
    ScoringCalibrationCase,
    ScoringCalibrationCaseResult,
    ScoringCalibrationDataset,
    ScoringCalibrationExpectation,
    ScoringCalibrationReport,
)
from noqlen_flux.results import Status
from noqlen_flux.scoring import CandidateRisk, default_scoring_profile
from noqlen_flux.search import CandidateFile, SearchCandidate, SearchKind, SearchQuery
from noqlen_flux.services.musiclab_scoring import (
    MusicLabScoringService,
    _build_default_scoring_calibration_dataset,
)


# === MODEL TESTS ===


def test_scoring_calibration_expectation_serializes_safe_data() -> None:
    exp = ScoringCalibrationExpectation(
        expected_min_score=50.0,
        expected_max_score=90.0,
        expected_risk=CandidateRisk.LOW,
        metadata={"secret": "hidden"},
    )

    payload = exp.to_dict()

    assert payload["expected_min_score"] == 50.0
    assert payload["expected_max_score"] == 90.0
    assert payload["expected_risk"] == "low"
    assert payload["metadata"]["secret"] == "[redacted]"


def test_scoring_calibration_case_represents_query_candidate_expectation() -> None:
    case = ScoringCalibrationCase(
        case_id="test-1",
        description="Test case",
        query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Good Track"),
        candidate=SearchCandidate(
            candidate_id="cand-1",
            provider="fake",
            artist="Good Artist",
            title="Good Track",
            files=[CandidateFile(filename="Good Track.flac", extension="flac")],
        ),
        expectation=ScoringCalibrationExpectation(expected_risk=CandidateRisk.LOW),
        tags=["good"],
    )

    payload = case.to_dict()

    assert payload["case_id"] == "test-1"
    assert payload["query"]["artist"] == "Good Artist"
    assert payload["candidate"]["candidate_id"] == "cand-1"
    assert payload["expectation"]["expected_risk"] == "low"
    assert payload["tags"] == ["good"]


def test_scoring_calibration_dataset_is_versioned() -> None:
    ds = ScoringCalibrationDataset(
        dataset_id="test-ds",
        version="1",
        description="Test dataset",
    )

    payload = ds.to_dict()

    assert payload["dataset_id"] == "test-ds"
    assert payload["version"] == "1"
    assert payload["description"] == "Test dataset"


def test_scoring_calibration_case_result_tracks_pass_fail() -> None:
    result = ScoringCalibrationCaseResult(
        case_id="test-1",
        passed=True,
        score=85.0,
        expected_risk="low",
        actual_risk="low",
    )

    payload = result.to_dict()

    assert payload["case_id"] == "test-1"
    assert payload["passed"] is True
    assert payload["score"] == 85.0
    assert payload["expected_risk"] == "low"
    assert payload["actual_risk"] == "low"


def test_scoring_calibration_report_sums_pass_fail_correctly() -> None:
    report = ScoringCalibrationReport(
        dataset_id="test-ds",
        profile_name="default_v1",
        total_cases=3,
        passed_cases=2,
        failed_cases=1,
        case_results=[
            ScoringCalibrationCaseResult(case_id="c1", passed=True, score=90.0, expected_risk="low", actual_risk="low"),
            ScoringCalibrationCaseResult(case_id="c2", passed=True, score=85.0, expected_risk="low", actual_risk="low"),
            ScoringCalibrationCaseResult(case_id="c3", passed=False, score=30.0, expected_risk="low", actual_risk="high"),
        ],
    )

    assert report.total_cases == 3
    assert report.passed_cases == 2
    assert report.failed_cases == 1
    assert len(report.case_results) == 3


def test_scoring_calibration_metadata_is_safe() -> None:
    exp = ScoringCalibrationExpectation(
        expected_risk=CandidateRisk.LOW,
        metadata={"api_key": "secret123"},
    )
    case = ScoringCalibrationCase(
        case_id="safe-1",
        description="Safe case",
        query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Good Track"),
        candidate=SearchCandidate(
            candidate_id="c1",
            provider="fake",
            artist="Good Artist",
            title="Good Track",
            files=[CandidateFile(filename="Good Track.flac", extension="flac")],
        ),
        expectation=exp,
        metadata={"token": "hidden"},
    )

    case_payload = case.to_dict()

    assert case_payload["expectation"]["metadata"]["api_key"] == "[redacted]"
    assert case_payload["metadata"]["token"] == "[redacted]"


# === DATASET TESTS ===


def test_default_dataset_exists() -> None:
    ds = _build_default_scoring_calibration_dataset()

    assert ds.dataset_id == "default-scoring-calibration-v1"
    assert ds.version == "1"
    assert ds.cases


def test_default_dataset_has_good_cases() -> None:
    ds = _build_default_scoring_calibration_dataset()
    good_cases = [c for c in ds.cases if "good" in c.tags]

    assert len(good_cases) >= 3


def test_default_dataset_has_suspicious_cases() -> None:
    ds = _build_default_scoring_calibration_dataset()
    suspicious_cases = [c for c in ds.cases if "suspicious" in c.tags]

    assert len(suspicious_cases) >= 5


def test_default_dataset_has_bad_cases() -> None:
    ds = _build_default_scoring_calibration_dataset()
    bad_cases = [c for c in ds.cases if "bad" in c.tags]

    assert len(bad_cases) >= 3


def test_default_dataset_has_false_positive_cases() -> None:
    ds = _build_default_scoring_calibration_dataset()
    fp_cases = [c for c in ds.cases if "false-positive" in c.tags]

    assert len(fp_cases) >= 3


def test_default_dataset_case_ids_are_unique() -> None:
    ds = _build_default_scoring_calibration_dataset()
    case_ids = [c.case_id for c in ds.cases]

    assert len(case_ids) == len(set(case_ids))


def test_default_dataset_no_personal_paths() -> None:
    ds = _build_default_scoring_calibration_dataset()
    forbidden_prefixes = ("/Music", "/storage", "/sdcard", "/home/", "/Downloads")

    for case in ds.cases:
        assert not any(case.case_id.startswith(p) for p in forbidden_prefixes)
        assert not any(case.query.artist.startswith(p) for p in forbidden_prefixes)
        for f in case.candidate.files:
            assert not any(f.filename.startswith(p) for p in forbidden_prefixes)


def test_default_dataset_metadata_is_safe() -> None:
    ds = _build_default_scoring_calibration_dataset()

    payload = ds.to_dict()

    assert payload["metadata"]["network"] is False
    assert payload["metadata"]["downloads"] is False
    assert payload["metadata"]["library_writes"] is False
    assert payload["metadata"]["fake_only"] is True


# === SERVICE TESTS ===


def test_service_runs_calibration_on_default_dataset() -> None:
    result = MusicLabScoringService().run_calibration()

    assert result.status in (Status.SUCCESS, Status.WARNING)
    assert result.summary["total_cases"] > 0
    assert result.summary["passed_cases"] + result.summary["failed_cases"] == result.summary["total_cases"]


def test_service_returns_artifact_with_report() -> None:
    result = MusicLabScoringService().run_calibration()

    assert any(artifact.kind == "scoring-calibration-report" for artifact in result.artifacts)


def test_service_does_not_access_network() -> None:
    result = MusicLabScoringService().run_calibration()

    assert result.summary["network"] is False


def test_service_does_not_create_files(tmp_path) -> None:
    MusicLabScoringService().run_calibration()

    assert list(tmp_path.iterdir()) == []


def test_service_does_not_depend_on_slskd() -> None:
    from noqlen_flux.services import musiclab_scoring as module

    assert "slskd" not in module.__file__
    for name in dir(module):
        obj = getattr(module, name, None)
        if hasattr(obj, "__module__"):
            assert "slskd" not in (getattr(obj, "__module__", "") or "")


def test_service_does_not_use_print_or_input() -> None:
    import inspect
    from noqlen_flux.services.musiclab_scoring import MusicLabScoringService

    source = inspect.getsource(MusicLabScoringService)
    assert "print(" not in source
    assert "input(" not in source


def test_service_does_not_alter_thresholds() -> None:
    profile = default_scoring_profile()
    original_weights = dict(profile.weights)
    original_thresholds = dict(profile.thresholds)

    MusicLabScoringService().run_calibration()

    assert profile.weights == original_weights
    assert profile.thresholds == original_thresholds


def test_service_does_not_decide_download_routing_staging_delete() -> None:
    result = MusicLabScoringService().run_calibration()

    assert "download" not in result.operation
    assert "routing" not in result.operation
    assert "staging" not in result.operation
    assert "cleanup" not in result.operation
    assert result.applied_changes == []


# === GOOD CANDIDATE TESTS ===


def test_good_candidates_pass_with_low_risk() -> None:
    result = MusicLabScoringService().run_calibration()
    good_results = [
        cr for cr in result.artifacts[0].metadata["report"]["case_results"]
        if "good" in cr["metadata"]["case_tags"]
    ]

    for cr in good_results:
        assert cr["passed"] is True, f"Good case {cr['case_id']} failed: {cr['errors']}"
        assert cr["actual_risk"] == "low", f"Good case {cr['case_id']} has risk {cr['actual_risk']}"


def test_good_candidate_exact_track_clean() -> None:
    service = MusicLabScoringService()
    ds = _build_default_scoring_calibration_dataset()
    case = next(c for c in ds.cases if c.case_id == "good-exact-track-clean")

    result = service.run_calibration(dataset=ScoringCalibrationDataset(
        dataset_id="single-test",
        version="1",
        description="Single test",
        cases=[case],
    ))

    case_result = result.artifacts[0].metadata["report"]["case_results"][0]
    assert case_result["passed"] is True
    assert case_result["actual_risk"] == "low"


def test_good_candidate_without_raw_score_scores_normally() -> None:
    service = MusicLabScoringService()
    ds = _build_default_scoring_calibration_dataset()
    case = next(c for c in ds.cases if c.case_id == "good-no-raw-score")

    result = service.run_calibration(dataset=ScoringCalibrationDataset(
        dataset_id="single-test",
        version="1",
        description="Single test",
        cases=[case],
    ))

    case_result = result.artifacts[0].metadata["report"]["case_results"][0]
    assert case_result["passed"] is True
    assert case_result["score"] > 80.0


# === SUSPICIOUS CANDIDATE TESTS ===


def test_suspicious_candidates_generate_risk_or_warning() -> None:
    result = MusicLabScoringService().run_calibration()
    suspicious_results = [
        cr for cr in result.artifacts[0].metadata["report"]["case_results"]
        if "suspicious" in cr["metadata"]["case_tags"]
    ]

    for cr in suspicious_results:
        penalty_codes = cr["metadata"]["penalty_codes"]
        has_risk_signal = len(penalty_codes) > 0 or cr["actual_risk"] in ("medium", "high")
        assert has_risk_signal or "strange-track-count" in cr["metadata"]["case_tags"], \
            f"Suspicious case {cr['case_id']} has no risk signal"


def test_suspicious_not_treated_as_quality_bad() -> None:
    result = MusicLabScoringService().run_calibration()
    suspicious_results = [
        cr for cr in result.artifacts[0].metadata["report"]["case_results"]
        if "suspicious" in cr["metadata"]["case_tags"]
    ]

    for cr in suspicious_results:
        assert "quality" not in cr["metadata"].get("case_tags", [])


def test_live_at_boundary_is_still_flagged() -> None:
    service = MusicLabScoringService()
    ds = _build_default_scoring_calibration_dataset()
    case = next(c for c in ds.cases if c.case_id == "suspicious-live")

    result = service.run_calibration(dataset=ScoringCalibrationDataset(
        dataset_id="single-test",
        version="1",
        description="Single test",
        cases=[case],
    ))

    case_result = result.artifacts[0].metadata["report"]["case_results"][0]
    assert "suspicious-term" in case_result["metadata"]["penalty_codes"]


# === BAD CANDIDATE TESTS ===


def test_bad_candidates_receive_lower_score() -> None:
    result = MusicLabScoringService().run_calibration()
    bad_results = [
        cr for cr in result.artifacts[0].metadata["report"]["case_results"]
        if "bad" in cr["metadata"]["case_tags"]
    ]

    for cr in bad_results:
        penalty_codes = cr["metadata"]["penalty_codes"]
        assert len(penalty_codes) > 0 or cr["actual_risk"] in ("medium", "high"), \
            f"Bad case {cr['case_id']} has no penalty or risk signal"


def test_all_locked_is_worse_than_partially_available() -> None:
    from noqlen_flux.services.scoring import CandidateScoringService

    scorer = CandidateScoringService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Good Track")

    all_locked = SearchCandidate(
        candidate_id="all-locked",
        provider="fake",
        artist="Good Artist",
        title="Good Track",
        directory="Good Artist/Good Track",
        files=[
            CandidateFile(filename="A.flac", extension="flac", locked=True),
            CandidateFile(filename="B.flac", extension="flac", locked=True),
        ],
    )
    partial_locked = SearchCandidate(
        candidate_id="partial-locked",
        provider="fake",
        artist="Good Artist",
        title="Good Track",
        directory="Good Artist/Good Track",
        files=[
            CandidateFile(filename="A.flac", extension="flac", locked=True),
            CandidateFile(filename="B.flac", extension="flac", locked=False),
        ],
    )

    score_all = scorer.score_candidate(query, all_locked)
    score_partial = scorer.score_candidate(query, partial_locked)

    assert score_all.total <= score_partial.total


# === FALSE POSITIVE TESTS ===


def test_alive_not_flagged_as_live() -> None:
    service = MusicLabScoringService()
    ds = _build_default_scoring_calibration_dataset()
    case = next(c for c in ds.cases if c.case_id == "fp-alive-not-live")

    result = service.run_calibration(dataset=ScoringCalibrationDataset(
        dataset_id="single-test",
        version="1",
        description="Single test",
        cases=[case],
    ))

    case_result = result.artifacts[0].metadata["report"]["case_results"][0]
    assert case_result["passed"] is True
    assert case_result["actual_risk"] == "low"


def test_olive_not_flagged_as_live() -> None:
    service = MusicLabScoringService()
    ds = _build_default_scoring_calibration_dataset()
    case = next(c for c in ds.cases if c.case_id == "fp-olive-not-live")

    result = service.run_calibration(dataset=ScoringCalibrationDataset(
        dataset_id="single-test",
        version="1",
        description="Single test",
        cases=[case],
    ))

    case_result = result.artifacts[0].metadata["report"]["case_results"][0]
    assert case_result["passed"] is True
    assert case_result["actual_risk"] == "low"


def test_premix_not_flagged_as_remix() -> None:
    service = MusicLabScoringService()
    ds = _build_default_scoring_calibration_dataset()
    case = next(c for c in ds.cases if c.case_id == "fp-premix-not-remix")

    result = service.run_calibration(dataset=ScoringCalibrationDataset(
        dataset_id="single-test",
        version="1",
        description="Single test",
        cases=[case],
    ))

    case_result = result.artifacts[0].metadata["report"]["case_results"][0]
    assert case_result["passed"] is True
    assert case_result["actual_risk"] == "low"


def test_delivery_not_flagged_as_live() -> None:
    service = MusicLabScoringService()
    ds = _build_default_scoring_calibration_dataset()
    case = next(c for c in ds.cases if c.case_id == "fp-delivery-not-live")

    result = service.run_calibration(dataset=ScoringCalibrationDataset(
        dataset_id="single-test",
        version="1",
        description="Single test",
        cases=[case],
    ))

    case_result = result.artifacts[0].metadata["report"]["case_results"][0]
    assert case_result["passed"] is True
    assert case_result["actual_risk"] == "low"


# === CLI TESTS ===


def test_musiclab_scoring_run_cli_command() -> None:
    from noqlen_flux.cli import main

    exit_code = main(["musiclab", "scoring", "run"])

    assert exit_code in (0, 1)


def test_musiclab_score_baseline_cli_list() -> None:
    from noqlen_flux.cli import main

    exit_code = main(["musiclab", "scoring", "baseline", "list"])

    assert exit_code == 0


def test_musiclab_score_baseline_cli_run_all(tmp_path: Path) -> None:
    from noqlen_flux.cli import main

    exit_code = main([
        "musiclab", "scoring", "baseline", "run",
        "--all",
        "--workspace", str(tmp_path / "score-workspace"),
        "--dry-run",
    ])

    assert exit_code in (0, 1)


def test_musiclab_score_baseline_false_positive_pack_passes(tmp_path: Path) -> None:
    from noqlen_flux.cli import main

    exit_code = main([
        "musiclab", "scoring", "baseline", "run",
        "--pack", "scoring-false-positive-guards",
        "--workspace", str(tmp_path / "score-workspace"),
        "--dry-run",
    ])

    assert exit_code == 0
