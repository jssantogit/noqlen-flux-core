from noqlen_flux.providers.base import SearchProvider
from noqlen_flux.providers.fake import FakeSearchProvider
from noqlen_flux.providers.status import ProviderAvailability, ProviderHealth
from noqlen_flux.results import Status
from noqlen_flux.search import CandidateFile, SearchCandidate, SearchKind, SearchProviderResult, SearchQuery
from noqlen_flux.services.search import SearchService


def test_search_service_returns_success_with_candidates() -> None:
    service = SearchService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    provider = FakeSearchProvider([_track_candidate()])

    result = service.search(query, provider)

    assert result.status == Status.SUCCESS
    assert result.summary["candidate_count"] == 1
    assert result.summary["candidates"][0]["candidate_id"] == "track-1"


def test_search_service_returns_warning_for_provider_warning_and_timeout() -> None:
    service = SearchService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    provider = FakeSearchProvider([_track_candidate()], warnings=["controlled warning"], timeout=True)

    result = service.search(query, provider)

    assert result.status == Status.WARNING
    assert result.summary["timeout_reached"] is True
    assert [warning.message for warning in result.warnings] == ["controlled warning", "fake provider timeout reached"]


def test_search_service_returns_failed_for_controlled_error() -> None:
    service = SearchService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    provider = FakeSearchProvider([_track_candidate()], errors=["controlled error"])

    result = service.search(query, provider)

    assert result.status == Status.FAILED
    assert result.errors[0].message == "controlled error"


def test_search_service_does_not_create_files(tmp_path) -> None:
    service = SearchService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    provider = FakeSearchProvider([_track_candidate()])

    result = service.search(query, provider)

    assert result.status == Status.SUCCESS
    assert list(tmp_path.iterdir()) == []


def test_search_service_depends_on_generic_provider_contract() -> None:
    class InlineProvider(SearchProvider):
        @property
        def name(self) -> str:
            return "inline"

        def capabilities(self) -> list:
            from noqlen_flux.providers.status import ProviderCapability

            return [ProviderCapability.SEARCH, ProviderCapability.HEALTH]

        def search(self, query: SearchQuery) -> SearchProviderResult:
            return SearchProviderResult(provider=self.name, query=query, candidates=[_track_candidate(provider=self.name)])

        def health(self) -> ProviderHealth:
            return ProviderHealth(provider=self.name, availability=ProviderAvailability.AVAILABLE)

    service = SearchService()
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")

    result = service.search(query, InlineProvider())

    assert result.status == Status.SUCCESS
    assert result.summary["provider"] == "inline"


def test_search_service_provider_health() -> None:
    service = SearchService()
    provider = FakeSearchProvider([_track_candidate()], status_message="ready")

    result = service.provider_health(provider)

    assert result.status == Status.SUCCESS
    assert result.summary["provider"] == "fake"
    assert result.summary["availability"] == "available"


def _track_candidate(provider: str = "fake") -> SearchCandidate:
    return SearchCandidate(
        candidate_id="track-1",
        provider=provider,
        artist="Example Artist",
        title="Example Track",
        files=[CandidateFile(filename="Example Track.flac")],
    )
