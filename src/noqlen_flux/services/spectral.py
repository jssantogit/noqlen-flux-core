from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from noqlen_flux.results import (
    Artifact,
    FluxError,
    FluxResult,
    FluxWarning,
    PlannedChange,
    Severity,
    Status,
)
from noqlen_flux.safety import (
    PathSafetyError,
    ensure_within_workspace,
    is_safe_relative_path,
    safe_workspace_root,
)
from noqlen_flux.spectral import (
    DEFAULT_SPECTRAL_POLICY,
    SpectralAnalysisRequest,
    SpectralAnalysisResult,
    SpectralEvidenceKind,
    SpectralFinding,
    SpectralPolicy,
    SpectralProfile,
    SpectralSignalKind,
)
from noqlen_flux.services.base import FluxService


class SpectralBackend(ABC):
    @property
    @abstractmethod
    def kind(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def analyze(self, file_path: Path, *, timeout_seconds: int = 30) -> SpectralAnalysisResult:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError


class FakeSpectralBackend(SpectralBackend):
    def __init__(
        self,
        *,
        profile: SpectralProfile | None = None,
        extra_findings: list[SpectralFinding] | None = None,
        success: bool = True,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> None:
        self._profile = profile or SpectralProfile()
        self._extra_findings = list(extra_findings or [])
        self._success = success
        self._warnings = list(warnings or [])
        self._errors = list(errors or [])

    @property
    def kind(self) -> str:
        return "fake"

    def is_available(self) -> bool:
        return True

    def analyze(self, file_path: Path, *, timeout_seconds: int = 30) -> SpectralAnalysisResult:
        request_id = str(uuid.uuid4())
        item_id = str(file_path.stem) if file_path.stem else "unknown"

        findings = list(self._extra_findings)
        if not self._extra_findings:
            findings = _build_default_findings(self._profile)

        objective_failures = [f for f in findings if f.kind == SpectralSignalKind.OBJECTIVE_FAILURE]
        heuristic_warnings = [f for f in findings if f.kind == SpectralSignalKind.HEURISTIC_WARNING]
        review_signals = [f for f in findings if f.kind == SpectralSignalKind.REVIEW_SIGNAL]
        confidence_signals = [f for f in findings if f.kind == SpectralSignalKind.CONFIDENCE_SIGNAL]
        diagnostics = [f for f in findings if f.kind == SpectralSignalKind.DIAGNOSTIC]

        evidence_summary = {
            "has_cutoff": self._profile.spectral_cutoff_hz is not None,
            "has_lowpass": self._profile.lowpass_detected,
            "has_fake_bit_depth": self._profile.fake_bit_depth,
            "has_fake_sample_rate": self._profile.fake_sample_rate,
            "has_upsampled": self._profile.upsampled,
            "has_downsampled": self._profile.downsampled,
            "has_transcode_signature": self._profile.transcode_signature is not None,
            "has_container_mismatch": self._profile.container_codec_mismatch,
            "has_bitrate_anomaly": self._profile.bitrate_anomaly,
            "has_clipping": self._profile.clipping_detected,
            "has_loudness_anomaly": self._profile.loudness_anomaly,
            "has_noise_floor_elevated": self._profile.noise_floor_elevated,
            "objective_failure_count": len(objective_failures),
            "heuristic_warning_count": len(heuristic_warnings),
            "review_signal_count": len(review_signals),
            "confidence_signal_count": len(confidence_signals),
        }

        return SpectralAnalysisResult(
            request_id=request_id,
            item_id=item_id,
            relative_path=str(file_path),
            backend=self.kind,
            success=self._success,
            profile=self._profile,
            findings=findings,
            objective_failures=objective_failures,
            heuristic_warnings=heuristic_warnings,
            review_signals=review_signals,
            confidence_signals=confidence_signals,
            diagnostics=diagnostics,
            evidence_summary=evidence_summary,
            warnings=list(self._warnings),
            errors=list(self._errors),
        )


def _build_default_findings(profile: SpectralProfile) -> list[SpectralFinding]:
    findings: list[SpectralFinding] = []

    if not profile.has_audio_stream:
        findings.append(SpectralFinding(
            code="no-audio-stream",
            message="No audio stream detected.",
            kind=SpectralSignalKind.OBJECTIVE_FAILURE,
            evidence=SpectralEvidenceKind.FORMAT_FLAG,
            confidence=1.0,
        ))
    if not profile.decode_ok:
        findings.append(SpectralFinding(
            code="decode-failure",
            message="Audio decode failed.",
            kind=SpectralSignalKind.OBJECTIVE_FAILURE,
            evidence=SpectralEvidenceKind.FORMAT_FLAG,
            confidence=1.0,
        ))
    if not profile.container_readable:
        findings.append(SpectralFinding(
            code="container-unreadable",
            message="Container metadata unreadable.",
            kind=SpectralSignalKind.OBJECTIVE_FAILURE,
            evidence=SpectralEvidenceKind.FORMAT_FLAG,
            confidence=1.0,
        ))

    if profile.spectral_cutoff_hz is not None:
        findings.append(SpectralFinding(
            code="spectral-cutoff",
            message=f"Spectral cutoff detected at {profile.spectral_cutoff_hz} Hz.",
            kind=SpectralSignalKind.HEURISTIC_WARNING,
            evidence=SpectralEvidenceKind.CUTOFF,
            confidence=0.6,
            cutoff_hz=float(profile.spectral_cutoff_hz),
            metadata={"cutoff_hz": profile.spectral_cutoff_hz},
        ))

    if profile.lowpass_detected:
        findings.append(SpectralFinding(
            code="lowpass-detected",
            message="Low-pass filter signature detected.",
            kind=SpectralSignalKind.HEURISTIC_WARNING,
            evidence=SpectralEvidenceKind.LOWPASS,
            confidence=0.55,
        ))

    if profile.fake_bit_depth:
        findings.append(SpectralFinding(
            code="fake-bit-depth",
            message="Declared bit depth does not match actual content.",
            kind=SpectralSignalKind.HEURISTIC_WARNING,
            evidence=SpectralEvidenceKind.FAKE_BIT_DEPTH,
            confidence=0.7,
        ))

    if profile.fake_sample_rate:
        findings.append(SpectralFinding(
            code="fake-sample-rate",
            message="Declared sample rate does not match actual content.",
            kind=SpectralSignalKind.HEURISTIC_WARNING,
            evidence=SpectralEvidenceKind.FAKE_SAMPLE_RATE,
            confidence=0.7,
        ))

    if profile.upsampled:
        findings.append(SpectralFinding(
            code="upsampled-content",
            message="Content appears to have been upsampled.",
            kind=SpectralSignalKind.HEURISTIC_WARNING,
            evidence=SpectralEvidenceKind.UPSAMPLED,
            confidence=0.6,
        ))

    if profile.downsampled:
        findings.append(SpectralFinding(
            code="downsampled-content",
            message="Content appears to have been downsampled.",
            kind=SpectralSignalKind.HEURISTIC_WARNING,
            evidence=SpectralEvidenceKind.DOWNSAMPLED,
            confidence=0.6,
        ))

    if profile.transcode_signature:
        findings.append(SpectralFinding(
            code="transcode-signature",
            message=f"Transcode signature detected: {profile.transcode_signature}.",
            kind=SpectralSignalKind.HEURISTIC_WARNING,
            evidence=SpectralEvidenceKind.TRANSCODE_SIGNATURE,
            confidence=0.65,
            metadata={"signature": profile.transcode_signature},
        ))

    if profile.container_codec_mismatch:
        findings.append(SpectralFinding(
            code="container-codec-mismatch",
            message="Container format is inconsistent with codec used.",
            kind=SpectralSignalKind.HEURISTIC_WARNING,
            evidence=SpectralEvidenceKind.CONTAINER_MISMATCH,
            confidence=0.65,
        ))

    if profile.bitrate_anomaly:
        findings.append(SpectralFinding(
            code="bitrate-anomaly",
            message="Bitrate is anomalous for declared format.",
            kind=SpectralSignalKind.HEURISTIC_WARNING,
            evidence=SpectralEvidenceKind.BITRATE_ANOMALY,
            confidence=0.6,
        ))

    if profile.clipping_detected:
        findings.append(SpectralFinding(
            code="clipping-detected",
            message="Audio clipping detected. May indicate poor source.",
            kind=SpectralSignalKind.REVIEW_SIGNAL,
            evidence=SpectralEvidenceKind.CLIPPING,
            confidence=0.5,
        ))

    if profile.loudness_anomaly:
        findings.append(SpectralFinding(
            code="loudness-anomaly",
            message="Loudness anomaly detected. Levels may be inconsistent.",
            kind=SpectralSignalKind.REVIEW_SIGNAL,
            evidence=SpectralEvidenceKind.LOUDNESS,
            confidence=0.5,
        ))

    if profile.noise_floor_elevated:
        findings.append(SpectralFinding(
            code="noise-floor-elevated",
            message="Noise floor appears elevated. May indicate transcoding.",
            kind=SpectralSignalKind.REVIEW_SIGNAL,
            evidence=SpectralEvidenceKind.NOISE_FLOOR,
            confidence=0.45,
        ))

    findings.append(SpectralFinding(
        code="spectral-analysis-complete",
        message=f"Spectral analysis complete: {profile.codec or 'unknown'} {profile.sample_rate or 0} Hz {profile.bit_depth or 0}-bit.",
        kind=SpectralSignalKind.DIAGNOSTIC,
        evidence=SpectralEvidenceKind.FORMAT_FLAG,
        confidence=1.0,
    ))

    return findings


class SpectralAnalysisService(FluxService):
    operation = "spectral-analysis"

    def analyze(
        self,
        request: SpectralAnalysisRequest,
        backend: SpectralBackend,
        *,
        policy: SpectralPolicy | None = None,
        dry_run: bool = True,
    ) -> FluxResult:
        effective_policy = policy or DEFAULT_SPECTRAL_POLICY

        if not is_safe_relative_path(request.relative_path):
            return self.result(Status.FAILED, error=f"Unsafe relative path: {request.relative_path}")

        workspace = Path(request.workspace_root)
        try:
            safe_workspace_root(workspace)
        except PathSafetyError as exc:
            return self.result(Status.FAILED, error=f"Unsafe workspace root: {exc.message}")

        full_path = workspace / request.relative_path
        try:
            ensure_within_workspace(full_path, workspace)
        except PathSafetyError as exc:
            return self.result(Status.FAILED, error=f"Path outside workspace: {exc.message}")

        if dry_run:
            planned = PlannedChange(
                action="spectral-analysis",
                target=str(full_path),
                reason=f"Would run spectral analysis on: {request.relative_path}",
                metadata={"backend": backend.kind, "item_id": request.item_id},
            )
            artifact = Artifact(
                kind="spectral-analysis-plan",
                description=f"Planned spectral analysis for {request.item_id}",
                metadata={"item_id": request.item_id, "relative_path": request.relative_path},
            )
            step = self.step(
                "spectral-dry-run",
                Status.SUCCESS,
                f"Would analyze {request.relative_path} with backend {backend.kind}",
                artifacts=[artifact],
            )
            return FluxResult(
                operation=self.operation,
                status=Status.SUCCESS,
                steps=[step],
                artifacts=[artifact],
                planned_changes=[planned],
                summary={"item_id": request.item_id, "relative_path": request.relative_path, "dry_run": True},
            ).finish()

        if not backend.is_available():
            return self.result(Status.FAILED, error=f"Spectral backend {backend.kind} is not available")

        try:
            result = backend.analyze(full_path, timeout_seconds=request.timeout_seconds)
        except Exception as exc:
            return self.result(Status.FAILED, error=f"Spectral analysis failed: {exc}")

        if result.errors:
            for e in result.errors:
                self.error("spectral-error", e)

        if result.warnings:
            for w in result.warnings:
                self.warning("spectral-warning", w, severity=Severity.WARNING)

        step_status = Status.SUCCESS
        has_issues = result.objective_failures or result.heuristic_warnings or result.review_signals
        if result.objective_failures:
            step_status = Status.WARNING
        elif has_issues:
            step_status = Status.SUCCESS

        artifact = Artifact(
            kind="spectral-analysis-result",
            description=f"Spectral analysis result for {result.item_id}",
            metadata={
                "item_id": result.item_id,
                "relative_path": result.relative_path,
                "backend": result.backend,
                "success": result.success,
                "objective_failure_count": len(result.objective_failures),
                "heuristic_warning_count": len(result.heuristic_warnings),
                "review_signal_count": len(result.review_signals),
                "evidence_summary": result.evidence_summary,
                "spectral_result": result.to_dict(),
            },
        )

        step = self.step(
            "spectral-apply",
            step_status,
            f"Spectral analysis complete for {result.item_id}",
            artifacts=[artifact],
        )

        return FluxResult(
            operation=self.operation,
            status=step_status,
            steps=[step],
            artifacts=[artifact],
            summary={
                "item_id": result.item_id,
                "relative_path": result.relative_path,
                "backend": result.backend,
                "success": result.success,
                "objective_failure_count": len(result.objective_failures),
                "heuristic_warning_count": len(result.heuristic_warnings),
                "review_signal_count": len(result.review_signals),
                "evidence_summary": result.evidence_summary,
                "spectral_result": result.to_dict(),
            },
        ).finish()
