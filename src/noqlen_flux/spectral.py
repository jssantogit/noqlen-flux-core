from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .results import _clean

SafeMetadata = dict[str, Any]


class SpectralSignalKind(StrEnum):
    OBJECTIVE_FAILURE = "objective_failure"
    HEURISTIC_WARNING = "heuristic_warning"
    REVIEW_SIGNAL = "review_signal"
    CONFIDENCE_SIGNAL = "confidence_signal"
    DIAGNOSTIC = "diagnostic"


class SpectralEvidenceKind(StrEnum):
    CUTOFF = "cutoff"
    LOWPASS = "lowpass"
    FAKE_BIT_DEPTH = "fake_bit_depth"
    FAKE_SAMPLE_RATE = "fake_sample_rate"
    UPSAMPLED = "upsampled"
    DOWNSAMPLED = "downsampled"
    TRANSCODE_SIGNATURE = "transcode_signature"
    CONTAINER_MISMATCH = "container_mismatch"
    CODEC_MISMATCH = "codec_mismatch"
    BITRATE_ANOMALY = "bitrate_anomaly"
    CLIPPING = "clipping"
    LOUDNESS = "loudness"
    NOISE_FLOOR = "noise_floor"
    FORMAT_FLAG = "format_flag"
    METADATA_HINT = "metadata_hint"
    UNKNOWN = "unknown"


@dataclass(slots=True, frozen=True)
class SpectralFinding:
    code: str
    message: str
    kind: SpectralSignalKind
    evidence: SpectralEvidenceKind
    confidence: float = 1.0
    frequency_hz: float | None = None
    cutoff_hz: float | None = None
    declared_value: str | None = None
    actual_value: str | None = None
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", SpectralSignalKind(self.kind))
        object.__setattr__(self, "evidence", SpectralEvidenceKind(self.evidence))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class SpectralProfile:
    codec: str | None = None
    sample_rate: int | None = None
    bit_depth: int | None = None
    bitrate_bps: int | None = None
    channels: int | None = None
    format_name: str | None = None
    duration_seconds: float | None = None
    has_audio_stream: bool = True
    decode_ok: bool = True
    container_readable: bool = True
    spectral_cutoff_hz: int | None = None
    lowpass_detected: bool = False
    fake_bit_depth: bool = False
    fake_sample_rate: bool = False
    upsampled: bool = False
    downsampled: bool = False
    transcode_signature: str | None = None
    container_codec_mismatch: bool = False
    bitrate_anomaly: bool = False
    clipping_detected: bool = False
    loudness_anomaly: bool = False
    noise_floor_elevated: bool = False
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class SpectralPolicy:
    name: str = "default-spectral"
    version: str = "1"
    cutoff_is_heuristic: bool = True
    lowpass_is_heuristic: bool = True
    bit_depth_fake_is_heuristic: bool = True
    sample_rate_fake_is_heuristic: bool = True
    upsampled_is_heuristic: bool = True
    downsampled_is_heuristic: bool = True
    transcode_signature_is_heuristic: bool = True
    container_mismatch_is_heuristic: bool = True
    bitrate_anomaly_is_heuristic: bool = True
    clipping_is_review: bool = True
    loudness_is_review: bool = True
    noise_floor_is_review: bool = True
    heuristic_confidence_threshold: float = 0.5
    review_signal_confidence_threshold: float = 0.4
    never_objective_on_heuristic: bool = True
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class SpectralAnalysisRequest:
    request_id: str
    item_id: str
    relative_path: str
    workspace_root: str
    backend: str = "fake"
    timeout_seconds: int = 30
    analyze_spectrum: bool = True
    detect_transcode: bool = True
    detect_fake_quality: bool = True
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("request_id is required")
        if not self.item_id.strip():
            raise ValueError("item_id is required")
        if not self.relative_path.strip():
            raise ValueError("relative_path is required")
        self._validate_relative_path()

    def _validate_relative_path(self) -> None:
        from .safety import is_safe_relative_path
        if not is_safe_relative_path(self.relative_path):
            raise ValueError(
                f"relative_path must be a safe relative path: {self.relative_path!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class SpectralAnalysisResult:
    request_id: str
    item_id: str
    relative_path: str
    backend: str
    success: bool = False
    profile: SpectralProfile = field(default_factory=SpectralProfile)
    findings: list[SpectralFinding] = field(default_factory=list)
    objective_failures: list[SpectralFinding] = field(default_factory=list)
    heuristic_warnings: list[SpectralFinding] = field(default_factory=list)
    review_signals: list[SpectralFinding] = field(default_factory=list)
    confidence_signals: list[SpectralFinding] = field(default_factory=list)
    diagnostics: list[SpectralFinding] = field(default_factory=list)
    evidence_summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("request_id is required")
        if not self.item_id.strip():
            raise ValueError("item_id is required")

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


DEFAULT_SPECTRAL_POLICY = SpectralPolicy(
    name="default-spectral",
    version="1",
    metadata={"stage": "post-download", "status": "contracts-only"},
)


def classify_spectral_finding(
    finding: SpectralFinding,
    policy: SpectralPolicy | None = None,
) -> SpectralSignalKind:
    effective_policy = policy or DEFAULT_SPECTRAL_POLICY
    evidence = finding.evidence

    if evidence == SpectralEvidenceKind.CUTOFF:
        return (
            SpectralSignalKind.HEURISTIC_WARNING
            if effective_policy.cutoff_is_heuristic
            else SpectralSignalKind.REVIEW_SIGNAL
        )
    if evidence == SpectralEvidenceKind.LOWPASS:
        return (
            SpectralSignalKind.HEURISTIC_WARNING
            if effective_policy.lowpass_is_heuristic
            else SpectralSignalKind.REVIEW_SIGNAL
        )
    if evidence in (
        SpectralEvidenceKind.FAKE_BIT_DEPTH,
        SpectralEvidenceKind.FAKE_SAMPLE_RATE,
        SpectralEvidenceKind.UPSAMPLED,
        SpectralEvidenceKind.DOWNSAMPLED,
        SpectralEvidenceKind.TRANSCODE_SIGNATURE,
        SpectralEvidenceKind.CONTAINER_MISMATCH,
        SpectralEvidenceKind.CODEC_MISMATCH,
        SpectralEvidenceKind.BITRATE_ANOMALY,
    ):
        return SpectralSignalKind.HEURISTIC_WARNING
    if evidence in (
        SpectralEvidenceKind.CLIPPING,
        SpectralEvidenceKind.LOUDNESS,
        SpectralEvidenceKind.NOISE_FLOOR,
    ):
        return SpectralSignalKind.REVIEW_SIGNAL
    return SpectralSignalKind.DIAGNOSTIC


def spectral_result_to_quality_findings(
    result: SpectralAnalysisResult,
) -> list[tuple[str, str, str, float]]:
    quality_findings: list[tuple[str, str, str, float]] = []
    for f in result.findings:
        kind_str = f.kind.value
        quality_findings.append((f.code, f.message, kind_str, f.confidence))
    return quality_findings
