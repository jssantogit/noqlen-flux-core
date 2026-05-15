from __future__ import annotations

from typing import Any

from .musiclab_score_baseline import (
    DEFAULT_SCORE_TOLERANCE,
    MusicLabScoreBaseline,
    MusicLabScoreBaselinePack,
    MusicLabScoreExpectation,
    MusicLabScoreTolerance,
    ScoreBaselineRisk,
)

SafeMetadata = dict[str, Any]


def _baseline(
    baseline_id: str,
    description: str,
    expected_min_score: float,
    *,
    expected_max_score: float | None = None,
    expected_risk: str = "low",
    expected_confidence_min: float | None = None,
    expected_confidence_max: float | None = None,
    expected_reason_codes: list[str] | None = None,
    expected_penalty_codes: list[str] | None = None,
    expected_warning_codes: list[str] | None = None,
    forbidden_reason_codes: list[str] | None = None,
    forbidden_penalty_codes: list[str] | None = None,
    forbidden_warning_codes: list[str] | None = None,
    category: str = "general",
    tolerance: MusicLabScoreTolerance | None = None,
    tags: list[str] | None = None,
    priority: str = "medium",
) -> MusicLabScoreBaseline:
    return MusicLabScoreBaseline(
        baseline_id=baseline_id,
        category=category,
        description=description,
        expectation=MusicLabScoreExpectation(
            expected_min_score=expected_min_score,
            expected_max_score=expected_max_score,
            expected_risk=ScoreBaselineRisk(expected_risk) if expected_risk else None,
            expected_confidence_min=expected_confidence_min,
            expected_confidence_max=expected_confidence_max,
            expected_reason_codes=expected_reason_codes or [],
            expected_penalty_codes=expected_penalty_codes or [],
            expected_warning_codes=expected_warning_codes or [],
            forbidden_reason_codes=forbidden_reason_codes or [],
            forbidden_penalty_codes=forbidden_penalty_codes or [],
            forbidden_warning_codes=forbidden_warning_codes or [],
            description=description,
        ),
        tolerance=tolerance or DEFAULT_SCORE_TOLERANCE,
        priority=priority,
        tags=tags or [],
    )


def build_scoring_good_candidates_pack() -> MusicLabScoreBaselinePack:
    baselines = [
        _baseline(
            "good-exact-track-flac",
            "Exact match for FLAC track - should score high, low risk",
            expected_min_score=85.0,
            expected_risk="low",
            expected_reason_codes=["exact-artist-match", "exact-title-match", "textual-match-artist-title"],
            forbidden_penalty_codes=["divergent-artist", "divergent-title", "low-bitrate"],
            category="good",
            tags=["good", "flac", "exact-match"],
        ),
        _baseline(
            "good-exact-track-mp3-320",
            "Exact match for MP3 320 track - should score high",
            expected_min_score=80.0,
            expected_risk="low",
            expected_reason_codes=["exact-artist-match", "exact-title-match", "textual-match-artist-title"],
            forbidden_penalty_codes=["divergent-artist", "divergent-title"],
            category="good",
            tags=["good", "mp3", "exact-match"],
        ),
        _baseline(
            "good-exact-track-aac-256",
            "Exact match for AAC 256 track - should score high",
            expected_min_score=80.0,
            expected_risk="low",
            expected_reason_codes=["exact-artist-match", "exact-title-match", "textual-match-artist-title"],
            forbidden_penalty_codes=["divergent-artist", "divergent-title"],
            category="good",
            tags=["good", "aac", "exact-match"],
        ),
        _baseline(
            "good-exact-track-opus",
            "Exact match for Opus track - should score high",
            expected_min_score=80.0,
            expected_risk="low",
            expected_reason_codes=["exact-artist-match", "exact-title-match", "textual-match-artist-title"],
            forbidden_penalty_codes=["divergent-artist", "divergent-title"],
            category="good",
            tags=["good", "opus", "exact-match"],
        ),
        _baseline(
            "good-album-complete",
            "Complete album with all tracks - should score high",
            expected_min_score=80.0,
            expected_risk="low",
            expected_reason_codes=["exact-artist-match", "exact-album-match", "textual-match-artist-album"],
            forbidden_penalty_codes=["divergent-artist", "divergent-album"],
            category="good",
            tags=["good", "album", "complete"],
        ),
        _baseline(
            "good-clean-candidate-name",
            "Candidate with clean, matching name - no suspicious terms",
            expected_min_score=80.0,
            expected_risk="low",
            forbidden_penalty_codes=["suspicious-term-live", "suspicious-term-remix"],
            category="good",
            tags=["good", "clean", "no-suspicious-terms"],
        ),
    ]
    return MusicLabScoreBaselinePack(
        pack_id="scoring-good-candidates",
        description="Good candidates: exact matches with clean metadata. All must score high with low risk.",
        version="1",
        baselines=baselines,
        metadata={"category": "good", "purpose": "ensure good candidates are not under-scored"},
    )


def build_scoring_bad_candidates_pack() -> MusicLabScoreBaselinePack:
    baselines = [
        _baseline(
            "bad-divergent-artist",
            "Artist name completely mismatched - should score low, high risk",
            expected_min_score=0.0,
            expected_max_score=30.0,
            expected_risk="high",
            expected_penalty_codes=["divergent-artist"],
            category="bad",
            tags=["bad", "divergent-artist"],
        ),
        _baseline(
            "bad-divergent-title",
            "Title completely mismatched - should score low",
            expected_min_score=0.0,
            expected_max_score=30.0,
            expected_risk="high",
            expected_penalty_codes=["divergent-title"],
            category="bad",
            tags=["bad", "divergent-title"],
        ),
        _baseline(
            "bad-divergent-album",
            "Album name completely mismatched - should score very low",
            expected_min_score=0.0,
            expected_max_score=25.0,
            expected_risk="high",
            expected_penalty_codes=["divergent-album"],
            category="bad",
            tags=["bad", "divergent-album"],
        ),
        _baseline(
            "bad-no-files",
            "Candidate with no files - should have no-file penalty",
            expected_min_score=0.0,
            expected_max_score=20.0,
            expected_risk="high",
            expected_penalty_codes=["no-files"],
            category="bad",
            tags=["bad", "no-files"],
        ),
        _baseline(
            "bad-all-locked",
            "All files locked - should penalize heavily",
            expected_min_score=0.0,
            expected_max_score=30.0,
            expected_risk="high",
            expected_penalty_codes=["all-files-locked"],
            category="bad",
            tags=["bad", "locked", "all-locked"],
        ),
        _baseline(
            "bad-distant-name",
            "Candidate name bears no resemblance to query - should score near zero",
            expected_min_score=0.0,
            expected_max_score=15.0,
            expected_risk="high",
            category="bad",
            tags=["bad", "distant-name"],
        ),
    ]
    return MusicLabScoreBaselinePack(
        pack_id="scoring-bad-candidates",
        description="Bad candidates: mismatched metadata, missing files, locked files. All must score low with high risk.",
        version="1",
        baselines=baselines,
        metadata={"category": "bad", "purpose": "ensure bad candidates are identified correctly"},
    )


def build_scoring_false_positive_guards_pack() -> MusicLabScoreBaselinePack:
    baselines = [
        _baseline(
            "fp-alive-not-live",
            "Track titled 'Alive' must NOT trigger 'live' suspicious term penalty",
            expected_min_score=80.0,
            expected_risk="low",
            forbidden_penalty_codes=["suspicious-term-live"],
            category="false-positive",
            priority="critical",
            tags=["false-positive", "alive", "live"],
        ),
        _baseline(
            "fp-olive-not-live",
            "Track titled 'Olive' must NOT trigger 'live' suspicious term penalty",
            expected_min_score=80.0,
            expected_risk="low",
            forbidden_penalty_codes=["suspicious-term-live"],
            category="false-positive",
            priority="critical",
            tags=["false-positive", "olive", "live"],
        ),
        _baseline(
            "fp-premix-not-remix",
            "Track titled 'Premix' must NOT trigger 'remix' suspicious term penalty",
            expected_min_score=80.0,
            expected_risk="low",
            forbidden_penalty_codes=["suspicious-term-remix"],
            category="false-positive",
            priority="critical",
            tags=["false-positive", "premix", "remix"],
        ),
        _baseline(
            "fp-source-profile-ignored",
            "Source profile hints must not penalize score aggressively",
            expected_min_score=75.0,
            expected_risk="low",
            forbidden_penalty_codes=["source-profile-suspicious"],
            category="false-positive",
            priority="critical",
            tags=["false-positive", "source-profile"],
        ),
        _baseline(
            "fp-lowpass-not-high-risk",
            "Lowpass suspicion alone must not produce high risk",
            expected_min_score=60.0,
            expected_risk="low",
            forbidden_penalty_codes=["lowpass-quality-penalty"],
            category="false-positive",
            priority="critical",
            tags=["false-positive", "lowpass", "cutoff"],
        ),
        _baseline(
            "fp-cutoff-not-high-risk",
            "Spectral cutoff alone must not produce high risk",
            expected_min_score=60.0,
            expected_risk="low",
            forbidden_penalty_codes=["cutoff-quality-penalty"],
            category="false-positive",
            priority="critical",
            tags=["false-positive", "cutoff"],
        ),
        _baseline(
            "fp-qobuz-like-not-high-risk",
            "Qobuz-like 9.4 kHz cutoff must not trigger high risk",
            expected_min_score=65.0,
            expected_risk="low",
            forbidden_penalty_codes=["lowpass-quality-penalty", "cutoff-quality-penalty"],
            category="false-positive",
            priority="critical",
            tags=["false-positive", "qobuz", "cutoff"],
        ),
        _baseline(
            "fp-bad-metadata-not-bad-score",
            "Bad metadata must reduce confidence, not prove file is bad",
            expected_min_score=50.0,
            expected_confidence_max=0.8,
            forbidden_penalty_codes=["provably-bad-file"],
            category="false-positive",
            priority="high",
            tags=["false-positive", "bad-metadata", "confidence"],
        ),
        _baseline(
            "delivery-not-live",
            "Track titled 'Delivery' must NOT trigger 'live' suspicious term",
            expected_min_score=80.0,
            expected_risk="low",
            forbidden_penalty_codes=["suspicious-term-live"],
            category="false-positive",
            priority="critical",
            tags=["false-positive", "delivery", "live"],
        ),
    ]
    return MusicLabScoreBaselinePack(
        pack_id="scoring-false-positive-guards",
        description="False-positive guards: ensures suspicious term detection does not over-punish innocent candidates. CRITICAL for safety regression.",
        version="1",
        baselines=baselines,
        metadata={"category": "false-positive", "purpose": "prevent false positive penalties from corrupting scores"},
    )


def build_scoring_provider_anomalies_pack() -> MusicLabScoreBaselinePack:
    baselines = [
        _baseline(
            "anomaly-candidate-locked",
            "Locked candidate should penalize availability but not turn into bad quality",
            expected_min_score=50.0,
            expected_risk="medium",
            expected_penalty_codes=["locked-file"],
            forbidden_penalty_codes=["provably-bad-file", "bad-quality"],
            category="anomaly",
            tags=["anomaly", "locked", "availability"],
        ),
        _baseline(
            "anomaly-user-offline",
            "User offline reduces confidence but should not zero the score",
            expected_min_score=40.0,
            expected_max_score=90.0,
            category="anomaly",
            tags=["anomaly", "offline", "availability"],
        ),
        _baseline(
            "anomaly-confusing-folder",
            "Confusing folder name should penalize consistency but not eliminate score",
            expected_min_score=30.0,
            expected_risk="medium",
            category="anomaly",
            tags=["anomaly", "folder", "consistency"],
        ),
        _baseline(
            "anomaly-low-bitrate-declared",
            "Low declared bitrate should penalize quality component, not crash score",
            expected_min_score=50.0,
            expected_penalty_codes=["low-bitrate"],
            forbidden_penalty_codes=["provably-bad-file"],
            category="anomaly",
            tags=["anomaly", "low-bitrate", "quality"],
        ),
        _baseline(
            "anomaly-suspicious-extension",
            "Suspicious extension should flag but not zero the score",
            expected_min_score=40.0,
            category="anomaly",
            priority="low",
            tags=["anomaly", "extension", "suspicious"],
        ),
        _baseline(
            "anomaly-fake-flac-probable",
            "Fake FLAC probable should generate review signal, not destructive action",
            expected_min_score=50.0,
            expected_risk="medium",
            forbidden_penalty_codes=["provably-bad-file", "delete-eligible"],
            category="anomaly",
            tags=["anomaly", "fake-flac", "transcode"],
        ),
        _baseline(
            "anomaly-transcode-probable",
            "Transcode probable should reduce score but not kill it",
            expected_min_score=45.0,
            expected_risk="medium",
            forbidden_penalty_codes=["provably-bad-file", "delete-eligible"],
            category="anomaly",
            tags=["anomaly", "transcode", "suspicious"],
        ),
    ]
    return MusicLabScoreBaselinePack(
        pack_id="scoring-provider-anomalies",
        description="Provider anomalies: locked files, offline users, confusing folders, low bitrate, suspicious extensions, fake FLAC, transcode. None should produce destructive actions.",
        version="1",
        baselines=baselines,
        metadata={"category": "anomaly", "purpose": "ensure provider anomalies generate warnings not destruction"},
    )


def build_scoring_quality_aware_preview_pack() -> MusicLabScoreBaselinePack:
    baselines = [
        _baseline(
            "qa-qobuz-like-cutoff",
            "Qobuz-like 9.4 kHz cutoff with decode OK - quality hints but score remains medium+",
            expected_min_score=60.0,
            expected_risk="low",
            forbidden_penalty_codes=["bad-quality", "rejected", "delete-eligible"],
            category="quality-aware",
            priority="high",
            tags=["quality-aware", "qobuz", "cutoff"],
        ),
        _baseline(
            "qa-lowpass-only",
            "Lowpass suspicion only - must not destroy score",
            expected_min_score=60.0,
            expected_risk="low",
            forbidden_penalty_codes=["bad-quality"],
            category="quality-aware",
            priority="high",
            tags=["quality-aware", "lowpass"],
        ),
        _baseline(
            "qa-mp3-320-lowpass-like",
            "MP3 320 kbps with inherent lowpass-like cutoff - must score well",
            expected_min_score=65.0,
            expected_risk="low",
            forbidden_penalty_codes=["bad-quality", "lowpass-quality-penalty"],
            category="quality-aware",
            priority="high",
            tags=["quality-aware", "mp3-320", "lowpass-like"],
        ),
        _baseline(
            "qa-fake-bit-depth",
            "Fake 24-bit on 16-bit content - should generate warning, not kill score",
            expected_min_score=55.0,
            expected_risk="medium",
            forbidden_penalty_codes=["bad-quality"],
            category="quality-aware",
            tags=["quality-aware", "fake-bit-depth"],
        ),
        _baseline(
            "qa-fake-sample-rate",
            "Fake 96 kHz on 44.1 kHz content - should generate warning",
            expected_min_score=55.0,
            expected_risk="medium",
            forbidden_penalty_codes=["bad-quality"],
            category="quality-aware",
            tags=["quality-aware", "fake-sample-rate"],
        ),
        _baseline(
            "qa-clipping-only",
            "Clipping detected but otherwise good - review signal, not bad quality",
            expected_min_score=60.0,
            expected_risk="low",
            forbidden_penalty_codes=["bad-quality"],
            category="quality-aware",
            tags=["quality-aware", "clipping"],
        ),
    ]
    return MusicLabScoreBaselinePack(
        pack_id="scoring-quality-aware-preview",
        description="Quality-aware score preview: quality hints (cutoff, lowpass, fake quality) inform scoring without destroying scores. QualityGrade != CandidateRisk.",
        version="1",
        baselines=baselines,
        metadata={"category": "quality-aware", "purpose": "ensure quality signals inform but do not dominate scoring"},
    )


def build_scoring_album_integrity_pack() -> MusicLabScoreBaselinePack:
    baselines = [
        _baseline(
            "album-complete-match",
            "Complete album with all tracks matching",
            expected_min_score=80.0,
            expected_risk="low",
            expected_reason_codes=["exact-artist-match", "exact-album-match", "textual-match-artist-album"],
            category="album",
            tags=["album", "complete", "integrity"],
        ),
        _baseline(
            "album-missing-track",
            "Album with one missing track - should reduce score but not destroy it",
            expected_min_score=50.0,
            expected_max_score=85.0,
            expected_risk="medium",
            category="album",
            tags=["album", "missing-track"],
        ),
        _baseline(
            "album-duplicate-track",
            "Album with duplicated track - should flag as suspicious",
            expected_min_score=45.0,
            expected_max_score=80.0,
            expected_risk="medium",
            category="album",
            tags=["album", "duplicate-track"],
        ),
        _baseline(
            "album-wrong-order",
            "Album with wrong track order - should reduce consistency score",
            expected_min_score=50.0,
            expected_max_score=80.0,
            expected_risk="medium",
            category="album",
            tags=["album", "wrong-order"],
        ),
        _baseline(
            "album-mixed-formats",
            "Album with mixed formats - should reduce quality score",
            expected_min_score=50.0,
            expected_max_score=80.0,
            expected_risk="medium",
            category="album",
            tags=["album", "mixed-formats"],
        ),
    ]
    return MusicLabScoreBaselinePack(
        pack_id="scoring-album-integrity",
        description="Album integrity: complete, missing, duplicate, wrong order, mixed formats. Scores should reflect album-level fidelity.",
        version="1",
        baselines=baselines,
        metadata={"category": "album", "purpose": "verify album-level scoring responds to structural anomalies"},
    )


def build_scoring_source_profiles_pack() -> MusicLabScoreBaselinePack:
    baselines = [
        _baseline(
            "source-bandcamp-like",
            "Bandcamp-like source profile must not penalize score aggressively",
            expected_min_score=75.0,
            expected_risk="low",
            forbidden_penalty_codes=["source-profile-suspicious"],
            category="source-profile",
            priority="high",
            tags=["source-profile", "bandcamp"],
        ),
        _baseline(
            "source-cd-rip-like",
            "CD rip source must not penalize score",
            expected_min_score=80.0,
            expected_risk="low",
            forbidden_penalty_codes=["source-profile-suspicious"],
            category="source-profile",
            tags=["source-profile", "cd-rip"],
        ),
        _baseline(
            "source-soulseek-like",
            "Soulseek folder source must not penalize score (it's the default)",
            expected_min_score=80.0,
            expected_risk="low",
            forbidden_penalty_codes=["source-profile-suspicious"],
            category="source-profile",
            tags=["source-profile", "soulseek"],
        ),
        _baseline(
            "source-youtube-rip-like",
            "YouTube rip source should flag as suspicious but not zero the score",
            expected_min_score=45.0,
            expected_max_score=80.0,
            expected_risk="medium",
            category="source-profile",
            tags=["source-profile", "youtube-rip"],
        ),
        _baseline(
            "source-web-rip-like",
            "Web rip source should flag as suspicious but not kill the score",
            expected_min_score=50.0,
            expected_max_score=80.0,
            expected_risk="medium",
            category="source-profile",
            tags=["source-profile", "web-rip"],
        ),
        _baseline(
            "source-vinyl-rip-like",
            "Vinyl rip source must not be auto-penalized (it is a legitimate source)",
            expected_min_score=70.0,
            expected_risk="low",
            forbidden_penalty_codes=["source-profile-suspicious", "bad-quality"],
            category="source-profile",
            priority="high",
            tags=["source-profile", "vinyl-rip"],
        ),
        _baseline(
            "source-live-bootleg-like",
            "Live bootleg source should flag as suspicious term but not zero score",
            expected_min_score=40.0,
            expected_max_score=75.0,
            expected_risk="medium",
            category="source-profile",
            tags=["source-profile", "live-bootleg"],
        ),
    ]
    return MusicLabScoreBaselinePack(
        pack_id="scoring-source-profiles",
        description="Source profile scoring: source hints should inform but not dominate scoring. Vinyl/bootleg sources must not be auto-punished.",
        version="1",
        baselines=baselines,
        metadata={"category": "source-profile", "purpose": "prevent source profile bias in scoring"},
    )


_ALL_SCORE_BASELINE_PACKS: dict[str, MusicLabScoreBaselinePack] | None = None


def all_score_baseline_packs() -> dict[str, MusicLabScoreBaselinePack]:
    global _ALL_SCORE_BASELINE_PACKS
    if _ALL_SCORE_BASELINE_PACKS is not None:
        return _ALL_SCORE_BASELINE_PACKS
    _ALL_SCORE_BASELINE_PACKS = {
        "scoring-good-candidates": build_scoring_good_candidates_pack(),
        "scoring-bad-candidates": build_scoring_bad_candidates_pack(),
        "scoring-false-positive-guards": build_scoring_false_positive_guards_pack(),
        "scoring-provider-anomalies": build_scoring_provider_anomalies_pack(),
        "scoring-quality-aware-preview": build_scoring_quality_aware_preview_pack(),
        "scoring-album-integrity": build_scoring_album_integrity_pack(),
        "scoring-source-profiles": build_scoring_source_profiles_pack(),
    }
    return _ALL_SCORE_BASELINE_PACKS


def get_score_baseline(baseline_id: str) -> MusicLabScoreBaseline | None:
    for pack in all_score_baseline_packs().values():
        for baseline in pack.baselines:
            if baseline.baseline_id == baseline_id:
                return baseline
    return None


def list_all_score_baselines() -> list[MusicLabScoreBaseline]:
    result: list[MusicLabScoreBaseline] = []
    for pack in all_score_baseline_packs().values():
        result.extend(pack.baselines)
    return result


def list_all_score_baseline_pack_ids() -> list[str]:
    return list(all_score_baseline_packs().keys())
