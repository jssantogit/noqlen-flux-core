from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from noqlen_flux.results import FluxResult
from noqlen_flux.safety import PathSafetyError, ensure_within_workspace, normalize_path


class ReportFormat(StrEnum):
    JSON = "json"
    TEXT = "text"


@dataclass(slots=True, frozen=True)
class ReportDocument:
    title: str
    operation: str
    status: str
    summary: dict[str, Any]
    created_at: str
    content: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class ReportTarget:
    workspace_root: Path
    reports_dir: Path
    filename: str
    format: ReportFormat
    path: Path

    @classmethod
    def resolve(
        cls,
        workspace_root: str | Path,
        filename: str,
        format: ReportFormat | str,
        *,
        protected_roots: tuple[Path, ...] = (),
    ) -> ReportTarget:
        report_format = ReportFormat(format)
        safe_name = validate_report_filename(filename, report_format)
        resolved_workspace = normalize_path(workspace_root)
        reports_dir = ensure_within_workspace(
            resolved_workspace / "reports",
            resolved_workspace,
            protected_roots=protected_roots,
        )
        if reports_dir.exists() and reports_dir.is_symlink():
            resolved_reports = reports_dir.resolve(strict=True)
            ensure_within_workspace(resolved_reports, resolved_workspace, protected_roots=protected_roots)
        path = ensure_within_workspace(reports_dir / safe_name, resolved_workspace, protected_roots=protected_roots)
        if path.parent != reports_dir:
            raise PathSafetyError(
                "unsafe-report-filename",
                "Report filename must resolve directly inside workspace reports directory.",
                {"filename": filename},
            )
        return cls(resolved_workspace, reports_dir, safe_name, report_format, path)


_SAFE_FILENAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*\.(json|txt)$")
_SAFE_SLUG_RE = re.compile(r"[^a-z0-9._-]+")


def build_json_report(result: FluxResult) -> str:
    document = _document_from_result(result)
    return json.dumps(document.to_dict(), sort_keys=True, indent=2) + "\n"


def build_text_report(result: FluxResult) -> str:
    document = _document_from_result(result)
    content = document.content
    lines = [
        document.title,
        f"operation: {document.operation}",
        f"status: {document.status}",
        f"created_at: {document.created_at}",
        "",
        "summary:",
    ]
    lines.extend(_format_mapping(document.summary))
    lines.extend(["", "steps:"])
    for step in content["steps"]:
        lines.append(f"- {step['name']}: {step['status']} {step.get('message', '')}".rstrip())
    lines.extend(_format_items("warnings", content["warnings"], ("code", "message")))
    lines.extend(_format_items("errors", content["errors"], ("code", "message")))
    lines.extend(_format_items("planned_changes", content["planned_changes"], ("action", "target", "reason")))
    lines.extend(_format_items("applied_changes", content["applied_changes"], ("action", "target", "result")))
    lines.extend(_format_items("artifacts", content["artifacts"], ("kind", "description", "path")))
    return "\n".join(lines).rstrip() + "\n"


def safe_report_filename(operation: str, suffix: str | None = None, *, format: ReportFormat | str = ReportFormat.JSON) -> str:
    report_format = ReportFormat(format)
    slug = _slug(operation)
    if suffix is None:
        suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_suffix = _slug(suffix)
    extension = "txt" if report_format == ReportFormat.TEXT else "json"
    return validate_report_filename(f"{slug}-{safe_suffix}.{extension}", report_format)


def validate_report_filename(filename: str, format: ReportFormat | str) -> str:
    report_format = ReportFormat(format)
    path = Path(filename)
    if path.name != filename or path.is_absolute() or ".." in path.parts:
        raise PathSafetyError("unsafe-report-filename", "Report filename cannot contain path traversal.", {"filename": filename})
    if not _SAFE_FILENAME_RE.fullmatch(filename):
        raise PathSafetyError("unsafe-report-filename", "Report filename contains unsafe characters.", {"filename": filename})
    expected_suffix = ".txt" if report_format == ReportFormat.TEXT else ".json"
    if not filename.endswith(expected_suffix):
        raise PathSafetyError(
            "report-format-mismatch",
            "Report filename extension does not match requested format.",
            {"filename": filename, "format": report_format.value},
        )
    return filename


def _document_from_result(result: FluxResult) -> ReportDocument:
    payload = _sanitize_report_value(result.to_dict())
    created_at = payload.get("finished_at") or payload.get("started_at") or datetime.now(timezone.utc).isoformat()
    return ReportDocument(
        title=f"Noqlen Flux Report: {payload['operation']}",
        operation=payload["operation"],
        status=payload["status"],
        summary=payload.get("summary", {}),
        created_at=created_at,
        content={
            "steps": payload.get("steps", []),
            "warnings": payload.get("warnings", []),
            "errors": payload.get("errors", []),
            "artifacts": payload.get("artifacts", []),
            "planned_changes": payload.get("planned_changes", []),
            "applied_changes": payload.get("applied_changes", []),
        },
        metadata={"schema": "noqlen-flux-report-v1"},
    )


def _sanitize_report_value(value: Any, *, key: str = "") -> Any:
    if isinstance(value, dict):
        return {str(item_key): _sanitize_report_value(item_value, key=str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_sanitize_report_value(item, key=key) for item in value]
    if isinstance(value, str) and (key == "path" or key.endswith("_path") or key == "target"):
        return _safe_path_text(value)
    return value


def _safe_path_text(value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        return path.name or "[absolute-path]"
    return value


def _format_mapping(mapping: dict[str, Any]) -> list[str]:
    if not mapping:
        return ["- none"]
    return [f"- {key}: {value}" for key, value in sorted(mapping.items())]


def _format_items(title: str, items: list[dict[str, Any]], fields: tuple[str, ...]) -> list[str]:
    lines = ["", f"{title}:"]
    if not items:
        lines.append("- none")
        return lines
    for item in items:
        parts = [str(item[field]) for field in fields if item.get(field) not in (None, "")]
        lines.append(f"- {' | '.join(parts)}")
    return lines


def _slug(value: str) -> str:
    normalized = _SAFE_SLUG_RE.sub("-", value.strip().lower()).strip(".-_")
    if not normalized or normalized in {".", ".."}:
        raise PathSafetyError("unsafe-report-filename", "Report filename component is empty or unsafe.", {"value": value})
    return normalized[:80]
