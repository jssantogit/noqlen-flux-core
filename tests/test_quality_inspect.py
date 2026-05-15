"""Tests for quality inspection bridge and integration."""

from pathlib import Path
import pytest

from noqlen_flux.audio_probe import (
    AudioProbeFinding as ProbeFinding,
    AudioProbeResult as ProbeResult,
)
from noqlen_flux.quality import (
    QualityFindingKind,
    QualityGrade,
)
from noqlen_flux.results import Status
from noqlen_flux.services.quality import QualityService


@pytest.fixture
def quality_service() -> QualityService:
    return QualityService()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


def _make_probe_result(
    *,
    item_id: str = "item-1",
    relative_path: str = "incoming/demo.flac",
    success: bool = True,
    decode_ok: bool = True,
    has_audio_stream: bool = True,
    duration_seconds: float | None = 240.0,
    sample_rate: int | None = 44100,
    codec: str | None = "flac",
    findings: list[ProbeFinding] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> ProbeResult:
    return ProbeResult(
        request_id="req-1",
        item_id=item_id,
        relative_path=relative_path,
        backend="fake",
        success=success,
        decode_ok=decode_ok,
        has_audio_stream=has_audio_stream,
        duration_seconds=duration_seconds,
        sample_rate=sample_rate,
        codec=codec,
        findings=findings or [],
        warnings=warnings or [],
        errors=errors or [],
    )


def test_probe_to_quality_excellent(quality_service: QualityService) -> None:
    probe = _make_probe_result(
        findings=[
            ProbeFinding(code="probe-ok", message="Probe ok", category="diagnostic", confidence=1.0),
            ProbeFinding(code="decode-ok", message="Decode ok", category="diagnostic", confidence=1.0),
        ],
    )
    result = quality_service.probe_to_quality_result(probe)
    assert result.grade == QualityGrade.EXCELLENT
    assert result.confidence > 0.8
    assert result.objective_failures == []
    assert result.heuristic_warnings == []


def test_probe_to_quality_medium(quality_service: QualityService) -> None:
    probe = _make_probe_result(
        findings=[
            ProbeFinding(code="probe-ok", message="Probe ok", category="diagnostic", confidence=1.0),
            ProbeFinding(code="lowpass-suspicion", message="Lowpass detected", category="heuristic_warning", confidence=0.55),
        ],
    )
    result = quality_service.probe_to_quality_result(probe)
    assert result.grade == QualityGrade.MEDIUM
    assert result.heuristic_warnings


def test_probe_to_quality_bad_objective(quality_service: QualityService) -> None:
    probe = _make_probe_result(
        success=False,
        decode_ok=False,
        findings=[
            ProbeFinding(code="decode-failure", message="Decode failed", category="objective_failure", confidence=1.0),
        ],
    )
    result = quality_service.probe_to_quality_result(probe)
    assert result.grade == QualityGrade.BAD
    assert result.objective_failures


def test_probe_to_quality_no_audio_stream(quality_service: QualityService) -> None:
    probe = _make_probe_result(
        has_audio_stream=False,
        findings=[
            ProbeFinding(code="no-audio-stream", message="No audio stream", category="objective_failure", confidence=1.0),
        ],
    )
    result = quality_service.probe_to_quality_result(probe)
    assert result.grade == QualityGrade.BAD


def test_probe_to_quality_unknown(quality_service: QualityService) -> None:
    probe = _make_probe_result(
        success=False,
        findings=[ProbeFinding(code="probe-timeout", message="Timeout", category="objective_failure", confidence=1.0)],
    )
    result = quality_service.probe_to_quality_result(probe)
    assert result.grade == QualityGrade.BAD


def test_quality_result_does_not_contain_routing(quality_service: QualityService) -> None:
    probe = _make_probe_result()
    result = quality_service.probe_to_quality_result(probe)
    d = result.to_dict()
    assert "routing_decision" not in str(d)
    assert "RoutingDecision" not in str(d)
    assert "quarantine" not in str(d)
    assert "delete_eligible" not in str(d)


def test_probe_to_quality_spectral_cutoff_heuristic_only(quality_service: QualityService) -> None:
    probe = _make_probe_result(
        findings=[
            ProbeFinding(code="probe-ok", message="Probe ok", category="diagnostic", confidence=1.0),
            ProbeFinding(code="decode-ok", message="Decode ok", category="diagnostic", confidence=1.0),
            ProbeFinding(code="spectral-cutoff-9-4khz", message="Spectral cutoff at 9.4 kHz", category="heuristic_warning", confidence=0.6),
        ],
    )
    result = quality_service.probe_to_quality_result(probe)
    assert result.grade == QualityGrade.MEDIUM, "spectral cutoff alone should not cause BAD"
    assert result.objective_failures == []
    assert len(result.heuristic_warnings) >= 1
    assert any(f.code == "spectral-cutoff-9-4khz" for f in result.heuristic_warnings)


def test_probe_to_quality_lowpass_decode_failure(quality_service: QualityService) -> None:
    probe = _make_probe_result(
        success=False,
        decode_ok=False,
        findings=[
            ProbeFinding(code="lowpass-suspicion", message="Lowpass detected", category="heuristic_warning", confidence=0.55),
            ProbeFinding(code="decode-failure", message="Decode failed", category="objective_failure", confidence=1.0),
        ],
    )
    result = quality_service.probe_to_quality_result(probe)
    assert result.grade == QualityGrade.BAD, "BAD should be from decode failure"
    assert any(f.code == "decode-failure" for f in result.objective_failures), "objective should be decode-failure"


def test_inspect_file_dry_run(quality_service: QualityService, workspace: Path) -> None:
    result = quality_service.inspect_file(
        item_id="item-1",
        relative_path="incoming/demo.wav",
        workspace_root=str(workspace),
        dry_run=True,
    )
    assert result.status == Status.SUCCESS
    assert len(result.planned_changes) >= 1


def test_inspect_file_apply_with_fake_backend(quality_service: QualityService, workspace: Path) -> None:
    from noqlen_flux.services.audio_probe import FakeProbeBackend

    backend = FakeProbeBackend(grade="excellent")
    result = quality_service.inspect_file(
        item_id="item-1",
        relative_path="incoming/demo.wav",
        workspace_root=str(workspace),
        backend=backend,
        dry_run=False,
    )
    assert result.status == Status.SUCCESS
    assert "quality_result" in result.summary
    assert result.summary["grade"] == "excellent"


def test_inspect_file_apply_bad_quality(quality_service: QualityService, workspace: Path) -> None:
    from noqlen_flux.services.audio_probe import FakeProbeBackend

    backend = FakeProbeBackend(grade="bad", has_audio_stream=False, decode_ok=False)
    result = quality_service.inspect_file(
        item_id="item-1",
        relative_path="incoming/corrupt.wav",
        workspace_root=str(workspace),
        backend=backend,
        dry_run=False,
    )
    assert result.status == Status.WARNING
    assert result.summary["grade"] == "bad"


def test_quality_service_does_not_import_routing() -> None:
    from noqlen_flux.services import quality as mod
    source = open(mod.__file__).read()
    assert "RoutingService" not in source
    assert "RoutingDecisionService" not in source


def test_quality_inspect_blocks_unsafe_path(quality_service: QualityService, workspace: Path) -> None:
    result = quality_service.inspect_file(
        item_id="item-1",
        relative_path="/etc/passwd",
        workspace_root=str(workspace),
        dry_run=True,
    )
    assert result.status == Status.FAILED
    assert result.errors
