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


# ---------------------------------------------------------------------------
# Spectral cutoff / low-pass false-positive protection tests
# ---------------------------------------------------------------------------


def _spectral_cutoff_finding() -> AudioProbeFinding:
    return AudioProbeFinding(
        code="spectral-cutoff-9-4khz",
        message="Spectral analysis shows energy cutoff around 9.4 kHz. Common in lossy encodes or streaming sources.",
        category="heuristic_warning",
        confidence=0.6,
    )


def _decode_failure_finding() -> AudioProbeFinding:
    return AudioProbeFinding(
        code="decode-failure",
        message="Audio decode failed.",
        category="objective_failure",
        confidence=1.0,
    )


def _decode_ok_finding() -> AudioProbeFinding:
    return AudioProbeFinding(
        code="decode-ok",
        message="Audio stream decoded successfully.",
        category="diagnostic",
        confidence=1.0,
    )


def test_spectral_cutoff_9_4khz_only_is_heuristic_warning(
    service: AudioProbeService, workspace: Path
) -> None:
    backend = FakeProbeBackend(
        grade="excellent",
        decode_ok=True,
        has_audio_stream=True,
        extra_findings=[_spectral_cutoff_finding()],
    )
    req = AudioProbeRequest(
        request_id="req-1",
        item_id="item-1",
        relative_path="incoming/demo.flac",
        workspace_root=str(workspace),
    )
    result = service.probe(req, backend, dry_run=False)
    probe_result = result.summary.get("probe_result", {})

    has_objective = any(
        f.get("category") == "objective_failure"
        for f in probe_result.get("findings", [])
    )
    has_heuristic = any(
        f.get("category") == "heuristic_warning"
        for f in probe_result.get("findings", [])
    )
    has_spectral = any(
        f.get("code") == "spectral-cutoff-9-4khz"
        for f in probe_result.get("findings", [])
    )

    assert has_spectral, "spectral-cutoff-9-4khz finding should be present"
    assert has_heuristic, "spectral cutoff should be a heuristic_warning"
    assert not has_objective, "spectral cutoff isolated must NOT be objective_failure"
    assert result.status != Status.FAILED, "spectral cutoff alone must not cause FAILED status"


def test_qobuz_like_cutoff_9_4khz_decode_ok_is_not_bad(
    service: AudioProbeService, workspace: Path
) -> None:
    backend = FakeProbeBackend(
        grade="excellent",
        decode_ok=True,
        has_audio_stream=True,
        extra_findings=[_spectral_cutoff_finding(), _decode_ok_finding()],
    )
    req = AudioProbeRequest(
        request_id="req-1",
        item_id="item-1",
        relative_path="incoming/qobuz_like.flac",
        workspace_root=str(workspace),
    )
    result = service.probe(req, backend, dry_run=False)
    probe_result = result.summary.get("probe_result", {})

    has_spectral = any(
        f.get("code") == "spectral-cutoff-9-4khz"
        for f in probe_result.get("findings", [])
    )
    has_decode_ok = any(
        f.get("code") == "decode-ok"
        for f in probe_result.get("findings", [])
    )
    has_objective = any(
        f.get("category") == "objective_failure"
        for f in probe_result.get("findings", [])
    )

    assert has_spectral, "spectral cutoff finding should be present"
    assert has_decode_ok, "decode-ok finding should be present"
    assert not has_objective, (
        "qobuz-like cutoff with decode_ok must NOT produce objective_failure"
    )


def test_lowpass_suspicion_only_is_heuristic_warning_not_objective(
    service: AudioProbeService, workspace: Path
) -> None:
    lowpass_finding = AudioProbeFinding(
        code="lowpass-suspicion",
        message="Energy rolloff suggests low-pass filter may have been applied.",
        category="heuristic_warning",
        confidence=0.55,
    )
    backend = FakeProbeBackend(
        grade="excellent",
        decode_ok=True,
        has_audio_stream=True,
        extra_findings=[lowpass_finding],
    )
    req = AudioProbeRequest(
        request_id="req-1",
        item_id="item-1",
        relative_path="incoming/lowpass.flac",
        workspace_root=str(workspace),
    )
    result = service.probe(req, backend, dry_run=False)
    probe_result = result.summary.get("probe_result", {})

    has_objective = any(
        f.get("category") == "objective_failure"
        for f in probe_result.get("findings", [])
    )
    has_lowpass = any(
        f.get("code") == "lowpass-suspicion"
        for f in probe_result.get("findings", [])
    )

    assert has_lowpass, "lowpass-suspicion finding should be present"
    assert not has_objective, "lowpass suspicion alone must NOT be objective_failure"


def test_lowpass_suspicion_with_valid_metadata_is_not_bad(
    service: AudioProbeService, workspace: Path
) -> None:
    lowpass_finding = AudioProbeFinding(
        code="lowpass-suspicion",
        message="Energy rolloff detected, but file metadata and decode are valid.",
        category="heuristic_warning",
        confidence=0.55,
    )
    decode_ok = AudioProbeFinding(
        code="decode-ok",
        message="Audio stream decoded successfully.",
        category="diagnostic",
        confidence=1.0,
    )
    backend = FakeProbeBackend(
        grade="excellent",
        decode_ok=True,
        has_audio_stream=True,
        extra_findings=[lowpass_finding, decode_ok],
    )
    req = AudioProbeRequest(
        request_id="req-1",
        item_id="item-1",
        relative_path="incoming/lowpass_valid.flac",
        workspace_root=str(workspace),
    )
    result = service.probe(req, backend, dry_run=False)
    probe_result = result.summary.get("probe_result", {})

    has_objective = any(
        f.get("category") == "objective_failure"
        for f in probe_result.get("findings", [])
    )
    has_lowpass = any(
        f.get("code") == "lowpass-suspicion"
        for f in probe_result.get("findings", [])
    )

    assert has_lowpass, "lowpass-suspicion finding should be present"
    assert not has_objective, (
        "lowpass + decode_ok + valid metadata must NOT produce objective_failure"
    )
    assert result.status != Status.FAILED, (
        "lowpass + valid metadata must not produce FAILED status"
    )


def test_lowpass_plus_decode_failure_is_bad_by_decode_not_lowpass(
    service: AudioProbeService, workspace: Path
) -> None:
    lowpass_finding = AudioProbeFinding(
        code="lowpass-suspicion",
        message="Energy rolloff detected.",
        category="heuristic_warning",
        confidence=0.55,
    )
    decode_fail = AudioProbeFinding(
        code="decode-failure",
        message="Audio decode failed.",
        category="objective_failure",
        confidence=1.0,
    )
    backend = FakeProbeBackend(
        grade="excellent",
        decode_ok=False,
        has_audio_stream=True,
        extra_findings=[lowpass_finding, decode_fail],
    )
    req = AudioProbeRequest(
        request_id="req-1",
        item_id="item-1",
        relative_path="incoming/lowpass_bad.flac",
        workspace_root=str(workspace),
    )
    result = service.probe(req, backend, dry_run=False)
    probe_result = result.summary.get("probe_result", {})

    has_objective = any(
        f.get("category") == "objective_failure"
        for f in probe_result.get("findings", [])
    )
    decode_fail_findings = [
        f for f in probe_result.get("findings", [])
        if f.get("category") == "objective_failure"
    ]
    lowpass_findings = [
        f for f in probe_result.get("findings", [])
        if f.get("category") == "heuristic_warning"
    ]

    assert has_objective, "decode_failure should produce objective_failure"
    assert any(f.get("code") == "decode-failure" for f in decode_fail_findings), (
        "objective_failure should be decode-failure, not lowpass"
    )
    assert any(f.get("code") == "lowpass-suspicion" for f in lowpass_findings), (
        "lowpass should still be present as heuristic_warning"
    )
    assert result.status == Status.FAILED, (
        "decode_failure should cause FAILED (but due to decode, not lowpass)"
    )


def test_quality_service_does_not_call_routing_service() -> None:
    from noqlen_flux.services.quality import QualityService

    service = QualityService()
    result = service.evaluate_fake_quality(
        item_id="item-1",
        grade="bad",
        findings=[{
            "code": "spectral-cutoff-9-4khz",
            "message": "Spectral cutoff at 9.4 kHz.",
            "kind": "heuristic_warning",
            "severity": "warning",
            "confidence": 0.6,
        }],
    )
    result_dict = result.to_dict()
    assert "routing_decision" not in str(result_dict)
    assert "RoutingDecision" not in str(result_dict)
    assert "RoutingService" not in str(result_dict)
    assert "routing" not in result_dict.get("operation", "")


def test_audio_probe_service_does_not_import_routing_service() -> None:
    from noqlen_flux.services import audio_probe as mod

    source = open(mod.__file__).read()
    assert "RoutingService" not in source
    assert "RoutingDecisionService" not in source
    assert "routing" not in source.lower().split("from")[-1].split("import")[0]
