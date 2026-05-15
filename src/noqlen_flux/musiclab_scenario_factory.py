from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .quality import (
    QualityFinding,
    QualityFindingKind,
    QualityFindingSeverity,
)
from .results import _clean
from .search import CandidateFile, SearchCandidate, SearchQuery

SafeMetadata = dict[str, Any]


@dataclass(slots=True, frozen=True)
class SyntheticProbeProfile:
    codec: str = "flac"
    sample_rate: int = 44100
    bit_depth: int = 16
    bitrate_bps: int = 0
    channels: int = 2
    duration_seconds: float = 240.0
    format_name: str = "flac"
    file_size_bytes: int = 25000000
    decode_ok: bool = True
    has_audio_stream: bool = True
    stream_count: int = 1
    audio_stream_count: int = 1
    probe_success: bool = True
    spectral_cutoff_hz: int | None = None
    lowpass_suspicion: bool = False
    fake_bit_depth: bool = False
    fake_sample_rate: bool = False
    upsampled: bool = False
    downsampled: bool = False
    transcode_cutoff_source: str | None = None
    truncated: bool = False
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class SyntheticFixture:
    fixture_id: str
    description: str
    query: SearchQuery
    candidate: SearchCandidate
    probe: SyntheticProbeProfile
    tags: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


def build_probe_findings(probe: SyntheticProbeProfile) -> list[QualityFinding]:
    findings: list[QualityFinding] = []

    if not probe.probe_success:
        findings.append(
            QualityFinding(
                code="probe-failure",
                message="Audio probe could not parse file.",
                kind=QualityFindingKind.OBJECTIVE_FAILURE,
                severity=QualityFindingSeverity.ERROR,
            )
        )
        return findings

    if not probe.has_audio_stream:
        findings.append(
            QualityFinding(
                code="no-audio-stream",
                message="File contains no audio stream.",
                kind=QualityFindingKind.OBJECTIVE_FAILURE,
                severity=QualityFindingSeverity.ERROR,
            )
        )

    if probe.file_size_bytes == 0:
        findings.append(
            QualityFinding(
                code="zero-byte-file",
                message="File is zero bytes.",
                kind=QualityFindingKind.OBJECTIVE_FAILURE,
                severity=QualityFindingSeverity.ERROR,
            )
        )

    if not probe.decode_ok:
        findings.append(
            QualityFinding(
                code="decode-failure",
                message="File fails decode validation.",
                kind=QualityFindingKind.OBJECTIVE_FAILURE,
                severity=QualityFindingSeverity.ERROR,
            )
        )

    if probe.truncated:
        findings.append(
            QualityFinding(
                code="truncated-file",
                message="File appears truncated or incomplete.",
                kind=QualityFindingKind.OBJECTIVE_FAILURE,
                severity=QualityFindingSeverity.ERROR,
            )
        )

    if probe.duration_seconds <= 0:
        findings.append(
            QualityFinding(
                code="invalid-duration",
                message="File has invalid or zero duration.",
                kind=QualityFindingKind.OBJECTIVE_FAILURE,
                severity=QualityFindingSeverity.ERROR,
            )
        )

    if probe.fake_bit_depth:
        findings.append(
            QualityFinding(
                code="fake-bit-depth",
                message="Declared bit depth does not match actual audio content.",
                kind=QualityFindingKind.HEURISTIC_WARNING,
                severity=QualityFindingSeverity.WARNING,
                confidence=0.7,
            )
        )

    if probe.fake_sample_rate:
        findings.append(
            QualityFinding(
                code="fake-sample-rate",
                message="Declared sample rate does not match actual audio content.",
                kind=QualityFindingKind.HEURISTIC_WARNING,
                severity=QualityFindingSeverity.WARNING,
                confidence=0.7,
            )
        )

    if probe.upsampled:
        findings.append(
            QualityFinding(
                code="upsampled-content",
                message="Audio content appears to have been upsampled.",
                kind=QualityFindingKind.HEURISTIC_WARNING,
                severity=QualityFindingSeverity.WARNING,
                confidence=0.6,
            )
        )

    if probe.downsampled:
        findings.append(
            QualityFinding(
                code="downsampled-content",
                message="Audio content appears to have been downsampled.",
                kind=QualityFindingKind.HEURISTIC_WARNING,
                severity=QualityFindingSeverity.WARNING,
                confidence=0.6,
            )
        )

    if probe.lowpass_suspicion:
        findings.append(
            QualityFinding(
                code="lowpass-suspicion",
                message="Low-pass filter detected; possible transcode or lossy origin.",
                kind=QualityFindingKind.HEURISTIC_WARNING,
                severity=QualityFindingSeverity.WARNING,
                confidence=0.55,
            )
        )

    if probe.spectral_cutoff_hz is not None:
        findings.append(
            QualityFinding(
                code="spectral-cutoff",
                message=f"Spectral cutoff detected at {probe.spectral_cutoff_hz} Hz.",
                kind=QualityFindingKind.HEURISTIC_WARNING,
                severity=QualityFindingSeverity.WARNING,
                confidence=0.6,
                metadata={"cutoff_hz": probe.spectral_cutoff_hz},
            )
        )

    if probe.transcode_cutoff_source:
        findings.append(
            QualityFinding(
                code="transcode-cutoff",
                message=f"Spectral cutoff consistent with {probe.transcode_cutoff_source} transcode.",
                kind=QualityFindingKind.HEURISTIC_WARNING,
                severity=QualityFindingSeverity.WARNING,
                confidence=0.65,
                metadata={"cutoff_source": probe.transcode_cutoff_source},
            )
        )

    findings.append(
        QualityFinding(
            code="probe-complete",
            message=f"Probe completed successfully: {probe.codec} {probe.sample_rate}Hz {probe.bit_depth}bit.",
            kind=QualityFindingKind.DIAGNOSTIC,
            severity=QualityFindingSeverity.INFO,
            confidence=1.0,
        )
    )

    return findings


def build_good_candidate(
    candidate_id: str,
    artist: str,
    title: str,
    files: list[tuple[str, str, int | None]] | None = None,
) -> SearchCandidate:
    default_files = files or [
        (f"{title}.flac", "flac", None),
    ]
    return SearchCandidate(
        candidate_id=candidate_id,
        provider="fake",
        username="flux_test_user",
        artist=artist,
        title=title,
        directory=f"{artist}/{title}",
        files=[
            CandidateFile(
                filename=fn,
                extension=ext,
                size_bytes=size_b,
            )
            for fn, ext, size_b in default_files
        ],
    )


def build_album_candidate(
    candidate_id: str,
    artist: str,
    album: str,
    tracks: list[str] | None = None,
) -> SearchCandidate:
    track_names = tracks or [f"{i:02d} Track {i}" for i in range(1, 11)]
    return SearchCandidate(
        candidate_id=candidate_id,
        provider="fake",
        username="flux_test_user",
        artist=artist,
        album=album,
        directory=f"{artist}/{album}",
        files=[
            CandidateFile(
                filename=f"{name}.flac",
                extension="flac",
                size_bytes=25000000,
            )
            for name in track_names
        ],
    )
