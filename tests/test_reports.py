import json
from pathlib import Path

import pytest

from noqlen_flux.config import FluxConfig
from noqlen_flux.reports import ReportFormat, build_json_report, build_text_report, safe_report_filename, validate_report_filename
from noqlen_flux.results import AppliedChange, Artifact, FluxError, FluxResult, FluxWarning, PlannedChange, Status, StepResult
from noqlen_flux.safety import PathSafetyError
from noqlen_flux.services import ReportService


def sample_result() -> FluxResult:
    result = FluxResult(
        operation="unit-report",
        status=Status.WARNING,
        steps=[StepResult("inspect", Status.WARNING, "review needed")],
        warnings=[FluxWarning("warn", "safe warning")],
        errors=[FluxError("err", "safe error")],
        artifacts=[Artifact("manifest", "safe artifact", path="workspace/reports/report.json")],
        planned_changes=[PlannedChange("create", "workspace/reports/report.json", "test planning")],
        applied_changes=[AppliedChange("write", "workspace/reports/report.json", "written")],
        summary={"items": 1, "api_token": "placeholder-secret"},
    )
    return result.finish(Status.WARNING)


def test_build_json_report_with_flux_result() -> None:
    raw = build_json_report(sample_result())
    payload = json.loads(raw)

    assert payload["operation"] == "unit-report"
    assert payload["status"] == "warning"
    assert payload["summary"]["items"] == 1
    assert payload["summary"]["api_token"] == "[redacted]"
    assert payload["metadata"]["schema"] == "noqlen-flux-report-v1"


def test_build_text_report_with_flux_result() -> None:
    report = build_text_report(sample_result())

    assert "Noqlen Flux Report: unit-report" in report
    assert "status: warning" in report
    assert "inspect: warning review needed" in report


def test_warnings_errors_changes_appear_in_reports() -> None:
    json_report = build_json_report(sample_result())
    text_report = build_text_report(sample_result())

    for expected in ("safe warning", "safe error", "test planning", "written"):
        assert expected in json_report
        assert expected in text_report


def test_safe_report_filename_blocks_dangerous_names() -> None:
    assert safe_report_filename("Report Demo", "preview", format=ReportFormat.JSON) == "report-demo-preview.json"
    with pytest.raises(PathSafetyError):
        validate_report_filename("../escape.json", ReportFormat.JSON)
    with pytest.raises(PathSafetyError):
        validate_report_filename("report/escape.json", ReportFormat.JSON)
    with pytest.raises(PathSafetyError):
        validate_report_filename("report text.json", ReportFormat.JSON)


def test_report_dry_run_does_not_create_file(tmp_path: Path) -> None:
    workspace = tmp_path / "flux-workspace"
    result = ReportService().preview_report(FluxConfig(workspace), sample_result(), ReportFormat.JSON)

    assert result.status == Status.SUCCESS
    assert result.planned_changes
    assert result.artifacts[0].metadata["planned"] is True
    assert not workspace.exists()


def test_report_apply_creates_file_in_workspace_reports(tmp_path: Path) -> None:
    workspace = tmp_path / "flux-workspace"
    result = ReportService().write_report(FluxConfig(workspace, dry_run=False), sample_result(), ReportFormat.JSON, "unit-report.json")

    report_path = workspace / "reports" / "unit-report.json"
    assert result.status == Status.SUCCESS
    assert result.applied_changes
    assert report_path.is_file()
    assert json.loads(report_path.read_text(encoding="utf-8"))["operation"] == "unit-report"


def test_report_path_traversal_is_blocked(tmp_path: Path) -> None:
    workspace = tmp_path / "flux-workspace"
    result = ReportService().write_report(FluxConfig(workspace, dry_run=False), sample_result(), ReportFormat.JSON, "../escape.json")

    assert result.status == Status.FAILED
    assert result.errors[0].code == "unsafe-report-filename"
    assert not (tmp_path / "escape.json").exists()


def test_report_symlink_escape_is_blocked(tmp_path: Path) -> None:
    workspace = tmp_path / "flux-workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "reports").symlink_to(outside, target_is_directory=True)

    result = ReportService().write_report(FluxConfig(workspace, dry_run=False), sample_result(), ReportFormat.TEXT, "unit-report.txt")

    assert result.status == Status.FAILED
    assert any(error.code in {"path-outside-workspace", "unsafe-symlink"} for error in result.errors)
    assert not (outside / "unit-report.txt").exists()
