from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .quality import (
    QualityFinding,
    QualityFindingKind,
    QualityFindingSeverity,
    QualityGrade,
)
from .results import _clean
from .spectral import (
    SpectralEvidenceKind,
    SpectralFinding,
    SpectralProfile,
    SpectralSignalKind,
)

SafeMetadata = dict[str, Any]


class TranscodeDetectionGrade(Any):
    pass


@dataclass(slots=True, frozen=True)
class TranscodeEvidence:
    signal_code: str
    message: str
    evidence_kind: str
    confidence: float
    source_hint: str | None = None
    cutoff_hz: float | None = None
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class TranscodeDetectionResult:
    item_id: str
    is_probable_transcode: bool
    is_probable_fake_lossless: bool
    evidence_items: list[TranscodeEvidence] = field(default_factory=list)
    detection_signals: list[str] = field(default_factory=list)
    objective_signals: list[str] = field(default_factory=list)
    heuristic_signals: list[str] = field(default_factory=list)
    review_signals: list[str] = field(default_factory=list)
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


def detect_transcode_from_profile(
    profile: SpectralProfile,
    item_id: str = "unknown",
) -> TranscodeDetectionResult:
    evidence_items: list[TranscodeEvidence] = []
    detection_signals: list[str] = []
    objective_signals: list[str] = []
    heuristic_signals: list[str] = []
    review_signals: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []

    if profile.transcode_signature:
        evidence_items.append(TranscodeEvidence(
            signal_code="transcode-signature",
            message=f"Transcode signature detected: {profile.transcode_signature}",
            evidence_kind="transcode_signature",
            confidence=0.65,
            source_hint=profile.transcode_signature,
        ))
        detection_signals.append("transcode_signature")
        heuristic_signals.append("transcode-signature")

    if profile.container_codec_mismatch:
        evidence_items.append(TranscodeEvidence(
            signal_code="container-codec-mismatch",
            message="Container format inconsistent with codec.",
            evidence_kind="container_mismatch",
            confidence=0.65,
        ))
        detection_signals.append("container_codec_mismatch")
        heuristic_signals.append("container-codec-mismatch")

    if profile.bitrate_anomaly:
        evidence_items.append(TranscodeEvidence(
            signal_code="bitrate-anomaly",
            message="Bitrate is anomalous for declared format.",
            evidence_kind="bitrate_anomaly",
            confidence=0.6,
        ))
        detection_signals.append("bitrate_anomaly")
        heuristic_signals.append("bitrate-anomaly")

    if profile.lowpass_detected:
        evidence_items.append(TranscodeEvidence(
            signal_code="lowpass-detected",
            message="Low-pass filter signature detected.",
            evidence_kind="lowpass",
            confidence=0.55,
            cutoff_hz=float(profile.spectral_cutoff_hz) if profile.spectral_cutoff_hz else None,
        ))
        detection_signals.append("lowpass_detected")
        heuristic_signals.append("lowpass-detected")

    if profile.spectral_cutoff_hz is not None:
        evidence_items.append(TranscodeEvidence(
            signal_code="spectral-cutoff",
            message=f"Spectral cutoff at {profile.spectral_cutoff_hz} Hz.",
            evidence_kind="cutoff",
            confidence=0.6,
            cutoff_hz=float(profile.spectral_cutoff_hz),
        ))
        detection_signals.append("spectral_cutoff")
        heuristic_signals.append("spectral-cutoff")

    if profile.fake_bit_depth:
        evidence_items.append(TranscodeEvidence(
            signal_code="fake-bit-depth",
            message="Declared bit depth does not match content.",
            evidence_kind="fake_bit_depth",
            confidence=0.7,
        ))
        detection_signals.append("fake_bit_depth")
        heuristic_signals.append("fake-bit-depth")

    if profile.fake_sample_rate:
        evidence_items.append(TranscodeEvidence(
            signal_code="fake-sample-rate",
            message="Declared sample rate does not match content.",
            evidence_kind="fake_sample_rate",
            confidence=0.7,
        ))
        detection_signals.append("fake_sample_rate")
        heuristic_signals.append("fake-sample-rate")

    if profile.upsampled:
        evidence_items.append(TranscodeEvidence(
            signal_code="upsampled-content",
            message="Content appears to have been upsampled.",
            evidence_kind="upsampled",
            confidence=0.6,
        ))
        detection_signals.append("upsampled")
        heuristic_signals.append("upsampled-content")

    if profile.downsampled:
        evidence_items.append(TranscodeEvidence(
            signal_code="downsampled-content",
            message="Content appears to have been downsampled.",
            evidence_kind="downsampled",
            confidence=0.6,
        ))
        detection_signals.append("downsampled")
        heuristic_signals.append("downsampled-content")

    if profile.clipping_detected:
        evidence_items.append(TranscodeEvidence(
            signal_code="clipping-detected",
            message="Audio clipping detected.",
            evidence_kind="clipping",
            confidence=0.5,
        ))
        detection_signals.append("clipping")
        review_signals.append("clipping-detected")

    if profile.loudness_anomaly:
        evidence_items.append(TranscodeEvidence(
            signal_code="loudness-anomaly",
            message="Loudness anomaly detected.",
            evidence_kind="loudness",
            confidence=0.5,
        ))
        detection_signals.append("loudness_anomaly")
        review_signals.append("loudness-anomaly")

    if profile.noise_floor_elevated:
        evidence_items.append(TranscodeEvidence(
            signal_code="noise-floor-elevated",
            message="Noise floor appears elevated.",
            evidence_kind="noise_floor",
            confidence=0.45,
        ))
        detection_signals.append("noise_floor_elevated")
        review_signals.append("noise-floor-elevated")

    if not profile.decode_ok or not profile.has_audio_stream or not profile.container_readable:
        objective_signals.append("decode-or-stream-failure")
        warnings.append("Audio decode/stream failure detected; transcode detection may be less reliable.")
        if not profile.decode_ok:
            errors.append("decode-failure")

    has_transcode = bool(detection_signals)
    has_fake_lossless = (
        profile.container_codec_mismatch
        or bool(profile.transcode_signature)
        or (profile.lowpass_detected and profile.codec in ("flac", "alac", "wav"))
    )
    is_probable_transcode = (
        has_transcode
        and len(heuristic_signals) >= 1
        and not (len(detection_signals) == 1 and "spectral_cutoff" in detection_signals and profile.decode_ok)
    )

    has_heuristic_only = (
        (profile.spectral_cutoff_hz is not None or profile.lowpass_detected)
        and profile.decode_ok
        and profile.has_audio_stream
        and not any(s in detection_signals for s in ("container_codec_mismatch", "transcode_signature"))
    )

    if has_heuristic_only and len(detection_signals) <= 2:
        is_probable_transcode = False

    total_signals = len(heuristic_signals) + len(review_signals)
    if total_signals > 0:
        confidence = min(0.85, 0.3 + total_signals * 0.12)
    else:
        confidence = 0.1

    return TranscodeDetectionResult(
        item_id=item_id,
        is_probable_transcode=is_probable_transcode,
        is_probable_fake_lossless=has_fake_lossless,
        evidence_items=evidence_items,
        detection_signals=detection_signals,
        objective_signals=objective_signals,
        heuristic_signals=heuristic_signals,
        review_signals=review_signals,
        confidence=round(confidence, 3),
        warnings=warnings,
        errors=errors,
    )


def transcode_detection_to_quality_findings(
    result: TranscodeDetectionResult,
) -> list[QualityFinding]:
    findings: list[QualityFinding] = []

    for evidence in result.evidence_items:
        if evidence.evidence_kind in ("cutoff", "lowpass"):
            kind = QualityFindingKind.HEURISTIC_WARNING
            severity = QualityFindingSeverity.WARNING
        elif evidence.evidence_kind == "decode_or_stream_failure":
            kind = QualityFindingKind.OBJECTIVE_FAILURE
            severity = QualityFindingSeverity.ERROR
        elif evidence.evidence_kind in ("clipping", "loudness", "noise_floor"):
            kind = QualityFindingKind.HEURISTIC_WARNING
            severity = QualityFindingSeverity.WARNING
        else:
            kind = QualityFindingKind.HEURISTIC_WARNING
            severity = QualityFindingSeverity.WARNING

        findings.append(QualityFinding(
            code=evidence.signal_code,
            message=evidence.message,
            kind=kind,
            severity=severity,
            confidence=evidence.confidence,
            metadata={
                "evidence_kind": evidence.evidence_kind,
                "source_hint": evidence.source_hint,
                "cutoff_hz": evidence.cutoff_hz,
            },
        ))

    return findings


def is_lowpass_cutoff_isolated(
    profile: SpectralProfile,
) -> bool:
    has_cutoff = profile.spectral_cutoff_hz is not None or profile.lowpass_detected
    has_other = any([
        profile.fake_bit_depth,
        profile.fake_sample_rate,
        profile.upsampled,
        profile.downsampled,
        profile.transcode_signature is not None,
        profile.container_codec_mismatch,
        profile.bitrate_anomaly,
    ])
    return has_cutoff and not has_other and profile.decode_ok and profile.has_audio_stream


def lowpass_cutoff_guard(
    profile: SpectralProfile,
) -> dict[str, Any]:
    isolated = is_lowpass_cutoff_isolated(profile)
    cutoff_value = profile.spectral_cutoff_hz
    lowpass = profile.lowpass_detected

    return {
        "is_isolated_cutoff_or_lowpass": isolated,
        "cutoff_hz": cutoff_value,
        "lowpass_detected": lowpass,
        "decode_ok": profile.decode_ok,
        "has_audio_stream": profile.has_audio_stream,
        "must_be_heuristic_only": isolated,
        "must_not_be_objective_failure": isolated,
        "must_not_be_quality_grade_bad": isolated,
        "must_not_trigger_quarantine_rejected_delete": isolated,
        "can_be_review_signal": isolated,
    }
