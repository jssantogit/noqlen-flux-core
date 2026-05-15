from __future__ import annotations

from typing import Any

from .musiclab_scenario import (
    MusicLabScenario,
    MusicLabScenarioConfig,
    MusicLabScenarioPack,
    ScenarioCategory,
    ScenarioKind,
    ScenarioSeverity,
)
from .musiclab_scenario_factory import (
    SyntheticFixture,
    SyntheticProbeProfile,
    build_album_candidate,
    build_good_candidate,
)
from .search import CandidateFile, SearchCandidate, SearchKind, SearchQuery

SafeMetadata = dict[str, Any]


def _candidate(
    candidate_id: str,
    artist: str,
    title: str,
    *,
    codec: str = "flac",
    ext: str = "flac",
) -> SearchCandidate:
    return build_good_candidate(
        candidate_id=candidate_id,
        artist=artist,
        title=title,
        files=[(f"{title}.{ext}", ext, 25000000)],
    )


def _scenario(
    scenario_id: str,
    description: str,
    category: ScenarioCategory,
    kind: ScenarioKind,
    *,
    severity: ScenarioSeverity = ScenarioSeverity.MEDIUM,
    tags: list[str] | None = None,
    config: MusicLabScenarioConfig | None = None,
) -> MusicLabScenario:
    return MusicLabScenario(
        scenario_id=scenario_id,
        description=description,
        category=ScenarioCategory(category),
        kind=ScenarioKind(kind),
        severity=ScenarioSeverity(severity),
        tags=tags or [],
        config=config or MusicLabScenarioConfig(),
    )


def _fixture(
    fixture_id: str,
    description: str,
    artist: str,
    title: str,
    probe: SyntheticProbeProfile,
    *,
    tags: list[str] | None = None,
    codec: str = "flac",
    ext: str = "flac",
) -> SyntheticFixture:
    candidate = build_good_candidate(
        candidate_id=fixture_id,
        artist=artist,
        title=title,
        files=[(f"{title}.{ext}", ext, 25000000)],
    )
    return SyntheticFixture(
        fixture_id=fixture_id,
        description=description,
        query=SearchQuery(kind=SearchKind.TRACK, artist=artist, title=title),
        candidate=candidate,
        probe=probe,
        tags=tags or [],
    )


def build_good_formats_pack() -> tuple[MusicLabScenarioPack, dict[str, SyntheticFixture]]:
    scenarios: list[MusicLabScenario] = []
    fixtures: dict[str, SyntheticFixture] = {}

    specs = [
        ("flac-16-44-good", "FLAC 16-bit 44.1 kHz good file", "flac", 44100, 16),
        ("flac-24-96-good", "FLAC 24-bit 96 kHz good file", "flac", 96000, 24),
        ("wav-good", "WAV good file", "wav", 44100, 16),
        ("alac-good", "ALAC good file", "alac", 44100, 16),
        ("mp3-320-good", "MP3 320 kbps good file", "mp3", 44100, 16),
        ("aac-256-good", "AAC 256 kbps good file", "aac", 44100, 16),
        ("opus-good", "Opus good file", "opus", 48000, 16),
        ("ogg-vorbis-good", "OGG/Vorbis good file", "vorbis", 44100, 16),
    ]

    for fid, desc, codec, sr, bd in specs:
        scenarios.append(
            _scenario(
                fid, desc, ScenarioCategory.GOOD, ScenarioKind.FORMAT_VARIANT,
                severity=ScenarioSeverity.LOW, tags=["good", codec],
            )
        )
        fixture = _fixture(
            fid, desc, "Test Artist", f"Good {codec.upper()} Track",
            SyntheticProbeProfile(
                codec=codec, sample_rate=sr, bit_depth=bd,
                format_name=codec,
            ),
            codec=codec, ext=codec,
        )
        fixtures[fid] = fixture

    pack = MusicLabScenarioPack(
        pack_id="good-formats",
        description="Good format variants: all expected to pass quality and routing as excellent.",
        version="1",
        scenarios=scenarios,
    )
    return pack, fixtures


def build_corrupt_and_invalid_pack() -> tuple[MusicLabScenarioPack, dict[str, SyntheticFixture]]:
    scenarios: list[MusicLabScenario] = []
    fixtures: dict[str, SyntheticFixture] = {}

    specs = [
        (
            "zero-byte", "Zero-byte file",
            SyntheticProbeProfile(
                file_size_bytes=0, probe_success=False, decode_ok=False,
                has_audio_stream=False,
            ),
            "flac", "flac",
        ),
        (
            "corrupt-file", "Corrupt file that cannot be parsed",
            SyntheticProbeProfile(
                probe_success=False, decode_ok=False, has_audio_stream=False,
            ),
            "flac", "flac",
        ),
        (
            "no-audio-stream", "File with no audio stream",
            SyntheticProbeProfile(
                probe_success=True, decode_ok=True, has_audio_stream=False,
                audio_stream_count=0, stream_count=0,
            ),
            "flac", "flac",
        ),
        (
            "invalid-duration", "File with invalid duration",
            SyntheticProbeProfile(
                duration_seconds=0.0, probe_success=True, decode_ok=True,
                has_audio_stream=True,
            ),
            "flac", "flac",
        ),
        (
            "truncated-file", "Truncated file",
            SyntheticProbeProfile(
                truncated=True, probe_success=True, decode_ok=False,
                has_audio_stream=True,
            ),
            "flac", "flac",
        ),
        (
            "container-unreadable", "Container unreadable",
            SyntheticProbeProfile(
                container_readable=False, probe_success=True, decode_ok=False,
                has_audio_stream=False,
            ),
            "flac", "flac",
        ),
        (
            "probe-timeout", "Probe timeout",
            SyntheticProbeProfile(
                timeout=True, probe_success=False, decode_ok=False,
                has_audio_stream=False,
            ),
            "flac", "flac",
        ),
    ]

    for fid, desc, probe, codec, ext in specs:
        scenarios.append(
            _scenario(
                fid, desc, ScenarioCategory.BAD, ScenarioKind.CORRUPT,
                severity=ScenarioSeverity.HIGH, tags=["bad", "corrupt", fid],
            )
        )
        fixture = SyntheticFixture(
            fixture_id=fid,
            description=desc,
            query=SearchQuery(kind=SearchKind.TRACK, artist="Test Artist", title="Corrupt Track"),
            candidate=build_good_candidate(fid, "Test Artist", "Corrupt Track", files=[(f"corrupt.{ext}", ext, None)]),
            probe=probe,
            tags=["bad", "corrupt"],
        )
        fixtures[fid] = fixture

    pack = MusicLabScenarioPack(
        pack_id="corrupt-and-invalid",
        description="Corrupt and invalid file scenarios: all expected to fail quality as bad.",
        version="1",
        scenarios=scenarios,
    )
    return pack, fixtures


def build_transcode_pack() -> tuple[MusicLabScenarioPack, dict[str, SyntheticFixture]]:
    scenarios: list[MusicLabScenario] = []
    fixtures: dict[str, SyntheticFixture] = {}

    specs = [
        (
            "fake-flac", "Fake FLAC: MP3 renamed as FLAC",
            SyntheticProbeProfile(
                codec="mp3", sample_rate=44100, bit_depth=16,
                format_name="mp3", lowpass_suspicion=True, transcode_cutoff_source="mp3",
            ),
            "flac", "flac",
        ),
        (
            "mp3-transcoded-to-flac", "MP3 transcoded to FLAC",
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=16,
                format_name="flac", lowpass_suspicion=True,
                transcode_cutoff_source="mp3-320",
            ),
            "flac", "flac",
        ),
        (
            "aac-transcoded-to-wav", "AAC transcoded to WAV",
            SyntheticProbeProfile(
                codec="pcm_s16le", sample_rate=44100, bit_depth=16,
                format_name="wav", lowpass_suspicion=True,
                transcode_cutoff_source="aac-256",
            ),
            "wav", "wav",
        ),
        (
            "opus-renamed-as-flac", "Opus renamed as FLAC",
            SyntheticProbeProfile(
                codec="opus", sample_rate=48000, bit_depth=16,
                format_name="opus", lowpass_suspicion=True,
            ),
            "flac", "flac",
        ),
        (
            "lossy-source-lossless-container", "Lossy source in lossless container",
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=16,
                format_name="flac", lossy_source_lossless_container=True,
            ),
            "flac", "flac",
        ),
        (
            "bitrate-container-incompatible", "Bitrate/container incompatible",
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=16,
                format_name="flac", bitrate_container_mismatch=True,
            ),
            "flac", "flac",
        ),
    ]

    for fid, desc, probe, codec, ext in specs:
        scenarios.append(
            _scenario(
                fid, desc, ScenarioCategory.SUSPICIOUS, ScenarioKind.TRANSCODE,
                severity=ScenarioSeverity.MEDIUM, tags=["suspicious", "transcode", fid],
            )
        )
        fixture = SyntheticFixture(
            fixture_id=fid,
            description=desc,
            query=SearchQuery(kind=SearchKind.TRACK, artist="Test Artist", title="Suspicious Track"),
            candidate=build_good_candidate(fid, "Test Artist", "Suspicious Track", files=[(f"track.{ext}", ext, 5000000)]),
            probe=probe,
            tags=["suspicious", "transcode"],
        )
        fixtures[fid] = fixture

    pack = MusicLabScenarioPack(
        pack_id="transcode-suspicion",
        description="Transcode and mislabeled format scenarios.",
        version="1",
        scenarios=scenarios,
    )
    return pack, fixtures


def build_fake_quality_pack() -> tuple[MusicLabScenarioPack, dict[str, SyntheticFixture]]:
    scenarios: list[MusicLabScenario] = []
    fixtures: dict[str, SyntheticFixture] = {}

    specs = [
        (
            "fake-24bit", "Fake 24-bit: actual content is 16-bit",
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=24,
                fake_bit_depth=True,
            ),
        ),
        (
            "fake-96khz", "Fake 96 kHz: actual content is 44.1 kHz",
            SyntheticProbeProfile(
                codec="flac", sample_rate=96000, bit_depth=16,
                fake_sample_rate=True,
            ),
        ),
    ]

    for fid, desc, probe in specs:
        scenarios.append(
            _scenario(
                fid, desc, ScenarioCategory.SUSPICIOUS, ScenarioKind.FAKE_BIT_DEPTH if "bit" in fid else ScenarioKind.FAKE_SAMPLE_RATE,
                severity=ScenarioSeverity.MEDIUM, tags=["suspicious", "fake-quality", fid],
            )
        )
        fixture = _fixture(fid, desc, "Test Artist", "Fake Quality Track", probe)
        fixtures[fid] = fixture

    pack = MusicLabScenarioPack(
        pack_id="fake-quality",
        description="Fake bit depth and sample rate scenarios.",
        version="1",
        scenarios=scenarios,
    )
    return pack, fixtures


def build_sample_rate_manipulation_pack() -> tuple[MusicLabScenarioPack, dict[str, SyntheticFixture]]:
    scenarios: list[MusicLabScenario] = []
    fixtures: dict[str, SyntheticFixture] = {}

    specs = [
        (
            "upsampled-44-to-96", "Upsampled 44.1 kHz to 96 kHz",
            SyntheticProbeProfile(
                codec="flac", sample_rate=96000, bit_depth=16,
                upsampled=True,
            ),
        ),
        (
            "downsampled-96-to-44", "Downsampled 96 kHz to 44.1 kHz",
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=24,
                downsampled=True,
            ),
        ),
    ]

    for fid, desc, probe in specs:
        scenarios.append(
            _scenario(
                fid, desc, ScenarioCategory.SUSPICIOUS, ScenarioKind.UPSAMPLED if "up" in fid else ScenarioKind.DOWNSAMPLED,
                severity=ScenarioSeverity.MEDIUM, tags=["suspicious", "sample-rate", fid],
            )
        )
        fixture = _fixture(fid, desc, "Test Artist", "SR Manip Track", probe)
        fixtures[fid] = fixture

    pack = MusicLabScenarioPack(
        pack_id="sample-rate-manipulation",
        description="Upsampled and downsampled content scenarios.",
        version="1",
        scenarios=scenarios,
    )
    return pack, fixtures


def build_lowpass_and_cutoff_pack() -> tuple[MusicLabScenarioPack, dict[str, SyntheticFixture]]:
    scenarios: list[MusicLabScenario] = []
    fixtures: dict[str, SyntheticFixture] = {}

    specs = [
        (
            "qobuz_like_cutoff_9_4khz_decode_ok",
            "Qobuz-like spectral cutoff at 9.4 kHz with successful decode (must NOT be auto-punished)",
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=16,
                decode_ok=True, has_audio_stream=True,
                spectral_cutoff_hz=9400,
            ),
        ),
        (
            "lowpass_suspicion_only",
            "Low-pass suspicion only, no objective failure (cutoff/lowpass alone = heuristic_warning)",
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=16,
                decode_ok=True, has_audio_stream=True,
                lowpass_suspicion=True,
            ),
        ),
        (
            "spectral_cutoff_only",
            "Spectral cutoff only, no objective failure (cutoff alone = heuristic_warning)",
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=16,
                decode_ok=True, has_audio_stream=True,
                spectral_cutoff_hz=16000,
            ),
        ),
        (
            "lowpass_with_valid_metadata",
            "Low-pass with otherwise valid metadata (cutoff alone = heuristic_warning, must not be bad)",
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=16,
                decode_ok=True, has_audio_stream=True,
                lowpass_suspicion=True, spectral_cutoff_hz=15500,
            ),
        ),
        (
            "lowpass_plus_decode_failure",
            "Low-pass PLUS decode failure (bad via decode_failure, NOT via lowpass)",
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=16,
                decode_ok=False, has_audio_stream=True,
                lowpass_suspicion=True, spectral_cutoff_hz=12000,
            ),
        ),
    ]

    for fid, desc, probe in specs:
        scenarios.append(
            _scenario(
                fid, desc, ScenarioCategory.FALSE_POSITIVE if "qobuz" in fid or "only" in fid else ScenarioCategory.SUSPICIOUS,
                ScenarioKind.EDGE_CASE,
                severity=ScenarioSeverity.HIGH, tags=["lowpass-cutoff", fid],
            )
        )
        fixture = _fixture(fid, desc, "Test Artist", "Cutoff Track", probe)
        fixtures[fid] = fixture

    pack = MusicLabScenarioPack(
        pack_id="lowpass-and-cutoff",
        description="Low-pass and spectral cutoff guard scenarios. CRITICAL: cutoff/lowpass alone must be heuristic_warning, never objective_failure, never QualityGrade bad, never quarantine/rejected/delete.",
        version="1",
        scenarios=scenarios,
    )
    return pack, fixtures


def build_false_positive_guard_pack() -> tuple[MusicLabScenarioPack, dict[str, SyntheticFixture]]:
    scenarios: list[MusicLabScenario] = []
    fixtures: dict[str, SyntheticFixture] = {}

    specs = [
        (
            "fp-good-flac-16-44",
            "Clean FLAC 16/44.1 - must pass as excellent, no false alarms",
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=16,
                decode_ok=True, has_audio_stream=True,
            ),
        ),
        (
            "fp-qobuz-like-decode-ok",
            "Qobuz-like with decode OK - must NOT be bad, must NOT be rejected",
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=16,
                decode_ok=True, has_audio_stream=True,
                spectral_cutoff_hz=9400,
            ),
        ),
        (
            "fp-lowpass-only-not-bad",
            "Low-pass only with clean decode - must NOT be QualityGrade bad",
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=16,
                decode_ok=True, has_audio_stream=True,
                lowpass_suspicion=True,
            ),
        ),
        (
            "fp-cutoff-only-not-quarantine",
            "Spectral cutoff only - must NOT route to quarantine or rejected",
            SyntheticProbeProfile(
                codec="flac", sample_rate=48000, bit_depth=16,
                decode_ok=True, has_audio_stream=True,
                spectral_cutoff_hz=16000,
            ),
        ),
        (
            "fp-source-profile-ignored",
            "Source profile hints must not alone decide quality",
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=16,
                decode_ok=True, has_audio_stream=True,
            ),
        ),
        (
            "fake_flac_lowpass_but_decode_ok",
            "Fake FLAC with low-pass but decode OK - heuristic only, not bad",
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=16,
                decode_ok=True, has_audio_stream=True,
                lowpass_suspicion=True,
            ),
        ),
        (
            "mp3_320_good_lowpass_like",
            "MP3 320 with low-pass-like cutoff - heuristic only, not bad",
            SyntheticProbeProfile(
                codec="mp3", sample_rate=44100, bit_depth=16,
                decode_ok=True, has_audio_stream=True,
                spectral_cutoff_hz=16000,
            ),
        ),
    ]

    for fid, desc, probe in specs:
        scenarios.append(
            _scenario(
                fid, desc, ScenarioCategory.FALSE_POSITIVE, ScenarioKind.EDGE_CASE,
                severity=ScenarioSeverity.CRITICAL, tags=["false-positive-guard", fid],
            )
        )
        fixture = _fixture(fid, desc, "Test Artist", "FP Test Track", probe)
        fixtures[fid] = fixture

    pack = MusicLabScenarioPack(
        pack_id="false-positive-guard",
        description="False-positive guard scenarios: ensures heuristic signals are never over-punished. CRITICAL for safety regression.",
        version="1",
        scenarios=scenarios,
    )
    return pack, fixtures


def build_album_scenarios_pack() -> tuple[MusicLabScenarioPack, dict[str, SyntheticFixture]]:
    scenarios: list[MusicLabScenario] = []
    fixtures: dict[str, SyntheticFixture] = {}

    album_tracks = [f"{i:02d} Track {i}" for i in range(1, 11)]
    album_missing = [f"{i:02d} Track {i}" for i in range(1, 11) if i != 5]
    album_duplicate = [f"{i:02d} Track {i}" for i in range(1, 11)] + ["05 Track 5"]
    album_wrong_order = ["02 Track 2", "01 Track 1"] + [f"{i:02d} Track {i}" for i in range(3, 11)]

    specs = [
        (
            "album-completo",
            "Complete album with all 10 tracks",
            album_tracks, None,
            SyntheticProbeProfile(codec="flac", sample_rate=44100, bit_depth=16),
        ),
        (
            "album-faixa-faltando",
            "Album with missing track #5",
            album_missing, None,
            SyntheticProbeProfile(codec="flac", sample_rate=44100, bit_depth=16),
        ),
        (
            "album-faixa-duplicada",
            "Album with duplicated track #5",
            album_duplicate, None,
            SyntheticProbeProfile(codec="flac", sample_rate=44100, bit_depth=16),
        ),
        (
            "album-ordem-errada",
            "Album with wrong track order",
            album_wrong_order, None,
            SyntheticProbeProfile(codec="flac", sample_rate=44100, bit_depth=16),
        ),
        (
            "album-mixed-formats",
            "Album with mixed formats",
            album_tracks, ["flac", "mp3", "m4a"],
            SyntheticProbeProfile(codec="flac", sample_rate=44100, bit_depth=16),
        ),
        (
            "album-um-arquivo-ruim",
            "One bad file in otherwise good album",
            album_tracks, None,
            SyntheticProbeProfile(codec="flac", sample_rate=44100, bit_depth=16, decode_ok=False),
        ),
    ]

    for fid, desc, tracks, formats, probe in specs:
        category = (
            ScenarioCategory.GOOD if fid == "album-completo"
            else ScenarioCategory.BAD if fid == "album-um-arquivo-ruim"
            else ScenarioCategory.SUSPICIOUS
        )
        scenarios.append(
            _scenario(
                fid, desc, category,
                ScenarioKind.ALBUM,
                severity=ScenarioSeverity.LOW if fid == "album-completo" else ScenarioSeverity.MEDIUM,
                tags=["album", fid],
            )
        )
        if formats:
            candidate = SearchCandidate(
                candidate_id=fid,
                provider="fake",
                username="flux_test_user",
                artist="Test Artist",
                album="Test Album",
                directory="Test Artist/Test Album",
                files=[
                    CandidateFile(
                        filename=f"{name}.{formats[index % len(formats)]}",
                        extension=formats[index % len(formats)],
                        size_bytes=25000000,
                    )
                    for index, name in enumerate(tracks)
                ],
            )
        else:
            candidate = build_album_candidate(
                candidate_id=fid,
                artist="Test Artist",
                album="Test Album",
                tracks=tracks,
            )
        fixture = SyntheticFixture(
            fixture_id=fid,
            description=desc,
            query=SearchQuery(kind=SearchKind.ALBUM, artist="Test Artist", album="Test Album"),
            candidate=candidate,
            probe=probe,
            tags=["album"],
        )
        fixtures[fid] = fixture

    pack = MusicLabScenarioPack(
        pack_id="album-scenarios",
        description="Album-level scenarios: complete, missing tracks, duplicate tracks.",
        version="1",
        scenarios=scenarios,
    )
    return pack, fixtures


def build_edge_case_pack() -> tuple[MusicLabScenarioPack, dict[str, SyntheticFixture]]:
    scenarios: list[MusicLabScenario] = []
    fixtures: dict[str, SyntheticFixture] = {}

    locked_candidate = SearchCandidate(
        candidate_id="arquivo-locked",
        provider="fake",
        username="flux_test_user",
        artist="Test Artist",
        title="Locked Track",
        directory="Test Artist",
        files=[
            CandidateFile(
                filename="Locked Track.flac",
                extension="flac",
                size_bytes=25000000,
                locked=True,
            )
        ],
    )

    fixtures["arquivo-locked"] = SyntheticFixture(
        fixture_id="arquivo-locked",
        description="File is locked on the provider side",
        query=SearchQuery(kind=SearchKind.TRACK, artist="Test Artist", title="Locked Track"),
        candidate=locked_candidate,
        probe=SyntheticProbeProfile(codec="flac", sample_rate=44100, bit_depth=16),
        tags=["edge-case", "locked"],
    )
    scenarios.append(_scenario(
        "arquivo-locked", "File is locked on provider",
        ScenarioCategory.SUSPICIOUS, ScenarioKind.EDGE_CASE,
        severity=ScenarioSeverity.MEDIUM, tags=["edge-case", "locked"],
    ))

    offline_candidate = SearchCandidate(
        candidate_id="usuario-offline",
        provider="fake",
        username="offline_user",
        artist="Test Artist",
        title="Offline Track",
        directory="Test Artist",
        files=[
            CandidateFile(
                filename="Offline Track.flac",
                extension="flac",
                size_bytes=25000000,
            )
        ],
        warnings=["user-offline"],
    )

    fixtures["usuario-offline"] = SyntheticFixture(
        fixture_id="usuario-offline",
        description="User is offline, download cannot proceed",
        query=SearchQuery(kind=SearchKind.TRACK, artist="Test Artist", title="Offline Track"),
        candidate=offline_candidate,
        probe=SyntheticProbeProfile(codec="flac", sample_rate=44100, bit_depth=16),
        tags=["edge-case", "offline"],
    )
    scenarios.append(_scenario(
        "usuario-offline", "User is offline",
        ScenarioCategory.SUSPICIOUS, ScenarioKind.EDGE_CASE,
        severity=ScenarioSeverity.HIGH, tags=["edge-case", "offline"],
    ))

    incomplete_candidate = SearchCandidate(
        candidate_id="download-incompleto",
        provider="fake",
        username="flux_test_user",
        artist="Test Artist",
        title="Incomplete Track",
        directory="Test Artist",
        files=[
            CandidateFile(
                filename="Incomplete Track.flac.part",
                extension="flac.part",
                size_bytes=5000000,
            )
        ],
    )

    fixtures["download-incompleto"] = SyntheticFixture(
        fixture_id="download-incompleto",
        description="Download incomplete (partial file)",
        query=SearchQuery(kind=SearchKind.TRACK, artist="Test Artist", title="Incomplete Track"),
        candidate=incomplete_candidate,
        probe=SyntheticProbeProfile(
            codec="flac", sample_rate=44100, bit_depth=16,
            truncated=True, file_size_bytes=5000000, decode_ok=False,
        ),
        tags=["edge-case", "incomplete"],
    )
    scenarios.append(_scenario(
        "download-incompleto", "Download incomplete",
        ScenarioCategory.BAD, ScenarioKind.EDGE_CASE,
        severity=ScenarioSeverity.HIGH, tags=["edge-case", "incomplete"],
    ))

    fixtures["candidato-errado-bom"] = SyntheticFixture(
        fixture_id="candidato-errado-bom",
        description="Wrong candidate but technically good file",
        query=SearchQuery(kind=SearchKind.TRACK, artist="Correct Artist", title="Correct Title"),
        candidate=build_good_candidate(
            "candidato-errado-bom",
            "Wrong Artist",
            "Wrong Title",
            files=[("Wrong Title.flac", "flac", 25000000)],
        ),
        probe=SyntheticProbeProfile(codec="flac", sample_rate=44100, bit_depth=16),
        tags=["edge-case", "wrong-candidate"],
    )
    scenarios.append(_scenario(
        "candidato-errado-bom", "Wrong candidate but technically good audio",
        ScenarioCategory.SUSPICIOUS, ScenarioKind.EDGE_CASE,
        severity=ScenarioSeverity.MEDIUM, tags=["edge-case", "wrong-candidate"],
    ))

    fixtures["candidato-bom-metadata-ruim"] = SyntheticFixture(
        fixture_id="candidato-bom-metadata-ruim",
        description="Good candidate with bad metadata",
        query=SearchQuery(kind=SearchKind.TRACK, artist="Test Artist", title="Good Track"),
        candidate=SearchCandidate(
            candidate_id="candidato-bom-metadata-ruim",
            provider="fake",
            username="flux_test_user",
            artist=None,
            title=None,
            directory="unknown/unknown",
            files=[
                CandidateFile(
                    filename="unknown.flac",
                    extension="flac",
                    size_bytes=25000000,
                )
            ],
        ),
        probe=SyntheticProbeProfile(codec="flac", sample_rate=44100, bit_depth=16),
        tags=["edge-case", "bad-metadata"],
    )
    scenarios.append(_scenario(
        "candidato-bom-metadata-ruim", "Good audio but bad metadata",
        ScenarioCategory.SUSPICIOUS, ScenarioKind.METADATA_VARIANT,
        severity=ScenarioSeverity.MEDIUM, tags=["edge-case", "bad-metadata"],
    ))

    pack = MusicLabScenarioPack(
        pack_id="edge-cases",
        description="Edge case scenarios: locked files, offline users, incomplete downloads, wrong but good candidates, bad metadata.",
        version="1",
        scenarios=scenarios,
    )
    return pack, fixtures


def build_source_profile_pack() -> tuple[MusicLabScenarioPack, dict[str, SyntheticFixture]]:
    scenarios: list[MusicLabScenario] = []
    fixtures: dict[str, SyntheticFixture] = {}
    source_profiles = [
        "qobuz_like",
        "bandcamp_like",
        "cd_rip_like",
        "soulseek_folder_like",
        "youtube_rip_like",
        "spotify_rip_like",
        "web_rip_like",
        "vinyl_rip_like",
        "live_bootleg_like",
    ]

    for source_profile in source_profiles:
        fid = f"source-{source_profile}"
        scenarios.append(
            _scenario(
                fid,
                f"Source profile {source_profile} alone must not decide quality",
                ScenarioCategory.FALSE_POSITIVE,
                ScenarioKind.EDGE_CASE,
                severity=ScenarioSeverity.HIGH,
                tags=["source-profile", source_profile],
            )
        )
        fixtures[fid] = _fixture(
            fid,
            f"Synthetic source profile {source_profile}",
            "Test Artist",
            "Source Profile Track",
            SyntheticProbeProfile(
                codec="flac",
                sample_rate=44100,
                bit_depth=16,
                decode_ok=True,
                has_audio_stream=True,
                metadata={"source_profile": source_profile},
            ),
            tags=["source-profile", source_profile],
        )

    pack = MusicLabScenarioPack(
        pack_id="source-profiles",
        description="Source profile scenarios. Source profile is metadata only and must not decide quality by itself.",
        version="1",
        scenarios=scenarios,
    )
    return pack, fixtures


def build_advanced_quality_pack() -> tuple[MusicLabScenarioPack, dict[str, SyntheticFixture]]:
    scenarios: list[MusicLabScenario] = []
    fixtures: dict[str, SyntheticFixture] = {}

    specs = [
        (
            "real-flac-good",
            "Real FLAC 16/44.1 proven good - should be EXCELLENT",
            ScenarioCategory.GOOD,
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=16,
                decode_ok=True, has_audio_stream=True,
            ),
        ),
        (
            "fake-flac-from-mp3",
            "Fake FLAC transcoded from MP3 - HEURISTIC only, not BAD, not rejected",
            ScenarioCategory.SUSPICIOUS,
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=16,
                decode_ok=True, has_audio_stream=True,
                lowpass_suspicion=True, spectral_cutoff_hz=16000,
                transcode_cutoff_source="mp3-320",
            ),
        ),
        (
            "fake-24bit-detected",
            "Fake 24-bit depth on 16-bit content - HEURISTIC, not objective",
            ScenarioCategory.SUSPICIOUS,
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=24,
                decode_ok=True, has_audio_stream=True,
                fake_bit_depth=True,
            ),
        ),
        (
            "fake-96khz-detected",
            "Fake 96 kHz on 44.1 kHz content - HEURISTIC, not objective",
            ScenarioCategory.SUSPICIOUS,
            SyntheticProbeProfile(
                codec="flac", sample_rate=96000, bit_depth=16,
                decode_ok=True, has_audio_stream=True,
                fake_sample_rate=True,
            ),
        ),
        (
            "upsampled-44-1-to-96",
            "Upsampled from 44.1 to 96 kHz - HEURISTIC, not BAD, not delete",
            ScenarioCategory.SUSPICIOUS,
            SyntheticProbeProfile(
                codec="flac", sample_rate=96000, bit_depth=16,
                decode_ok=True, has_audio_stream=True,
                upsampled=True,
            ),
        ),
        (
            "downsampled-96-to-44-1",
            "Downsampled from 96 to 44.1 kHz - HEURISTIC, not BAD, not delete",
            ScenarioCategory.SUSPICIOUS,
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=24,
                decode_ok=True, has_audio_stream=True,
                downsampled=True,
            ),
        ),
        (
            "lossy-source-lossless-container",
            "Lossy source in lossless container - HEURISTIC, review candidate",
            ScenarioCategory.SUSPICIOUS,
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=16,
                decode_ok=True, has_audio_stream=True,
                lossy_source_lossless_container=True,
            ),
        ),
        (
            "bitrate-container-mismatch",
            "Bitrate/container incompatibility - HEURISTIC, review candidate",
            ScenarioCategory.SUSPICIOUS,
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=16,
                decode_ok=True, has_audio_stream=True,
                bitrate_container_mismatch=True,
            ),
        ),
        (
            "clipping-suspicion-only",
            "Clipping detected but otherwise fine - REVIEW signal, not BAD",
            ScenarioCategory.SUSPICIOUS,
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=16,
                decode_ok=True, has_audio_stream=True,
            ),
        ),
        (
            "loudness-suspicion-only",
            "Loudness anomaly but otherwise fine - REVIEW signal, not BAD",
            ScenarioCategory.SUSPICIOUS,
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=16,
                decode_ok=True, has_audio_stream=True,
            ),
        ),
        (
            "multiple-heuristics-review",
            "Multiple heuristic signals together - must be review, not rejected/delete",
            ScenarioCategory.SUSPICIOUS,
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=24,
                decode_ok=True, has_audio_stream=True,
                lowpass_suspicion=True, spectral_cutoff_hz=16000,
                bitrate_container_mismatch=True,
            ),
        ),
        (
            "objective-failure-plus-heuristics",
            "Objective failure with heuristic signals - BAD via objective, not via heuristics",
            ScenarioCategory.BAD,
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=16,
                decode_ok=False, has_audio_stream=True,
                lowpass_suspicion=True, spectral_cutoff_hz=12000,
            ),
        ),
        (
            "qobuz-like-advanced",
            "Qobuz-like 9.4 kHz cutoff decode OK - HEURISTIC only, never bad, never delete",
            ScenarioCategory.FALSE_POSITIVE,
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=16,
                decode_ok=True, has_audio_stream=True,
                spectral_cutoff_hz=9400,
                metadata={"source_profile": "qobuz_like"},
            ),
        ),
        (
            "mp3-320-good-lowpass-like",
            "MP3 320 kbps with lowpass-like profile - HEURISTIC only, never BAD",
            ScenarioCategory.FALSE_POSITIVE,
            SyntheticProbeProfile(
                codec="mp3", sample_rate=44100, bit_depth=16,
                bitrate_bps=320000,
                decode_ok=True, has_audio_stream=True,
                spectral_cutoff_hz=16000,
            ),
        ),
        (
            "fake-flac-lowpass-decode-ok",
            "Fake FLAC with lowpass but decode OK - HEURISTIC, not bad objetivo",
            ScenarioCategory.FALSE_POSITIVE,
            SyntheticProbeProfile(
                codec="flac", sample_rate=44100, bit_depth=16,
                decode_ok=True, has_audio_stream=True,
                lowpass_suspicion=True,
            ),
        ),
    ]

    for fid, desc, category, probe in specs:
        sct = MusicLabScenario(
            scenario_id=fid,
            description=desc,
            category=category,
            kind=_kind_for_advanced(scenario_id=fid, probe=probe),
            severity=_severity_for_advanced(category=category, probe=probe),
            tags=["advanced-quality", fid],
            config=MusicLabScenarioConfig(),
        )
        scenarios.append(sct)
        fixtures[fid] = _fixture(
            fid, desc, "Test Artist", "Advanced Quality Track", probe,
            tags=["advanced-quality", fid],
        )

    pack = MusicLabScenarioPack(
        pack_id="advanced-quality",
        description="Advanced quality calibration: fake FLAC, transcode, upsampling, downsampling, fake bit-depth/sample-rate, bitrate/container mismatch, clipping, loudness, multiple heuristics, objective+heuristic mix. CRITICAL: cutoff/lowpass isolated = heuristic_warning only. Fake/transcode = review candidate, never delete.",
        version="1",
        scenarios=scenarios,
    )
    return pack, fixtures


def _kind_for_advanced(scenario_id: str, probe: SyntheticProbeProfile) -> ScenarioKind:
    if "flac-from-mp3" in scenario_id or "transcode" in scenario_id or "lossy-source" in scenario_id or "bitrate-container" in scenario_id:
        return ScenarioKind.TRANSCODE
    if "fake-24bit" in scenario_id:
        return ScenarioKind.FAKE_BIT_DEPTH
    if "fake-96khz" in scenario_id:
        return ScenarioKind.FAKE_SAMPLE_RATE
    if "upsampled" in scenario_id:
        return ScenarioKind.UPSAMPLED
    if "downsampled" in scenario_id:
        return ScenarioKind.DOWNSAMPLED
    if "objective-failure" in scenario_id:
        return ScenarioKind.CORRUPT
    if "clipping" in scenario_id or "loudness" in scenario_id:
        return ScenarioKind.EDGE_CASE
    if "multiple-heuristics" in scenario_id:
        return ScenarioKind.EDGE_CASE
    return ScenarioKind.FORMAT_VARIANT


def _severity_for_advanced(category: ScenarioCategory, probe: SyntheticProbeProfile) -> ScenarioSeverity:
    if category == ScenarioCategory.BAD:
        return ScenarioSeverity.HIGH
    if category == ScenarioCategory.FALSE_POSITIVE:
        return ScenarioSeverity.CRITICAL
    if not probe.decode_ok:
        return ScenarioSeverity.HIGH
    return ScenarioSeverity.MEDIUM


_ALL_PACKS: dict[str, tuple[MusicLabScenarioPack, dict[str, SyntheticFixture]]] | None = None


def all_scenario_packs() -> dict[str, tuple[MusicLabScenarioPack, dict[str, SyntheticFixture]]]:
    global _ALL_PACKS
    if _ALL_PACKS is not None:
        return _ALL_PACKS
    _ALL_PACKS = {
        "good-formats": build_good_formats_pack(),
        "corrupt-and-invalid": build_corrupt_and_invalid_pack(),
        "transcode-suspicion": build_transcode_pack(),
        "fake-quality": build_fake_quality_pack(),
        "sample-rate-manipulation": build_sample_rate_manipulation_pack(),
        "lowpass-and-cutoff": build_lowpass_and_cutoff_pack(),
        "false-positive-guard": build_false_positive_guard_pack(),
        "advanced-quality": build_advanced_quality_pack(),
        "album-scenarios": build_album_scenarios_pack(),
        "edge-cases": build_edge_case_pack(),
        "source-profiles": build_source_profile_pack(),
    }
    return _ALL_PACKS


def get_scenario_fixture(scenario_id: str) -> SyntheticFixture | None:
    for _pack_id, (_, fixtures) in all_scenario_packs().items():
        if scenario_id in fixtures:
            return fixtures[scenario_id]
    return None


def get_scenario(scenario_id: str) -> MusicLabScenario | None:
    for _pack_id, (pack, _fixtures) in all_scenario_packs().items():
        for scenario in pack.scenarios:
            if scenario.scenario_id == scenario_id:
                return scenario
    return None


def list_all_scenarios() -> list[MusicLabScenario]:
    all_scenarios: list[MusicLabScenario] = []
    for _pack_id, (pack, _fixtures) in all_scenario_packs().items():
        all_scenarios.extend(pack.scenarios)
    return all_scenarios


def list_all_packs() -> list[MusicLabScenarioPack]:
    return [pack for _pack_id, (pack, _fixtures) in all_scenario_packs().items()]
