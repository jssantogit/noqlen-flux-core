import pytest

from noqlen_flux.downloads import (
    DownloadConstraint,
    DownloadIntent,
    DownloadItem,
    DownloadPlan,
    DownloadPlanArtifact,
    DownloadRequest,
)
from noqlen_flux.results import PlannedChange
from noqlen_flux.search import CandidateFile, SearchCandidate


def test_download_intent_values() -> None:
    assert DownloadIntent.TRACK.value == "track"
    assert DownloadIntent.ALBUM.value == "album"


def test_download_item_valid() -> None:
    item = DownloadItem(
        item_id="item-1",
        candidate_id="candidate-1",
        filename="Example Track.flac",
        target_relative_path="candidate-1/Example Track.flac",
        size_bytes=12345678,
        locked=False,
    )

    assert item.item_id == "item-1"
    assert item.filename == "Example Track.flac"
    assert item.locked is False
    assert item.size_bytes == 12345678


def test_download_item_locked_defaults_false() -> None:
    item = DownloadItem(
        item_id="item-1",
        candidate_id="candidate-1",
        filename="Example Track.flac",
        target_relative_path="candidate-1/Example Track.flac",
    )

    assert item.locked is False


def test_download_item_serializes_safely() -> None:
    item = DownloadItem(
        item_id="item-1",
        candidate_id="candidate-1",
        filename="Example Track.flac",
        target_relative_path="candidate-1/Example Track.flac",
        metadata={"token": "placeholder-secret"},
    )

    payload = item.to_dict()

    assert payload["item_id"] == "item-1"
    assert payload["metadata"]["token"] == "[redacted]"


def test_download_item_requires_item_id() -> None:
    with pytest.raises(ValueError):
        DownloadItem(
            item_id="",
            candidate_id="candidate-1",
            filename="Example Track.flac",
            target_relative_path="candidate-1/Example Track.flac",
        )


def test_download_item_requires_filename() -> None:
    with pytest.raises(ValueError):
        DownloadItem(
            item_id="item-1",
            candidate_id="candidate-1",
            filename="",
            target_relative_path="candidate-1/Example Track.flac",
        )


def test_download_item_requires_target_relative_path() -> None:
    with pytest.raises(ValueError):
        DownloadItem(
            item_id="item-1",
            candidate_id="candidate-1",
            filename="Example Track.flac",
            target_relative_path="",
        )


def test_download_item_blocks_path_traversal() -> None:
    with pytest.raises(ValueError):
        DownloadItem(
            item_id="item-1",
            candidate_id="candidate-1",
            filename="Example Track.flac",
            target_relative_path="../escape/Example Track.flac",
        )


def test_download_item_blocks_absolute_path() -> None:
    with pytest.raises(ValueError):
        DownloadItem(
            item_id="item-1",
            candidate_id="candidate-1",
            filename="Example Track.flac",
            target_relative_path="/etc/passwd",
        )


def test_download_item_blocks_dot_segments() -> None:
    with pytest.raises(ValueError):
        DownloadItem(
            item_id="item-1",
            candidate_id="candidate-1",
            filename="Example Track.flac",
            target_relative_path="candidate-1/./Example Track.flac",
        )


def test_download_constraint_defaults() -> None:
    constraint = DownloadConstraint()

    assert constraint.max_files is None
    assert constraint.max_total_bytes is None
    assert constraint.allow_locked is False
    assert constraint.require_score_min is None
    assert constraint.allowed_extensions == set()


def test_download_constraint_normalizes_extensions() -> None:
    constraint = DownloadConstraint(allowed_extensions={"FLAC", "Mp3"})

    assert constraint.allowed_extensions == {"flac", "mp3"}


def test_download_constraint_requires_positive_max_files() -> None:
    with pytest.raises(ValueError):
        DownloadConstraint(max_files=0)


def test_download_constraint_requires_positive_max_total_bytes() -> None:
    with pytest.raises(ValueError):
        DownloadConstraint(max_total_bytes=0)


def test_download_constraint_requires_valid_score_min() -> None:
    with pytest.raises(ValueError):
        DownloadConstraint(require_score_min=-1.0)
    with pytest.raises(ValueError):
        DownloadConstraint(require_score_min=101.0)


def test_download_constraint_serializes_safely() -> None:
    constraint = DownloadConstraint(
        max_files=10,
        max_total_bytes=1000000,
        allow_locked=True,
        require_score_min=50.0,
        allowed_extensions={"flac"},
        metadata={"token": "placeholder-secret"},
    )

    payload = constraint.to_dict()

    assert payload["max_files"] == 10
    assert payload["allow_locked"] is True
    assert payload["metadata"]["token"] == "[redacted]"
    assert "flac" in payload["allowed_extensions"]


def test_download_request_valid() -> None:
    request = DownloadRequest(
        request_id="req-1",
        intent=DownloadIntent.TRACK,
        query="Example Artist - Example Track",
        candidate_id="candidate-1",
        candidate_files=[{"filename": "Example Track.flac", "extension": "flac"}],
    )

    assert request.request_id == "req-1"
    assert request.intent == DownloadIntent.TRACK
    assert request.candidate_id == "candidate-1"


def test_download_request_from_candidate() -> None:
    candidate = SearchCandidate(
        candidate_id="candidate-1",
        provider="fake",
        artist="Example Artist",
        title="Example Track",
        files=[CandidateFile(filename="Example Track.flac", extension="flac", size_bytes=12345678)],
    )

    request = DownloadRequest.from_candidate(
        candidate=candidate,
        intent=DownloadIntent.TRACK,
        query="Example Artist - Example Track",
    )

    assert request.candidate_id == "candidate-1"
    assert request.intent == DownloadIntent.TRACK
    assert len(request.candidate_files) == 1
    assert request.request_id


def test_download_request_from_candidate_with_score() -> None:
    candidate = SearchCandidate(
        candidate_id="candidate-1",
        provider="fake",
        artist="Example Artist",
        title="Example Track",
        files=[CandidateFile(filename="Example Track.flac", extension="flac")],
    )

    from noqlen_flux.scoring import CandidateRisk, CandidateScore

    score = CandidateScore(
        candidate_id="candidate-1",
        total=85.0,
        max_score=100.0,
        risk=CandidateRisk.LOW,
        confidence=0.85,
    )

    request = DownloadRequest.from_candidate(
        candidate=candidate,
        intent=DownloadIntent.TRACK,
        query="Example Artist - Example Track",
        score=score,
    )

    assert request.score_total == 85.0
    assert request.score_max == 100.0
    assert request.score_risk == "low"


def test_download_request_requires_query() -> None:
    with pytest.raises(ValueError):
        DownloadRequest(
            request_id="req-1",
            intent=DownloadIntent.TRACK,
            query="",
            candidate_id="candidate-1",
            candidate_files=[],
        )


def test_download_request_serializes_safely() -> None:
    request = DownloadRequest(
        request_id="req-1",
        intent=DownloadIntent.TRACK,
        query="Example Artist - Example Track",
        candidate_id="candidate-1",
        candidate_files=[{"filename": "Example Track.flac", "metadata": {"token": "secret"}}],
        metadata={"token": "request-secret"},
    )

    payload = request.to_dict()

    assert payload["metadata"]["token"] == "[redacted]"
    assert payload["candidate_files"][0]["metadata"]["token"] == "[redacted]"


def test_download_plan_valid() -> None:
    item = DownloadItem(
        item_id="item-1",
        candidate_id="candidate-1",
        filename="Example Track.flac",
        target_relative_path="candidate-1/Example Track.flac",
    )

    plan = DownloadPlan(
        plan_id="plan-1",
        request_id="req-1",
        candidate_id="candidate-1",
        intent=DownloadIntent.TRACK,
        items=[item],
        target_relative_root="incoming/tracks/candidate-1",
        total_size_bytes=12345678,
    )

    assert plan.plan_id == "plan-1"
    assert len(plan.items) == 1
    assert plan.blocked is False
    assert plan.block_reasons == []


def test_download_plan_blocked() -> None:
    plan = DownloadPlan(
        plan_id="plan-1",
        request_id="req-1",
        candidate_id="candidate-1",
        intent=DownloadIntent.TRACK,
        items=[],
        blocked=True,
        block_reasons=["candidate has no files"],
    )

    assert plan.blocked is True
    assert len(plan.block_reasons) == 1


def test_download_plan_serializes_safely() -> None:
    plan = DownloadPlan(
        plan_id="plan-1",
        request_id="req-1",
        candidate_id="candidate-1",
        intent=DownloadIntent.TRACK,
        items=[],
        metadata={"token": "placeholder-secret"},
    )

    payload = plan.to_dict()

    assert payload["metadata"]["token"] == "[redacted]"


def test_download_plan_contains_planned_change_not_applied_change() -> None:
    item = DownloadItem(
        item_id="item-1",
        candidate_id="candidate-1",
        filename="Example Track.flac",
        target_relative_path="candidate-1/Example Track.flac",
    )

    change = PlannedChange(
        action="plan-download",
        target=item.target_relative_path,
        reason="planned download item",
    )

    assert hasattr(change, "action")
    assert hasattr(change, "target")
    assert hasattr(change, "reason")
    assert not hasattr(change, "result")


def test_download_plan_artifact_valid() -> None:
    artifact = DownloadPlanArtifact(
        artifact_id="artifact-1",
        kind="download-plan",
        relative_path="plans/plan-1.json",
        description="Logical download plan",
    )

    assert artifact.artifact_id == "artifact-1"
    assert artifact.kind == "download-plan"


def test_download_plan_artifact_does_not_require_absolute_path() -> None:
    artifact = DownloadPlanArtifact(
        artifact_id="artifact-1",
        kind="download-plan",
        description="Logical download plan without path",
    )

    assert artifact.relative_path is None


def test_download_plan_artifact_serializes_safely() -> None:
    artifact = DownloadPlanArtifact(
        artifact_id="artifact-1",
        kind="download-plan",
        metadata={"token": "placeholder-secret"},
    )

    payload = artifact.to_dict()

    assert payload["metadata"]["token"] == "[redacted]"
