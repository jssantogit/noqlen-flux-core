from __future__ import annotations

from pathlib import Path

from noqlen_flux.config import FluxConfig
from noqlen_flux.reports import ReportFormat, ReportTarget, build_json_report, build_text_report, safe_report_filename
from noqlen_flux.results import AppliedChange, Artifact, FluxResult, FluxWarning, PlannedChange, Status, StepResult
from noqlen_flux.safety import PathSafetyError, safe_workspace_root
from noqlen_flux.services.base import FluxService


class ReportService(FluxService):
    operation = "report"

    def preview_report(self, config: FluxConfig, source: FluxResult, format: ReportFormat | str) -> FluxResult:
        report_format = ReportFormat(format)
        filename = safe_report_filename(source.operation, "preview", format=report_format)
        result = self.result(Status.SUCCESS, workspace_root=str(config.workspace_root), dry_run=True, format=report_format.value)
        target = self._target(config, filename, report_format, result)
        if target is None:
            return result.finish(Status.FAILED)
        content = self._render(source, report_format)
        result.planned_changes.append(PlannedChange("write-report", str(target.path), "Preview report artifact"))
        result.artifacts.append(
            Artifact(
                "report",
                "Planned report artifact",
                path=target.path,
                metadata={"format": report_format.value, "bytes": len(content.encode("utf-8")), "planned": True},
            )
        )
        result.steps.append(self.step("report-preview", Status.SUCCESS, f"Would write report: {target.filename}"))
        result.summary.update({"report_path": str(target.path), "planned_changes": 1, "applied_changes": 0})
        return result.finish(Status.SUCCESS)

    def write_report(
        self,
        config: FluxConfig,
        source: FluxResult,
        format: ReportFormat | str,
        filename: str | None = None,
    ) -> FluxResult:
        report_format = ReportFormat(format)
        report_filename = filename or safe_report_filename(source.operation, format=report_format)
        result = self.result(Status.SUCCESS, workspace_root=str(config.workspace_root), dry_run=False, format=report_format.value)
        target = self._target(config, report_filename, report_format, result)
        if target is None:
            return result.finish(Status.FAILED)
        content = self._render(source, report_format)
        try:
            if target.reports_dir.exists() and target.reports_dir.is_symlink():
                raise PathSafetyError(
                    "unsafe-symlink",
                    "Reports directory must not be a symlink.",
                    {"path": str(target.reports_dir)},
                )
            target.reports_dir.mkdir(parents=True, exist_ok=True)
            if target.path.exists() and target.path.is_symlink():
                raise PathSafetyError("unsafe-symlink", "Report file must not be a symlink.", {"path": str(target.path)})
            target.path.write_text(content, encoding="utf-8")
        except PathSafetyError as exc:
            self._append_error(result, exc)
            return result.finish(Status.FAILED)
        except OSError as exc:
            result.errors.append(self.error("filesystem-error", "Report could not be written.", path=str(target.path), reason=str(exc)))
            result.steps.append(self.step("report-write", Status.FAILED, result.errors[-1].message, errors=result.errors[-1:]))
            return result.finish(Status.FAILED)

        result.applied_changes.append(AppliedChange("write-report", str(target.path), "written"))
        result.artifacts.append(
            Artifact(
                "report",
                "Written report artifact",
                path=target.path,
                metadata={"format": report_format.value, "bytes": len(content.encode("utf-8")), "planned": False},
            )
        )
        result.steps.append(self.step("report-write", Status.SUCCESS, f"Wrote report: {target.filename}"))
        result.summary.update({"report_path": str(target.path), "planned_changes": 0, "applied_changes": 1})
        return result.finish(Status.SUCCESS)

    def demo_result(self) -> FluxResult:
        result = FluxResult(
            operation="report-demo",
            status=Status.WARNING,
            steps=[StepResult("demo", Status.SUCCESS, "Safe report demo result generated without network or library access.")],
            warnings=[FluxWarning("demo-warning", "This is a safe demo warning.")],
            summary={"network": False, "downloads": False, "library_writes": False},
        )
        result.planned_changes.append(PlannedChange("write-report", "workspace/reports", "Demonstrate report planning"))
        result.artifacts.append(Artifact("demo", "Safe demo artifact", metadata={"provider_payload": "not included"}))
        return result.finish(Status.WARNING)

    def _target(self, config: FluxConfig, filename: str, format: ReportFormat, result: FluxResult) -> ReportTarget | None:
        try:
            safe_workspace_root(config.workspace_root, protected_roots=config.protected_roots)
            return ReportTarget.resolve(config.workspace_root, filename, format, protected_roots=config.protected_roots)
        except PathSafetyError as exc:
            self._append_error(result, exc)
            return None

    def _append_error(self, result: FluxResult, exc: PathSafetyError) -> None:
        error = self.error(exc.code, exc.message, **exc.context)
        result.errors.append(error)
        result.steps.append(self.step("report-target", Status.FAILED, exc.message, errors=[error]))

    def _render(self, source: FluxResult, format: ReportFormat) -> str:
        if format == ReportFormat.TEXT:
            return build_text_report(source)
        return build_json_report(source)
