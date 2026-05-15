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
from noqlen_flux.results import Artifact, FluxError, FluxResult, FluxWarning, PlannedChange, Severity, Status
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

    def probe_to_quality_result(
        self,
        probe_result: Any,
        *,
        item_id: str | None = None,
        relative_path: str | None = None,
        profile: QualityProfile | None = None,
    ) -> QualityResult:
        item = item_id or getattr(probe_result, "item_id", "unknown")
        path = relative_path or getattr(probe_result, "relative_path", None)

        findings: list[QualityFinding] = []
        objective_failures: list[QualityFinding] = []
        heuristic_warnings: list[QualityFinding] = []
        diagnostics: list[QualityFinding] = []

        probe_findings = getattr(probe_result, "findings", [])
        for pf in probe_findings:
            category = getattr(pf, "category", "diagnostic")
            kind_map = {
                "objective_failure": QualityFindingKind.OBJECTIVE_FAILURE,
                "heuristic_warning": QualityFindingKind.HEURISTIC_WARNING,
                "diagnostic": QualityFindingKind.DIAGNOSTIC,
            }
            kind = kind_map.get(category, QualityFindingKind.UNKNOWN)
            severity = (
                QualityFindingSeverity.ERROR
                if kind == QualityFindingKind.OBJECTIVE_FAILURE
                else QualityFindingSeverity.WARNING
                if kind == QualityFindingKind.HEURISTIC_WARNING
                else QualityFindingSeverity.INFO
            )

            qf = QualityFinding(
                code=getattr(pf, "code", "unknown"),
                message=getattr(pf, "message", ""),
                kind=kind,
                severity=severity,
                confidence=getattr(pf, "confidence", None),
            )

            findings.append(qf)
            if kind == QualityFindingKind.OBJECTIVE_FAILURE:
                objective_failures.append(qf)
            elif kind == QualityFindingKind.HEURISTIC_WARNING:
                heuristic_warnings.append(qf)
            elif kind == QualityFindingKind.DIAGNOSTIC:
                diagnostics.append(qf)

        has_audio = getattr(probe_result, "has_audio_stream", True)
        decode_ok = getattr(probe_result, "decode_ok", True)
        probe_success = getattr(probe_result, "success", True)

        if objective_failures:
            grade = QualityGrade.BAD
        elif heuristic_warnings:
            grade = QualityGrade.MEDIUM
        elif not probe_success and not objective_failures:
            grade = QualityGrade.UNKNOWN
        elif not has_audio or not decode_ok:
            grade = QualityGrade.BAD
        else:
            grade = QualityGrade.EXCELLENT

        confidence = _compute_quality_confidence(grade, objective_failures, heuristic_warnings, findings)

        warnings_list = [
            f"{qf.code}: {qf.message}"
            for qf in heuristic_warnings
        ]
        errors_list = [
            f"{qf.code}: {qf.message}"
            for qf in objective_failures
        ]

        selected_profile = profile or DEFAULT_QUALITY_PROFILE

        return QualityResult(
            item_id=item,
            relative_path=path,
            grade=grade,
            findings=findings,
            objective_failures=objective_failures,
            heuristic_warnings=heuristic_warnings,
            diagnostics=diagnostics,
            confidence=confidence,
            profile=selected_profile,
            warnings=warnings_list,
            errors=errors_list,
            metadata={
                "stage": "post-download",
                "analysis": "real-probe",
                "probe_success": probe_success,
                "has_audio_stream": has_audio,
                "decode_ok": decode_ok,
            },
        )

    def inspect_file(
        self,
        item_id: str,
        relative_path: str,
        workspace_root: str,
        *,
        backend: Any | None = None,
        dry_run: bool = True,
    ) -> FluxResult:
        from noqlen_flux.audio_probe import AudioProbeRequest
        from noqlen_flux.services.audio_probe import AudioProbeService, FakeProbeBackend

        effective_backend = backend or FakeProbeBackend()
        probe_service = AudioProbeService()

        try:
            request = AudioProbeRequest(
                request_id=f"quality-inspect-{item_id}",
                item_id=item_id,
                relative_path=relative_path,
                workspace_root=workspace_root,
            )
        except ValueError as exc:
            return FluxResult(
                operation=self.operation,
                status=Status.FAILED,
                errors=[self.error("unsafe-quality-path", str(exc))],
                summary={"error": str(exc), "relative_path": relative_path},
            ).finish()

        probe_result = probe_service.probe(request, effective_backend, dry_run=dry_run)

        if probe_result.status == Status.FAILED:
            return probe_result

        if dry_run:
            planned = PlannedChange(
                action="quality-inspect",
                target=relative_path,
                reason=f"Dry-run quality inspection for {item_id}",
                metadata={"item_id": item_id, "relative_path": relative_path},
            )
            artifact = Artifact(
                kind="quality-inspection-plan",
                description=f"Planned quality inspection for {item_id}",
                metadata={"item_id": item_id, "relative_path": relative_path},
            )
            step = self.step(
                "quality-inspect-dry-run",
                Status.SUCCESS,
                f"Would inspect {relative_path} for quality",
                artifacts=[artifact],
            )
            return FluxResult(
                operation=self.operation,
                status=Status.SUCCESS,
                steps=[step],
                artifacts=[artifact],
                planned_changes=[planned],
                summary={
                    "item_id": item_id,
                    "relative_path": relative_path,
                    "dry_run": True,
                },
            ).finish()

        probe_data = probe_result.summary.get("probe_result", {})
        if not probe_data:
            return self.result(Status.FAILED, error="No probe result available")

        from noqlen_flux.audio_probe import AudioProbeFinding as ProbeFindingModel, AudioProbeResult as ProbeResultModel
        raw_findings = probe_data.get("findings", [])
        reconstructed_findings = [
            ProbeFindingModel(
                code=f.get("code", "unknown"),
                message=f.get("message", ""),
                category=f.get("category", "diagnostic"),
                confidence=f.get("confidence", 1.0),
                metadata=f.get("metadata", {}),
            )
            for f in raw_findings
        ]
        probe_model = ProbeResultModel(
            request_id=probe_data.get("request_id", ""),
            item_id=probe_data.get("item_id", item_id),
            relative_path=probe_data.get("relative_path", relative_path),
            backend=probe_data.get("backend", "unknown"),
            success=probe_data.get("success", False),
            duration_seconds=probe_data.get("duration_seconds"),
            sample_rate=probe_data.get("sample_rate"),
            codec=probe_data.get("codec"),
            decode_ok=probe_data.get("decode_ok", False),
            has_audio_stream=probe_data.get("has_audio_stream", False),
            stream_count=probe_data.get("stream_count", 0),
            audio_stream_count=probe_data.get("audio_stream_count", 0),
            warnings=list(probe_data.get("warnings", [])),
            errors=list(probe_data.get("errors", [])),
            findings=reconstructed_findings,
        )

        quality_result = self.probe_to_quality_result(
            probe_model, item_id=item_id, relative_path=relative_path,
        )

        artifact = Artifact(
            kind="quality-inspection-result",
            description=f"Quality inspection result for {item_id}: {quality_result.grade.value}",
            metadata={
                "item_id": item_id,
                "grade": quality_result.grade.value,
                "confidence": quality_result.confidence,
                "objective_failure_count": len(quality_result.objective_failures),
                "heuristic_warning_count": len(quality_result.heuristic_warnings),
                "quality_result": quality_result.to_dict(),
            },
        )

        status = (
            Status.WARNING if quality_result.grade in (QualityGrade.BAD, QualityGrade.MEDIUM, QualityGrade.UNKNOWN)
            else Status.SUCCESS
        )

        step = self.step(
            "quality-inspect-apply",
            status,
            f"Quality inspection: {item_id} -> {quality_result.grade.value} (confidence={quality_result.confidence:.2f})",
            artifacts=[artifact],
        )

        return FluxResult(
            operation=self.operation,
            status=status,
            steps=[step],
            artifacts=[artifact],
            summary={
                "item_id": item_id,
                "grade": quality_result.grade.value,
                "confidence": quality_result.confidence,
                "objective_failure_count": len(quality_result.objective_failures),
                "heuristic_warning_count": len(quality_result.heuristic_warnings),
                "quality_result": quality_result.to_dict(),
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


def _compute_quality_confidence(
    grade: QualityGrade,
    objective_failures: list[QualityFinding],
    heuristic_warnings: list[QualityFinding],
    all_findings: list[QualityFinding],
) -> float:
    if grade == QualityGrade.EXCELLENT:
        return 0.95
    if grade == QualityGrade.BAD and objective_failures:
        return max(0.7, 1.0 - len(objective_failures) * 0.15)
    if grade == QualityGrade.MEDIUM:
        return max(0.45, 0.75 - len(heuristic_warnings) * 0.1)
    if grade == QualityGrade.UNKNOWN:
        return 0.15
    if objective_failures:
        return max(0.3, 1.0 - len(objective_failures) * 0.2)
    if heuristic_warnings:
        return max(0.4, 1.0 - len(heuristic_warnings) * 0.1)
    return 0.5
