from __future__ import annotations

from typing import Any

from noqlen_flux.musiclab_quality import (
    QualityCalibrationCase,
    QualityCalibrationCaseResult,
    QualityCalibrationDataset,
    QualityCalibrationExpectation,
    QualityCalibrationReport,
)
from noqlen_flux.quality import (
    DEFAULT_QUALITY_PROFILE,
    QualityFindingKind,
    QualityFindingSeverity,
    QualityGrade,
    QualityProfile,
)
from noqlen_flux.results import Artifact, FluxResult, Status
from noqlen_flux.services.base import FluxService
from noqlen_flux.services.quality import QualityService


class MusicLabQualityService(FluxService):
    operation = "musiclab-quality"

    def build_default_dataset(self) -> QualityCalibrationDataset:
        return _build_default_quality_calibration_dataset()

    def run_calibration(
        self,
        dataset: QualityCalibrationDataset | None = None,
        quality_service: QualityService | None = None,
        profile: QualityProfile | None = None,
    ) -> FluxResult:
        result = self.result(
            Status.SUCCESS,
            dry_run=True,
            action="quality-calibration",
        )
        ds = dataset or self.build_default_dataset()
        evaluator = quality_service or QualityService()
        selected_profile = profile or DEFAULT_QUALITY_PROFILE

        case_results: list[QualityCalibrationCaseResult] = []
        passed_count = 0
        failed_count = 0
        report_warnings: list[str] = []
        report_errors: list[str] = []

        for case in ds.cases:
            case_result = self._evaluate_case(case, evaluator, selected_profile)
            case_results.append(case_result)
            if case_result.passed:
                passed_count += 1
            else:
                failed_count += 1
            report_warnings.extend(case_result.warnings)
            report_errors.extend(case_result.errors)

        report = QualityCalibrationReport(
            dataset_id=ds.dataset_id,
            profile_name=selected_profile.name,
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
                "audio_analysis": False,
                "ffmpeg": False,
                "routing_decisions": False,
            },
        )

        result.artifacts.append(
            Artifact(
                kind="quality-calibration-report",
                description="Logical quality calibration report",
                metadata={"report": report.to_dict()},
            )
        )

        status = Status.SUCCESS if failed_count == 0 else Status.WARNING
        result.summary.update(
            {
                "dataset_id": ds.dataset_id,
                "dataset_version": ds.version,
                "profile_name": selected_profile.name,
                "total_cases": len(ds.cases),
                "passed_cases": passed_count,
                "failed_cases": failed_count,
                "failed_case_ids": [cr.case_id for cr in case_results if not cr.passed],
                "network": False,
                "downloads": False,
                "library_writes": False,
                "audio_analysis": False,
                "ffmpeg": False,
                "routing_decisions": False,
            }
        )
        result.steps.append(
            self.step(
                "quality-calibration",
                status,
                f"Calibration complete: {passed_count}/{len(ds.cases)} passed with profile {selected_profile.name}",
            )
        )
        return result.finish(status)

    def _evaluate_case(
        self,
        case: QualityCalibrationCase,
        evaluator: QualityService,
        profile: QualityProfile,
    ) -> QualityCalibrationCaseResult:
        exp = case.expectation
        eval_result = evaluator.evaluate_fake_quality(
            item_id=case.item_id,
            relative_path=case.relative_path,
            grade=exp.expected_grade,
            findings=case.findings,
            profile=profile,
        )

        actual_grade = eval_result.summary.get("grade")
        actual_confidence = eval_result.summary.get("confidence")
        errors: list[str] = []
        warnings: list[str] = []

        if exp.expected_grade is not None and actual_grade != exp.expected_grade:
            errors.append(
                f"Grade '{actual_grade}' does not match expected '{exp.expected_grade}'"
            )

        if exp.expected_min_confidence is not None and actual_confidence is not None:
            if actual_confidence < exp.expected_min_confidence:
                errors.append(
                    f"Confidence {actual_confidence} below expected minimum {exp.expected_min_confidence}"
                )

        actual_finding_codes = {f.get("code") for f in case.findings}
        for expected_code in exp.expected_finding_codes:
            if expected_code not in actual_finding_codes:
                errors.append(f"Expected finding code '{expected_code}' not found")

        actual_objective_codes = {
            f.get("code")
            for f in case.findings
            if f.get("kind") == QualityFindingKind.OBJECTIVE_FAILURE.value
        }
        for expected_code in exp.expected_objective_failure_codes:
            if expected_code not in actual_objective_codes:
                errors.append(f"Expected objective failure code '{expected_code}' not found")

        actual_heuristic_codes = {
            f.get("code")
            for f in case.findings
            if f.get("kind") == QualityFindingKind.HEURISTIC_WARNING.value
        }
        for expected_code in exp.expected_heuristic_warning_codes:
            if expected_code not in actual_heuristic_codes:
                warnings.append(f"Expected heuristic warning code '{expected_code}' not found")

        if exp.expected_no_routing_decision:
            summary_keys = set(eval_result.summary.keys())
            routing_keys = {"routing_decision", "routing_outcome", "routing_plan"}
            if summary_keys & routing_keys:
                errors.append("Unexpected routing decision found in quality result")

        objective_failures_in_result = eval_result.summary.get("objective_failure_count", 0)
        heuristic_warnings_in_result = eval_result.summary.get("heuristic_warning_count", 0)

        passed = len(errors) == 0

        return QualityCalibrationCaseResult(
            case_id=case.case_id,
            passed=passed,
            expected_grade=exp.expected_grade,
            actual_grade=actual_grade,
            expected_confidence=exp.expected_min_confidence,
            actual_confidence=actual_confidence,
            warnings=warnings,
            errors=errors,
            metadata={
                "case_description": case.description,
                "case_tags": case.tags,
                "finding_count": eval_result.summary.get("finding_count", 0),
                "objective_failure_count": objective_failures_in_result,
                "heuristic_warning_count": heuristic_warnings_in_result,
                "diagnostic_count": eval_result.summary.get("diagnostic_count", 0),
            },
        )


def _build_default_quality_calibration_dataset() -> QualityCalibrationDataset:
    cases: list[QualityCalibrationCase] = []

    # === EXCELLENT ===

    cases.append(
        QualityCalibrationCase(
            case_id="excellent-clean-flac",
            description="Conceptual clean FLAC file with no findings",
            item_id="excellent-1",
            relative_path="incoming/artist/album/track.flac",
            findings=[],
            expectation=QualityCalibrationExpectation(
                expected_grade=QualityGrade.EXCELLENT.value,
                expected_min_confidence=0.8,
            ),
            tags=["excellent", "clean", "no-findings"],
            metadata={"fake": True, "codec": "flac", "bitrate": None, "duration_seconds": 240},
        )
    )

    cases.append(
        QualityCalibrationCase(
            case_id="excellent-high-bitrate",
            description="Conceptual high-bitrate file with plausible metadata",
            item_id="excellent-2",
            relative_path="incoming/artist/album/track.flac",
            findings=[],
            expectation=QualityCalibrationExpectation(
                expected_grade=QualityGrade.EXCELLENT.value,
                expected_min_confidence=0.8,
            ),
            tags=["excellent", "high-bitrate"],
            metadata={"fake": True, "codec": "flac", "bitrate": 900, "duration_seconds": 300},
        )
    )

    # === MEDIUM ===

    cases.append(
        QualityCalibrationCase(
            case_id="medium-incomplete-metadata",
            description="File with incomplete metadata but no objective failure",
            item_id="medium-1",
            relative_path="incoming/artist/album/track.flac",
            findings=[
                {
                    "code": "missing-metadata",
                    "message": "Some metadata fields are missing.",
                    "kind": QualityFindingKind.HEURISTIC_WARNING.value,
                    "severity": QualityFindingSeverity.WARNING.value,
                    "confidence": 0.6,
                }
            ],
            expectation=QualityCalibrationExpectation(
                expected_grade=QualityGrade.MEDIUM.value,
                expected_min_confidence=0.4,
                expected_heuristic_warning_codes=["missing-metadata"],
            ),
            tags=["medium", "incomplete-metadata", "heuristic-warning"],
            metadata={"fake": True, "codec": "flac"},
        )
    )

    cases.append(
        QualityCalibrationCase(
            case_id="medium-clipping-suspicion",
            description="File with clipping suspicion as heuristic warning only",
            item_id="medium-2",
            relative_path="incoming/artist/album/track.flac",
            findings=[
                {
                    "code": "clipping-suspicion",
                    "message": "Possible clipping detected.",
                    "kind": QualityFindingKind.HEURISTIC_WARNING.value,
                    "severity": QualityFindingSeverity.WARNING.value,
                    "confidence": 0.5,
                }
            ],
            expectation=QualityCalibrationExpectation(
                expected_grade=QualityGrade.MEDIUM.value,
                expected_heuristic_warning_codes=["clipping-suspicion"],
            ),
            tags=["medium", "clipping-suspicion", "heuristic-warning"],
            metadata={"fake": True, "codec": "flac"},
        )
    )

    cases.append(
        QualityCalibrationCase(
            case_id="medium-transcode-suspicion",
            description="File with transcode suspicion as heuristic warning, not objective failure",
            item_id="medium-3",
            relative_path="incoming/artist/album/track.flac",
            findings=[
                {
                    "code": "low-pass-suspicion",
                    "message": "Low-pass filter suggests possible transcode.",
                    "kind": QualityFindingKind.HEURISTIC_WARNING.value,
                    "severity": QualityFindingSeverity.WARNING.value,
                    "confidence": 0.55,
                },
                {
                    "code": "loudness-warning",
                    "message": "Loudness level is outside typical range.",
                    "kind": QualityFindingKind.HEURISTIC_WARNING.value,
                    "severity": QualityFindingSeverity.WARNING.value,
                    "confidence": 0.5,
                }
            ],
            expectation=QualityCalibrationExpectation(
                expected_grade=QualityGrade.MEDIUM.value,
                expected_heuristic_warning_codes=["low-pass-suspicion", "loudness-warning"],
            ),
            tags=["medium", "transcode-suspicion", "heuristic-warning"],
            metadata={"fake": True, "codec": "mp3", "declared_bitrate": 320},
        )
    )

    # === BAD OBJECTIVE ===

    cases.append(
        QualityCalibrationCase(
            case_id="bad-decode-failure",
            description="File that fails decode validation",
            item_id="bad-1",
            relative_path="incoming/artist/album/track.flac",
            findings=[
                {
                    "code": "decode-failure",
                    "message": "File fails decode validation.",
                    "kind": QualityFindingKind.OBJECTIVE_FAILURE.value,
                    "severity": QualityFindingSeverity.ERROR.value,
                }
            ],
            expectation=QualityCalibrationExpectation(
                expected_grade=QualityGrade.BAD.value,
                expected_objective_failure_codes=["decode-failure"],
            ),
            tags=["bad", "objective-failure", "decode-failure"],
            metadata={"fake": True},
        )
    )

    cases.append(
        QualityCalibrationCase(
            case_id="bad-no-audio-stream",
            description="File with no audio stream",
            item_id="bad-2",
            relative_path="incoming/artist/album/track.flac",
            findings=[
                {
                    "code": "no-audio-stream",
                    "message": "File contains no audio stream.",
                    "kind": QualityFindingKind.OBJECTIVE_FAILURE.value,
                    "severity": QualityFindingSeverity.ERROR.value,
                }
            ],
            expectation=QualityCalibrationExpectation(
                expected_grade=QualityGrade.BAD.value,
                expected_objective_failure_codes=["no-audio-stream"],
            ),
            tags=["bad", "objective-failure", "no-audio-stream"],
            metadata={"fake": True},
        )
    )

    cases.append(
        QualityCalibrationCase(
            case_id="bad-zero-byte",
            description="Zero-byte file",
            item_id="bad-3",
            relative_path="incoming/artist/album/track.flac",
            findings=[
                {
                    "code": "zero-byte-file",
                    "message": "File is zero bytes.",
                    "kind": QualityFindingKind.OBJECTIVE_FAILURE.value,
                    "severity": QualityFindingSeverity.ERROR.value,
                }
            ],
            expectation=QualityCalibrationExpectation(
                expected_grade=QualityGrade.BAD.value,
                expected_objective_failure_codes=["zero-byte-file"],
            ),
            tags=["bad", "objective-failure", "zero-byte"],
            metadata={"fake": True, "size_bytes": 0},
        )
    )

    cases.append(
        QualityCalibrationCase(
            case_id="bad-invalid-duration",
            description="File with invalid duration",
            item_id="bad-4",
            relative_path="incoming/artist/album/track.flac",
            findings=[
                {
                    "code": "invalid-duration",
                    "message": "File has invalid or zero duration.",
                    "kind": QualityFindingKind.OBJECTIVE_FAILURE.value,
                    "severity": QualityFindingSeverity.ERROR.value,
                }
            ],
            expectation=QualityCalibrationExpectation(
                expected_grade=QualityGrade.BAD.value,
                expected_objective_failure_codes=["invalid-duration"],
            ),
            tags=["bad", "objective-failure", "invalid-duration"],
            metadata={"fake": True, "duration_seconds": 0},
        )
    )

    cases.append(
        QualityCalibrationCase(
            case_id="bad-below-confidence-floor",
            description="File objectively below configured confidence floor",
            item_id="bad-5",
            relative_path="incoming/artist/album/track.flac",
            findings=[
                {
                    "code": "below-confidence-floor",
                    "message": "Quality confidence below configured minimum.",
                    "kind": QualityFindingKind.OBJECTIVE_FAILURE.value,
                    "severity": QualityFindingSeverity.ERROR.value,
                }
            ],
            expectation=QualityCalibrationExpectation(
                expected_grade=QualityGrade.BAD.value,
                expected_objective_failure_codes=["below-confidence-floor"],
            ),
            tags=["bad", "objective-failure", "below-floor"],
            metadata={"fake": True},
        )
    )

    cases.append(
        QualityCalibrationCase(
            case_id="bad-corrupt-file",
            description="Corrupt file that cannot be parsed",
            item_id="bad-6",
            relative_path="incoming/artist/album/track.flac",
            findings=[
                {
                    "code": "corrupt-file",
                    "message": "File is corrupt and cannot be parsed.",
                    "kind": QualityFindingKind.OBJECTIVE_FAILURE.value,
                    "severity": QualityFindingSeverity.ERROR.value,
                }
            ],
            expectation=QualityCalibrationExpectation(
                expected_grade=QualityGrade.BAD.value,
                expected_objective_failure_codes=["corrupt-file"],
            ),
            tags=["bad", "objective-failure", "corrupt"],
            metadata={"fake": True},
        )
    )

    # === BAD SUSPICIOUS / REVIEW-WORTHY ===

    cases.append(
        QualityCalibrationCase(
            case_id="bad-suspicious-strong-low-pass",
            description="Strong low-pass suspicion as heuristic warning, not objective failure",
            item_id="bad-susp-1",
            relative_path="incoming/artist/album/track.flac",
            findings=[
                {
                    "code": "strong-low-pass",
                    "message": "Strong low-pass filter detected; possible transcode.",
                    "kind": QualityFindingKind.HEURISTIC_WARNING.value,
                    "severity": QualityFindingSeverity.WARNING.value,
                    "confidence": 0.7,
                }
            ],
            expectation=QualityCalibrationExpectation(
                expected_grade=QualityGrade.BAD.value,
                expected_heuristic_warning_codes=["strong-low-pass"],
            ),
            tags=["bad-suspicious", "low-pass", "heuristic-warning", "review-worthy"],
            metadata={"fake": True, "codec": "mp3", "declared_bitrate": 320},
        )
    )

    cases.append(
        QualityCalibrationCase(
            case_id="bad-suspicious-source-tag",
            description="Suspicious source tag as heuristic warning",
            item_id="bad-susp-2",
            relative_path="incoming/artist/album/track.flac",
            findings=[
                {
                    "code": "suspicious-source",
                    "message": "Source tag indicates low-quality origin.",
                    "kind": QualityFindingKind.HEURISTIC_WARNING.value,
                    "severity": QualityFindingSeverity.WARNING.value,
                    "confidence": 0.6,
                }
            ],
            expectation=QualityCalibrationExpectation(
                expected_grade=QualityGrade.BAD.value,
                expected_heuristic_warning_codes=["suspicious-source"],
            ),
            tags=["bad-suspicious", "source-tag", "heuristic-warning", "review-worthy"],
            metadata={"fake": True, "source_tag": "web-rip"},
        )
    )

    cases.append(
        QualityCalibrationCase(
            case_id="bad-suspicious-bitrate-mismatch",
            description="Bitrate/size mismatch as heuristic warning",
            item_id="bad-susp-3",
            relative_path="incoming/artist/album/track.flac",
            findings=[
                {
                    "code": "bitrate-size-mismatch",
                    "message": "Declared bitrate does not match file size.",
                    "kind": QualityFindingKind.HEURISTIC_WARNING.value,
                    "severity": QualityFindingSeverity.WARNING.value,
                    "confidence": 0.65,
                }
            ],
            expectation=QualityCalibrationExpectation(
                expected_grade=QualityGrade.BAD.value,
                expected_heuristic_warning_codes=["bitrate-size-mismatch"],
            ),
            tags=["bad-suspicious", "bitrate-mismatch", "heuristic-warning", "review-worthy"],
            metadata={"fake": True, "codec": "mp3", "declared_bitrate": 320, "size_bytes": 1024},
        )
    )

    cases.append(
        QualityCalibrationCase(
            case_id="bad-suspicious-weak-hf-energy",
            description="Weak high-frequency energy as heuristic warning",
            item_id="bad-susp-4",
            relative_path="incoming/artist/album/track.flac",
            findings=[
                {
                    "code": "weak-hf-energy",
                    "message": "Weak high-frequency energy suggests lossy source.",
                    "kind": QualityFindingKind.HEURISTIC_WARNING.value,
                    "severity": QualityFindingSeverity.WARNING.value,
                    "confidence": 0.55,
                }
            ],
            expectation=QualityCalibrationExpectation(
                expected_grade=QualityGrade.BAD.value,
                expected_heuristic_warning_codes=["weak-hf-energy"],
            ),
            tags=["bad-suspicious", "hf-energy", "heuristic-warning", "review-worthy"],
            metadata={"fake": True, "codec": "flac"},
        )
    )

    # === UNKNOWN ===

    cases.append(
        QualityCalibrationCase(
            case_id="unknown-insufficient-data",
            description="Insufficient data to determine quality",
            item_id="unknown-1",
            relative_path=None,
            findings=[],
            expectation=QualityCalibrationExpectation(
                expected_grade=QualityGrade.UNKNOWN.value,
            ),
            tags=["unknown", "insufficient-data"],
            metadata={"fake": True},
        )
    )

    cases.append(
        QualityCalibrationCase(
            case_id="unknown-not-analyzed",
            description="File has not been analyzed",
            item_id="unknown-2",
            relative_path="incoming/artist/album/track.flac",
            findings=[],
            expectation=QualityCalibrationExpectation(
                expected_grade=QualityGrade.UNKNOWN.value,
            ),
            tags=["unknown", "not-analyzed"],
            metadata={"fake": True},
        )
    )

    cases.append(
        QualityCalibrationCase(
            case_id="unknown-low-confidence",
            description="Analysis produced very low confidence",
            item_id="unknown-3",
            relative_path="incoming/artist/album/track.flac",
            findings=[
                {
                    "code": "low-confidence",
                    "message": "Analysis confidence is too low to classify.",
                    "kind": QualityFindingKind.DIAGNOSTIC.value,
                    "severity": QualityFindingSeverity.INFO.value,
                    "confidence": 0.1,
                }
            ],
            expectation=QualityCalibrationExpectation(
                expected_grade=QualityGrade.UNKNOWN.value,
            ),
            tags=["unknown", "low-confidence"],
            metadata={"fake": True},
        )
    )

    return QualityCalibrationDataset(
        dataset_id="default-quality-calibration-v1",
        version="1",
        description="Default quality calibration dataset with excellent, medium, bad objective, bad suspicious, and unknown cases.",
        cases=cases,
        metadata={
            "network": False,
            "downloads": False,
            "library_writes": False,
            "audio_analysis": False,
            "ffmpeg": False,
            "fake_only": True,
        },
    )
