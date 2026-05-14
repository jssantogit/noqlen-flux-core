"""Tests for the slskd provider adapter skeleton.

All tests use fake payloads and fake clients only.
No network access, no real slskd, no real downloads.
"""

import importlib
import inspect
import pkgutil
from pathlib import Path

import pytest

from noqlen_flux.providers.base import SearchProvider
from noqlen_flux.providers.slskd import (
    FakeSlskdClient,
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


def _fake_no_files_response() -> dict:
    return {"responses": [{"username": "no-files-user", "directory": "NoFiles", "files": "not-a-list", "locked_files": []}], "response_count": 0}


def _fake_malformed_response() -> dict:
    return {"responses": "not-a-list", "response_count": 0}


def _fake_weird_file_response() -> dict:
    return {
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
    }


# --- Config tests ---


def test_config_defaults() -> None:
    config = SlskdProviderConfig()
    assert config.base_url is None
    assert config.api_key is None
    assert config.timeout_seconds == 30


def test_config_custom_values() -> None:
    config = SlskdProviderConfig(base_url="http://localhost:5000", api_key="secret-key", timeout_seconds=60)
    assert config.base_url == "http://localhost:5000"
    assert config.api_key == "secret-key"
    assert config.timeout_seconds == 60


def test_config_rejects_invalid_timeout() -> None:
    with pytest.raises(ValueError, match="timeout_seconds must be positive"):
        SlskdProviderConfig(timeout_seconds=0)
    with pytest.raises(ValueError, match="timeout_seconds must be positive"):
        SlskdProviderConfig(timeout_seconds=-5)


def test_config_to_dict_redacts_api_key() -> None:
    config = SlskdProviderConfig(api_key="super-secret")
    d = config.to_dict()
    assert d["api_key"] == "[redacted]"
    assert d["base_url"] is None
    assert d["timeout_seconds"] == 30


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
    assert "no active client" in (health.status_message or "").lower()
    assert len(health.warnings) >= 1


def test_provider_search_without_client_returns_error() -> None:
    provider = SlskdProvider()
    result = provider.search(_track_query())
    assert result.provider == "slskd"
    assert len(result.errors) >= 1
    assert result.candidates == []
    assert "no active client" in " ".join(result.errors).lower()


# --- Provider with fake client ---


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
    candidates = SlskdPayloadMapper.map_search_response_to_candidates(_fake_malformed_response(), _track_query())
    assert candidates == []


def test_mapper_no_files_response_returns_empty_list() -> None:
    candidates = SlskdPayloadMapper.map_search_response_to_candidates(_fake_no_files_response(), _track_query())
    assert candidates == []


def test_mapper_weird_file_payload_does_not_crash() -> None:
    candidates = SlskdPayloadMapper.map_search_response_to_candidates(_fake_weird_file_response(), _track_query())
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
    result = client.search(_track_query())
    assert result["responses"] == []
    assert result["response_count"] == 0


def test_fake_slskd_client_health() -> None:
    healthy = FakeSlskdClient(healthy=True)
    assert healthy.health_check()["status"] == "ok"

    unhealthy = FakeSlskdClient(healthy=False)
    assert unhealthy.health_check()["status"] == "error"
