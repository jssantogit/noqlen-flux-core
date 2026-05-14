from noqlen_flux.providers.fake import FakeSearchProvider
from noqlen_flux.results import Status
from noqlen_flux.scoring import CandidateRisk, CandidateScore, default_scoring_profile
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


def test_alive_is_not_flagged_as_live() -> None:
    service = CandidateScoringService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Pearl Jam", title="Alive")
    candidate = _track_candidate(artist="Pearl Jam", title="Alive", directory="Pearl Jam/Alive", files=[CandidateFile(filename="Alive.flac", extension="flac")])

    score = service.score_candidate(query, candidate)

    assert not any(penalty.code == "suspicious-term" for penalty in score.penalties)


def test_premix_is_not_flagged_as_remix() -> None:
    service = CandidateScoringService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Premix Track")
    candidate = _track_candidate(title="Premix Track", directory="Example Artist/Premix Track", files=[CandidateFile(filename="Premix Track.flac", extension="flac")])

    score = service.score_candidate(query, candidate)

    assert not any(penalty.code == "suspicious-term" for penalty in score.penalties)


def test_live_at_boundary_is_still_flagged() -> None:
    service = CandidateScoringService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    candidate = _track_candidate(directory="Example Artist/Live at Wembley", files=[CandidateFile(filename="Example Track - Live.flac", extension="flac")])

    score = service.score_candidate(query, candidate)

    assert any(penalty.code == "suspicious-term" for penalty in score.penalties)


def test_divergent_artist_scores_lower() -> None:
    service = CandidateScoringService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")

    good = service.score_candidate(query, _track_candidate())
    bad = service.score_candidate(query, _track_candidate(artist="Totally Different Artist", title="Example Track"))

    assert good.total > bad.total
    assert any(penalty.code == "artist-mismatch" for penalty in bad.penalties)


def test_divergent_title_scores_lower() -> None:
    service = CandidateScoringService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")

    good = service.score_candidate(query, _track_candidate())
    bad = service.score_candidate(query, _track_candidate(title="Completely Different Title"))

    assert good.total > bad.total
    assert any(penalty.code == "title-album-mismatch" for penalty in bad.penalties)


def test_all_files_locked_gets_penalty() -> None:
    service = CandidateScoringService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    candidate = _track_candidate(
        files=[
            CandidateFile(filename="Track A.flac", locked=True),
            CandidateFile(filename="Track B.flac", locked=True),
        ]
    )

    score = service.score_candidate(query, candidate)

    assert any(penalty.code == "locked-files" for penalty in score.penalties)
    assert any("locked" in warning.casefold() for warning in score.warnings)


def test_scoring_independent_of_provider() -> None:
    service = CandidateScoringService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    candidate_a = SearchCandidate(candidate_id="from-A", provider="slskd-future", artist="Example Artist", title="Example Track", files=[])
    candidate_b = SearchCandidate(candidate_id="from-B", provider="native-future", artist="Example Artist", title="Example Track", files=[])

    score_a = service.score_candidate(query, candidate_a)
    score_b = service.score_candidate(query, candidate_b)

    assert score_a.total == score_b.total
    assert score_a.risk == score_b.risk


def test_scoring_does_not_import_slskd() -> None:
    import sys
    from noqlen_flux.services import scoring as scoring_module

    assert "slskd" not in scoring_module.__file__
    for name in dir(scoring_module):
        obj = getattr(scoring_module, name, None)
        if hasattr(obj, "__module__"):
            assert "slskd" not in (getattr(obj, "__module__", "") or "")


def test_candidate_score_does_not_contain_quality_grade_concepts() -> None:
    score = CandidateScore(
        candidate_id="test-1",
        total=50.0,
        max_score=100.0,
        risk=CandidateRisk.MEDIUM,
        confidence=0.5,
    )
    payload = score.to_dict()

    assert "quality_grade" not in payload
    assert "approved" not in payload
    assert "quarantine" not in payload
    assert "rejected" not in payload
    assert "delete_eligible" not in payload


def test_candidate_risk_is_not_quality_grade() -> None:
    assert CandidateRisk.LOW.value == "low"
    assert CandidateRisk.MEDIUM.value == "medium"
    assert CandidateRisk.HIGH.value == "high"
    assert "excellent" not in {risk.value for risk in CandidateRisk}
    assert "bad" not in {risk.value for risk in CandidateRisk}


def test_score_ordering_is_stable_for_equal_candidates() -> None:
    service = CandidateScoringService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")

    candidates = [_track_candidate(candidate_id=f"track-{i}") for i in range(3)]
    scores = [service.score_candidate(query, c) for c in candidates]

    assert len({s.total for s in scores}) == 1
    assert len({s.risk for s in scores}) == 1


def test_declared_quality_with_low_bitrate_gets_penalty() -> None:
    service = CandidateScoringService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    candidate = _track_candidate(
        files=[CandidateFile(filename="Track.mp3", extension="mp3", declared_bitrate=128)]
    )

    score = service.score_candidate(query, candidate)

    assert any(penalty.code == "low-declared-bitrate" for penalty in score.penalties)


def test_candidate_without_raw_score_still_scores_normally() -> None:
    service = CandidateScoringService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    candidate = SearchCandidate(
        candidate_id="no-raw",
        provider="fake",
        artist="Example Artist",
        title="Example Track",
        files=[CandidateFile(filename="Track.flac", extension="flac")],
    )

    score = service.score_candidate(query, candidate)

    assert score.total > 80.0
    assert score.risk == CandidateRisk.LOW


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
