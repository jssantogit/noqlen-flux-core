from __future__ import annotations

import re

from noqlen_flux.results import Artifact, FluxResult, FluxWarning, Status
from noqlen_flux.scoring import (
    DEFAULT_SCORING_PROFILE,
    CandidateRisk,
    CandidateScore,
    ScoreComponent,
    ScorePenalty,
    ScoreReason,
    ScoringProfile,
    ScoringResult,
)
from noqlen_flux.search import SearchCandidate, SearchKind, SearchQuery
from noqlen_flux.services.base import FluxService


SUSPICIOUS_TERMS = {
    "live": 8.0,
    "remix": 8.0,
    "radio edit": 8.0,
    "youtube": 20.0,
    "web rip": 20.0,
    "reencode": 20.0,
    "low quality": 20.0,
}


class CandidateScoringService(FluxService):
    operation = "candidate-scoring"

    def score_candidate(
        self,
        query: SearchQuery,
        candidate: SearchCandidate,
        profile: ScoringProfile | None = None,
    ) -> CandidateScore:
        scoring_profile = profile or DEFAULT_SCORING_PROFILE
        components = [
            _artist_match_component(query, candidate, scoring_profile),
            _title_or_album_match_component(query, candidate, scoring_profile),
            _textual_match_component(query, candidate, scoring_profile),
            _folder_consistency_component(candidate, scoring_profile),
            _declared_quality_component(candidate, scoring_profile),
            _availability_component(candidate, scoring_profile),
            _risk_penalties_component(candidate),
        ]
        reasons = [reason for component in components for reason in component.reasons]
        penalties = [penalty for component in components for penalty in component.penalties]
        warnings = _warnings(candidate, penalties)
        max_score = sum(scoring_profile.weights.values())
        raw_total = sum(component.score for component in components)
        total = round(max(0.0, min(max_score, raw_total)), 2)
        confidence = round(max(scoring_profile.thresholds["minimum_confidence"], total / max_score), 2)
        risk = _risk(sum(penalty.value for penalty in penalties), scoring_profile)
        return CandidateScore(
            candidate_id=candidate.candidate_id,
            total=total,
            max_score=max_score,
            risk=risk,
            confidence=confidence,
            components=components,
            reasons=reasons,
            penalties=penalties,
            warnings=warnings,
            metadata={"profile": scoring_profile.name},
        )

    def score_candidates(
        self,
        query: SearchQuery,
        candidates: list[SearchCandidate],
        profile: ScoringProfile | None = None,
    ) -> FluxResult:
        scoring_profile = profile or DEFAULT_SCORING_PROFILE
        scores = [self.score_candidate(query, candidate, scoring_profile) for candidate in candidates]
        provider = candidates[0].provider if candidates else "unknown"
        result_model = ScoringResult(query=query, provider=provider, scores=scores, profile=scoring_profile)
        score_payload = [score.to_dict() for score in scores]
        warnings = [FluxWarning(code="candidate-risk", message=warning) for score in scores for warning in score.warnings]
        status = Status.WARNING if warnings else Status.SUCCESS
        artifact = Artifact(
            kind="candidate-scores",
            description="Logical pre-download candidate score result set",
            metadata={"provider": provider, "scores": score_payload},
        )
        step = self.step(
            "score-candidates",
            status,
            f"Scored {len(scores)} candidate(s) with profile {scoring_profile.name}",
            warnings=warnings,
            artifacts=[artifact],
        )
        return FluxResult(
            operation=self.operation,
            status=status,
            steps=[step],
            warnings=warnings,
            artifacts=[artifact],
            summary={
                "provider": provider,
                "profile": scoring_profile.to_dict(),
                "score_count": len(scores),
                "scores": score_payload,
                "scoring_result": result_model.to_dict(),
            },
        ).finish()


def _artist_match_component(
    query: SearchQuery, candidate: SearchCandidate, profile: ScoringProfile
) -> ScoreComponent:
    max_score = profile.weights["artist_match"]
    if _same_text(query.artist, candidate.artist):
        reason = ScoreReason("artist-exact", "Artist matches exactly.", max_score, max_score)
        return ScoreComponent("artist_match", max_score, max_score, reasons=[reason])
    penalty = ScorePenalty("artist-mismatch", "Artist does not match exactly.", 10.0)
    return ScoreComponent("artist_match", 0.0, max_score, penalties=[penalty])


def _title_or_album_match_component(
    query: SearchQuery, candidate: SearchCandidate, profile: ScoringProfile
) -> ScoreComponent:
    max_score = profile.weights["title_or_album_match"]
    expected = query.title if query.kind == SearchKind.TRACK else query.album
    actual = candidate.title if query.kind == SearchKind.TRACK else candidate.album
    label = "Title" if query.kind == SearchKind.TRACK else "Album"
    if _same_text(expected, actual):
        reason = ScoreReason("title-album-exact", f"{label} matches exactly.", max_score, max_score)
        return ScoreComponent("title_or_album_match", max_score, max_score, reasons=[reason])
    penalty = ScorePenalty("title-album-mismatch", f"{label} does not match exactly.", 10.0)
    return ScoreComponent("title_or_album_match", 0.0, max_score, penalties=[penalty])


def _textual_match_component(query: SearchQuery, candidate: SearchCandidate, profile: ScoringProfile) -> ScoreComponent:
    max_score = profile.weights["textual_match"]
    exact_artist = _same_text(query.artist, candidate.artist)
    expected = query.title if query.kind == SearchKind.TRACK else query.album
    actual = candidate.title if query.kind == SearchKind.TRACK else candidate.album
    exact_title_or_album = _same_text(expected, actual)
    if exact_artist and exact_title_or_album:
        reason = ScoreReason("textual-exact", "Artist and requested title/album match exactly.", max_score, max_score)
        return ScoreComponent("textual_match", max_score, max_score, reasons=[reason])
    haystack = _candidate_text(candidate)
    if query.artist.casefold() in haystack and expected and expected.casefold() in haystack:
        score = max_score / 2
        reason = ScoreReason("textual-contained", "Requested terms are present in candidate text.", max_score, score)
        return ScoreComponent("textual_match", score, max_score, reasons=[reason])
    penalty = ScorePenalty("textual-weak", "Requested terms are not strongly represented in candidate text.", 10.0)
    return ScoreComponent("textual_match", 0.0, max_score, penalties=[penalty])


def _folder_consistency_component(candidate: SearchCandidate, profile: ScoringProfile) -> ScoreComponent:
    max_score = profile.weights["folder_consistency"]
    if not candidate.directory:
        return ScoreComponent("folder_consistency", max_score / 2, max_score)
    text = candidate.directory.casefold()
    terms = [term for term in (candidate.artist, candidate.title, candidate.album) if term]
    if terms and all(term.casefold() in text for term in terms):
        reason = ScoreReason("folder-consistent", "Directory text is consistent with candidate metadata.", max_score, max_score)
        return ScoreComponent("folder_consistency", max_score, max_score, reasons=[reason])
    penalty = ScorePenalty("folder-inconsistent", "Directory text is not fully consistent with metadata.", 5.0)
    return ScoreComponent("folder_consistency", 0.0, max_score, penalties=[penalty])


def _declared_quality_component(candidate: SearchCandidate, profile: ScoringProfile) -> ScoreComponent:
    max_score = profile.weights["declared_quality"]
    if not candidate.files:
        penalty = ScorePenalty("no-files", "Candidate has no declared files.", 30.0)
        return ScoreComponent("declared_quality", 0.0, max_score, penalties=[penalty])
    penalties: list[ScorePenalty] = []
    reasons: list[ScoreReason] = []
    for candidate_file in candidate.files:
        if candidate_file.declared_bitrate is not None and candidate_file.declared_bitrate < 192:
            penalties.append(ScorePenalty("low-declared-bitrate", "Declared bitrate is below a conservative threshold.", 4.0))
    if penalties:
        return ScoreComponent("declared_quality", max_score / 2, max_score, penalties=penalties)
    if any((item.extension or "").casefold() in {"flac", "wav", "aiff"} for item in candidate.files):
        reasons.append(ScoreReason("declared-lossless-container", "Declared extension suggests a lossless container.", max_score, max_score))
        return ScoreComponent("declared_quality", max_score, max_score, reasons=reasons)
    return ScoreComponent("declared_quality", max_score / 2, max_score)


def _availability_component(candidate: SearchCandidate, profile: ScoringProfile) -> ScoreComponent:
    max_score = profile.weights["availability"]
    if not candidate.files:
        penalty = ScorePenalty("no-available-files", "Candidate has no files visible before download.", 30.0)
        return ScoreComponent("availability", 0.0, max_score, penalties=[penalty])
    locked_count = sum(1 for candidate_file in candidate.files if candidate_file.locked)
    if locked_count:
        penalty = ScorePenalty("locked-files", "Candidate includes locked files.", 10.0, metadata={"locked_count": locked_count})
        return ScoreComponent("availability", max_score / 2, max_score, penalties=[penalty])
    reason = ScoreReason("files-visible", "Candidate has visible files before download.", max_score, max_score)
    return ScoreComponent("availability", max_score, max_score, reasons=[reason])


def _risky_term_in_text(term: str, text: str) -> bool:
    if " " in term:
        return term in text
    return bool(re.search(rf"\b{re.escape(term)}\b", text))


def _risk_penalties_component(candidate: SearchCandidate) -> ScoreComponent:
    candidate_text = _candidate_text(candidate)
    penalties = [
        ScorePenalty("suspicious-term", f"Suspicious pre-download term found: {term}.", value, metadata={"term": term})
        for term, value in SUSPICIOUS_TERMS.items()
        if _risky_term_in_text(term, candidate_text)
    ]
    penalty_total = sum(penalty.value for penalty in penalties)
    return ScoreComponent("risk_penalties", -penalty_total, 0.0, penalties=penalties)


def _risk(penalty_total: float, profile: ScoringProfile) -> CandidateRisk:
    if penalty_total >= profile.thresholds["high_risk_penalty"]:
        return CandidateRisk.HIGH
    if penalty_total >= profile.thresholds["medium_risk_penalty"]:
        return CandidateRisk.MEDIUM
    return CandidateRisk.LOW


def _warnings(candidate: SearchCandidate, penalties: list[ScorePenalty]) -> list[str]:
    messages = list(candidate.warnings)
    messages.extend(penalty.message for penalty in penalties if penalty.code in {"locked-files", "suspicious-term", "no-files"})
    return messages


def _same_text(expected: str | None, actual: str | None) -> bool:
    if expected is None or actual is None:
        return False
    return expected.strip().casefold() == actual.strip().casefold()


def _candidate_text(candidate: SearchCandidate) -> str:
    parts = [candidate.directory, candidate.artist, candidate.title, candidate.album]
    parts.extend(candidate_file.filename for candidate_file in candidate.files)
    return " ".join(part for part in parts if part).casefold()
