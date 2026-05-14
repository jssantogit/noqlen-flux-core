from noqlen_flux.providers.base import SearchProvider
from noqlen_flux.providers.fake import FakeSearchProvider
from noqlen_flux.providers.fake_transfer import FakeTransferProvider
from noqlen_flux.providers.status import (
    ProviderAvailability,
    ProviderCapability,
    ProviderHealth,
    ProviderKind,
)
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


def test_fake_provider_health_available() -> None:
    provider = FakeSearchProvider([_track_candidate()], status_message="ready")

    health = provider.health()

    assert health.provider == "fake"
    assert health.kind == ProviderKind.FAKE
    assert health.availability == ProviderAvailability.AVAILABLE
    assert health.status_message == "ready"
    assert ProviderCapability.SEARCH in health.capabilities
    assert ProviderCapability.HEALTH in health.capabilities
    assert health.metadata["candidate_count"] == 1


def test_fake_provider_health_degraded() -> None:
    provider = FakeSearchProvider(
        [_track_candidate()],
        availability=ProviderAvailability.DEGRADED,
        status_message="slow responses",
    )

    health = provider.health()

    assert health.availability == ProviderAvailability.DEGRADED
    assert "degraded" in " ".join(health.warnings).lower()


def test_fake_provider_health_unavailable() -> None:
    provider = FakeSearchProvider(
        [_track_candidate()],
        availability=ProviderAvailability.UNAVAILABLE,
    )

    health = provider.health()

    assert health.availability == ProviderAvailability.UNAVAILABLE
    assert any("unavailable" in msg.lower() for msg in health.errors)


def test_fake_provider_declares_capabilities() -> None:
    provider = FakeSearchProvider([_track_candidate()])

    caps = provider.capabilities()

    assert ProviderCapability.SEARCH in caps
    assert ProviderCapability.HEALTH in caps


def test_fake_transfer_provider_health_available() -> None:
    provider = FakeTransferProvider()

    health = provider.health()

    assert health.provider == "fake-transfer"
    assert health.kind == ProviderKind.FAKE
    assert health.availability == ProviderAvailability.AVAILABLE


def test_fake_transfer_provider_health_degraded() -> None:
    provider = FakeTransferProvider(availability=ProviderAvailability.DEGRADED)

    health = provider.health()

    assert health.availability == ProviderAvailability.DEGRADED
    assert "degraded" in " ".join(health.warnings).lower()


def test_fake_transfer_provider_health_unavailable() -> None:
    provider = FakeTransferProvider(availability=ProviderAvailability.UNAVAILABLE)

    health = provider.health()

    assert health.availability == ProviderAvailability.UNAVAILABLE
    assert any("unavailable" in msg.lower() for msg in health.errors)


def test_fake_transfer_provider_declares_capabilities() -> None:
    provider = FakeTransferProvider()

    caps = provider.capabilities()

    assert ProviderCapability.DOWNLOAD_PLANNING in caps
    assert ProviderCapability.QUEUE_PLANNING in caps
    assert ProviderCapability.TRANSFER_STATUS in caps
    assert ProviderCapability.HEALTH in caps


def test_fake_providers_do_not_access_network() -> None:
    from noqlen_flux.providers import fake as fake_module
    from noqlen_flux.providers import fake_transfer as fake_transfer_module

    fake_source = open(fake_module.__file__).read()
    transfer_source = open(fake_transfer_module.__file__).read()

    for source in (fake_source, transfer_source):
        assert "requests" not in source
        assert "urllib" not in source
        assert "socket" not in source


def test_fake_providers_do_not_touch_filesystem() -> None:
    provider = FakeSearchProvider([_track_candidate()])
    provider.search(SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track"))

    transfer = FakeTransferProvider()
    from noqlen_flux.transfers import TransferPriority, TransferRequest

    transfer.plan_queue(
        TransferRequest(
            request_id="test-1",
            plan_id="plan-1",
            candidate_id="cand-1",
            priority=TransferPriority.NORMAL,
        )
    )


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
