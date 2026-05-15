"""Tests for audio probe contracts and service."""

from pathlib import Path
import pytest

from noqlen_flux.audio_probe import (
    AudioProbeFinding,
    AudioProbePolicy,
    AudioProbeRequest,
    AudioProbeResult,
    ProbeBackendKind,
)
from noqlen_flux.results import Status
from noqlen_flux.services.audio_probe import (
    AudioProbeService,
    FakeProbeBackend,
)


@pytest.fixture
def service() -> AudioProbeService:
    return AudioProbeService()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.fixture
def probe_request(workspace: Path) -> AudioProbeRequest:
    return AudioProbeRequest(
        request_id="req-1",
        item_id="item-1",
        relative_path="incoming/demo.wav",
        workspace_root=str(workspace),
    )


def test_audio_probe_request_valid(workspace: Path) -> None:
    req = AudioProbeRequest(
        request_id="req-1",
        item_id="item-1",
        relative_path="incoming/demo.wav",
        workspace_root=str(workspace),
    )
    assert req.relative_path == "incoming/demo.wav"
    assert req.backend == ProbeBackendKind.FAKE.value
    assert req.timeout_seconds == 30


def test_audio_probe_request_blocks_absolute_path(workspace: Path) -> None:
    with pytest.raises(ValueError):
        AudioProbeRequest(
            request_id="req-1",
            item_id="item-1",
            relative_path="/etc/passwd",
            workspace_root=str(workspace),
        )


def test_audio_probe_request_blocks_traversal(workspace: Path) -> None:
    with pytest.raises(ValueError):
        AudioProbeRequest(
            request_id="req-1",
            item_id="item-1",
            relative_path="../escape/file.wav",
            workspace_root=str(workspace),
        )


def test_audio_probe_request_blocks_tilde(workspace: Path) -> None:
    with pytest.raises(ValueError):
        AudioProbeRequest(
            request_id="req-1",
            item_id="item-1",
            relative_path="~/Music/file.wav",
            workspace_root=str(workspace),
        )


def test_audio_probe_request_requires_fields(workspace: Path) -> None:
    with pytest.raises(ValueError):
        AudioProbeRequest(
            request_id="",
            item_id="item-1",
            relative_path="incoming/demo.wav",
            workspace_root=str(workspace),
        )


def test_audio_probe_request_validates_timeout(workspace: Path) -> None:
    with pytest.raises(ValueError):
        AudioProbeRequest(
            request_id="req-1",
            item_id="item-1",
            relative_path="incoming/demo.wav",
            workspace_root=str(workspace),
            timeout_seconds=0,
        )


def test_audio_probe_result_valid() -> None:
    result = AudioProbeResult(
        request_id="req-1",
        item_id="item-1",
        relative_path="incoming/demo.wav",
        backend="fake",
        success=True,
        decode_ok=True,
        has_audio_stream=True,
        duration_seconds=240.0,
        sample_rate=44100,
        codec="flac",
    )
    assert result.success is True
    assert result.codec == "flac"


def test_audio_probe_result_serializes_safely() -> None:
    result = AudioProbeResult(
        request_id="req-1",
        item_id="item-1",
        relative_path="incoming/demo.wav",
        backend="fake",
        metadata={"token": "secret", "api_key": "key-value"},
    )
    d = result.to_dict()
    assert d["metadata"]["token"] == "[redacted]"
    assert d["metadata"]["api_key"] == "[redacted]"


def test_audio_probe_finding_valid() -> None:
    finding = AudioProbeFinding(
        code="decode-ok",
        message="Decode successful",
        category="diagnostic",
        confidence=1.0,
    )
    assert finding.code == "decode-ok"


def test_audio_probe_finding_requires_code() -> None:
    with pytest.raises(ValueError):
        AudioProbeFinding(code="", message="test")


def test_audio_probe_finding_serializes_safely() -> None:
    finding = AudioProbeFinding(
        code="decode-ok",
        message="Decode successful",
        metadata={"token": "secret"},
    )
    d = finding.to_dict()
    assert d["metadata"]["token"] == "[redacted]"


def test_audio_probe_policy_defaults() -> None:
    policy = AudioProbePolicy()
    assert policy.timeout_seconds == 30
    assert policy.require_audio_stream is True
    assert policy.require_decode is True


def test_audio_probe_policy_validates_timeout() -> None:
    with pytest.raises(ValueError):
        AudioProbePolicy(timeout_seconds=0)


def test_fake_probe_backend_excellent() -> None:
    backend = FakeProbeBackend(grade="excellent")
    assert backend.is_available()
    assert backend.kind == ProbeBackendKind.FAKE.value


def test_fake_probe_backend_probe_excellent(tmp_path: Path) -> None:
    backend = FakeProbeBackend(grade="excellent")
    result = backend.probe(tmp_path / "incoming" / "demo.flac")
    assert result.success is True
    assert result.decode_ok is True
    assert result.has_audio_stream is True
    assert result.duration_seconds == 240.0
    assert result.sample_rate == 44100
    assert result.codec == "flac"
    assert len(result.findings) >= 1


def test_fake_probe_backend_probe_bad_no_audio(tmp_path: Path) -> None:
    backend = FakeProbeBackend(grade="bad", has_audio_stream=False, decode_ok=False)
    result = backend.probe(tmp_path / "incoming" / "corrupt.flac")
    assert result.success is False
    assert result.decode_ok is False
    assert result.has_audio_stream is False
    assert any(f.code == "no-audio-stream" for f in result.findings)
    assert any(f.code == "decode-failure" for f in result.findings)


def test_fake_probe_backend_probe_medium(tmp_path: Path) -> None:
    backend = FakeProbeBackend(grade="medium")
    result = backend.probe(tmp_path / "incoming" / "suspicious.flac")
    assert result.success is False
    assert any(f.code == "heuristic-warning" for f in result.findings)


def test_fake_probe_backend_probe_unknown(tmp_path: Path) -> None:
    backend = FakeProbeBackend(grade="unknown")
    result = backend.probe(tmp_path / "incoming" / "mystery.flac")
    assert result.success is False
    assert any(f.code == "insufficient-data" for f in result.findings)


def test_audio_probe_service_dry_run(
    service: AudioProbeService, probe_request: AudioProbeRequest
) -> None:
    backend = FakeProbeBackend()
    result = service.probe(probe_request, backend, dry_run=True)
    assert result.status == Status.SUCCESS
    assert len(result.planned_changes) == 1
    assert result.summary["dry_run"] is True


def test_audio_probe_service_apply_excellent(
    service: AudioProbeService, probe_request: AudioProbeRequest
) -> None:
    backend = FakeProbeBackend(grade="excellent")
    result = service.probe(probe_request, backend, dry_run=False)
    assert result.status == Status.SUCCESS
    assert result.summary["success"] is True
    assert result.summary["decode_ok"] is True


def test_audio_probe_service_apply_bad(
    service: AudioProbeService, probe_request: AudioProbeRequest
) -> None:
    backend = FakeProbeBackend(grade="bad", has_audio_stream=False, decode_ok=False)
    result = service.probe(probe_request, backend, dry_run=False)
    assert result.status == Status.FAILED
    assert result.summary["success"] is False


def test_audio_probe_service_apply_medium(
    service: AudioProbeService, probe_request: AudioProbeRequest
) -> None:
    backend = FakeProbeBackend(grade="medium")
    result = service.probe(probe_request, backend, dry_run=False)
    assert result.status == Status.WARNING
    assert result.summary["success"] is False


def test_audio_probe_service_blocks_unsafe_path(
    service: AudioProbeService, workspace: Path
) -> None:
    with pytest.raises(ValueError):
        AudioProbeRequest(
            request_id="req-1",
            item_id="item-1",
            relative_path="/etc/passwd",
            workspace_root=str(workspace),
        )


def test_audio_probe_service_blocks_traversal(
    service: AudioProbeService, workspace: Path
) -> None:
    with pytest.raises(ValueError):
        AudioProbeRequest(
            request_id="req-1",
            item_id="item-1",
            relative_path="../escape/file.wav",
            workspace_root=str(workspace),
        )


def test_audio_probe_service_blocks_outside_workspace(
    service: AudioProbeService, workspace: Path
) -> None:
    with pytest.raises(ValueError):
        AudioProbeRequest(
            request_id="req-1",
            item_id="item-1",
            relative_path="../../outside/file.wav",
            workspace_root=str(workspace),
        )


def test_audio_probe_service_does_not_access_network() -> None:
    from noqlen_flux.services import audio_probe as mod
    source = open(mod.__file__).read()
    assert "requests" not in source
    assert "urllib" not in source
    assert "socket" not in source


def test_audio_probe_service_does_not_import_slskd() -> None:
    from noqlen_flux.services import audio_probe as mod
    assert "slskd" not in mod.__file__
    for name in dir(mod):
        obj = getattr(mod, name, None)
        if hasattr(obj, "__module__"):
            assert "slskd" not in (getattr(obj, "__module__", "") or "")


def test_audio_probe_service_does_not_create_files(
    service: AudioProbeService, tmp_path: Path
) -> None:
    backend = FakeProbeBackend()
    req = AudioProbeRequest(
        request_id="req-1",
        item_id="item-1",
        relative_path="incoming/demo.wav",
        workspace_root=str(tmp_path),
    )
    before = set(tmp_path.iterdir())
    service.probe(req, backend, dry_run=True)
    service.probe(req, backend, dry_run=False)
    after = set(tmp_path.iterdir())
    assert before == after
