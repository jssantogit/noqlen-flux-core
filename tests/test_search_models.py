import pytest

from noqlen_flux.providers.status import ProviderAvailability, ProviderKind
from noqlen_flux.search import (
    CandidateFile,
    DownloadArtifact,
    DownloadRequest,
    ProviderHealth,
    SearchCandidate,
    SearchKind,
    SearchProviderResult,
    SearchQuery,
    TransferStatus,
)


def test_search_query_track_valid() -> None:
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")

    assert query.to_dict()["kind"] == "track"
    assert query.to_dict()["artist"] == "Example Artist"


def test_search_query_album_valid() -> None:
    query = SearchQuery(kind=SearchKind.ALBUM, artist="Example Artist", album="Example Album")

    assert query.to_dict()["kind"] == "album"
    assert query.to_dict()["album"] == "Example Album"


def test_search_query_requires_matching_title_or_album() -> None:
    with pytest.raises(ValueError):
        SearchQuery(kind=SearchKind.TRACK, artist="Example Artist")
    with pytest.raises(ValueError):
        SearchQuery(kind=SearchKind.ALBUM, artist="Example Artist")


def test_candidate_file_locked_defaults_false() -> None:
    candidate_file = CandidateFile(filename="Example Track.flac")

    assert candidate_file.locked is False
    assert candidate_file.to_dict()["locked"] is False


def test_search_candidate_serializes_safely() -> None:
    candidate = SearchCandidate(
        candidate_id="candidate-1",
        provider="fake",
        artist="Example Artist",
        title="Example Track",
        files=[CandidateFile(filename="Example Track.flac", metadata={"token": "placeholder-secret"})],
    )

    payload = candidate.to_dict()

    assert payload["candidate_id"] == "candidate-1"
    assert payload["files"][0]["metadata"]["token"] == "[redacted]"


def test_search_provider_result_timeout_warnings_errors() -> None:
    query = SearchQuery(kind=SearchKind.TRACK, artist="Example Artist", title="Example Track")
    result = SearchProviderResult(
        provider="fake",
        query=query,
        warnings=["slow fake response"],
        errors=["controlled fake error"],
        timeout_reached=True,
    )

    payload = result.to_dict()

    assert payload["timeout_reached"] is True
    assert payload["warnings"] == ["slow fake response"]
    assert payload["errors"] == ["controlled fake error"]


def test_provider_health_basic() -> None:
    health = ProviderHealth(
        provider="fake",
        kind=ProviderKind.FAKE,
        availability=ProviderAvailability.AVAILABLE,
        status_message="ready",
    )

    assert health.to_dict()["availability"] == "available"
    assert health.to_dict()["status_message"] == "ready"


def test_future_download_placeholders_do_not_execute_logic() -> None:
    candidate_file = CandidateFile(filename="Example Track.flac")

    request = DownloadRequest(provider="fake", candidate_id="candidate-1", files=[candidate_file])
    status = TransferStatus(provider="fake", transfer_id="transfer-1", state="planned")
    artifact = DownloadArtifact(provider="fake", candidate_id="candidate-1", artifact_id="artifact-1")

    assert request.to_dict()["candidate_id"] == "candidate-1"
    assert status.to_dict()["state"] == "planned"
    assert artifact.to_dict()["artifact_id"] == "artifact-1"
