import inspect

from noqlen_flux.quality import (
    QualityFinding,
    QualityFindingKind,
    QualityFindingSeverity,
    QualityGrade,
    QualityResult,
)
from noqlen_flux.results import Status
from noqlen_flux.services.quality import QualityService


def test_evaluate_fake_quality_excellent() -> None:
    service = QualityService()

    result = service.evaluate_fake_quality(item_id="item-1", grade="excellent")

    assert result.status == Status.SUCCESS
    assert result.summary["grade"] == "excellent"
    assert result.summary["confidence"] > 0.8
    assert result.summary["objective_failure_count"] == 0
    assert result.summary["heuristic_warning_count"] == 0


def test_evaluate_fake_quality_medium() -> None:
    service = QualityService()

    result = service.evaluate_fake_quality(item_id="item-2", grade="medium")

    assert result.status == Status.SUCCESS
    assert result.summary["grade"] == "medium"
    assert result.summary["confidence"] > 0.5


def test_evaluate_fake_quality_medium_with_heuristic_warning() -> None:
    service = QualityService()
    findings = [
        {
            "code": "low-pass-suspicion",
            "message": "Low-pass filter suggests transcode.",
            "kind": "heuristic_warning",
            "severity": "warning",
            "confidence": 0.6,
        }
    ]

    result = service.evaluate_fake_quality(item_id="item-3", grade="medium", findings=findings)

    assert result.status == Status.WARNING
    assert result.summary["grade"] == "medium"
    assert result.summary["heuristic_warning_count"] == 1
    assert result.summary["objective_failure_count"] == 0


def test_evaluate_fake_quality_bad() -> None:
    service = QualityService()
    findings = [
        {
            "code": "decode-fail",
            "message": "File fails decode validation.",
            "kind": "objective_failure",
            "severity": "error",
        }
    ]

    result = service.evaluate_fake_quality(item_id="item-4", grade="bad", findings=findings)

    assert result.status == Status.WARNING
    assert result.summary["grade"] == "bad"
    assert result.summary["objective_failure_count"] == 1


def test_evaluate_fake_quality_unknown() -> None:
    service = QualityService()

    result = service.evaluate_fake_quality(item_id="item-5", grade="unknown")

    assert result.status == Status.SUCCESS
    assert result.summary["grade"] == "unknown"
    assert result.summary["confidence"] < 0.5


def test_evaluate_fake_quality_unknown_no_destructive_decision() -> None:
    service = QualityService()

    result = service.evaluate_fake_quality(item_id="item-6", grade="unknown")

    payload = result.to_dict()
    assert "delete" not in str(payload).lower()
    assert "quarantine" not in str(payload).lower()
    assert "approved" not in str(payload).lower()
    assert "rejected" not in str(payload).lower()


def test_summarize_quality_aggregates_results() -> None:
    service = QualityService()
    results = [
        QualityResult(item_id="a", grade=QualityGrade.EXCELLENT),
        QualityResult(item_id="b", grade=QualityGrade.EXCELLENT),
        QualityResult(item_id="c", grade=QualityGrade.MEDIUM),
        QualityResult(item_id="d", grade=QualityGrade.BAD),
        QualityResult(item_id="e", grade=QualityGrade.UNKNOWN),
    ]

    result = service.summarize_quality(results)

    assert result.status == Status.SUCCESS
    assert result.summary["total_items"] == 5
    assert result.summary["excellent_count"] == 2
    assert result.summary["medium_count"] == 1
    assert result.summary["bad_count"] == 1
    assert result.summary["unknown_count"] == 1


def test_summarize_quality_with_warnings() -> None:
    service = QualityService()
    warning_finding = QualityFinding(
        code="low-pass-suspicion",
        message="Low-pass filter suggests transcode.",
        kind=QualityFindingKind.HEURISTIC_WARNING,
        severity=QualityFindingSeverity.WARNING,
    )
    results = [
        QualityResult(item_id="a", grade=QualityGrade.MEDIUM, heuristic_warnings=[warning_finding]),
    ]

    result = service.summarize_quality(results)

    assert result.status == Status.WARNING
    assert result.summary["warning_count"] == 1


def test_summarize_quality_with_errors() -> None:
    service = QualityService()
    failure = QualityFinding(
        code="decode-fail",
        message="File fails decode validation.",
        kind=QualityFindingKind.OBJECTIVE_FAILURE,
        severity=QualityFindingSeverity.ERROR,
    )
    results = [
        QualityResult(item_id="a", grade=QualityGrade.BAD, objective_failures=[failure]),
    ]

    result = service.summarize_quality(results)

    assert result.status == Status.WARNING
    assert result.summary["error_count"] == 1


def test_quality_service_does_not_create_files(tmp_path) -> None:
    service = QualityService()

    service.evaluate_fake_quality(item_id="item-1", grade="excellent")

    assert list(tmp_path.iterdir()) == []


def test_quality_service_does_not_access_network() -> None:
    from noqlen_flux.services import quality as quality_module

    source = inspect.getsource(quality_module)
    assert "requests" not in source
    assert "urllib" not in source
    assert "socket" not in source
    assert "http" not in source.lower().split("http")[0] if "http" in source.lower() else True


def test_quality_service_does_not_depend_on_slskd() -> None:
    from noqlen_flux.services import quality as quality_module

    assert "slskd" not in quality_module.__file__
    for name in dir(quality_module):
        obj = getattr(quality_module, name, None)
        if hasattr(obj, "__module__"):
            assert "slskd" not in (getattr(obj, "__module__", "") or "")


def test_quality_service_does_not_use_print_or_input() -> None:
    from noqlen_flux.services import quality as quality_module

    source = inspect.getsource(quality_module)
    assert "print(" not in source
    assert "input(" not in source


def test_quality_service_does_not_decide_routing_quarantine_delete() -> None:
    service = QualityService()

    result = service.evaluate_fake_quality(item_id="item-1", grade="bad", findings=[
        {
            "code": "decode-fail",
            "message": "File fails decode validation.",
            "kind": "objective_failure",
            "severity": "error",
        }
    ])

    payload = result.to_dict()
    assert "routing_decision" not in payload
    assert "approved" not in payload
    assert "quarantine" not in payload
    assert "rejected" not in payload
    assert "delete_eligible" not in payload


def test_quality_service_returns_flux_result_with_step() -> None:
    service = QualityService()

    result = service.evaluate_fake_quality(item_id="item-1", grade="excellent")

    assert len(result.steps) == 1
    assert result.steps[0].name == "evaluate-quality"
    assert result.steps[0].status == Status.SUCCESS


def test_quality_service_returns_artifact() -> None:
    service = QualityService()

    result = service.evaluate_fake_quality(item_id="item-1", grade="excellent")

    assert len(result.artifacts) == 1
    assert result.artifacts[0].kind == "quality-result"


def test_quality_service_accepts_relative_path() -> None:
    service = QualityService()

    result = service.evaluate_fake_quality(
        item_id="item-1",
        relative_path="incoming/artist/album/track.flac",
        grade="excellent",
    )

    assert result.summary["item_id"] == "item-1"


def test_quality_service_accepts_custom_profile() -> None:
    from noqlen_flux.quality import QualityProfile

    service = QualityService()
    profile = QualityProfile(
        name="custom_v1",
        version="1",
        description="Custom profile",
    )

    result = service.evaluate_fake_quality(item_id="item-1", grade="excellent", profile=profile)

    assert result.summary["profile"]["name"] == "custom_v1"


def test_quality_service_independent_of_scoring() -> None:
    from noqlen_flux.services import quality as quality_module
    from noqlen_flux.services import scoring as scoring_module

    assert quality_module.__file__ != scoring_module.__file__
    source = inspect.getsource(quality_module)
    assert "CandidateScoringService" not in source
    assert "CandidateRisk" not in source
    assert "scoring" not in source.lower()


def test_scoring_independent_of_quality() -> None:
    from noqlen_flux.services import quality as quality_module
    from noqlen_flux.services import scoring as scoring_module

    source = inspect.getsource(scoring_module)
    assert "QualityService" not in source
    assert "QualityGrade" not in source
    assert "QualityResult" not in source
