from noqlen_flux.providers.base import SearchProvider
from noqlen_flux.providers.fake import FakeSearchProvider
from noqlen_flux.search import CandidateFile, SearchCandidate, SearchKind, SearchQuery


def test_search_provider_contract_is_abstract() -> None:
    assert issubclass(FakeSearchProvider, SearchProvider)


def test_fake_provider_returns_matching_track_candidate() -> None:
    provider = FakeSearchProvider([_track_candidate()])
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")

    result = provider.search(query)

    assert result.candidates[0].candidate_id == "track-1"
    assert result.response_count == 1


def test_fake_provider_returns_matching_album_candidate() -> None:
    provider = FakeSearchProvider([_album_candidate()])
    query = SearchQuery(kind=SearchKind.ALBUM, artist="Example Artist", album="Example Album")

    result = provider.search(query)

    assert result.candidates[0].candidate_id == "album-1"
    assert len(result.candidates[0].files) == 2


def test_fake_provider_keeps_locked_files_visible() -> None:
    provider = FakeSearchProvider([_locked_candidate()])
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Locked Track")

    result = provider.search(query)

    assert result.candidates[0].files[0].locked is True


def test_fake_provider_simulates_timeout() -> None:
    provider = FakeSearchProvider([_track_candidate()], timeout=True)
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")

    result = provider.search(query)

    assert result.timeout_reached is True
    assert result.warnings == ["fake provider timeout reached"]


def test_fake_provider_simulates_warning() -> None:
    provider = FakeSearchProvider([_track_candidate()], warnings=["controlled warning"])
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")

    result = provider.search(query)

    assert result.warnings == ["controlled warning"]


def test_fake_provider_simulates_controlled_error() -> None:
    provider = FakeSearchProvider([_track_candidate()], errors=["controlled error"])
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")

    result = provider.search(query)

    assert result.errors == ["controlled error"]
    assert result.candidates == []


def test_fake_provider_health() -> None:
    provider = FakeSearchProvider([_track_candidate()], status_message="ready")

    health = provider.health()

    assert health.provider == "fake"
    assert health.available is True
    assert health.metadata["candidate_count"] == 1


def _track_candidate() -> SearchCandidate:
    return SearchCandidate(
        candidate_id="track-1",
        provider="fake",
        artist="Example Artist",
        title="Example Track",
        files=[CandidateFile(filename="Example Track.flac")],
    )


def _album_candidate() -> SearchCandidate:
    return SearchCandidate(
        candidate_id="album-1",
        provider="fake",
        artist="Example Artist",
        album="Example Album",
        files=[CandidateFile(filename="01 Intro.flac"), CandidateFile(filename="02 Track.flac")],
    )


def _locked_candidate() -> SearchCandidate:
    return SearchCandidate(
        candidate_id="locked-1",
        provider="fake",
        artist="Example Artist",
        title="Locked Track",
        files=[CandidateFile(filename="Locked Track.flac", locked=True)],
    )
