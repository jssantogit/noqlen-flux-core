from __future__ import annotations

from typing import Any

from noqlen_flux.quality import (
    DEFAULT_QUALITY_PROFILE,
    QualityFinding,
    QualityFindingKind,
    QualityFindingSeverity,
    QualityGrade,
    QualityProfile,
    QualityResult,
    QualitySummary,
)
from noqlen_flux.results import Artifact, FluxError, FluxResult, FluxWarning, Severity, Status
from noqlen_flux.services.base import FluxService


class QualityService(FluxService):
    operation = "quality"

    def evaluate_fake_quality(
        self,
        item_id: str,
        relative_path: str | None = None,
        grade: str | QualityGrade | None = None,
        findings: list[dict[str, Any]] | None = None,
        profile: QualityProfile | None = None,
    ) -> FluxResult:
        warnings: list[FluxWarning] = []
        errors: list[FluxError] = []

        selected_profile = profile or DEFAULT_QUALITY_PROFILE
        selected_grade = QualityGrade(grade) if grade else QualityGrade.UNKNOWN

        parsed_findings = [
            QualityFinding(
                code=f.get("code", "unknown"),
                message=f.get("message", ""),
                kind=f.get("kind", QualityFindingKind.UNKNOWN),
                severity=f.get("severity", QualityFindingSeverity.INFO),
                confidence=f.get("confidence"),
                metadata=f.get("metadata", {}),
            )
            for f in (findings or [])
        ]

        if selected_grade == QualityGrade.BAD and not parsed_findings:
            parsed_findings.append(
                QualityFinding(
                    code="simulated-failure",
                    message="Simulated objective failure for bad grade.",
                    kind=QualityFindingKind.OBJECTIVE_FAILURE,
                    severity=QualityFindingSeverity.ERROR,
                )
            )

        objective_failures = [f for f in parsed_findings if f.kind == QualityFindingKind.OBJECTIVE_FAILURE]
        heuristic_warnings_list = [f for f in parsed_findings if f.kind == QualityFindingKind.HEURISTIC_WARNING]
        diagnostics = [f for f in parsed_findings if f.kind == QualityFindingKind.DIAGNOSTIC]

        confidence = _compute_confidence(selected_grade, objective_failures, heuristic_warnings_list)

        result = QualityResult(
            item_id=item_id,
            relative_path=relative_path,
            grade=selected_grade,
            findings=parsed_findings,
            objective_failures=objective_failures,
            heuristic_warnings=heuristic_warnings_list,
            diagnostics=diagnostics,
            confidence=confidence,
            profile=selected_profile,
            warnings=[f.message for f in heuristic_warnings_list],
            errors=[f.message for f in objective_failures],
            metadata={"stage": "post-download", "analysis": "fake"},
        )

        artifact = Artifact(
            kind="quality-result",
            description="Logical post-download quality analysis result (fake/contracts-only)",
            metadata={"item_id": item_id, "grade": result.grade.value, "confidence": result.confidence},
        )

        if objective_failures:
            step_status = Status.WARNING
            step_message = f"Quality evaluation for {item_id}: {selected_grade.value} with {len(objective_failures)} objective failure(s)"
            warnings.append(
                self.warning(
                    "objective-failure-detected",
                    f"{len(objective_failures)} objective failure(s) found.",
                    severity=Severity.WARNING,
                    item_id=item_id,
                )
            )
        elif heuristic_warnings_list:
            step_status = Status.WARNING
            step_message = f"Quality evaluation for {item_id}: {selected_grade.value} with {len(heuristic_warnings_list)} heuristic warning(s)"
            warnings.append(
                self.warning(
                    "heuristic-warning-detected",
                    f"{len(heuristic_warnings_list)} heuristic warning(s) found.",
                    severity=Severity.WARNING,
                    item_id=item_id,
                )
            )
        else:
            step_status = Status.SUCCESS
            step_message = f"Quality evaluation for {item_id}: {selected_grade.value}"

        step = self.step(
            "evaluate-quality",
            step_status,
            step_message,
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
                "item_id": item_id,
                "grade": result.grade.value,
                "confidence": result.confidence,
                "finding_count": len(parsed_findings),
                "objective_failure_count": len(objective_failures),
                "heuristic_warning_count": len(heuristic_warnings_list),
                "diagnostic_count": len(diagnostics),
                "profile": selected_profile.to_dict(),
                "quality_result": result.to_dict(),
            },
        ).finish()

    def summarize_quality(self, results: list[QualityResult]) -> FluxResult:
        summary = QualitySummary(
            total_items=len(results),
            excellent_count=sum(1 for r in results if r.grade == QualityGrade.EXCELLENT),
            medium_count=sum(1 for r in results if r.grade == QualityGrade.MEDIUM),
            bad_count=sum(1 for r in results if r.grade == QualityGrade.BAD),
            unknown_count=sum(1 for r in results if r.grade == QualityGrade.UNKNOWN),
            warning_count=sum(len(r.heuristic_warnings) for r in results),
            error_count=sum(len(r.objective_failures) for r in results),
        )

        artifact = Artifact(
            kind="quality-summary",
            description="Logical post-download quality summary (fake/contracts-only)",
            metadata={"total_items": summary.total_items},
        )

        step_status = Status.WARNING if (summary.warning_count > 0 or summary.error_count > 0) else Status.SUCCESS
        step_message = f"Quality summary: {summary.total_items} item(s) evaluated"

        step = self.step(
            "summarize-quality",
            step_status,
            step_message,
            artifacts=[artifact],
        )

        return FluxResult(
            operation=self.operation,
            status=step_status,
            steps=[step],
            artifacts=[artifact],
            summary={
                "total_items": summary.total_items,
                "excellent_count": summary.excellent_count,
                "medium_count": summary.medium_count,
                "bad_count": summary.bad_count,
                "unknown_count": summary.unknown_count,
                "warning_count": summary.warning_count,
                "error_count": summary.error_count,
                "quality_summary": summary.to_dict(),
            },
        ).finish()


def _compute_confidence(
    grade: QualityGrade,
    objective_failures: list[QualityFinding],
    heuristic_warnings: list[QualityFinding],
) -> float:
    if grade == QualityGrade.EXCELLENT and not objective_failures:
        return 0.95
    if grade == QualityGrade.MEDIUM and not objective_failures:
        return 0.7
    if grade == QualityGrade.BAD and objective_failures:
        return 0.85
    if grade == QualityGrade.UNKNOWN:
        return 0.1
    if objective_failures:
        return max(0.3, 1.0 - len(objective_failures) * 0.2)
    if heuristic_warnings:
        return max(0.5, 1.0 - len(heuristic_warnings) * 0.1)
    return 0.5
