from noqlen_flux.providers.fake import FakeSearchProvider
from noqlen_flux.results import Status
from noqlen_flux.scoring import CandidateRisk
from noqlen_flux.search import CandidateFile, SearchCandidate, SearchKind, SearchQuery
from noqlen_flux.services.scoring import CandidateScoringService
from noqlen_flux.services.search import SearchService


def test_exact_track_candidate_scores_higher_than_mismatch() -> None:
    service = CandidateScoringService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")

    good = service.score_candidate(query, _track_candidate())
    weak = service.score_candidate(query, _track_candidate(title="Different Track"))

    assert good.total > weak.total
    assert good.risk == CandidateRisk.LOW
    assert good.reasons


def test_exact_album_candidate_scores_higher_for_album_query() -> None:
    service = CandidateScoringService()
    query = SearchQuery(kind=SearchKind.ALBUM, artist="Example Artist", album="Example Album")

    good = service.score_candidate(query, _album_candidate())
    weak = service.score_candidate(query, _album_candidate(album="Different Album"))

    assert good.total > weak.total
    assert any(reason.code == "title-album-exact" for reason in good.reasons)


def test_candidate_without_files_gets_penalty() -> None:
    service = CandidateScoringService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    candidate = SearchCandidate(
        candidate_id="no-files",
        provider="fake",
        artist="Example Artist",
        title="Example Track",
        files=[],
    )

    score = service.score_candidate(query, candidate)

    assert any(penalty.code == "no-files" for penalty in score.penalties)
    assert score.risk in {CandidateRisk.MEDIUM, CandidateRisk.HIGH}


def test_locked_file_gets_warning_and_penalty() -> None:
    service = CandidateScoringService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    candidate = _track_candidate(files=[CandidateFile(filename="Example Track.flac", locked=True)])

    score = service.score_candidate(query, candidate)

    assert any(penalty.code == "locked-files" for penalty in score.penalties)
    assert any("locked" in warning.casefold() for warning in score.warnings)


def test_suspicious_terms_raise_risk() -> None:
    service = CandidateScoringService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    candidate = _track_candidate(
        directory="Example Artist/Example Track youtube web rip",
        files=[CandidateFile(filename="Example Track low quality.flac")],
    )

    score = service.score_candidate(query, candidate)

    assert score.risk == CandidateRisk.HIGH
    assert any(penalty.code == "suspicious-term" for penalty in score.penalties)


def test_good_candidate_is_low_risk_and_deterministic() -> None:
    service = CandidateScoringService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    candidate = _track_candidate()

    first = service.score_candidate(query, candidate)
    second = service.score_candidate(query, candidate)

    assert first.risk == CandidateRisk.LOW
    assert first.to_dict() == second.to_dict()


def test_score_candidates_returns_flux_result() -> None:
    service = CandidateScoringService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")

    result = service.score_candidates(query, [_track_candidate()])

    assert result.status == Status.SUCCESS
    assert result.summary["score_count"] == 1
    assert result.summary["scores"][0]["candidate_id"] == "track-1"


def test_scoring_service_does_not_create_files(tmp_path) -> None:
    service = CandidateScoringService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")

    service.score_candidate(query, _track_candidate())

    assert list(tmp_path.iterdir()) == []


def test_fake_track_search_with_scoring_returns_scores() -> None:
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    provider = FakeSearchProvider([_track_candidate()])

    result = SearchService().search(query, provider, CandidateScoringService())

    assert result.status == Status.SUCCESS
    assert result.summary["scores"][0]["risk"] == "low"


def test_fake_album_search_with_scoring_returns_scores() -> None:
    query = SearchQuery(kind=SearchKind.ALBUM, artist="Example Artist", album="Example Album")
    provider = FakeSearchProvider([_album_candidate()])

    result = SearchService().search(query, provider, CandidateScoringService())

    assert result.status == Status.SUCCESS
    assert result.summary["scores"][0]["candidate_id"] == "album-1"


def test_search_service_continues_without_scoring() -> None:
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    provider = FakeSearchProvider([_track_candidate()])

    result = SearchService().search(query, provider)

    assert result.status == Status.SUCCESS
    assert result.summary["scores"] == []


def _track_candidate(
    title: str = "Example Track",
    directory: str = "Example Artist/Example Track",
    files: list[CandidateFile] | None = None,
) -> SearchCandidate:
    return SearchCandidate(
        candidate_id="track-1",
        provider="fake",
        directory=directory,
        artist="Example Artist",
        title=title,
        files=files if files is not None else [CandidateFile(filename="Example Track.flac", extension="flac")],
    )


def _album_candidate(album: str = "Example Album") -> SearchCandidate:
    return SearchCandidate(
        candidate_id="album-1",
        provider="fake",
        directory="Example Artist/Example Album",
        artist="Example Artist",
        album=album,
        files=[CandidateFile(filename="01 Intro.flac", extension="flac"), CandidateFile(filename="02 Track.flac", extension="flac")],
    )
