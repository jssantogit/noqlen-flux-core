from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from noqlen_flux.audio_probe import (
    AudioProbeFinding,
    AudioProbePolicy,
    AudioProbeRequest,
    AudioProbeResult,
    ProbeBackendKind,
)
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
from noqlen_flux.services.base import FluxService


class ProbeBackend(ABC):
    @property
    @abstractmethod
    def kind(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def probe(self, file_path: Path, *, timeout_seconds: int = 30) -> AudioProbeResult:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError


class FakeProbeBackend(ProbeBackend):
    def __init__(
        self,
        *,
        grade: str = "excellent",
        decode_ok: bool = True,
        has_audio_stream: bool = True,
        duration_seconds: float | None = 240.0,
        sample_rate: int | None = 44100,
        bit_depth: int | None = 16,
        codec: str | None = "flac",
        bitrate_bps: int | None = None,
        channels: int | None = 2,
        file_size_bytes: int | None = None,
        extra_findings: list[AudioProbeFinding] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> None:
        self._grade = grade
        self._decode_ok = decode_ok
        self._has_audio_stream = has_audio_stream
        self._duration_seconds = duration_seconds
        self._sample_rate = sample_rate
        self._bit_depth = bit_depth
        self._codec = codec
        self._bitrate_bps = bitrate_bps
        self._channels = channels
        self._file_size_bytes = file_size_bytes
        self._extra_findings = list(extra_findings or [])
        self._warnings = list(warnings or [])
        self._errors = list(errors or [])

    @property
    def kind(self) -> str:
        return ProbeBackendKind.FAKE.value

    def is_available(self) -> bool:
        return True

    def probe(self, file_path: Path, *, timeout_seconds: int = 30) -> AudioProbeResult:
        request_id = str(uuid.uuid4())
        item_id = str(file_path.stem)

        success = self._grade == "excellent" and self._decode_ok and self._has_audio_stream

        findings: list[AudioProbeFinding] = list(self._extra_findings)

        has_explicit_objective = any(
            f.category == "objective_failure" for f in self._extra_findings
        )

        if not has_explicit_objective and self._grade == "excellent":
            findings.append(
                AudioProbeFinding(
                    code="probe-ok",
                    message="Audio file probe completed successfully.",
                    category="diagnostic",
                    confidence=1.0,
                )
            )
            if self._decode_ok:
                findings.append(
                    AudioProbeFinding(
                        code="decode-ok",
                        message="Audio stream decoded successfully.",
                        category="diagnostic",
                        confidence=1.0,
                    )
                )
        elif not has_explicit_objective and self._grade == "medium":
            findings.append(
                AudioProbeFinding(
                    code="heuristic-warning",
                    message="Potential quality concern detected in audio stream.",
                    category="heuristic_warning",
                    confidence=0.7,
                )
            )
        elif not has_explicit_objective and self._grade == "bad":
            if not self._has_audio_stream:
                findings.append(
                    AudioProbeFinding(
                        code="no-audio-stream",
                        message="No audio stream found in file.",
                        category="objective_failure",
                        confidence=1.0,
                    )
                )
            if not self._decode_ok:
                findings.append(
                    AudioProbeFinding(
                        code="decode-failure",
                        message="Audio decode failed.",
                        category="objective_failure",
                        confidence=1.0,
                    )
                )
            if self._duration_seconds and self._duration_seconds <= 0:
                findings.append(
                    AudioProbeFinding(
                        code="invalid-duration",
                        message="Invalid or zero duration detected.",
                        category="objective_failure",
                        confidence=1.0,
                    )
                )
        elif not has_explicit_objective and self._grade == "unknown":
            findings.append(
                AudioProbeFinding(
                    code="insufficient-data",
                    message="Insufficient data to determine quality.",
                    category="diagnostic",
                    confidence=0.1,
                )
            )

        return AudioProbeResult(
            request_id=request_id,
            item_id=item_id,
            relative_path=str(file_path),
            backend=self.kind,
            success=success,
            duration_seconds=self._duration_seconds,
            sample_rate=self._sample_rate,
            bit_depth=self._bit_depth,
            codec=self._codec,
            bitrate_bps=self._bitrate_bps,
            channels=self._channels,
            file_size_bytes=self._file_size_bytes,
            decode_ok=self._decode_ok,
            has_audio_stream=self._has_audio_stream,
            stream_count=1 if self._has_audio_stream else 0,
            audio_stream_count=1 if self._has_audio_stream else 0,
            findings=findings,
            warnings=list(self._warnings),
            errors=list(self._errors),
        )


class AudioProbeService(FluxService):
    operation = "audio-probe"

    def probe(
        self,
        request: AudioProbeRequest,
        backend: ProbeBackend,
        *,
        policy: AudioProbePolicy | None = None,
        dry_run: bool = True,
    ) -> FluxResult:
        warnings: list[FluxWarning] = []
        errors: list[FluxError] = []

        effective_policy = policy or AudioProbePolicy()

        if not is_safe_relative_path(request.relative_path):
            return self.result(
                Status.FAILED,
                error=f"Unsafe relative path: {request.relative_path}",
            )

        workspace = Path(request.workspace_root)
        try:
            safe_workspace_root(workspace)
        except PathSafetyError as exc:
            return self.result(
                Status.FAILED,
                error=f"Unsafe workspace root: {exc.message}",
            )

        full_path = workspace / request.relative_path
        try:
            ensure_within_workspace(full_path, workspace)
        except PathSafetyError as exc:
            return self.result(
                Status.FAILED,
                error=f"Path outside workspace: {exc.message}",
            )

        if dry_run:
            planned = PlannedChange(
                action="probe-audio",
                target=str(full_path),
                reason=f"Would probe audio file: {request.relative_path}",
                metadata={"backend": backend.kind, "item_id": request.item_id},
            )
            artifact = Artifact(
                kind="audio-probe-plan",
                description=f"Planned audio probe for {request.item_id}",
                metadata={
                    "item_id": request.item_id,
                    "relative_path": request.relative_path,
                    "backend": backend.kind,
                },
            )
            step = self.step(
                "probe-dry-run",
                Status.SUCCESS,
                f"Would probe {request.relative_path} with backend {backend.kind}",
            )
            return FluxResult(
                operation=self.operation,
                status=Status.SUCCESS,
                steps=[step],
                artifacts=[artifact],
                planned_changes=[planned],
                summary={
                    "item_id": request.item_id,
                    "relative_path": request.relative_path,
                    "backend": backend.kind,
                    "dry_run": True,
                },
            ).finish()

        if not backend.is_available():
            return self.result(
                Status.FAILED,
                error=f"Probe backend {backend.kind} is not available",
            )

        try:
            result = backend.probe(full_path, timeout_seconds=effective_policy.timeout_seconds)
        except Exception as exc:
            return self.result(
                Status.FAILED,
                error=f"Probe failed: {exc}",
            )

        if result.errors:
            for e in result.errors:
                errors.append(self.error("probe-error", e, context={"item_id": result.item_id}))

        if result.warnings:
            for w in result.warnings:
                warnings.append(
                    self.warning("probe-warning", w, severity=Severity.WARNING, context={"item_id": result.item_id})
                )

        has_objective_failures = any(
            f.category == "objective_failure" for f in result.findings
        )

        if has_objective_failures:
            errors.append(
                self.error(
                    "objective-failure",
                    "Objective failure(s) found during audio probe",
                    context={"item_id": result.item_id},
                )
            )

        artifact = Artifact(
            kind="audio-probe-result",
            description=f"Audio probe result for {result.item_id}",
            metadata={
                "item_id": result.item_id,
                "relative_path": result.relative_path,
                "backend": result.backend,
                "success": result.success,
                "decode_ok": result.decode_ok,
                "has_audio_stream": result.has_audio_stream,
                "finding_count": len(result.findings),
                "probe_result": result.to_dict(),
            },
        )

        step_status = (
            Status.FAILED if errors
            else Status.WARNING if (warnings or not result.success)
            else Status.SUCCESS
        )
        step = self.step(
            "probe-apply",
            step_status,
            f"Probed {request.relative_path} with backend {result.backend}",
            warnings=warnings,
            errors=errors,
            artifacts=[artifact],
        )

        return FluxResult(
            operation=self.operation,
            status=step_status,
            steps=[step],
            warnings=warnings,
            errors=errors,
            artifacts=[artifact],
            summary={
                "item_id": result.item_id,
                "relative_path": result.relative_path,
                "backend": result.backend,
                "success": result.success,
                "decode_ok": result.decode_ok,
                "has_audio_stream": result.has_audio_stream,
                "finding_count": len(result.findings),
                "duration_seconds": result.duration_seconds,
                "sample_rate": result.sample_rate,
                "codec": result.codec,
                "probe_result": result.to_dict(),
            },
        ).finish()
