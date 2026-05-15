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


class FfmpegProbeBackend(ProbeBackend):
    def __init__(
        self,
        *,
        ffprobe_path: str = "ffprobe",
        ffmpeg_path: str = "ffmpeg",
        timeout_seconds: int = 30,
    ) -> None:
        self._ffprobe_path = ffprobe_path
        self._ffmpeg_path = ffmpeg_path
        self._timeout_seconds = timeout_seconds

    @property
    def kind(self) -> str:
        return ProbeBackendKind.FFPROBE.value

    def is_available(self) -> bool:
        import subprocess
        try:
            ffprobe_result = subprocess.run(
                [self._ffprobe_path, "-version"],
                capture_output=True,
                timeout=5,
            )
            ffmpeg_result = subprocess.run(
                [self._ffmpeg_path, "-version"],
                capture_output=True,
                timeout=5,
            )
            return ffprobe_result.returncode == 0 and ffmpeg_result.returncode == 0
        except Exception:
            return False

    def probe(self, file_path: Path, *, timeout_seconds: int = 30) -> AudioProbeResult:
        import json
        import subprocess

        request_id = str(uuid.uuid4())
        item_id = str(file_path.stem)
        effective_timeout = min(timeout_seconds, self._timeout_seconds)

        try:
            cmd = [
                self._ffprobe_path,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(file_path),
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=effective_timeout,
            )

            if result.returncode != 0:
                stderr_text = result.stderr.decode("utf-8", errors="replace").strip()
                return AudioProbeResult(
                    request_id=request_id,
                    item_id=item_id,
                    relative_path=str(file_path),
                    backend=self.kind,
                    success=False,
                    findings=[
                        AudioProbeFinding(
                            code="ffprobe-error",
                            message=f"ffprobe returned non-zero exit code: {stderr_text[:200] if stderr_text else str(result.returncode)}",
                            category="objective_failure",
                            confidence=1.0,
                        )
                    ],
                    errors=[f"ffprobe error: {stderr_text[:200] if stderr_text else 'exit code ' + str(result.returncode)}"],
                )

            data = json.loads(result.stdout.decode("utf-8"))
            parsed = self._parse_ffprobe_output(data, file_path, request_id, item_id)
            if parsed.success and parsed.has_audio_stream:
                self._validate_decode(file_path, parsed, effective_timeout)
            return parsed

        except subprocess.TimeoutExpired:
            return AudioProbeResult(
                request_id=request_id,
                item_id=item_id,
                relative_path=str(file_path),
                backend=self.kind,
                success=False,
                findings=[
                    AudioProbeFinding(
                        code="probe-timeout",
                        message=f"ffprobe timed out after {effective_timeout}s.",
                        category="objective_failure",
                        confidence=1.0,
                    )
                ],
                errors=[f"ffprobe timed out after {effective_timeout}s"],
            )
        except FileNotFoundError:
            return AudioProbeResult(
                request_id=request_id,
                item_id=item_id,
                relative_path=str(file_path),
                backend=self.kind,
                success=False,
                findings=[
                    AudioProbeFinding(
                        code="ffprobe-missing",
                        message=f"ffprobe not found at '{self._ffprobe_path}'. ffmpeg/ffprobe is optional and must be installed separately.",
                        category="objective_failure",
                        confidence=1.0,
                    )
                ],
                errors=[f"ffprobe not found: {self._ffprobe_path}"],
            )
        except json.JSONDecodeError:
            return AudioProbeResult(
                request_id=request_id,
                item_id=item_id,
                relative_path=str(file_path),
                backend=self.kind,
                success=False,
                findings=[
                    AudioProbeFinding(
                        code="ffprobe-parse-error",
                        message="ffprobe output could not be parsed as JSON.",
                        category="objective_failure",
                        confidence=1.0,
                    )
                ],
                errors=["ffprobe output parse error"],
            )
        except Exception as exc:
            return AudioProbeResult(
                request_id=request_id,
                item_id=item_id,
                relative_path=str(file_path),
                backend=self.kind,
                success=False,
                findings=[
                    AudioProbeFinding(
                        code="probe-exception",
                        message=f"Unexpected error during probe: {str(exc)[:200]}",
                        category="objective_failure",
                        confidence=1.0,
                    )
                ],
                errors=[f"Probe exception: {str(exc)[:200]}"],
            )

    def _validate_decode(
        self,
        file_path: Path,
        result: AudioProbeResult,
        timeout_seconds: int,
    ) -> None:
        import subprocess

        try:
            decode = subprocess.run(
                [
                    self._ffmpeg_path,
                    "-v", "error",
                    "-i", str(file_path),
                    "-f", "null",
                    "-",
                ],
                capture_output=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            object.__setattr__(result, "success", False)
            object.__setattr__(result, "decode_ok", False)
            result.findings.append(
                AudioProbeFinding(
                    code="decode-timeout",
                    message=f"ffmpeg decode timed out after {timeout_seconds}s.",
                    category="objective_failure",
                    confidence=1.0,
                )
            )
            result.errors.append(f"ffmpeg decode timed out after {timeout_seconds}s")
            return
        except FileNotFoundError:
            object.__setattr__(result, "success", False)
            object.__setattr__(result, "decode_ok", False)
            result.findings.append(
                AudioProbeFinding(
                    code="ffmpeg-missing",
                    message=f"ffmpeg not found at '{self._ffmpeg_path}'. ffmpeg/ffprobe is optional and must be installed separately.",
                    category="objective_failure",
                    confidence=1.0,
                )
            )
            result.errors.append(f"ffmpeg not found: {self._ffmpeg_path}")
            return

        if decode.returncode != 0:
            stderr_text = decode.stderr.decode("utf-8", errors="replace").strip()
            object.__setattr__(result, "success", False)
            object.__setattr__(result, "decode_ok", False)
            result.findings.append(
                AudioProbeFinding(
                    code="decode-failure",
                    message=f"ffmpeg decode returned non-zero exit code: {stderr_text[:200] if stderr_text else str(decode.returncode)}",
                    category="objective_failure",
                    confidence=1.0,
                )
            )
            result.errors.append(f"ffmpeg decode error: {stderr_text[:200] if stderr_text else 'exit code ' + str(decode.returncode)}")
            return

        result.findings.append(
            AudioProbeFinding(
                code="decode-ok",
                message="Audio stream decoded successfully.",
                category="diagnostic",
                confidence=1.0,
            )
        )

    def _parse_ffprobe_output(
        self,
        data: dict[str, Any],
        file_path: Path,
        request_id: str,
        item_id: str,
    ) -> AudioProbeResult:
        fmt = data.get("format", {})
        streams = data.get("streams", [])
        if not isinstance(streams, list):
            streams = []

        audio_streams = [s for s in streams if isinstance(s, dict) and s.get("codec_type") == "audio"]
        has_audio_stream = len(audio_streams) > 0

        duration_raw = fmt.get("duration")
        duration = None
        if isinstance(duration_raw, str):
            try:
                duration = float(duration_raw)
            except (ValueError, TypeError):
                duration = None
        elif isinstance(duration_raw, (int, float)):
            duration = float(duration_raw)

        file_size = fmt.get("size")
        if isinstance(file_size, str):
            try:
                file_size = int(file_size)
            except (ValueError, TypeError):
                file_size = None

        sample_rate = None
        bit_depth = None
        codec = None
        channels = None
        bitrate = None

        if audio_streams:
            first_audio = audio_streams[0]
            sr = first_audio.get("sample_rate")
            if isinstance(sr, str):
                try:
                    sample_rate = int(sr)
                except (ValueError, TypeError):
                    pass
            elif isinstance(sr, (int, float)):
                sample_rate = int(sr)

            bd = first_audio.get("bits_per_raw_sample") or first_audio.get("bits_per_sample")
            if isinstance(bd, str):
                try:
                    bit_depth = int(bd)
                except (ValueError, TypeError):
                    pass
            elif isinstance(bd, (int, float)):
                bit_depth = int(bd)

            codec = first_audio.get("codec_name") or first_audio.get("codec")
            if isinstance(codec, str):
                codec = codec.lower().strip()

            ch = first_audio.get("channels")
            if isinstance(ch, str):
                try:
                    channels = int(ch)
                except (ValueError, TypeError):
                    pass
            elif isinstance(ch, (int, float)):
                channels = int(ch)

        br = fmt.get("bit_rate")
        if isinstance(br, str):
            try:
                bitrate = int(br)
            except (ValueError, TypeError):
                pass
        elif isinstance(br, (int, float)):
            bitrate = int(br)

        findings: list[AudioProbeFinding] = []
        warnings: list[str] = []
        errors: list[str] = []

        decode_ok = True
        success = True

        if not has_audio_stream:
            findings.append(
                AudioProbeFinding(
                    code="no-audio-stream",
                    message="No audio stream found in file.",
                    category="objective_failure",
                    confidence=1.0,
                )
            )
            errors.append("No audio stream found")
            decode_ok = False
            success = False

        if duration is not None and duration <= 0:
            findings.append(
                AudioProbeFinding(
                    code="invalid-duration",
                    message=f"Invalid or zero duration: {duration}s.",
                    category="objective_failure",
                    confidence=1.0,
                )
            )
            errors.append(f"Invalid duration: {duration}")
            success = False

        if file_size is not None and file_size <= 0:
            findings.append(
                AudioProbeFinding(
                    code="zero-byte-file",
                    message="File appears to be empty or zero bytes.",
                    category="objective_failure",
                    confidence=1.0,
                )
            )
            errors.append("Zero-byte file detected")
            success = False

        if not findings:
            findings.append(
                AudioProbeFinding(
                    code="probe-ok",
                    message="ffprobe completed successfully.",
                    category="diagnostic",
                    confidence=1.0,
                )
            )

        return AudioProbeResult(
            request_id=request_id,
            item_id=item_id,
            relative_path=str(file_path),
            backend=self.kind,
            success=success,
            duration_seconds=duration,
            sample_rate=sample_rate,
            bit_depth=bit_depth,
            codec=codec,
            bitrate_bps=bitrate,
            channels=channels,
            file_size_bytes=file_size,
            decode_ok=decode_ok,
            has_audio_stream=has_audio_stream,
            stream_count=len(streams),
            audio_stream_count=len(audio_streams),
            findings=findings,
            warnings=warnings,
            errors=errors,
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

        step_status = (
            Status.FAILED if errors
            else Status.WARNING if (warnings or not result.success)
            else Status.SUCCESS
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
