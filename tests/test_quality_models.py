from noqlen_flux.quality import (
    DEFAULT_QUALITY_PROFILE,
    QualityFinding,
    QualityFindingKind,
    QualityFindingSeverity,
    QualityGrade,
    QualityProfile,
    QualityResult,
    QualitySummary,
    default_quality_profile,
)


def test_quality_grade_enum_values() -> None:
    assert QualityGrade.EXCELLENT.value == "excellent"
    assert QualityGrade.MEDIUM.value == "medium"
    assert QualityGrade.BAD.value == "bad"
    assert QualityGrade.UNKNOWN.value == "unknown"


def test_quality_finding_severity_enum_values() -> None:
    assert QualityFindingSeverity.INFO.value == "info"
    assert QualityFindingSeverity.WARNING.value == "warning"
    assert QualityFindingSeverity.ERROR.value == "error"


def test_quality_finding_kind_enum_values() -> None:
    assert QualityFindingKind.OBJECTIVE_FAILURE.value == "objective_failure"
    assert QualityFindingKind.HEURISTIC_WARNING.value == "heuristic_warning"
    assert QualityFindingKind.DIAGNOSTIC.value == "diagnostic"
    assert QualityFindingKind.METADATA_SIGNAL.value == "metadata_signal"
    assert QualityFindingKind.UNKNOWN.value == "unknown"


def test_quality_finding_separates_objective_from_heuristic() -> None:
    objective = QualityFinding(
        code="decode-fail",
        message="File fails decode validation.",
        kind=QualityFindingKind.OBJECTIVE_FAILURE,
        severity=QualityFindingSeverity.ERROR,
    )
    heuristic = QualityFinding(
        code="low-pass-suspicion",
        message="Low-pass filter suggests transcode.",
        kind=QualityFindingKind.HEURISTIC_WARNING,
        severity=QualityFindingSeverity.WARNING,
    )

    assert objective.kind == QualityFindingKind.OBJECTIVE_FAILURE
    assert heuristic.kind == QualityFindingKind.HEURISTIC_WARNING
    assert objective.kind != heuristic.kind


def test_quality_finding_serializes_safely() -> None:
    finding = QualityFinding(
        code="test",
        message="Test finding",
        kind=QualityFindingKind.DIAGNOSTIC,
        severity=QualityFindingSeverity.INFO,
        confidence=0.9,
        metadata={"token": "placeholder-secret"},
    )

    payload = finding.to_dict()

    assert payload["code"] == "test"
    assert payload["kind"] == "diagnostic"
    assert payload["confidence"] == 0.9
    assert payload["metadata"]["token"] == "[redacted]"


def test_quality_result_bad_with_objective_failure_no_delete() -> None:
    failure = QualityFinding(
        code="decode-fail",
        message="File fails decode validation.",
        kind=QualityFindingKind.OBJECTIVE_FAILURE,
        severity=QualityFindingSeverity.ERROR,
    )
    result = QualityResult(
        item_id="item-1",
        grade=QualityGrade.BAD,
        objective_failures=[failure],
        findings=[failure],
    )

    payload = result.to_dict()

    assert payload["grade"] == "bad"
    assert payload["objective_failures"][0]["code"] == "decode-fail"
    assert "delete" not in str(payload).lower()
    assert "quarantine" not in str(payload).lower()
    assert "approved" not in str(payload).lower()
    assert "rejected" not in str(payload).lower()


def test_quality_result_medium_with_heuristic_warning_not_bad() -> None:
    warning = QualityFinding(
        code="low-pass-suspicion",
        message="Low-pass filter suggests transcode.",
        kind=QualityFindingKind.HEURISTIC_WARNING,
        severity=QualityFindingSeverity.WARNING,
    )
    result = QualityResult(
        item_id="item-2",
        grade=QualityGrade.MEDIUM,
        heuristic_warnings=[warning],
        findings=[warning],
    )

    assert result.grade == QualityGrade.MEDIUM
    assert result.grade != QualityGrade.BAD


def test_quality_profile_is_versioned() -> None:
    profile = QualityProfile(
        name="test_v1",
        version="1",
        description="Test profile",
    )

    assert profile.name == "test_v1"
    assert profile.version == "1"
    assert profile.description == "Test profile"


def test_quality_profile_serializes_safely() -> None:
    profile = QualityProfile(
        name="test_v2",
        version="2",
        description="Test with secret",
        thresholds={"min_confidence": 0.5},
        metadata={"secret": "hidden"},
    )

    payload = profile.to_dict()

    assert payload["name"] == "test_v2"
    assert payload["version"] == "2"
    assert payload["metadata"]["secret"] == "[redacted]"


def test_quality_summary_counts_grades_correctly() -> None:
    results = [
        QualityResult(item_id="a", grade=QualityGrade.EXCELLENT),
        QualityResult(item_id="b", grade=QualityGrade.EXCELLENT),
        QualityResult(item_id="c", grade=QualityGrade.MEDIUM),
        QualityResult(item_id="d", grade=QualityGrade.BAD),
        QualityResult(item_id="e", grade=QualityGrade.UNKNOWN),
    ]
    summary = QualitySummary(
        total_items=len(results),
        excellent_count=sum(1 for r in results if r.grade == QualityGrade.EXCELLENT),
        medium_count=sum(1 for r in results if r.grade == QualityGrade.MEDIUM),
        bad_count=sum(1 for r in results if r.grade == QualityGrade.BAD),
        unknown_count=sum(1 for r in results if r.grade == QualityGrade.UNKNOWN),
    )

    assert summary.total_items == 5
    assert summary.excellent_count == 2
    assert summary.medium_count == 1
    assert summary.bad_count == 1
    assert summary.unknown_count == 1


def test_quality_summary_serializes_safely() -> None:
    summary = QualitySummary(
        total_items=3,
        excellent_count=1,
        medium_count=1,
        bad_count=1,
        metadata={"token": "placeholder-secret"},
    )

    payload = summary.to_dict()

    assert payload["total_items"] == 3
    assert payload["metadata"]["token"] == "[redacted]"


def test_default_quality_profile_exists() -> None:
    profile = default_quality_profile()

    assert profile.name == "default_v1"
    assert profile.version == "1"
    assert "post-download" in profile.metadata.get("stage", "")


def test_quality_grade_is_not_candidate_risk() -> None:
    from noqlen_flux.scoring import CandidateRisk

    assert "excellent" not in {r.value for r in CandidateRisk}
    assert "bad" not in {r.value for r in CandidateRisk}
    assert "unknown" not in {r.value for r in CandidateRisk}
    assert "low" not in {g.value for g in QualityGrade}
    assert "high" not in {g.value for g in QualityGrade}


def test_quality_result_does_not_contain_routing_decision() -> None:
    result = QualityResult(
        item_id="item-1",
        grade=QualityGrade.BAD,
        objective_failures=[
            QualityFinding(
                code="decode-fail",
                message="Fails decode.",
                kind=QualityFindingKind.OBJECTIVE_FAILURE,
                severity=QualityFindingSeverity.ERROR,
            )
        ],
    )

    payload = result.to_dict()

    assert "routing_decision" not in payload
    assert "approved" not in payload
    assert "quarantine" not in payload
    assert "rejected" not in payload
    assert "delete_eligible" not in payload


def test_quality_result_metadata_is_safe() -> None:
    result = QualityResult(
        item_id="item-1",
        grade=QualityGrade.EXCELLENT,
        metadata={"token": "secret", "password": "hidden", "fingerprint": "raw-data"},
    )

    payload = result.to_dict()

    assert payload["metadata"]["token"] == "[redacted]"
    assert payload["metadata"]["password"] == "[redacted]"
    assert payload["metadata"]["fingerprint"] == "[redacted]"


def test_quality_result_with_relative_path() -> None:
    result = QualityResult(
        item_id="item-1",
        grade=QualityGrade.EXCELLENT,
        relative_path="incoming/artist/album/track.flac",
    )

    assert result.relative_path == "incoming/artist/album/track.flac"
    payload = result.to_dict()
    assert payload["relative_path"] == "incoming/artist/album/track.flac"
