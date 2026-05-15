"""Tests for download artifact registration models and service."""

import pytest

from noqlen_flux.artifact_registration import DownloadArtifactRegistration
from noqlen_flux.results import Status
from noqlen_flux.services.artifact_registration import ArtifactRegistrationService


def test_download_artifact_registration_valid() -> None:
    reg = DownloadArtifactRegistration(
        artifact_id="artifact-1",
        candidate_id="candidate-1",
        queue_item_id="qi-1",
        provider="slskd",
        relative_path="candidate-1/Track.flac",
        state="completed",
        size_bytes=12345678,
    )
    assert reg.artifact_id == "artifact-1"
    assert reg.candidate_id == "candidate-1"
    assert reg.queue_item_id == "qi-1"
    assert reg.provider == "slskd"
    assert reg.relative_path == "candidate-1/Track.flac"
    assert reg.state == "completed"
    assert reg.size_bytes == 12345678


def test_download_artifact_registration_requires_artifact_id() -> None:
    with pytest.raises(ValueError):
        DownloadArtifactRegistration(
            artifact_id="",
            candidate_id="candidate-1",
            queue_item_id="qi-1",
            provider="slskd",
            relative_path="candidate-1/Track.flac",
            state="completed",
        )


def test_download_artifact_registration_requires_candidate_id() -> None:
    with pytest.raises(ValueError):
        DownloadArtifactRegistration(
            artifact_id="artifact-1",
            candidate_id="",
            queue_item_id="qi-1",
            provider="slskd",
            relative_path="candidate-1/Track.flac",
            state="completed",
        )


def test_download_artifact_registration_requires_queue_item_id() -> None:
    with pytest.raises(ValueError):
        DownloadArtifactRegistration(
            artifact_id="artifact-1",
            candidate_id="candidate-1",
            queue_item_id="",
            provider="slskd",
            relative_path="candidate-1/Track.flac",
            state="completed",
        )


def test_download_artifact_registration_requires_provider() -> None:
    with pytest.raises(ValueError):
        DownloadArtifactRegistration(
            artifact_id="artifact-1",
            candidate_id="candidate-1",
            queue_item_id="qi-1",
            provider="",
            relative_path="candidate-1/Track.flac",
            state="completed",
        )


def test_download_artifact_registration_requires_relative_path() -> None:
    with pytest.raises(ValueError):
        DownloadArtifactRegistration(
            artifact_id="artifact-1",
            candidate_id="candidate-1",
            queue_item_id="qi-1",
            provider="slskd",
            relative_path="",
            state="completed",
        )


def test_download_artifact_registration_requires_state() -> None:
    with pytest.raises(ValueError):
        DownloadArtifactRegistration(
            artifact_id="artifact-1",
            candidate_id="candidate-1",
            queue_item_id="qi-1",
            provider="slskd",
            relative_path="candidate-1/Track.flac",
            state="",
        )


def test_download_artifact_registration_validates_size_bytes() -> None:
    with pytest.raises(ValueError, match="size_bytes cannot be negative"):
        DownloadArtifactRegistration(
            artifact_id="artifact-1",
            candidate_id="candidate-1",
            queue_item_id="qi-1",
            provider="slskd",
            relative_path="candidate-1/Track.flac",
            state="completed",
            size_bytes=-1,
        )


def test_download_artifact_registration_blocks_absolute_path() -> None:
    with pytest.raises(ValueError):
        DownloadArtifactRegistration(
            artifact_id="artifact-1",
            candidate_id="candidate-1",
            queue_item_id="qi-1",
            provider="slskd",
            relative_path="/etc/passwd",
            state="completed",
        )


def test_download_artifact_registration_blocks_traversal() -> None:
    with pytest.raises(ValueError):
        DownloadArtifactRegistration(
            artifact_id="artifact-1",
            candidate_id="candidate-1",
            queue_item_id="qi-1",
            provider="slskd",
            relative_path="../escape/Track.flac",
            state="completed",
        )


def test_download_artifact_registration_blocks_dot_segments() -> None:
    with pytest.raises(ValueError):
        DownloadArtifactRegistration(
            artifact_id="artifact-1",
            candidate_id="candidate-1",
            queue_item_id="qi-1",
            provider="slskd",
            relative_path="candidate-1/./Track.flac",
            state="completed",
        )


def test_download_artifact_registration_serializes_safely() -> None:
    reg = DownloadArtifactRegistration(
        artifact_id="artifact-1",
        candidate_id="candidate-1",
        queue_item_id="qi-1",
        provider="slskd",
        relative_path="candidate-1/Track.flac",
        state="completed",
        metadata={"token": "secret"},
    )
    d = reg.to_dict()
    assert d["metadata"]["token"] == "[redacted]"
    assert "secret" not in str(d)


def test_download_artifact_registration_from_transfer_status() -> None:
    reg = DownloadArtifactRegistration.from_transfer_status(
        transfer_id="transfer-1",
        queue_item_id="qi-1",
        candidate_id="candidate-1",
        provider="slskd",
        state="completed",
        relative_path="candidate-1/Track.flac",
        size_bytes=12345678,
    )
    assert reg.artifact_id == "transfer-1"
    assert reg.state == "completed"
    assert reg.size_bytes == 12345678


def test_download_artifact_registration_from_submission_result() -> None:
    reg = DownloadArtifactRegistration.from_submission_result(
        submission_id="sub-1",
        queue_item_id="qi-1",
        candidate_id="candidate-1",
        provider="slskd",
        state="success",
        relative_path="candidate-1/Track.flac",
    )
    assert reg.artifact_id == "submit-sub-1"
    assert reg.state == "success"


def test_artifact_registration_service_register_dry_run() -> None:
    service = ArtifactRegistrationService()
    reg = DownloadArtifactRegistration(
        artifact_id="artifact-1",
        candidate_id="candidate-1",
        queue_item_id="qi-1",
        provider="slskd",
        relative_path="candidate-1/Track.flac",
        state="completed",
    )
    result = service.register_artifact(reg, dry_run=True)
    assert result.status == Status.SUCCESS
    assert len(result.planned_changes) == 1
    assert len(result.applied_changes) == 0
    assert result.summary["state"] == "completed"


def test_artifact_registration_service_register_apply() -> None:
    service = ArtifactRegistrationService()
    reg = DownloadArtifactRegistration(
        artifact_id="artifact-1",
        candidate_id="candidate-1",
        queue_item_id="qi-1",
        provider="slskd",
        relative_path="candidate-1/Track.flac",
        state="completed",
    )
    result = service.register_artifact(reg, dry_run=False)
    assert result.status == Status.SUCCESS
    assert result.summary["state"] == "completed"


def test_artifact_registration_service_register_with_warnings() -> None:
    service = ArtifactRegistrationService()
    reg = DownloadArtifactRegistration(
        artifact_id="artifact-1",
        candidate_id="candidate-1",
        queue_item_id="qi-1",
        provider="slskd",
        relative_path="candidate-1/Track.flac",
        state="completed",
        warnings=["file was locked during transfer"],
    )
    result = service.register_artifact(reg, dry_run=True)
    assert result.status == Status.WARNING
    assert len(result.warnings) >= 1


def test_artifact_registration_service_register_with_errors() -> None:
    service = ArtifactRegistrationService()
    reg = DownloadArtifactRegistration(
        artifact_id="artifact-1",
        candidate_id="candidate-1",
        queue_item_id="qi-1",
        provider="slskd",
        relative_path="candidate-1/Track.flac",
        state="failed",
        errors=["transfer failed"],
    )
    result = service.register_artifact(reg, dry_run=True)
    assert result.status == Status.FAILED
    assert len(result.errors) >= 1


def test_artifact_registration_service_register_from_transfer_status() -> None:
    service = ArtifactRegistrationService()
    result = service.register_from_transfer_status(
        transfer_id="transfer-1",
        queue_item_id="qi-1",
        candidate_id="candidate-1",
        provider="slskd",
        state="completed",
        relative_path="candidate-1/Track.flac",
        dry_run=True,
    )
    assert result.status == Status.SUCCESS
    assert result.summary["artifact_id"] == "transfer-1"
    assert result.summary["state"] == "completed"


def test_artifact_registration_service_register_from_submission() -> None:
    service = ArtifactRegistrationService()
    result = service.register_from_submission(
        submission_id="sub-1",
        queue_item_id="qi-1",
        candidate_id="candidate-1",
        provider="slskd",
        state="success",
        relative_path="candidate-1/Track.flac",
        dry_run=True,
    )
    assert result.status == Status.SUCCESS
    assert result.summary["artifact_id"] == "submit-sub-1"
    assert result.summary["state"] == "success"


def test_artifact_registration_service_rejects_invalid_relative_path() -> None:
    service = ArtifactRegistrationService()
    result = service.register_from_transfer_status(
        transfer_id="transfer-1",
        queue_item_id="qi-1",
        candidate_id="candidate-1",
        provider="slskd",
        state="completed",
        relative_path="/absolute/path/Track.flac",
        dry_run=True,
    )
    assert result.status == Status.FAILED


def test_artifact_registration_service_does_not_read_files(tmp_path) -> None:
    service = ArtifactRegistrationService()
    reg = DownloadArtifactRegistration(
        artifact_id="artifact-1",
        candidate_id="candidate-1",
        queue_item_id="qi-1",
        provider="slskd",
        relative_path="candidate-1/Track.flac",
        state="completed",
    )
    service.register_artifact(reg, dry_run=True)
    service.register_artifact(reg, dry_run=False)
    assert list(tmp_path.iterdir()) == []


def test_artifact_registration_service_does_not_access_network() -> None:
    from noqlen_flux.services import artifact_registration as mod
    source = open(mod.__file__).read()
    assert "requests" not in source
    assert "urllib" not in source
    assert "socket" not in source


def test_artifact_registration_service_does_not_import_slskd() -> None:
    from noqlen_flux.services import artifact_registration as mod
    assert "slskd" not in mod.__file__
    for name in dir(mod):
        obj = getattr(mod, name, None)
        if hasattr(obj, "__module__"):
            assert "slskd" not in (getattr(obj, "__module__", "") or "")


def test_artifact_registration_does_not_compute_checksum() -> None:
    reg = DownloadArtifactRegistration(
        artifact_id="artifact-1",
        candidate_id="candidate-1",
        queue_item_id="qi-1",
        provider="slskd",
        relative_path="candidate-1/Track.flac",
        state="completed",
    )
    d = reg.to_dict()
    assert "checksum" not in str(d).lower()
    assert "sha" not in str(d).lower()
    assert "md5" not in str(d).lower()


def test_artifact_registration_metadata_is_safe() -> None:
    reg = DownloadArtifactRegistration(
        artifact_id="artifact-1",
        candidate_id="candidate-1",
        queue_item_id="qi-1",
        provider="slskd",
        relative_path="candidate-1/Track.flac",
        state="completed",
        metadata={"api_key": "x-secret-12345", "token": "x-token-67890", "password": "x-pw-11111"},
    )
    d = reg.to_dict()
    assert d["metadata"]["api_key"] == "[redacted]"
    assert d["metadata"]["token"] == "[redacted]"
    assert d["metadata"]["password"] == "[redacted]"
    assert "x-secret-12345" not in str(d)
    assert "x-token-67890" not in str(d)
    assert "x-pw-11111" not in str(d)
