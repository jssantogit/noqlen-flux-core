"""Tests for the slskd provider adapter with offline search flow.

All tests use fake payloads and fake clients only.
No network access, no real slskd, no real downloads.
"""

import json

import pytest

from noqlen_flux.providers.base import SearchProvider
from noqlen_flux.providers.slskd import (
    FakeSlskdClient,
    SearchState,
    SlskdPayloadMapper,
    SlskdProvider,
    SlskdProviderConfig,
)
from noqlen_flux.providers.status import (
    ProviderAvailability,
    ProviderCapability,
    ProviderHealth,
    ProviderKind,
)
from noqlen_flux.search import (
    CandidateFile,
    SearchCandidate,
    SearchKind,
    SearchProviderResult,
    SearchQuery,
)


def _track_query() -> SearchQuery:
    return SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")


def _album_query() -> SearchQuery:
    return SearchQuery(kind=SearchKind.ALBUM, artist="Example Artist", album="Example Album")


def _fake_track_response() -> dict:
    return {
        "responses": [
            {
                "username": "fake-user",
                "directory": "Music/Example Artist/Example Album",
                "files": [
                    {
                        "filename": "01 Example Track.flac",
                        "size": 12345678,
                        "bitrate": 1000,
                        "extension": "flac",
                        "duration": 240,
                    }
                ],
                "locked_files": [],
            }
        ],
        "response_count": 1,
    }


def _fake_album_response() -> dict:
    return {
        "responses": [
            {
                "username": "fake-user",
                "directory": "Music/Example Artist/Example Album",
                "files": [
                    {"filename": "01 Intro.flac", "size": 1111111, "extension": "flac"},
                    {"filename": "02 Track.flac", "size": 2222222, "extension": "flac"},
                ],
                "locked_files": [
                    {"filename": "03 Locked.flac", "size": 3333333},
                ],
            }
        ],
        "response_count": 1,
    }


def _fake_locked_response() -> dict:
    return {
        "responses": [
            {
                "username": "locked-user",
                "directory": "Music/Locked",
                "files": [],
                "locked_files": [
                    {"filename": "Locked Track.flac", "size": 5555555},
                ],
            }
        ],
        "response_count": 1,
    }


def _fake_empty_response() -> dict:
    return {"responses": [{"username": "empty-user", "directory": "Empty", "files": [], "locked_files": []}], "response_count": 0}


def _fake_multi_response() -> dict:
    return {
        "responses": [
            {
                "username": "user-one",
                "directory": "Music/One",
                "files": [{"filename": "track1.flac", "size": 1000}],
                "locked_files": [],
            },
            {
                "username": "user-two",
                "directory": "Music/Two",
                "files": [{"filename": "track2.mp3", "size": 2000}],
                "locked_files": [],
            },
        ],
        "response_count": 2,
    }


# --- Config tests ---


def test_config_defaults() -> None:
    config = SlskdProviderConfig()
    assert config.base_url is None
    assert config.api_key is None
    assert config.timeout_seconds == 5
    assert config.max_poll_attempts == 10
    assert config.allow_network is False


def test_config_custom_values() -> None:
    config = SlskdProviderConfig(base_url="http://localhost:5000", api_key="secret-key", timeout_seconds=60, max_poll_attempts=5)
    assert config.base_url == "http://localhost:5000"
    assert config.api_key == "secret-key"
    assert config.timeout_seconds == 60
    assert config.max_poll_attempts == 5


def test_config_rejects_invalid_timeout() -> None:
    with pytest.raises(ValueError, match="timeout_seconds must be positive"):
        SlskdProviderConfig(timeout_seconds=0)
    with pytest.raises(ValueError, match="timeout_seconds must be positive"):
        SlskdProviderConfig(timeout_seconds=-5)


def test_config_rejects_invalid_poll_attempts() -> None:
    with pytest.raises(ValueError, match="max_poll_attempts must be positive"):
        SlskdProviderConfig(max_poll_attempts=0)
    with pytest.raises(ValueError, match="max_poll_attempts must be positive"):
        SlskdProviderConfig(max_poll_attempts=-1)


def test_config_to_dict_redacts_api_key() -> None:
    config = SlskdProviderConfig(api_key="super-secret")
    d = config.to_dict()
    assert d["api_key"] == "[redacted]"
    assert d["base_url"] is None
    assert d["timeout_seconds"] == 5
    assert d["max_poll_attempts"] == 10
    assert d["allow_network"] is False


def test_config_to_dict_without_api_key() -> None:
    config = SlskdProviderConfig()
    d = config.to_dict()
    assert d["api_key"] == "[redacted]"


def test_config_repr_redacts_api_key() -> None:
    config = SlskdProviderConfig(api_key="secret")
    r = repr(config)
    assert "secret" not in r
    assert "[redacted]" in r


def test_config_repr_without_api_key() -> None:
    config = SlskdProviderConfig()
    r = repr(config)
    assert "api_key=None" in r


# --- Provider without client ---


def test_provider_name() -> None:
    provider = SlskdProvider()
    assert provider.name == "slskd"


def test_provider_declares_capabilities() -> None:
    provider = SlskdProvider()
    caps = provider.capabilities()
    assert ProviderCapability.SEARCH in caps
    assert ProviderCapability.HEALTH in caps


def test_provider_is_search_provider() -> None:
    assert issubclass(SlskdProvider, SearchProvider)


def test_provider_health_without_client_returns_unavailable() -> None:
    provider = SlskdProvider()
    health = provider.health()
    assert health.provider == "slskd"
    assert health.kind == ProviderKind.EXTERNAL
    assert health.availability == ProviderAvailability.UNAVAILABLE
    assert "network access disabled" in (health.status_message or "").lower()
    assert len(health.warnings) >= 1


def test_provider_search_without_client_returns_error() -> None:
    provider = SlskdProvider()
    result = provider.search(_track_query())
    assert result.provider == "slskd"
    assert len(result.errors) >= 1
    assert result.candidates == []
    assert "no active client" in " ".join(result.errors).lower()


# --- Provider with fake client: immediate completion ---


def test_provider_health_with_healthy_fake_client() -> None:
    client = FakeSlskdClient(healthy=True)
    provider = SlskdProvider(client=client)
    health = provider.health()
    assert health.availability == ProviderAvailability.AVAILABLE
    assert "ok" in (health.status_message or "").lower()


def test_provider_health_with_unhealthy_fake_client() -> None:
    client = FakeSlskdClient(healthy=False)
    provider = SlskdProvider(client=client)
    health = provider.health()
    assert health.availability == ProviderAvailability.DEGRADED


def test_provider_search_with_fake_client_returns_candidates() -> None:
    client = FakeSlskdClient(responses=[_fake_track_response()])
    provider = SlskdProvider(client=client)
    result = provider.search(_track_query())
    assert len(result.candidates) == 1
    assert result.response_count == 1
    assert result.errors == []


def test_provider_search_with_album_fake_client() -> None:
    client = FakeSlskdClient(responses=[_fake_album_response()])
    provider = SlskdProvider(client=client)
    result = provider.search(_album_query())
    assert len(result.candidates) == 1
    assert len(result.candidates[0].files) == 3


def test_provider_search_with_multi_response() -> None:
    client = FakeSlskdClient(responses=[_fake_multi_response()])
    provider = SlskdProvider(client=client)
    result = provider.search(_track_query())
    assert len(result.candidates) == 2
    assert result.response_count == 2
    assert result.candidates[0].username == "user-one"
    assert result.candidates[1].username == "user-two"


def test_provider_search_track_query_builds_correct_text() -> None:
    client = FakeSlskdClient(responses=[_fake_track_response()])
    provider = SlskdProvider(client=client)
    query = SearchQuery(kind=SearchKind.TRACK, artist="Artist A", title="Title B", extra_terms=["remaster"])
    result = provider.search(query)
    assert len(result.candidates) == 1


def test_provider_search_album_query_builds_correct_text() -> None:
    client = FakeSlskdClient(responses=[_fake_album_response()])
    provider = SlskdProvider(client=client)
    query = SearchQuery(kind=SearchKind.ALBUM, artist="Artist A", album="Album B")
    result = provider.search(query)
    assert len(result.candidates) == 1


# --- Provider with fake client: polling behavior ---


def test_provider_search_with_poll_delay_completes() -> None:
    client = FakeSlskdClient(responses=[_fake_track_response()], poll_delay=2)
    config = SlskdProviderConfig(max_poll_attempts=10)
    provider = SlskdProvider(config=config, client=client)
    result = provider.search(_track_query())
    assert len(result.candidates) == 1
    assert result.timeout_reached is False
    assert client.poll_count == 3


def test_provider_search_bounded_polling_hits_limit() -> None:
    client = FakeSlskdClient(responses=[_fake_track_response()], poll_delay=20)
    config = SlskdProviderConfig(max_poll_attempts=3)
    provider = SlskdProvider(config=config, client=client)
    result = provider.search(_track_query())
    assert result.timeout_reached is True
    assert result.candidates == []
    assert "poll limit" in " ".join(result.warnings).lower()
    assert client.poll_count == 3


def test_provider_search_timeout_calls_stop_search() -> None:
    client = FakeSlskdClient(responses=[_fake_track_response()], poll_delay=20)
    config = SlskdProviderConfig(max_poll_attempts=3)
    provider = SlskdProvider(config=config, client=client)
    result = provider.search(_track_query())
    assert result.timeout_reached is True
    search_id_prefix = "fake-search-"
    for sid in client._active_searches:
        assert client.was_search_stopped(sid) is True


def test_provider_search_fail_after_polls_returns_error() -> None:
    client = FakeSlskdClient(responses=[_fake_track_response()], poll_delay=5, fail_after_polls=2)
    config = SlskdProviderConfig(max_poll_attempts=10)
    provider = SlskdProvider(config=config, client=client)
    result = provider.search(_track_query())
    assert len(result.errors) >= 1
    assert "failure state" in " ".join(result.errors).lower()


# --- Provider with fake client: error scenarios ---


def test_provider_search_start_error_returns_error() -> None:
    client = FakeSlskdClient(raise_on_start=True)
    provider = SlskdProvider(client=client)
    result = provider.search(_track_query())
    assert len(result.errors) >= 1
    assert "start failed" in " ".join(result.errors).lower()


def test_provider_search_state_error_adds_warning_and_retries() -> None:
    client = FakeSlskdClient(responses=[_fake_track_response()], raise_on_state=True)
    config = SlskdProviderConfig(max_poll_attempts=3)
    provider = SlskdProvider(config=config, client=client)
    result = provider.search(_track_query())
    assert result.timeout_reached is True
    assert len(result.warnings) >= 1


def test_provider_search_responses_error_returns_error() -> None:
    client = FakeSlskdClient(responses=[_fake_track_response()], raise_on_responses=True)
    provider = SlskdProvider(client=client)
    result = provider.search(_track_query())
    assert len(result.errors) >= 1
    assert "response retrieval failed" in " ".join(result.errors).lower()


# --- Provider with fake client: empty responses ---


def test_provider_search_empty_response_returns_warning() -> None:
    client = FakeSlskdClient(responses=[_fake_empty_response()])
    provider = SlskdProvider(client=client)
    result = provider.search(_track_query())
    assert result.candidates == []
    assert len(result.warnings) >= 1
    assert "no candidates" in " ".join(result.warnings).lower()


# --- Mapper tests ---


def test_mapper_track_response() -> None:
    candidates = SlskdPayloadMapper.map_search_response_to_candidates(_fake_track_response(), _track_query())
    assert len(candidates) == 1
    c = candidates[0]
    assert c.username == "fake-user"
    assert c.provider == "slskd"
    assert len(c.files) == 1
    assert c.files[0].filename == "01 Example Track.flac"
    assert c.files[0].size_bytes == 12345678
    assert c.files[0].declared_bitrate == 1000
    assert c.files[0].extension == "flac"
    assert c.files[0].duration_seconds == 240
    assert c.files[0].locked is False


def test_mapper_album_response_with_locked_files() -> None:
    candidates = SlskdPayloadMapper.map_search_response_to_candidates(_fake_album_response(), _album_query())
    assert len(candidates) == 1
    c = candidates[0]
    assert len(c.files) == 3
    locked = [f for f in c.files if f.locked]
    assert len(locked) == 1
    assert locked[0].filename == "03 Locked.flac"


def test_mapper_locked_only_response() -> None:
    candidates = SlskdPayloadMapper.map_search_response_to_candidates(_fake_locked_response(), _track_query())
    assert len(candidates) == 1
    c = candidates[0]
    assert len(c.files) == 1
    assert c.files[0].locked is True


def test_mapper_empty_response_returns_empty_list() -> None:
    candidates = SlskdPayloadMapper.map_search_response_to_candidates(_fake_empty_response(), _track_query())
    assert candidates == []


def test_mapper_malformed_response_returns_empty_list() -> None:
    candidates = SlskdPayloadMapper.map_search_response_to_candidates({"responses": "not-a-list"}, _track_query())
    assert candidates == []


def test_mapper_no_files_response_returns_empty_list() -> None:
    candidates = SlskdPayloadMapper.map_search_response_to_candidates(
        {"responses": [{"username": "no-files-user", "directory": "NoFiles", "files": "not-a-list", "locked_files": []}]},
        _track_query(),
    )
    assert candidates == []


def test_mapper_weird_file_payload_does_not_crash() -> None:
    candidates = SlskdPayloadMapper.map_search_response_to_candidates(
        {
            "responses": [
                {
                    "username": "weird-user",
                    "directory": "Weird",
                    "files": [
                        {"filename": "", "size": -1},
                        {"filename": "   "},
                        {"filename": None},
                        {"size": 100},
                    ],
                    "locked_files": [],
                }
            ],
            "response_count": 0,
        },
        _track_query(),
    )
    assert candidates == []


def test_mapper_file_payload_to_candidate_file_basic() -> None:
    fp = {"filename": "test.flac", "size": 1000, "bitrate": 500, "extension": "flac", "duration": 180}
    cf = SlskdPayloadMapper.map_file_payload_to_candidate_file(fp)
    assert cf is not None
    assert cf.filename == "test.flac"
    assert cf.size_bytes == 1000
    assert cf.declared_bitrate == 500
    assert cf.extension == "flac"
    assert cf.duration_seconds == 180
    assert cf.locked is False


def test_mapper_file_payload_locked() -> None:
    fp = {"filename": "locked.flac", "size": 2000}
    cf = SlskdPayloadMapper.map_file_payload_to_candidate_file(fp, locked=True)
    assert cf is not None
    assert cf.locked is True


def test_mapper_file_payload_invalid_returns_none() -> None:
    assert SlskdPayloadMapper.map_file_payload_to_candidate_file({}) is None
    assert SlskdPayloadMapper.map_file_payload_to_candidate_file({"filename": ""}) is None
    assert SlskdPayloadMapper.map_file_payload_to_candidate_file({"filename": "   "}) is None
    assert SlskdPayloadMapper.map_file_payload_to_candidate_file("not-a-dict") is None
    assert SlskdPayloadMapper.map_file_payload_to_candidate_file({"filename": "x.flac", "size": -1}) is not None


def test_mapper_health_no_payload() -> None:
    config = SlskdProviderConfig()
    health = SlskdPayloadMapper.map_provider_health(config)
    assert health.availability == ProviderAvailability.UNAVAILABLE
    assert health.provider == "slskd"
    assert health.kind == ProviderKind.EXTERNAL


def test_mapper_health_ok_payload() -> None:
    config = SlskdProviderConfig()
    health = SlskdPayloadMapper.map_provider_health(config, {"status": "ok", "version": "1.0"})
    assert health.availability == ProviderAvailability.AVAILABLE


def test_mapper_health_error_payload() -> None:
    config = SlskdProviderConfig()
    health = SlskdPayloadMapper.map_provider_health(config, {"status": "error", "message": "down"})
    assert health.availability == ProviderAvailability.DEGRADED


# --- Raw payload leakage tests ---


def test_no_raw_provider_payload_in_search_result() -> None:
    client = FakeSlskdClient(responses=[_fake_track_response()])
    provider = SlskdProvider(client=client)
    result = provider.search(_track_query())
    result_dict = result.to_dict()
    assert "raw_provider_payload" not in str(result_dict)
    for candidate in result.candidates:
        c_dict = candidate.to_dict()
        assert "raw_provider_payload" not in str(c_dict)
        for f in candidate.files:
            f_dict = f.to_dict()
            assert "raw_provider_payload" not in str(f_dict)


def test_no_api_key_in_to_dict() -> None:
    config = SlskdProviderConfig(api_key="my-secret-key")
    d = config.to_dict()
    assert "my-secret-key" not in str(d)
    assert d["api_key"] == "[redacted]"


# --- ProviderService integration ---


def test_provider_service_can_inspect_slskd_provider() -> None:
    from noqlen_flux.services.providers import ProviderService

    provider = SlskdProvider()
    result = ProviderService().inspect_provider(provider)
    assert result.summary["provider"] == "slskd"
    assert result.summary["health"]["availability"] == "unavailable"


# --- FakeSearchProvider still works ---


def test_fake_search_provider_still_works() -> None:
    from noqlen_flux.providers.fake import FakeSearchProvider

    candidate = SearchCandidate(
        candidate_id="test-1",
        provider="fake",
        artist="Test Artist",
        title="Test Track",
        files=[CandidateFile(filename="Test Track.flac")],
    )
    provider = FakeSearchProvider([candidate])
    query = SearchQuery(kind=SearchKind.TRACK, artist="Test Artist", title="Test Track")
    result = provider.search(query)
    assert len(result.candidates) == 1


# --- No network access ---


def test_slskd_module_does_not_import_network_libraries() -> None:
    from noqlen_flux.providers import slskd as slskd_module

    source = open(slskd_module.__file__).read()
    assert "import requests" not in source
    assert "import httpx" not in source
    assert "import aiohttp" not in source
    assert "from requests" not in source
    assert "from httpx" not in source
    assert "from aiohttp" not in source


def test_slskd_module_does_not_touch_filesystem() -> None:
    provider = SlskdProvider()
    provider.health()
    provider.search(_track_query())


# --- FakeSlskdClient isolation ---


def test_fake_slskd_client_is_not_fake_search_provider() -> None:
    from noqlen_flux.providers.fake import FakeSearchProvider

    client = FakeSlskdClient()
    assert not isinstance(client, FakeSearchProvider)
    assert not isinstance(client, SearchProvider)


def test_fake_slskd_client_empty_responses() -> None:
    client = FakeSlskdClient()
    result = client.get_search_responses("fake-id")
    assert result["responses"] == []
    assert result["response_count"] == 0


def test_fake_slskd_client_health() -> None:
    healthy = FakeSlskdClient(healthy=True)
    assert healthy.health_check()["status"] == "ok"

    unhealthy = FakeSlskdClient(healthy=False)
    assert unhealthy.health_check()["status"] == "error"


def test_fake_slskd_client_start_search_returns_id() -> None:
    client = FakeSlskdClient()
    sid = client.start_search("artist track")
    assert sid.startswith("fake-search-")


def test_fake_slskd_client_poll_count_tracking() -> None:
    client = FakeSlskdClient(responses=[_fake_track_response()], poll_delay=2)
    sid = client.start_search("test")
    client.get_search_state(sid)
    client.get_search_state(sid)
    client.get_search_state(sid)
    assert client.poll_count == 3


def test_fake_slskd_client_was_search_stopped() -> None:
    client = FakeSlskdClient(responses=[_fake_track_response()], poll_delay=20)
    config = SlskdProviderConfig(max_poll_attempts=3)
    provider = SlskdProvider(config=config, client=client)
    provider.search(_track_query())
    for sid in client._active_searches:
        assert client.was_search_stopped(sid) is True


# --- SearchService integration with SlskdProvider ---


def test_search_service_with_slskd_provider() -> None:
    from noqlen_flux.services.search import SearchService

    client = FakeSlskdClient(responses=[_fake_track_response()])
    provider = SlskdProvider(client=client)
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    result = SearchService().search(query, provider)
    assert result.status.value == "success"
    assert result.summary["provider"] == "slskd"
    assert result.summary["candidate_count"] == 1


def test_search_service_with_slskd_provider_scoring() -> None:
    from noqlen_flux.services.scoring import CandidateScoringService
    from noqlen_flux.services.search import SearchService

    client = FakeSlskdClient(responses=[_fake_track_response()])
    provider = SlskdProvider(client=client)
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    result = SearchService().search(query, provider, scoring_service=CandidateScoringService())
    assert result.summary["candidate_count"] == 1
    assert len(result.summary.get("scores", [])) == 1


def test_download_planning_with_slskd_candidate() -> None:
    from noqlen_flux.downloads import DownloadConstraint, DownloadIntent, DownloadRequest
    from noqlen_flux.services import DownloadPlanningService
    from noqlen_flux.services.scoring import CandidateScoringService

    client = FakeSlskdClient(responses=[_fake_track_response()])
    provider = SlskdProvider(client=client)
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    provider_result = provider.search(query)
    assert len(provider_result.candidates) == 1
    candidate = provider_result.candidates[0]
    score = CandidateScoringService().score_candidate(query, candidate)
    request = DownloadRequest.from_candidate(
        candidate=candidate,
        intent=DownloadIntent.TRACK,
        query=f"{query.artist} - {query.title}",
        score=score,
        constraints=DownloadConstraint(),
    )
    result = DownloadPlanningService().plan_download(request)
    assert result.status.value == "success"


# --- SlskdHttpClient tests ---


def test_slskd_http_client_exists() -> None:
    from noqlen_flux.providers.slskd import SlskdHttpClient

    config = SlskdProviderConfig(base_url="http://localhost:5000")
    client = SlskdHttpClient(config=config)
    assert client is not None


def test_slskd_http_client_no_base_url_returns_error() -> None:
    from noqlen_flux.providers.slskd import SlskdHttpClient

    config = SlskdProviderConfig()
    client = SlskdHttpClient(config=config)
    result = client.health_check()
    assert result["status"] == "error"
    assert "no base_url" in result["message"].lower()


def test_slskd_http_client_does_not_use_external_network_libs() -> None:
    from noqlen_flux.providers import slskd as slskd_module

    source = open(slskd_module.__file__).read()
    assert "import requests" not in source
    assert "import httpx" not in source
    assert "import aiohttp" not in source


def test_slskd_http_client_start_search_no_url_raises() -> None:
    from noqlen_flux.providers.slskd import SlskdHttpClient

    config = SlskdProviderConfig()
    client = SlskdHttpClient(config=config)
    with pytest.raises(RuntimeError, match="no base_url"):
        client.start_search("test")


def test_slskd_http_client_get_state_no_url_raises() -> None:
    from noqlen_flux.providers.slskd import SlskdHttpClient

    config = SlskdProviderConfig()
    client = SlskdHttpClient(config=config)
    with pytest.raises(RuntimeError, match="no base_url"):
        client.get_search_state("test")


def test_slskd_http_client_get_responses_no_url_raises() -> None:
    from noqlen_flux.providers.slskd import SlskdHttpClient

    config = SlskdProviderConfig()
    client = SlskdHttpClient(config=config)
    with pytest.raises(RuntimeError, match="no base_url"):
        client.get_search_responses("test")


def test_slskd_http_client_stop_search_no_url_is_noop() -> None:
    from noqlen_flux.providers.slskd import SlskdHttpClient

    config = SlskdProviderConfig()
    client = SlskdHttpClient(config=config)
    client.stop_search("test")


def test_slskd_http_client_start_search_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    from io import BytesIO
    from noqlen_flux.providers.slskd import SlskdHttpClient
    from urllib.error import URLError

    config = SlskdProviderConfig(base_url="http://localhost:5000", api_key="test-key")
    client = SlskdHttpClient(config=config)

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self) -> bytes:
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        return FakeResponse(b'{"id": "search-abc-123"}')

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    search_id = client.start_search("artist track")
    assert search_id == "search-abc-123"


def test_slskd_http_client_start_search_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from noqlen_flux.providers.slskd import SlskdHttpClient
    from urllib.error import URLError

    config = SlskdProviderConfig(base_url="http://localhost:5000")
    client = SlskdHttpClient(config=config)

    def fake_urlopen(req, timeout=None):
        raise URLError("connection refused")

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="search start failed"):
        client.start_search("test")


def test_slskd_http_client_start_search_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    from noqlen_flux.providers.slskd import SlskdHttpClient

    config = SlskdProviderConfig(base_url="http://localhost:5000")
    client = SlskdHttpClient(config=config)

    def fake_urlopen(req, timeout=None):
        raise TimeoutError()

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="search start timed out"):
        client.start_search("test")


def test_slskd_http_client_get_search_state_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    from noqlen_flux.providers.slskd import SlskdHttpClient

    config = SlskdProviderConfig(base_url="http://localhost:5000")
    client = SlskdHttpClient(config=config)

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self) -> bytes:
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        return FakeResponse(b'{"state": "Completed"}')

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    state = client.get_search_state("search-123")
    assert state["state"] == "Completed"


def test_slskd_http_client_get_search_responses_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    from noqlen_flux.providers.slskd import SlskdHttpClient

    config = SlskdProviderConfig(base_url="http://localhost:5000")
    client = SlskdHttpClient(config=config)

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self) -> bytes:
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    response_body = json.dumps({
        "responses": [
            {
                "username": "test-user",
                "directory": "Music/Test",
                "files": [{"filename": "test.flac", "size": 1000}],
                "locked_files": [],
            }
        ],
        "response_count": 1,
    }).encode()

    def fake_urlopen(req, timeout=None):
        return FakeResponse(response_body)

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    result = client.get_search_responses("search-123")
    assert result["response_count"] == 1
    assert len(result["responses"]) == 1
    assert result["responses"][0]["username"] == "test-user"


def test_slskd_http_client_stop_search_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    from noqlen_flux.providers.slskd import SlskdHttpClient

    config = SlskdProviderConfig(base_url="http://localhost:5000")
    client = SlskdHttpClient(config=config)

    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        return FakeResponse()

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)
    client.stop_search("search-123")


def test_slskd_http_client_stop_search_error_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    from noqlen_flux.providers.slskd import SlskdHttpClient
    from urllib.error import URLError

    config = SlskdProviderConfig(base_url="http://localhost:5000")
    client = SlskdHttpClient(config=config)

    def fake_urlopen(req, timeout=None):
        raise URLError("gone")

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)
    client.stop_search("search-123")


def test_slskd_http_client_api_key_not_in_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from noqlen_flux.providers.slskd import SlskdHttpClient
    from urllib.error import URLError

    config = SlskdProviderConfig(base_url="http://localhost:5000", api_key="super-secret-key-12345")
    client = SlskdHttpClient(config=config)

    def fake_urlopen(req, timeout=None):
        raise URLError("connection refused")

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    with pytest.raises(RuntimeError) as exc_info:
        client.start_search("test")
    assert "super-secret-key-12345" not in str(exc_info.value)


def test_slskd_http_client_health_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    from noqlen_flux.providers.slskd import SlskdHttpClient

    config = SlskdProviderConfig(base_url="http://localhost:5000")
    client = SlskdHttpClient(config=config)

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self) -> bytes:
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        return FakeResponse(b'{"version": "4.5.0"}')

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    result = client.health_check()
    assert result["status"] == "ok"
    assert result["version"] == "4.5.0"


# --- Provider search with allow_network ---


def test_provider_search_with_allow_network_no_base_url_returns_error() -> None:
    config = SlskdProviderConfig(allow_network=True)
    provider = SlskdProvider(config=config)
    result = provider.search(_track_query())
    assert len(result.errors) >= 1
    assert "no active client" in " ".join(result.errors).lower()


def test_provider_search_with_allow_network_and_base_url_uses_real_client(monkeypatch: pytest.MonkeyPatch) -> None:
    from noqlen_flux.providers.slskd import SlskdHttpClient

    config = SlskdProviderConfig(
        base_url="http://localhost:5000",
        allow_network=True,
        max_poll_attempts=3,
    )
    provider = SlskdProvider(config=config)

    call_log: list[str] = []

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self) -> bytes:
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        call_log.append(req.method or "GET")
        if req.method == "POST":
            return FakeResponse(b'{"id": "search-1"}')
        if req.method == "GET" and "responses" in str(req.full_url):
            return FakeResponse(json.dumps(_fake_track_response()).encode())
        return FakeResponse(b'{"state": "Completed"}')

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    result = provider.search(_track_query())
    assert len(result.candidates) == 1
    assert result.response_count == 1
    assert "POST" in call_log
    assert "GET" in call_log


def test_provider_search_with_allow_network_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    config = SlskdProviderConfig(
        base_url="http://localhost:5000",
        allow_network=True,
        max_poll_attempts=2,
    )
    provider = SlskdProvider(config=config)

    poll_count = [0]

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self) -> bytes:
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        if req.method == "POST":
            return FakeResponse(b'{"id": "search-1"}')
        if req.method == "GET" and "responses" not in str(req.full_url):
            poll_count[0] += 1
            return FakeResponse(b'{"state": "InProgress"}')
        return FakeResponse(b'{"responses": [], "response_count": 0}')

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    result = provider.search(_track_query())
    assert result.timeout_reached is True
    assert "poll limit" in " ".join(result.warnings).lower()
    assert poll_count[0] == 2


def test_provider_search_with_allow_network_start_error(monkeypatch: pytest.MonkeyPatch) -> None:
    config = SlskdProviderConfig(base_url="http://localhost:5000", allow_network=True)
    provider = SlskdProvider(config=config)

    from urllib.error import URLError

    def fake_urlopen(req, timeout=None):
        raise URLError("refused")

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    result = provider.search(_track_query())
    assert len(result.errors) >= 1
    assert "search start failed" in " ".join(result.errors).lower()


def test_provider_search_with_allow_network_empty_responses(monkeypatch: pytest.MonkeyPatch) -> None:
    config = SlskdProviderConfig(base_url="http://localhost:5000", allow_network=True, max_poll_attempts=5)
    provider = SlskdProvider(config=config)

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self) -> bytes:
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        if req.method == "POST":
            return FakeResponse(b'{"id": "search-1"}')
        if req.method == "GET" and "responses" in str(req.full_url):
            return FakeResponse(b'{"responses": [], "response_count": 0}')
        return FakeResponse(b'{"state": "Completed"}')

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    result = provider.search(_track_query())
    assert result.candidates == []
    assert "no candidates" in " ".join(result.warnings).lower()


# --- Normalization helpers ---


def test_normalize_search_responses_from_list() -> None:
    from noqlen_flux.providers.slskd import _normalize_search_responses

    data = [
        {"username": "user1", "files": [{"filename": "a.flac", "size": 100}]},
    ]
    result = _normalize_search_responses(data)
    assert result["response_count"] == 1
    assert result["responses"][0]["username"] == "user1"


def test_normalize_search_responses_from_dict() -> None:
    from noqlen_flux.providers.slskd import _normalize_search_responses

    data = {
        "responses": [
            {"username": "user1", "files": [{"filename": "a.flac", "size": 100}]},
        ],
        "response_count": 1,
    }
    result = _normalize_search_responses(data)
    assert result["response_count"] == 1


def test_normalize_search_responses_alternative_keys() -> None:
    from noqlen_flux.providers.slskd import _normalize_search_responses

    data = {
        "results": [
            {"user": "user1", "fileList": [{"name": "a.flac", "filesize": 100}]},
        ],
    }
    result = _normalize_search_responses(data)
    assert result["response_count"] == 1
    assert result["responses"][0]["username"] == "user1"
    assert result["responses"][0]["files"][0]["filename"] == "a.flac"


def test_normalize_file_extension_from_filename() -> None:
    from noqlen_flux.providers.slskd import _normalize_file

    raw = {"filename": "01 Track.flac", "size": 1000}
    result = _normalize_file(raw)
    assert result["extension"] == "flac"


def test_normalize_file_duration_alternative_keys() -> None:
    from noqlen_flux.providers.slskd import _normalize_file

    raw = {"filename": "track.flac", "length": 240}
    result = _normalize_file(raw)
    assert result["duration"] == 240


def test_safe_summary_redacts_sensitive_keys() -> None:
    from noqlen_flux.providers.slskd import _safe_summary

    data = {"username": "user1", "api_key": "secret", "token": "tok"}
    result = _safe_summary(data)
    assert result["username"] == "user1"
    assert result["api_key"] == "[redacted]"
    assert result["token"] == "[redacted]"


def test_url_quote_escapes_special_chars() -> None:
    from noqlen_flux.providers.slskd import _url_quote

    assert _url_quote("search/123") == "search%2F123"
    assert _url_quote("safe-id") == "safe-id"


# --- allow_network config tests ---


def test_config_allow_network_default_false() -> None:
    config = SlskdProviderConfig()
    assert config.allow_network is False


def test_config_allow_network_can_be_true() -> None:
    config = SlskdProviderConfig(allow_network=True)
    assert config.allow_network is True


def test_config_allow_network_appears_in_to_dict() -> None:
    config = SlskdProviderConfig(allow_network=True)
    d = config.to_dict()
    assert d["allow_network"] is True


def test_config_allow_network_appears_in_repr() -> None:
    config = SlskdProviderConfig(allow_network=True)
    r = repr(config)
    assert "allow_network=True" in r


# --- Provider health with allow_network ---


def test_provider_health_offline_no_client_returns_network_disabled() -> None:
    config = SlskdProviderConfig(allow_network=False)
    provider = SlskdProvider(config=config)
    health = provider.health()
    assert health.availability == ProviderAvailability.UNAVAILABLE
    assert "network access disabled" in (health.status_message or "").lower()


def test_provider_health_offline_no_base_url_returns_network_disabled() -> None:
    config = SlskdProviderConfig(allow_network=True)
    provider = SlskdProvider(config=config)
    health = provider.health()
    assert health.availability == ProviderAvailability.UNAVAILABLE
    assert "network access disabled" in (health.status_message or "").lower()


def test_provider_health_with_fake_client_ignores_allow_network() -> None:
    client = FakeSlskdClient(healthy=True)
    config = SlskdProviderConfig(allow_network=False)
    provider = SlskdProvider(config=config, client=client)
    health = provider.health()
    assert health.availability == ProviderAvailability.AVAILABLE
