from __future__ import annotations

import uuid
from typing import Any

from noqlen_flux.musiclab_score_baseline import (
    MusicLabScoreBaseline,
    MusicLabScoreBaselineResult,
    MusicLabScoreCalibrationReport,
)
from noqlen_flux.musiclab_score_baseline_packs import (
    all_score_baseline_packs,
    get_score_baseline,
    list_all_score_baselines,
    list_all_score_baseline_pack_ids,
)
from noqlen_flux.results import Artifact, FluxResult, Status
from noqlen_flux.scoring import CandidateScore, ScoringProfile
from noqlen_flux.search import CandidateFile, SearchCandidate, SearchKind, SearchQuery
from noqlen_flux.services.base import FluxService
from noqlen_flux.services.scoring import CandidateScoringService


class MusicLabScoreBaselineRunnerService(FluxService):
    operation = "musiclab-score-baseline"

    def __init__(self) -> None:
        self._scoring_service = CandidateScoringService()

    def list_packs(self) -> FluxResult:
        packs = list_all_score_baseline_pack_ids()
        details = []
        for pid in packs:
            pack = all_score_baseline_packs().get(pid)
            if pack:
                details.append({
                    "pack_id": pack.pack_id,
                    "description": pack.description,
                    "version": pack.version,
                    "baseline_count": len(pack.baselines),
                })
        return self.result(
            Status.SUCCESS,
            pack_count=len(packs),
            packs=details,
        )

    def list_baselines(self) -> FluxResult:
        baselines = list_all_score_baselines()
        baseline_data = [b.to_dict() for b in baselines]
        return self.result(
            Status.SUCCESS,
            baseline_count=len(baseline_data),
            baselines=baseline_data,
        )

    def run_pack(
        self,
        pack_id: str,
        query: SearchQuery,
        candidate: SearchCandidate,
        *,
        profile: ScoringProfile | None = None,
    ) -> FluxResult:
        pack = all_score_baseline_packs().get(pack_id)
        if pack is None:
            return self.result(
                Status.FAILED,
                error=f"Score baseline pack not found: {pack_id}",
                available_packs=list_all_score_baseline_pack_ids(),
            )

        baseline_results: list[MusicLabScoreBaselineResult] = []
        passed = 0
        failed = 0
        score_drifts: list[float] = []
        risk_mismatches = 0
        confidence_oor = 0
        missing_reasons = 0
        unexpected_penalties = 0
        forbidden_detected = 0
        threshold_pressures: list[str] = []
        review_notes: list[str] = []

        for baseline in pack.baselines:
            baseline_query, baseline_candidate = _fixture_for_baseline(baseline, query, candidate)
            actual_score = self._scoring_service.score_candidate(
                baseline_query,
                baseline_candidate,
                profile=profile,
            )
            actual_reason_codes = [r.code for r in actual_score.reasons]
            actual_penalty_codes = _penalty_identifiers(actual_score)
            actual_warning_codes = list(actual_score.warnings)
            exp = baseline.expectation
            tol = baseline.tolerance

            median_expected = exp.expected_min_score
            if exp.expected_max_score is not None:
                median_expected = (exp.expected_min_score + exp.expected_max_score) / 2.0

            score_drift = actual_score.total - median_expected
            score_drifts.append(abs(score_drift))

            score_ok = actual_score.total >= exp.expected_min_score
            if exp.expected_max_score is not None:
                score_ok = score_ok and actual_score.total <= exp.expected_max_score

            risk_matched = (
                exp.expected_risk is None
                or actual_score.risk.value == exp.expected_risk.value
            )

            confidence_ok = True
            if exp.expected_confidence_min is not None:
                confidence_ok = confidence_ok and actual_score.confidence >= exp.expected_confidence_min
            if exp.expected_confidence_max is not None:
                confidence_ok = confidence_ok and actual_score.confidence <= exp.expected_confidence_max

            missing_exp_reasons = [
                c for c in exp.expected_reason_codes
                if c not in actual_reason_codes
            ]
            missing_exp_penalties = [
                c for c in exp.expected_penalty_codes
                if c not in actual_penalty_codes
            ]
            missing_exp_warnings = [
                c for c in exp.expected_warning_codes
                if c not in actual_warning_codes
            ]

            unexpected_reasons = [
                c for c in exp.forbidden_reason_codes
                if c in actual_reason_codes
            ]
            unexpected_penalty_codes = [
                c for c in exp.forbidden_penalty_codes
                if c in actual_penalty_codes
            ]
            unexpected_warn_codes = [
                c for c in exp.forbidden_warning_codes
                if c in actual_warning_codes
            ]

            forbidden = unexpected_reasons + unexpected_penalty_codes + unexpected_warn_codes

            baseline_passed = (
                score_ok
                and risk_matched
                and confidence_ok
                and not missing_exp_reasons
                and not missing_exp_penalties
                and not missing_exp_warnings
                and not forbidden
            )

            if missing_exp_reasons:
                missing_reasons += len(missing_exp_reasons)
                review_notes.append(
                    f"{baseline.baseline_id}: missing expected reasons: {missing_exp_reasons}"
                )

            if unexpected_penalty_codes:
                unexpected_penalties += len(unexpected_penalty_codes)
                threshold_pressures.append(
                    f"{baseline.baseline_id}: unexpected penalties: {unexpected_penalty_codes}"
                )

            if forbidden:
                forbidden_detected += len(forbidden)
                review_notes.append(
                    f"FORBIDDEN in {baseline.baseline_id}: {forbidden}"
                )

            if not risk_matched:
                risk_mismatches += 1
                review_notes.append(
                    f"{baseline.baseline_id}: risk mismatch expected={exp.expected_risk.value if exp.expected_risk else 'any'} actual={actual_score.risk.value}"
                )

            if not confidence_ok:
                confidence_oor += 1

            if baseline_passed:
                passed += 1
            else:
                failed += 1

            baseline_results.append(
                MusicLabScoreBaselineResult(
                    baseline_id=baseline.baseline_id,
                    passed=baseline_passed,
                    actual_score=actual_score.total,
                    actual_max_score=actual_score.max_score,
                    actual_risk=actual_score.risk.value,
                    actual_confidence=actual_score.confidence,
                    expected_min_score=exp.expected_min_score,
                    expected_max_score=exp.expected_max_score,
                    expected_risk=exp.expected_risk.value if exp.expected_risk else None,
                    score_drift=score_drift,
                    risk_matched=risk_matched,
                    confidence_in_range=confidence_ok,
                    missing_expected_reasons=missing_exp_reasons,
                    missing_expected_penalties=missing_exp_penalties,
                    missing_expected_warnings=missing_exp_warnings,
                    unexpected_reasons=unexpected_reasons,
                    unexpected_penalties=unexpected_penalty_codes,
                    unexpected_warnings=unexpected_warn_codes,
                    forbidden_detected=forbidden,
                    reasons=[r.code for r in actual_score.reasons],
                    warnings=list(actual_score.warnings),
                )
            )

        avg_drift = round(sum(score_drifts) / len(score_drifts), 3) if score_drifts else 0.0
        max_drift = round(max(score_drifts), 3) if score_drifts else 0.0

        report = MusicLabScoreCalibrationReport(
            report_id=str(uuid.uuid4()),
            pack_id=pack_id,
            total_baselines=len(pack.baselines),
            passed=passed,
            failed=failed,
            score_drift_avg=avg_drift,
            score_drift_max=max_drift,
            risk_mismatch_count=risk_mismatches,
            confidence_out_of_range_count=confidence_oor,
            missing_expected_reasons_count=missing_reasons,
            unexpected_penalties_count=unexpected_penalties,
            forbidden_detected_count=forbidden_detected,
            threshold_pressure_notes=threshold_pressures,
            suggested_review_notes=review_notes,
            baseline_results=baseline_results,
            metadata={
                "pack_id": pack_id,
                "query_artist": query.artist,
                "query_title": query.title or query.album,
                "candidate_id": candidate.candidate_id,
            },
        )

        artifact = Artifact(
            kind="score-baseline-calibration-report",
            description=f"Score baseline calibration report for pack: {pack_id}",
            metadata={"report": report.to_dict()},
        )

        overall_status = Status.SUCCESS if failed == 0 else Status.WARNING

        result = self.result(
            overall_status,
            pack_id=pack_id,
            total_baselines=report.total_baselines,
            passed=report.passed,
            failed=report.failed,
            score_drift_avg=report.score_drift_avg,
            score_drift_max=report.score_drift_max,
            risk_mismatch_count=report.risk_mismatch_count,
            forbidden_detected_count=report.forbidden_detected_count,
            threshold_pressure_notes=report.threshold_pressure_notes,
            suggested_review_notes=report.suggested_review_notes,
            report=report.to_dict(),
        )
        result.artifacts.append(artifact)
        return result.finish()

    def run_all(
        self,
        query: SearchQuery,
        candidate: SearchCandidate,
        *,
        profile: ScoringProfile | None = None,
    ) -> FluxResult:
        pack_ids = list_all_score_baseline_pack_ids()
        all_reports: list[dict[str, Any]] = []
        total_passed = 0
        total_failed = 0
        total_baselines = 0

        for pid in pack_ids:
            pack_result = self.run_pack(pid, query, candidate, profile=profile)
            report_data = pack_result.summary.get("report", {})
            all_reports.append(report_data)
            total_passed += report_data.get("passed", 0)
            total_failed += report_data.get("failed", 0)
            total_baselines += report_data.get("total_baselines", 0)

        overall_status = Status.SUCCESS if total_failed == 0 else Status.WARNING

        return self.result(
            overall_status,
            pack_count=len(pack_ids),
            total_baselines=total_baselines,
            total_passed=total_passed,
            total_failed=total_failed,
            pack_reports=all_reports,
        ).finish()

    def run_with_fixture(
        self,
        pack_id: str,
        workspace_root: str,
        *,
        dry_run: bool = True,
    ) -> FluxResult:
        pack = all_score_baseline_packs().get(pack_id)
        if pack is None:
            return self.result(
                Status.FAILED,
                error=f"Score baseline pack not found: {pack_id}",
                available_packs=list_all_score_baseline_pack_ids(),
            )

        from noqlen_flux.search import CandidateFile, SearchCandidate, SearchKind, SearchQuery

        query = SearchQuery(
            kind=SearchKind.TRACK,
            artist="Test Artist",
            title="Test Track",
        )

        candidate = SearchCandidate(
            candidate_id="score-baseline-test-candidate",
            provider="fake",
            username="flux_test_user",
            artist="Test Artist",
            title="Test Track",
            directory="Test Artist",
            files=[
                CandidateFile(
                    filename="Test Track.flac",
                    extension="flac",
                    size_bytes=25000000,
                )
            ],
        )

        return self.run_pack(pack_id, query, candidate)


def _penalty_identifiers(score: CandidateScore) -> list[str]:
    identifiers: list[str] = []
    for penalty in score.penalties:
        identifiers.append(penalty.code)
        term = penalty.metadata.get("term") if penalty.metadata else None
        if term:
            identifiers.append(f"{penalty.code}-{str(term).replace(' ', '-')}")
    return identifiers


def _fixture_for_baseline(
    baseline: MusicLabScoreBaseline,
    default_query: SearchQuery,
    default_candidate: SearchCandidate,
) -> tuple[SearchQuery, SearchCandidate]:
    bid = baseline.baseline_id

    if bid == "fp-alive-not-live":
        return _track_fixture("Test Artist", "Alive")
    if bid == "fp-olive-not-live":
        return _track_fixture("Test Artist", "Olive")
    if bid == "fp-premix-not-remix":
        return _track_fixture("Test Artist", "Premix")
    if bid == "delivery-not-live":
        return _track_fixture("Test Artist", "Delivery")

    if bid == "fp-bad-metadata-not-bad-score":
        query, candidate = _track_fixture("Test Artist", "Test Track")
        return query, SearchCandidate(
            candidate_id=bid,
            provider="fake",
            username="flux_test_user",
            artist=None,
            title="Test Track",
            directory="unknown/Test Track",
            files=candidate.files,
        )

    if bid.startswith("bad-divergent-artist"):
        query, candidate = _track_fixture("Correct Artist", "Test Track")
        return query, _replace_candidate(candidate, candidate_id=bid, artist="Wrong Artist")
    if bid.startswith("bad-divergent-title"):
        query, candidate = _track_fixture("Test Artist", "Correct Title")
        return query, _replace_candidate(candidate, candidate_id=bid, title="Wrong Title")
    if bid.startswith("bad-divergent-album"):
        return _album_fixture("Test Artist", "Correct Album", candidate_album="Wrong Album", candidate_id=bid)
    if bid == "bad-no-files":
        query, candidate = _track_fixture("Test Artist", "Test Track")
        return query, _replace_candidate(candidate, candidate_id=bid, files=[])
    if bid == "bad-all-locked":
        query, candidate = _track_fixture("Test Artist", "Test Track")
        return query, _replace_candidate(
            candidate,
            candidate_id=bid,
            files=[CandidateFile(filename="Test Track.flac", extension="flac", locked=True)],
        )
    if bid == "bad-distant-name":
        query, candidate = _track_fixture("Correct Artist", "Correct Title")
        return query, _replace_candidate(
            candidate,
            candidate_id=bid,
            artist="Other Artist",
            title="Other Title",
            directory="Other Artist/Other Title",
        )

    if "locked" in bid:
        query, candidate = _track_fixture("Test Artist", "Test Track")
        return query, _replace_candidate(
            candidate,
            candidate_id=bid,
            files=[CandidateFile(filename="Test Track.flac", extension="flac", locked=True)],
        )
    if "low-bitrate" in bid:
        query, candidate = _track_fixture("Test Artist", "Test Track")
        return query, _replace_candidate(
            candidate,
            candidate_id=bid,
            files=[CandidateFile(filename="Test Track.mp3", extension="mp3", declared_bitrate=128)],
        )
    if "confusing-folder" in bid:
        query, candidate = _track_fixture("Test Artist", "Test Track")
        return query, _replace_candidate(candidate, candidate_id=bid, directory="Various/Unknown")
    if "youtube" in bid:
        return _track_fixture("Test Artist", "Test Track youtube")
    if "web-rip" in bid:
        return _track_fixture("Test Artist", "Test Track web rip")
    if "live-bootleg" in bid:
        return _track_fixture("Test Artist", "Test Track live")

    if bid in {"good-album-complete", "album-complete-match"}:
        return _album_fixture("Test Artist", "Test Album", candidate_id=bid)

    if bid.startswith("good-exact-track-mp3") or "mp3-320" in bid:
        return _track_fixture("Test Artist", "Test Track", ext="mp3", bitrate=320)
    if bid.startswith("good-exact-track-aac"):
        return _track_fixture("Test Artist", "Test Track", ext="aac", bitrate=256)
    if bid.startswith("good-exact-track-opus"):
        return _track_fixture("Test Artist", "Test Track", ext="opus")

    return default_query, _replace_candidate(default_candidate, candidate_id=bid)


def _track_fixture(
    artist: str,
    title: str,
    *,
    ext: str = "flac",
    bitrate: int | None = None,
) -> tuple[SearchQuery, SearchCandidate]:
    query = SearchQuery(kind=SearchKind.TRACK, artist=artist, title=title)
    candidate = SearchCandidate(
        candidate_id=f"baseline-{title.casefold().replace(' ', '-')}",
        provider="fake",
        username="flux_test_user",
        artist=artist,
        title=title,
        directory=f"{artist}/{title}",
        files=[CandidateFile(
            filename=f"{title}.{ext}",
            extension=ext,
            declared_bitrate=bitrate,
            size_bytes=25000000,
        )],
    )
    return query, candidate


def _album_fixture(
    artist: str,
    album: str,
    *,
    candidate_album: str | None = None,
    candidate_id: str = "baseline-album",
) -> tuple[SearchQuery, SearchCandidate]:
    query = SearchQuery(kind=SearchKind.ALBUM, artist=artist, album=album)
    actual_album = candidate_album or album
    candidate = SearchCandidate(
        candidate_id=candidate_id,
        provider="fake",
        username="flux_test_user",
        artist=artist,
        album=actual_album,
        directory=f"{artist}/{actual_album}",
        files=[CandidateFile(filename=f"{idx:02d} Track {idx}.flac", extension="flac") for idx in range(1, 11)],
    )
    return query, candidate


def _replace_candidate(candidate: SearchCandidate, **updates: Any) -> SearchCandidate:
    data = candidate.to_dict()
    data.update(updates)
    files = data.pop("files", candidate.files)
    normalized_files = [
        item if isinstance(item, CandidateFile) else CandidateFile(**item)
        for item in files
    ]
    return SearchCandidate(files=normalized_files, **data)
