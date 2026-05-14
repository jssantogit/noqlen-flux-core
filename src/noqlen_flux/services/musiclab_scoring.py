from __future__ import annotations

from noqlen_flux.musiclab_scoring import (
    ScoringCalibrationCase,
    ScoringCalibrationCaseResult,
    ScoringCalibrationDataset,
    ScoringCalibrationExpectation,
    ScoringCalibrationReport,
)
from noqlen_flux.results import Artifact, FluxResult, Status
from noqlen_flux.scoring import DEFAULT_SCORING_PROFILE, CandidateRisk, CandidateScore, ScoringProfile
from noqlen_flux.search import CandidateFile, SearchCandidate, SearchKind, SearchQuery
from noqlen_flux.services.base import FluxService
from noqlen_flux.services.scoring import CandidateScoringService


class MusicLabScoringService(FluxService):
    operation = "musiclab-scoring"

    def build_default_dataset(self) -> ScoringCalibrationDataset:
        return _build_default_scoring_calibration_dataset()

    def run_calibration(
        self,
        dataset: ScoringCalibrationDataset | None = None,
        scoring_service: CandidateScoringService | None = None,
        profile: ScoringProfile | None = None,
    ) -> FluxResult:
        result = self.result(
            Status.SUCCESS,
            dry_run=True,
            action="scoring-calibration",
        )
        ds = dataset or self.build_default_dataset()
        scorer = scoring_service or CandidateScoringService()
        scoring_profile = profile or DEFAULT_SCORING_PROFILE

        case_results: list[ScoringCalibrationCaseResult] = []
        passed_count = 0
        failed_count = 0
        report_warnings: list[str] = []
        report_errors: list[str] = []

        for case in ds.cases:
            case_result = self._evaluate_case(case, scorer, scoring_profile)
            case_results.append(case_result)
            if case_result.passed:
                passed_count += 1
            else:
                failed_count += 1
            case_result_warnings = [w for w in case_result.warnings]
            report_warnings.extend(case_result_warnings)
            case_result_errors = [e for e in case_result.errors]
            report_errors.extend(case_result_errors)

        report = ScoringCalibrationReport(
            dataset_id=ds.dataset_id,
            profile_name=scoring_profile.name,
            total_cases=len(ds.cases),
            passed_cases=passed_count,
            failed_cases=failed_count,
            case_results=case_results,
            warnings=report_warnings,
            errors=report_errors,
            metadata={
                "dataset_version": ds.version,
                "network": False,
                "downloads": False,
                "library_writes": False,
            },
        )

        result.artifacts.append(
            Artifact(
                kind="scoring-calibration-report",
                description="Logical scoring calibration report",
                metadata={"report": report.to_dict()},
            )
        )

        status = Status.SUCCESS if failed_count == 0 else Status.WARNING
        result.summary.update(
            {
                "dataset_id": ds.dataset_id,
                "dataset_version": ds.version,
                "profile_name": scoring_profile.name,
                "total_cases": len(ds.cases),
                "passed_cases": passed_count,
                "failed_cases": failed_count,
                "failed_case_ids": [cr.case_id for cr in case_results if not cr.passed],
                "network": False,
                "downloads": False,
                "library_writes": False,
            }
        )
        result.steps.append(
            self.step(
                "scoring-calibration",
                status,
                f"Calibration complete: {passed_count}/{len(ds.cases)} passed with profile {scoring_profile.name}",
            )
        )
        return result.finish(status)

    def _evaluate_case(
        self,
        case: ScoringCalibrationCase,
        scorer: CandidateScoringService,
        profile: ScoringProfile,
    ) -> ScoringCalibrationCaseResult:
        score: CandidateScore = scorer.score_candidate(case.query, case.candidate, profile)
        exp = case.expectation
        errors: list[str] = []
        warnings: list[str] = []

        if exp.expected_min_score is not None and score.total < exp.expected_min_score:
            errors.append(
                f"Score {score.total} below expected minimum {exp.expected_min_score}"
            )
        if exp.expected_max_score is not None and score.total > exp.expected_max_score:
            errors.append(
                f"Score {score.total} above expected maximum {exp.expected_max_score}"
            )
        if exp.expected_risk is not None and score.risk != exp.expected_risk:
            errors.append(
                f"Risk {score.risk.value} does not match expected {exp.expected_risk.value}"
            )
        if exp.expected_higher_than is not None and score.total <= exp.expected_higher_than:
            errors.append(
                f"Score {score.total} not higher than {exp.expected_higher_than}"
            )
        if exp.expected_lower_than is not None and score.total >= exp.expected_lower_than:
            errors.append(
                f"Score {score.total} not lower than {exp.expected_lower_than}"
            )

        actual_penalty_codes = {p.code for p in score.penalties}
        for expected_code in exp.expected_penalty_codes:
            if expected_code not in actual_penalty_codes:
                errors.append(f"Expected penalty code '{expected_code}' not found")

        actual_warning_codes: set[str] = set()
        for w in score.warnings:
            for penalty in score.penalties:
                if penalty.code in w.casefold():
                    actual_warning_codes.add(penalty.code)
        for expected_code in exp.expected_warning_codes:
            if expected_code not in actual_warning_codes:
                warnings.append(f"Expected warning code '{expected_code}' not found in warnings")

        passed = len(errors) == 0
        expected_risk_str = exp.expected_risk.value if exp.expected_risk else None

        return ScoringCalibrationCaseResult(
            case_id=case.case_id,
            passed=passed,
            score=score.total,
            expected_risk=expected_risk_str,
            actual_risk=score.risk.value,
            warnings=warnings,
            errors=errors,
            metadata={
                "case_description": case.description,
                "case_tags": case.tags,
                "score_max": score.max_score,
                "score_confidence": score.confidence,
                "penalty_codes": sorted(actual_penalty_codes),
            },
        )


def _build_default_scoring_calibration_dataset() -> ScoringCalibrationDataset:
    cases: list[ScoringCalibrationCase] = []

    # === GOOD CANDIDATES ===

    cases.append(
        ScoringCalibrationCase(
            case_id="good-exact-track-clean",
            description="Exact track match with clean file",
            query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Good Track"),
            candidate=SearchCandidate(
                candidate_id="good-1",
                provider="fake",
                artist="Good Artist",
                title="Good Track",
                directory="Good Artist/Good Track",
                files=[CandidateFile(filename="Good Track.flac", extension="flac")],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_min_score=80.0,
                expected_risk=CandidateRisk.LOW,
            ),
            tags=["good", "exact-match", "clean"],
        )
    )

    cases.append(
        ScoringCalibrationCase(
            case_id="good-exact-album-coherent",
            description="Exact album match with multiple coherent tracks",
            query=SearchQuery(kind=SearchKind.ALBUM, artist="Good Artist", album="Good Album"),
            candidate=SearchCandidate(
                candidate_id="good-2",
                provider="fake",
                artist="Good Artist",
                album="Good Album",
                directory="Good Artist/Good Album",
                files=[
                    CandidateFile(filename="01 Track A.flac", extension="flac"),
                    CandidateFile(filename="02 Track B.flac", extension="flac"),
                    CandidateFile(filename="03 Track C.flac", extension="flac"),
                ],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_min_score=80.0,
                expected_risk=CandidateRisk.LOW,
            ),
            tags=["good", "album", "coherent"],
        )
    )

    cases.append(
        ScoringCalibrationCase(
            case_id="good-no-raw-score",
            description="Good candidate without raw_score still scores normally",
            query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Good Track"),
            candidate=SearchCandidate(
                candidate_id="good-3",
                provider="fake",
                artist="Good Artist",
                title="Good Track",
                directory="Good Artist/Good Track",
                files=[CandidateFile(filename="Good Track.flac", extension="flac")],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_min_score=80.0,
                expected_risk=CandidateRisk.LOW,
            ),
            tags=["good", "no-raw-score"],
        )
    )

    cases.append(
        ScoringCalibrationCase(
            case_id="good-simple-filename",
            description="Candidate with simple but coherent filename",
            query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Good Track"),
            candidate=SearchCandidate(
                candidate_id="good-4",
                provider="fake",
                artist="Good Artist",
                title="Good Track",
                directory="Good Artist",
                files=[CandidateFile(filename="Good Track.flac", extension="flac")],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_min_score=70.0,
                expected_risk=CandidateRisk.LOW,
            ),
            tags=["good", "simple-filename"],
        )
    )

    cases.append(
        ScoringCalibrationCase(
            case_id="good-common-bitrate-ext",
            description="Candidate with common declared bitrate and extension",
            query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Good Track"),
            candidate=SearchCandidate(
                candidate_id="good-5",
                provider="fake",
                artist="Good Artist",
                title="Good Track",
                directory="Good Artist/Good Track",
                files=[CandidateFile(filename="Good Track.flac", extension="flac", declared_bitrate=320)],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_min_score=80.0,
                expected_risk=CandidateRisk.LOW,
            ),
            tags=["good", "bitrate", "extension"],
        )
    )

    # === SUSPICIOUS BUT NOT AUTO-BAD ===

    cases.append(
        ScoringCalibrationCase(
            case_id="suspicious-live",
            description="Filename with live term",
            query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Good Track"),
            candidate=SearchCandidate(
                candidate_id="susp-1",
                provider="fake",
                artist="Good Artist",
                title="Good Track",
                directory="Good Artist/Live at Venue",
                files=[CandidateFile(filename="Good Track - Live.flac", extension="flac")],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_penalty_codes=["suspicious-term"],
            ),
            tags=["suspicious", "live"],
        )
    )

    cases.append(
        ScoringCalibrationCase(
            case_id="suspicious-remix",
            description="Filename with remix term",
            query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Good Track"),
            candidate=SearchCandidate(
                candidate_id="susp-2",
                provider="fake",
                artist="Good Artist",
                title="Good Track",
                directory="Good Artist/Good Track Remix",
                files=[CandidateFile(filename="Good Track (Remix).flac", extension="flac")],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_penalty_codes=["suspicious-term"],
            ),
            tags=["suspicious", "remix"],
        )
    )

    cases.append(
        ScoringCalibrationCase(
            case_id="suspicious-radio-edit",
            description="Filename with radio edit term",
            query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Good Track"),
            candidate=SearchCandidate(
                candidate_id="susp-3",
                provider="fake",
                artist="Good Artist",
                title="Good Track",
                directory="Good Artist/Good Track Radio Edit",
                files=[CandidateFile(filename="Good Track (Radio Edit).flac", extension="flac")],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_penalty_codes=["suspicious-term"],
            ),
            tags=["suspicious", "radio-edit"],
        )
    )

    cases.append(
        ScoringCalibrationCase(
            case_id="suspicious-youtube",
            description="Filename with youtube term",
            query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Good Track"),
            candidate=SearchCandidate(
                candidate_id="susp-4",
                provider="fake",
                artist="Good Artist",
                title="Good Track",
                directory="Good Artist/Good Track youtube",
                files=[CandidateFile(filename="Good Track youtube.flac", extension="flac")],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_risk=CandidateRisk.MEDIUM,
                expected_penalty_codes=["suspicious-term"],
            ),
            tags=["suspicious", "youtube"],
        )
    )

    cases.append(
        ScoringCalibrationCase(
            case_id="suspicious-web-rip",
            description="Filename with web rip term",
            query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Good Track"),
            candidate=SearchCandidate(
                candidate_id="susp-5",
                provider="fake",
                artist="Good Artist",
                title="Good Track",
                directory="Good Artist/Good Track web rip",
                files=[CandidateFile(filename="Good Track web rip.flac", extension="flac")],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_risk=CandidateRisk.MEDIUM,
                expected_penalty_codes=["suspicious-term"],
            ),
            tags=["suspicious", "web-rip"],
        )
    )

    cases.append(
        ScoringCalibrationCase(
            case_id="suspicious-reencode",
            description="Filename with reencode term",
            query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Good Track"),
            candidate=SearchCandidate(
                candidate_id="susp-6",
                provider="fake",
                artist="Good Artist",
                title="Good Track",
                directory="Good Artist/Good Track reencode",
                files=[CandidateFile(filename="Good Track reencode.flac", extension="flac")],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_risk=CandidateRisk.MEDIUM,
                expected_penalty_codes=["suspicious-term"],
            ),
            tags=["suspicious", "reencode"],
        )
    )

    cases.append(
        ScoringCalibrationCase(
            case_id="suspicious-low-quality",
            description="Filename with low quality term",
            query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Good Track"),
            candidate=SearchCandidate(
                candidate_id="susp-7",
                provider="fake",
                artist="Good Artist",
                title="Good Track",
                directory="Good Artist/Good Track low quality",
                files=[CandidateFile(filename="Good Track low quality.flac", extension="flac")],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_risk=CandidateRisk.MEDIUM,
                expected_penalty_codes=["suspicious-term"],
            ),
            tags=["suspicious", "low-quality"],
        )
    )

    cases.append(
        ScoringCalibrationCase(
            case_id="suspicious-locked-file",
            description="Candidate with locked file",
            query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Good Track"),
            candidate=SearchCandidate(
                candidate_id="susp-8",
                provider="fake",
                artist="Good Artist",
                title="Good Track",
                directory="Good Artist/Good Track",
                files=[CandidateFile(filename="Good Track.flac", extension="flac", locked=True)],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_penalty_codes=["locked-files"],
            ),
            tags=["suspicious", "locked"],
        )
    )

    cases.append(
        ScoringCalibrationCase(
            case_id="suspicious-strange-track-count",
            description="Album with strange track count",
            query=SearchQuery(kind=SearchKind.ALBUM, artist="Good Artist", album="Good Album"),
            candidate=SearchCandidate(
                candidate_id="susp-9",
                provider="fake",
                artist="Good Artist",
                album="Good Album",
                directory="Good Artist/Good Album",
                files=[
                    CandidateFile(filename="01 Track.flac", extension="flac"),
                ],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_min_score=50.0,
            ),
            tags=["suspicious", "strange-track-count"],
        )
    )

    cases.append(
        ScoringCalibrationCase(
            case_id="suspicious-partially-inconsistent-folder",
            description="Partially inconsistent folder",
            query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Good Track"),
            candidate=SearchCandidate(
                candidate_id="susp-10",
                provider="fake",
                artist="Good Artist",
                title="Good Track",
                directory="Some Other Artist/Some Other Album",
                files=[CandidateFile(filename="Good Track.flac", extension="flac")],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_penalty_codes=["folder-inconsistent"],
            ),
            tags=["suspicious", "inconsistent-folder"],
        )
    )

    # === CLEARLY BAD ===

    cases.append(
        ScoringCalibrationCase(
            case_id="bad-divergent-artist",
            description="Divergent artist",
            query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Good Track"),
            candidate=SearchCandidate(
                candidate_id="bad-1",
                provider="fake",
                artist="Wrong Artist",
                title="Good Track",
                directory="Wrong Artist/Good Track",
                files=[CandidateFile(filename="Good Track.flac", extension="flac")],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_lower_than=70.0,
                expected_penalty_codes=["artist-mismatch"],
            ),
            tags=["bad", "divergent-artist"],
        )
    )

    cases.append(
        ScoringCalibrationCase(
            case_id="bad-divergent-title",
            description="Divergent title",
            query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Good Track"),
            candidate=SearchCandidate(
                candidate_id="bad-2",
                provider="fake",
                artist="Good Artist",
                title="Wrong Title",
                directory="Good Artist/Wrong Title",
                files=[CandidateFile(filename="Wrong Title.flac", extension="flac")],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_lower_than=70.0,
                expected_penalty_codes=["title-album-mismatch"],
            ),
            tags=["bad", "divergent-title"],
        )
    )

    cases.append(
        ScoringCalibrationCase(
            case_id="bad-divergent-album",
            description="Divergent album for album query",
            query=SearchQuery(kind=SearchKind.ALBUM, artist="Good Artist", album="Good Album"),
            candidate=SearchCandidate(
                candidate_id="bad-3",
                provider="fake",
                artist="Good Artist",
                album="Wrong Album",
                directory="Good Artist/Wrong Album",
                files=[CandidateFile(filename="Track.flac", extension="flac")],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_lower_than=70.0,
                expected_penalty_codes=["title-album-mismatch"],
            ),
            tags=["bad", "divergent-album"],
        )
    )

    cases.append(
        ScoringCalibrationCase(
            case_id="bad-no-files",
            description="Candidate without files",
            query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Good Track"),
            candidate=SearchCandidate(
                candidate_id="bad-4",
                provider="fake",
                artist="Good Artist",
                title="Good Track",
                files=[],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_risk=CandidateRisk.HIGH,
                expected_penalty_codes=["no-files"],
            ),
            tags=["bad", "no-files"],
        )
    )

    cases.append(
        ScoringCalibrationCase(
            case_id="bad-all-locked",
            description="All files locked is worse than partially available",
            query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Good Track"),
            candidate=SearchCandidate(
                candidate_id="bad-5",
                provider="fake",
                artist="Good Artist",
                title="Good Track",
                directory="Good Artist/Good Track",
                files=[
                    CandidateFile(filename="Track A.flac", extension="flac", locked=True),
                    CandidateFile(filename="Track B.flac", extension="flac", locked=True),
                ],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_penalty_codes=["locked-files"],
            ),
            tags=["bad", "all-locked"],
        )
    )

    cases.append(
        ScoringCalibrationCase(
            case_id="bad-distant-name",
            description="Name very distant from query",
            query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Good Track"),
            candidate=SearchCandidate(
                candidate_id="bad-6",
                provider="fake",
                artist="Totally Different Artist",
                title="Completely Different Song",
                directory="Totally Different Artist/Completely Different Song",
                files=[CandidateFile(filename="Completely Different Song.flac", extension="flac")],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_lower_than=40.0,
                expected_penalty_codes=["artist-mismatch", "title-album-mismatch", "textual-weak"],
            ),
            tags=["bad", "distant-name"],
        )
    )

    # === FALSE POSITIVE GUARDS ===

    cases.append(
        ScoringCalibrationCase(
            case_id="fp-alive-not-live",
            description="Alive must not be detected as live",
            query=SearchQuery(kind=SearchKind.TRACK, artist="Pearl Jam", title="Alive"),
            candidate=SearchCandidate(
                candidate_id="fp-1",
                provider="fake",
                artist="Pearl Jam",
                title="Alive",
                directory="Pearl Jam/Alive",
                files=[CandidateFile(filename="Alive.flac", extension="flac")],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_min_score=80.0,
                expected_risk=CandidateRisk.LOW,
            ),
            tags=["false-positive", "alive"],
        )
    )

    cases.append(
        ScoringCalibrationCase(
            case_id="fp-olive-not-live",
            description="Olive must not be detected as live",
            query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Olive"),
            candidate=SearchCandidate(
                candidate_id="fp-2",
                provider="fake",
                artist="Good Artist",
                title="Olive",
                directory="Good Artist/Olive",
                files=[CandidateFile(filename="Olive.flac", extension="flac")],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_min_score=80.0,
                expected_risk=CandidateRisk.LOW,
            ),
            tags=["false-positive", "olive"],
        )
    )

    cases.append(
        ScoringCalibrationCase(
            case_id="fp-premix-not-remix",
            description="Premix must not be detected as remix",
            query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Premix Track"),
            candidate=SearchCandidate(
                candidate_id="fp-3",
                provider="fake",
                artist="Good Artist",
                title="Premix Track",
                directory="Good Artist/Premix Track",
                files=[CandidateFile(filename="Premix Track.flac", extension="flac")],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_min_score=80.0,
                expected_risk=CandidateRisk.LOW,
            ),
            tags=["false-positive", "premix"],
        )
    )

    cases.append(
        ScoringCalibrationCase(
            case_id="fp-delivery-not-live",
            description="Delivery must not be detected as live",
            query=SearchQuery(kind=SearchKind.TRACK, artist="Good Artist", title="Delivery"),
            candidate=SearchCandidate(
                candidate_id="fp-4",
                provider="fake",
                artist="Good Artist",
                title="Delivery",
                directory="Good Artist/Delivery",
                files=[CandidateFile(filename="Delivery.flac", extension="flac")],
            ),
            expectation=ScoringCalibrationExpectation(
                expected_min_score=80.0,
                expected_risk=CandidateRisk.LOW,
            ),
            tags=["false-positive", "delivery"],
        )
    )

    return ScoringCalibrationDataset(
        dataset_id="default-scoring-calibration-v1",
        version="1",
        description="Default scoring calibration dataset with good, suspicious, bad, and false-positive cases.",
        cases=cases,
        metadata={
            "network": False,
            "downloads": False,
            "library_writes": False,
            "fake_only": True,
        },
    )
