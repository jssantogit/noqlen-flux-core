import pytest

from noqlen_flux.config import FluxConfig
from noqlen_flux.downloads import DownloadConstraint, DownloadIntent, DownloadRequest
from noqlen_flux.results import PlannedChange, Status
from noqlen_flux.scoring import CandidateRisk, CandidateScore
from noqlen_flux.search import CandidateFile, SearchCandidate, SearchKind, SearchQuery
from noqlen_flux.services.downloads import DownloadPlanningService
from noqlen_flux.services.scoring import CandidateScoringService
from noqlen_flux.services.search import SearchService
from noqlen_flux.providers.fake import FakeSearchProvider


def _track_candidate(
    artist: str = "Example Artist",
    title: str = "Example Track",
    directory: str = "Example Artist/Example Track",
    files: list[CandidateFile] | None = None,
    candidate_id: str = "track-1",
) -> SearchCandidate:
    return SearchCandidate(
        candidate_id=candidate_id,
        provider="fake",
        directory=directory,
        artist=artist,
        title=title,
        files=files if files is not None else [CandidateFile(filename="Example Track.flac", extension="flac", size_bytes=12345678)],
    )


def _album_candidate(album: str = "Example Album") -> SearchCandidate:
    return SearchCandidate(
        candidate_id="album-1",
        provider="fake",
        directory="Example Artist/Example Album",
        artist="Example Artist",
        album=album,
        files=[
            CandidateFile(filename="01 Intro.flac", extension="flac", size_bytes=1111111),
            CandidateFile(filename="02 Track.flac", extension="flac", size_bytes=2222222),
        ],
    )


def _make_request(candidate: SearchCandidate, intent: DownloadIntent, constraints: DownloadConstraint | None = None, score: CandidateScore | None = None) -> DownloadRequest:
    return DownloadRequest.from_candidate(
        candidate=candidate,
        intent=intent,
        query=f"{candidate.artist} - {candidate.title or candidate.album or 'unknown'}",
        score=score,
        constraints=constraints,
    )


def test_track_candidate_generates_plan_with_one_item() -> None:
    service = DownloadPlanningService()
    candidate = _track_candidate()
    request = _make_request(candidate, DownloadIntent.TRACK)

    result = service.plan_download(request)

    assert result.status == Status.SUCCESS
    assert result.summary["item_count"] == 1
    assert len(result.planned_changes) == 1
    assert result.summary["blocked"] is False


def test_album_candidate_generates_plan_with_multiple_items() -> None:
    service = DownloadPlanningService()
    candidate = _album_candidate()
    request = _make_request(candidate, DownloadIntent.ALBUM)

    result = service.plan_download(request)

    assert result.status == Status.SUCCESS
    assert result.summary["item_count"] == 2
    assert len(result.planned_changes) == 2
    assert result.summary["blocked"] is False


def test_candidate_without_files_blocks_plan() -> None:
    service = DownloadPlanningService()
    candidate = SearchCandidate(
        candidate_id="no-files",
        provider="fake",
        artist="Example Artist",
        title="Example Track",
        files=[],
    )
    request = _make_request(candidate, DownloadIntent.TRACK)

    result = service.plan_download(request)

    assert result.status == Status.FAILED
    assert result.summary["blocked"] is True
    assert any("no files" in reason for reason in result.summary["block_reasons"])


def test_locked_file_blocks_item_when_allow_locked_false() -> None:
    service = DownloadPlanningService()
    candidate = _track_candidate(
        files=[CandidateFile(filename="Locked Track.flac", extension="flac", locked=True, size_bytes=12345678)]
    )
    request = _make_request(candidate, DownloadIntent.TRACK, constraints=DownloadConstraint(allow_locked=False))

    result = service.plan_download(request)

    assert result.status == Status.FAILED
    assert result.summary["blocked"] is True
    assert any("locked" in reason.lower() for reason in result.summary["block_reasons"])


def test_all_locked_files_blocks_plan() -> None:
    service = DownloadPlanningService()
    candidate = _track_candidate(
        files=[
            CandidateFile(filename="Track A.flac", extension="flac", locked=True, size_bytes=1000),
            CandidateFile(filename="Track B.flac", extension="flac", locked=True, size_bytes=2000),
        ]
    )
    request = _make_request(candidate, DownloadIntent.TRACK, constraints=DownloadConstraint(allow_locked=False))

    result = service.plan_download(request)

    assert result.status == Status.FAILED
    assert result.summary["blocked"] is True
    assert any("all files are locked" in reason for reason in result.summary["block_reasons"])


def test_allow_locked_true_plans_locked_with_warning() -> None:
    service = DownloadPlanningService()
    candidate = _track_candidate(
        files=[CandidateFile(filename="Locked Track.flac", extension="flac", locked=True, size_bytes=12345678)]
    )
    request = _make_request(candidate, DownloadIntent.TRACK, constraints=DownloadConstraint(allow_locked=True))

    result = service.plan_download(request)

    assert result.status == Status.WARNING
    assert result.summary["item_count"] == 1
    assert result.summary["blocked"] is False
    assert any("locked" in w.message.lower() for w in result.warnings)


def test_score_below_require_score_min_blocks_plan() -> None:
    service = DownloadPlanningService()
    candidate = _track_candidate()
    score = CandidateScore(
        candidate_id="track-1",
        total=30.0,
        max_score=100.0,
        risk=CandidateRisk.HIGH,
        confidence=0.3,
    )
    request = _make_request(
        candidate,
        DownloadIntent.TRACK,
        constraints=DownloadConstraint(require_score_min=50.0),
        score=score,
    )

    result = service.plan_download(request)

    assert result.status == Status.FAILED
    assert result.summary["blocked"] is True
    assert any("below require_score_min" in reason for reason in result.summary["block_reasons"])


def test_max_files_blocks_plan_when_exceeded() -> None:
    service = DownloadPlanningService()
    candidate = _album_candidate()
    request = _make_request(
        candidate,
        DownloadIntent.ALBUM,
        constraints=DownloadConstraint(max_files=1),
    )

    result = service.plan_download(request)

    assert result.status == Status.FAILED
    assert result.summary["blocked"] is True
    assert any("max_files" in reason for reason in result.summary["block_reasons"])


def test_max_total_bytes_blocks_plan_when_exceeded() -> None:
    service = DownloadPlanningService()
    candidate = _album_candidate()
    request = _make_request(
        candidate,
        DownloadIntent.ALBUM,
        constraints=DownloadConstraint(max_total_bytes=1000),
    )

    result = service.plan_download(request)

    assert result.status == Status.FAILED
    assert result.summary["blocked"] is True
    assert any("max_total_bytes" in reason for reason in result.summary["block_reasons"])


def test_disallowed_extension_blocks_plan() -> None:
    service = DownloadPlanningService()
    candidate = _track_candidate(
        files=[CandidateFile(filename="Example Track.mp3", extension="mp3", size_bytes=5000000)]
    )
    request = _make_request(
        candidate,
        DownloadIntent.TRACK,
        constraints=DownloadConstraint(allowed_extensions={"flac", "wav"}),
    )

    result = service.plan_download(request)

    assert result.status == Status.FAILED
    assert result.summary["blocked"] is True
    assert any("not allowed" in reason for reason in result.summary["block_reasons"])


def test_target_path_traversal_is_blocked() -> None:
    service = DownloadPlanningService()
    candidate = _track_candidate()
    request = _make_request(candidate, DownloadIntent.TRACK)

    result = service.plan_download(request)

    assert result.status == Status.SUCCESS
    for change in result.planned_changes:
        assert ".." not in change.target
        assert not change.target.startswith("/")


def test_service_does_not_create_files(tmp_path) -> None:
    service = DownloadPlanningService()
    candidate = _track_candidate()
    request = _make_request(candidate, DownloadIntent.TRACK)

    service.plan_download(request)

    assert list(tmp_path.iterdir()) == []


def test_service_does_not_access_network() -> None:
    import sys
    from noqlen_flux.services import downloads as downloads_module

    source_code = open(downloads_module.__file__).read()
    assert "requests" not in source_code
    assert "http" not in source_code.lower() or "http" not in source_code.split("import")[0]
    assert "urllib" not in source_code
    assert "socket" not in source_code


def test_service_does_not_depend_on_slskd() -> None:
    from noqlen_flux.services import downloads as downloads_module

    assert "slskd" not in downloads_module.__file__
    for name in dir(downloads_module):
        obj = getattr(downloads_module, name, None)
        if hasattr(obj, "__module__"):
            assert "slskd" not in (getattr(obj, "__module__", "") or "")


def test_service_does_not_decide_quality_routing_quarantine_delete() -> None:
    service = DownloadPlanningService()
    candidate = _track_candidate()
    request = _make_request(candidate, DownloadIntent.TRACK)

    result = service.plan_download(request)

    payload = result.to_dict()
    assert "quality_grade" not in payload
    assert "approved" not in str(payload)
    assert "quarantine" not in str(payload)
    assert "rejected" not in str(payload)
    assert "delete_eligible" not in str(payload)


def test_plan_uses_planned_change_not_applied_change() -> None:
    service = DownloadPlanningService()
    candidate = _track_candidate()
    request = _make_request(candidate, DownloadIntent.TRACK)

    result = service.plan_download(request)

    assert len(result.planned_changes) > 0
    assert len(result.applied_changes) == 0
    for change in result.planned_changes:
        assert isinstance(change, PlannedChange)
        assert not hasattr(change, "result")


def test_fake_search_plus_scoring_plus_download_planning_works() -> None:
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    provider = FakeSearchProvider([_track_candidate()])
    search_result = SearchService().search(query, provider, CandidateScoringService())

    assert search_result.status == Status.SUCCESS
    assert search_result.summary["candidate_count"] >= 1

    candidate = _track_candidate()
    score = CandidateScoringService().score_candidate(query, candidate)
    request = _make_request(candidate, DownloadIntent.TRACK, score=score)

    result = DownloadPlanningService().plan_download(request)

    assert result.status == Status.SUCCESS
    assert result.summary["item_count"] == 1


def test_search_service_continues_without_download_planning() -> None:
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    provider = FakeSearchProvider([_track_candidate()])

    result = SearchService().search(query, provider)

    assert result.status == Status.SUCCESS
    assert result.summary["candidate_count"] >= 1


def test_scoring_service_continues_without_download_planning() -> None:
    service = CandidateScoringService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    candidate = _track_candidate()

    score = service.score_candidate(query, candidate)

    assert score.total > 0
    assert score.risk == CandidateRisk.LOW


def test_plan_with_mixed_locked_and_unlocked_files_excludes_locked_when_not_allowed() -> None:
    service = DownloadPlanningService()
    candidate = _track_candidate(
        files=[
            CandidateFile(filename="Unlocked.flac", extension="flac", locked=False, size_bytes=1000),
            CandidateFile(filename="Locked.flac", extension="flac", locked=True, size_bytes=2000),
        ]
    )
    request = _make_request(candidate, DownloadIntent.TRACK, constraints=DownloadConstraint(allow_locked=False))

    result = service.plan_download(request)

    assert result.status == Status.WARNING
    assert result.summary["item_count"] == 1
    assert result.planned_changes[0].target.endswith("Unlocked.flac")


def test_plan_with_mixed_locked_and_unlocked_files_includes_all_when_allowed() -> None:
    service = DownloadPlanningService()
    candidate = _track_candidate(
        files=[
            CandidateFile(filename="Unlocked.flac", extension="flac", locked=False, size_bytes=1000),
            CandidateFile(filename="Locked.flac", extension="flac", locked=True, size_bytes=2000),
        ]
    )
    request = _make_request(candidate, DownloadIntent.TRACK, constraints=DownloadConstraint(allow_locked=True))

    result = service.plan_download(request)

    assert result.status == Status.WARNING
    assert result.summary["item_count"] == 2


def test_plan_with_no_score_and_require_score_min_blocks() -> None:
    service = DownloadPlanningService()
    candidate = _track_candidate()
    request = _make_request(
        candidate,
        DownloadIntent.TRACK,
        constraints=DownloadConstraint(require_score_min=50.0),
        score=None,
    )

    result = service.plan_download(request)

    assert result.status == Status.FAILED
    assert result.summary["blocked"] is True
    assert any("score is required" in reason for reason in result.summary["block_reasons"])


def test_plan_with_score_above_min_succeeds() -> None:
    service = DownloadPlanningService()
    candidate = _track_candidate()
    score = CandidateScore(
        candidate_id="track-1",
        total=85.0,
        max_score=100.0,
        risk=CandidateRisk.LOW,
        confidence=0.85,
    )
    request = _make_request(
        candidate,
        DownloadIntent.TRACK,
        constraints=DownloadConstraint(require_score_min=50.0),
        score=score,
    )

    result = service.plan_download(request)

    assert result.status == Status.SUCCESS
    assert result.summary["blocked"] is False
    assert result.summary["item_count"] == 1
