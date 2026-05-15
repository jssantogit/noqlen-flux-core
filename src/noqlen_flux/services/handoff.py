from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from noqlen_flux.config import FluxConfig
from noqlen_flux.handoff import (
    HANDOFF_MANIFEST_VERSION,
    HandoffApplyItemOutcome,
    HandoffApplyItemResult,
    HandoffApplyMode,
    HandoffApplyReport,
    HandoffApplyResult,
    HandoffCandidateRef,
    HandoffItem,
    HandoffItemStatus,
    HandoffItemType,
    HandoffManifest,
    HandoffPathRef,
    HandoffQualityRef,
    HandoffReportRef,
    HandoffRoutingRef,
    HandoffSource,
    HandoffValidationIssue,
    HandoffValidationResult,
    _FORBIDDEN_FIELDS,
    validate_relative_path,
    validate_safe_metadata,
)
from noqlen_flux.safety import _TRAVERSAL_MARKERS, is_safe_relative_path
from noqlen_flux.results import AppliedChange, Artifact, FluxError, FluxResult, FluxWarning, PlannedChange, Severity, Status
from noqlen_flux.safety import PathSafetyError, ensure_not_protected, ensure_within_workspace, normalize_path, safe_workspace_root
from noqlen_flux.services.base import FluxService

_SAFE_MANIFEST_FILENAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*\.json$")


class HandoffManifestService(FluxService):
    operation = "handoff"

    def build_manifest(
        self,
        items: list[HandoffItem],
        source: HandoffSource | None = None,
        reports: list[HandoffReportRef] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> HandoffManifest:
        selected_source = source or HandoffSource(name="noqlen-flux")
        selected_reports = reports or []
        selected_metadata = metadata or {}

        return HandoffManifest(
            handoff_version=HANDOFF_MANIFEST_VERSION,
            source=selected_source,
            items=list(items),
            reports=list(selected_reports),
            metadata=selected_metadata,
        )

    def validate_manifest(self, manifest: HandoffManifest) -> HandoffValidationResult:
        issues: list[HandoffValidationIssue] = []
        warnings: list[str] = []
        errors: list[str] = []

        if manifest.handoff_version != HANDOFF_MANIFEST_VERSION:
            issues.append(
                HandoffValidationIssue(
                    code="invalid-version",
                    message=f"Unsupported manifest version: {manifest.handoff_version}. Expected {HANDOFF_MANIFEST_VERSION}.",
                    severity="error",
                )
            )

        if not manifest.items:
            issues.append(
                HandoffValidationIssue(
                    code="empty-manifest",
                    message="Manifest contains no items.",
                    severity="warning",
                )
            )

        for item in manifest.items:
            item_issues = self._validate_item(item)
            issues.extend(item_issues)

        for item_issue in issues:
            if item_issue.severity == "error":
                errors.append(item_issue.message)
            elif item_issue.severity == "warning":
                warnings.append(item_issue.message)

        is_valid = len([i for i in issues if i.severity == "error"]) == 0

        return HandoffValidationResult(
            valid=is_valid,
            issues=issues,
            warnings=warnings,
            errors=errors,
            metadata={"item_count": len(manifest.items), "issue_count": len(issues)},
        )

    def preview_manifest(
        self,
        config: FluxConfig,
        manifest: HandoffManifest,
        filename: str | None = None,
    ) -> FluxResult:
        try:
            safe_workspace_root(config.workspace_root, protected_roots=config.protected_roots)
        except PathSafetyError as exc:
            return self._error_result("workspace-safety", exc.message, exc.context)

        manifest_filename = filename or _safe_manifest_filename(manifest)

        try:
            target = _resolve_manifest_target(config.workspace_root, manifest_filename, protected_roots=config.protected_roots)
        except PathSafetyError as exc:
            return self._error_result(exc.code, exc.message, exc.context)

        content = manifest.to_json()
        planned_change = PlannedChange(
            action="write-manifest",
            target=str(target),
            reason="Planned handoff manifest write",
            metadata={"filename": manifest_filename, "bytes": len(content.encode("utf-8"))},
        )

        artifact = Artifact(
            kind="handoff-manifest",
            description="Planned handoff manifest artifact",
            path=target,
            metadata={
                "handoff_version": manifest.handoff_version,
                "item_count": len(manifest.items),
                "format": "json",
                "bytes": len(content.encode("utf-8")),
                "planned": True,
            },
        )

        step = self.step(
            "manifest-preview",
            Status.SUCCESS,
            f"Would write manifest: {manifest_filename}",
            artifacts=[artifact],
        )

        return FluxResult(
            operation=self.operation,
            status=Status.SUCCESS,
            steps=[step],
            artifacts=[artifact],
            planned_changes=[planned_change],
            summary={
                "manifest_filename": manifest_filename,
                "manifest_path": str(target),
                "handoff_version": manifest.handoff_version,
                "item_count": len(manifest.items),
                "planned_changes": 1,
                "applied_changes": 0,
                "dry_run": True,
            },
        ).finish()

    def write_manifest(
        self,
        config: FluxConfig,
        manifest: HandoffManifest,
        filename: str | None = None,
        *,
        dry_run: bool = True,
    ) -> FluxResult:
        if dry_run:
            return self.preview_manifest(config, manifest, filename=filename)

        try:
            safe_workspace_root(config.workspace_root, protected_roots=config.protected_roots)
        except PathSafetyError as exc:
            return self._error_result("workspace-safety", exc.message, exc.context)

        manifest_filename = filename or _safe_manifest_filename(manifest)

        try:
            target = _resolve_manifest_target(config.workspace_root, manifest_filename, protected_roots=config.protected_roots)
        except PathSafetyError as exc:
            return self._error_result(exc.code, exc.message, exc.context)

        content = manifest.to_json()

        try:
            manifests_dir = target.parent
            if manifests_dir.exists() and manifests_dir.is_symlink():
                raise PathSafetyError(
                    "unsafe-symlink",
                    "Manifests directory must not be a symlink.",
                    {"path": str(manifests_dir)},
                )
            manifests_dir.mkdir(parents=True, exist_ok=True)

            if target.exists() and target.is_symlink():
                raise PathSafetyError(
                    "unsafe-symlink",
                    "Manifest file must not be a symlink.",
                    {"path": str(target)},
                )

            target.write_text(content, encoding="utf-8")
        except PathSafetyError as exc:
            return self._error_result(exc.code, exc.message, exc.context)
        except OSError as exc:
            error = self.error(
                "filesystem-error",
                "Manifest could not be written.",
                path=str(target),
                reason=str(exc),
            )
            step = self.step("manifest-write", Status.FAILED, error.message, errors=[error])
            return FluxResult(
                operation=self.operation,
                status=Status.FAILED,
                steps=[step],
                errors=[error],
                summary={"manifest_filename": manifest_filename, "dry_run": False},
            ).finish()

        applied_change = AppliedChange(
            action="write-manifest",
            target=str(target),
            result="written",
            metadata={"filename": manifest_filename, "bytes": len(content.encode("utf-8"))},
        )

        artifact = Artifact(
            kind="handoff-manifest",
            description="Written handoff manifest artifact",
            path=target,
            metadata={
                "handoff_version": manifest.handoff_version,
                "item_count": len(manifest.items),
                "format": "json",
                "bytes": len(content.encode("utf-8")),
                "planned": False,
            },
        )

        step = self.step(
            "manifest-write",
            Status.SUCCESS,
            f"Wrote manifest: {manifest_filename}",
            artifacts=[artifact],
        )

        return FluxResult(
            operation=self.operation,
            status=Status.SUCCESS,
            steps=[step],
            artifacts=[artifact],
            applied_changes=[applied_change],
            summary={
                "manifest_filename": manifest_filename,
                "manifest_path": str(target),
                "handoff_version": manifest.handoff_version,
                "item_count": len(manifest.items),
                "planned_changes": 0,
                "applied_changes": 1,
                "dry_run": False,
            },
        ).finish()

    def demo_manifest(self) -> HandoffManifest:
        source = HandoffSource(
            name="noqlen-flux",
            version="1",
            metadata={"purpose": "demo", "status": "handoff-foundation"},
        )

        approved_item = HandoffItem(
            item_id="demo-track-001",
            item_type=HandoffItemType.TRACK,
            status=HandoffItemStatus.APPROVED,
            path=HandoffPathRef(
                relative_path="approved/demo-track-001.flac",
                workspace_area="approved",
                description="Demo approved track",
            ),
            query_metadata={"artist": "Demo Artist", "title": "Demo Track"},
            candidate=HandoffCandidateRef(
                candidate_id="demo-candidate-001",
                provider="fake",
                risk="low",
                score=0.95,
            ),
            quality=HandoffQualityRef(
                grade="excellent",
                confidence=0.98,
                finding_count=0,
                objective_failure_count=0,
                heuristic_warning_count=0,
            ),
            routing=HandoffRoutingRef(
                outcome="approved",
                action_type="plan_only",
                reason_count=1,
            ),
            reports=[
                HandoffReportRef(
                    kind="quality-report",
                    relative_path="reports/quality-demo.json",
                    description="Demo quality report",
                ),
            ],
            metadata={"demo": True},
        )

        quarantine_item = HandoffItem(
            item_id="demo-track-002",
            item_type=HandoffItemType.TRACK,
            status=HandoffItemStatus.QUARANTINE,
            path=HandoffPathRef(
                relative_path="quarantine/demo-track-002.flac",
                workspace_area="quarantine",
                description="Demo quarantine track",
            ),
            query_metadata={"artist": "Demo Artist", "title": "Demo Track 2"},
            candidate=HandoffCandidateRef(
                candidate_id="demo-candidate-002",
                provider="fake",
                risk="medium",
                score=0.60,
            ),
            quality=HandoffQualityRef(
                grade="medium",
                confidence=0.70,
                finding_count=1,
                objective_failure_count=0,
                heuristic_warning_count=1,
            ),
            routing=HandoffRoutingRef(
                outcome="quarantine",
                action_type="plan_only",
                reason_count=1,
            ),
            warnings=["Heuristic warning: low-pass suspicion"],
            metadata={"demo": True},
        )

        return HandoffManifest(
            handoff_version=HANDOFF_MANIFEST_VERSION,
            source=source,
            items=[approved_item, quarantine_item],
            reports=[
                HandoffReportRef(
                    kind="handoff-summary",
                    relative_path="reports/handoff-summary.json",
                    description="Demo handoff summary report",
                ),
            ],
            metadata={"purpose": "demo", "status": "handoff-foundation"},
        )

    def load_manifest_from_file(
        self,
        workspace_root: Path,
        relative_path: str,
        *,
        protected_roots: tuple[Path, ...] = (),
    ) -> FluxResult:
        try:
            safe_workspace_root(workspace_root, protected_roots=protected_roots)
        except PathSafetyError as exc:
            return self._error_result(exc.code, exc.message, exc.context)

        validated_path = validate_relative_path(relative_path, field_name="relative_path")
        target = ensure_within_workspace(
            workspace_root / validated_path,
            workspace_root,
            protected_roots=protected_roots,
        )

        if target.exists() and target.is_symlink():
            return self._error_result(
                "unsafe-symlink",
                "Manifest file must not be a symlink.",
                {"path": str(target)},
            )

        try:
            raw = target.read_text(encoding="utf-8")
        except OSError as exc:
            return self._error_result(
                "manifest-read-error",
                f"Could not read manifest file: {exc}",
                {"path": str(target)},
            )

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            return self._error_result(
                "manifest-parse-error",
                f"Manifest file is not valid JSON: {exc}",
                {"path": str(target)},
            )

        if not isinstance(data, dict):
            return self._error_result(
                "manifest-format-error",
                "Manifest file root must be a JSON object.",
                {"path": str(target)},
            )

        version = data.get("handoff_version")
        if version != HANDOFF_MANIFEST_VERSION:
            return self._error_result(
                "manifest-version-mismatch",
                f"Manifest version {version} is not supported. Expected {HANDOFF_MANIFEST_VERSION}.",
                {"path": str(target)},
            )

        items_raw = data.get("items", [])
        if not isinstance(items_raw, list):
            return self._error_result(
                "manifest-items-format-error",
                "Manifest items must be a JSON array.",
                {"path": str(target)},
            )

        items: list[HandoffItem] = []
        for i, item_data in enumerate(items_raw):
            if not isinstance(item_data, dict):
                return self._error_result(
                    "manifest-item-format-error",
                    f"Manifest item at index {i} is not a JSON object.",
                    {"path": str(target)},
                )
            try:
                item = _parse_handoff_item(item_data)
                items.append(item)
            except (KeyError, ValueError) as exc:
                return self._error_result(
                    "manifest-item-parse-error",
                    f"Could not parse manifest item at index {i}: {exc}",
                    {"path": str(target)},
                )

        manifest = self.build_manifest(items=items)
        artifact = Artifact(
            kind="handoff-manifest-loaded",
            description="Loaded handoff manifest from file",
            path=target,
            metadata={
                "handoff_version": manifest.handoff_version,
                "item_count": len(manifest.items),
                "dry_run": True,
            },
        )
        step = self.step(
            "manifest-load",
            Status.SUCCESS,
            f"Loaded manifest: {relative_path}",
            artifacts=[artifact],
        )
        return FluxResult(
            operation=self.operation,
            status=Status.SUCCESS,
            steps=[step],
            artifacts=[artifact],
            summary={
                "manifest_filename": relative_path,
                "manifest_path": str(target),
                "handoff_version": manifest.handoff_version,
                "item_count": len(manifest.items),
                "dry_run": True,
                "manifest": manifest.to_dict(),
            },
        ).finish()

    def apply_manifest(
        self,
        config: FluxConfig,
        manifest_path: str,
        *,
        dry_run: bool = True,
    ) -> FluxResult:
        try:
            safe_workspace_root(
                config.workspace_root,
                protected_roots=config.protected_roots,
            )
        except PathSafetyError as exc:
            return self._error_result(exc.code, exc.message, exc.context)

        load_result = self.load_manifest_from_file(
            config.workspace_root,
            manifest_path,
            protected_roots=config.protected_roots,
        )
        if load_result.status == Status.FAILED:
            return load_result

        manifest_data = load_result.summary.get("manifest", {})
        items_raw = manifest_data.get("items", [])
        items: list[HandoffItem] = []
        for item_data in items_raw:
            try:
                items.append(_parse_handoff_item(item_data))
            except (KeyError, ValueError):
                continue

        mode = HandoffApplyMode.DRY_RUN if dry_run else HandoffApplyMode.APPLY
        item_results: list[HandoffApplyItemResult] = []
        applied = 0
        blocked = 0
        skipped = 0
        apply_warnings: list[str] = []
        apply_errors: list[str] = []

        for item in items:
            outcome, reason = self._check_forge_ready(item)
            forge_ready = outcome == HandoffApplyItemOutcome.APPLIED
            item_warnings: list[str] = []
            item_errors: list[str] = []

            if outcome == HandoffApplyItemOutcome.APPLIED:
                applied += 1
            elif outcome == HandoffApplyItemOutcome.BLOCKED:
                blocked += 1
                if reason:
                    item_errors.append(reason)
                    apply_errors.append(f"{item.item_id}: {reason}")
            else:
                skipped += 1
                if reason:
                    item_warnings.append(reason)
                    apply_warnings.append(f"{item.item_id}: {reason}")

            item_results.append(
                HandoffApplyItemResult(
                    item_id=item.item_id,
                    outcome=outcome,
                    reason=reason,
                    forge_ready=forge_ready,
                    warnings=item_warnings,
                    errors=item_errors,
                )
            )

        apply_result = HandoffApplyResult(
            mode=mode,
            manifest_version=HANDOFF_MANIFEST_VERSION,
            total_items=len(items),
            applied=applied,
            blocked=blocked,
            skipped=skipped,
            item_results=item_results,
            warnings=apply_warnings,
            errors=apply_errors,
            metadata={
                "dry_run": dry_run,
                "manifest_path": manifest_path,
            },
        )

        report = HandoffApplyReport(
            report_id=str(uuid.uuid4()),
            manifest_path=manifest_path,
            mode=mode,
            valid=len(apply_errors) == 0,
            total_items=len(items),
            applied=applied,
            blocked=blocked,
            skipped=skipped,
            item_results=item_results,
            warnings=apply_warnings,
            errors=apply_errors,
            metadata={
                "dry_run": dry_run,
                "workspace_root": "[workspace-root]",
            },
        )

        report_artifact = Artifact(
            kind="handoff-apply-report",
            description="Handoff apply bridge report",
            metadata={"report": report.to_dict()},
        )

        action = "apply-manifest-dry-run" if dry_run else "apply-manifest"
        overall_status = Status.WARNING if blocked > 0 or skipped > 0 else Status.SUCCESS
        if len(apply_errors) > 0:
            overall_status = Status.WARNING

        planned_changes = []
        if dry_run:
            planned_changes.append(
                PlannedChange(
                    action="handoff-apply",
                    target=str(config.workspace_root / manifest_path),
                    reason="Would apply handoff manifest for Forge bridge",
                    metadata={"items_applied": applied, "items_blocked": blocked, "items_skipped": skipped},
                )
            )

        result = FluxResult(
            operation="handoff-apply",
            status=overall_status,
            artifacts=[report_artifact],
            planned_changes=planned_changes,
            summary={
                "manifest_path": manifest_path,
                "mode": mode.value,
                "total_items": len(items),
                "applied": applied,
                "blocked": blocked,
                "skipped": skipped,
                "valid": report.valid,
                "dry_run": dry_run,
                "report": report.to_dict(),
            },
        )
        result.warnings.extend(
            FluxWarning(code="blocked-item", message=w, severity=Severity.WARNING)
            for w in apply_warnings
        )
        return result.finish()

    def _check_forge_ready(
        self,
        item: HandoffItem,
    ) -> tuple[HandoffApplyItemOutcome, str]:
        if item.status != HandoffItemStatus.APPROVED:
            return (
                HandoffApplyItemOutcome.BLOCKED,
                f"Item status '{item.status.value}' is not 'approved'. Only approved items can be handed off to Forge.",
            )

        if item.item_type == HandoffItemType.UNKNOWN:
            return (
                HandoffApplyItemOutcome.SKIPPED,
                "Item has unknown type. Skipping handoff.",
            )

        issues = self._validate_item(item)
        error_issues = [i for i in issues if i.severity == "error"]
        if error_issues:
            return (
                HandoffApplyItemOutcome.BLOCKED,
                f"Item failed validation: {'; '.join(i.message for i in error_issues)}",
            )

        return (HandoffApplyItemOutcome.APPLIED, "")

    def _validate_item(self, item: HandoffItem) -> list[HandoffValidationIssue]:
        issues: list[HandoffValidationIssue] = []

        if not item.item_id:
            issues.append(
                HandoffValidationIssue(
                    code="missing-item-id",
                    message="Item must have a non-empty item_id.",
                    severity="error",
                )
            )

        valid_statuses = {s.value for s in HandoffItemStatus}
        if item.status.value not in valid_statuses:
            issues.append(
                HandoffValidationIssue(
                    code="invalid-status",
                    message=f"Invalid item status: {item.status.value}",
                    severity="error",
                    item_id=item.item_id,
                )
            )

        if not is_safe_relative_path(item.path.relative_path):
            issues.append(
                HandoffValidationIssue(
                    code="unsafe-path",
                    message=f"Item path is not a safe relative path: {item.path.relative_path}",
                    severity="error",
                    item_id=item.item_id,
                )
            )

        if item.path.relative_path.startswith("/") or item.path.relative_path.startswith("\\"):
            issues.append(
                HandoffValidationIssue(
                    code="absolute-path",
                    message="Item path must not be absolute.",
                    severity="error",
                    item_id=item.item_id,
                )
            )

        for marker in _TRAVERSAL_MARKERS:
            if marker in item.path.relative_path:
                issues.append(
                    HandoffValidationIssue(
                        code="path-traversal",
                        message=f"Item path contains traversal marker: {marker}",
                        severity="error",
                        item_id=item.item_id,
                    )
                )
                break

        dicts_to_check: list[dict[str, Any]] = [
            item.metadata or {},
            item.query_metadata or {},
            item.path.metadata or {},
            item.quality.metadata if item.quality else {},
            item.routing.metadata if item.routing else {},
            item.candidate.metadata if item.candidate else {},
        ]
        for report in (item.reports or []):
            dicts_to_check.append(report.metadata or {})

        for data_dict in dicts_to_check:
            if data_dict:
                for key in data_dict:
                    normalized_key = key.lower().replace("_", "-")
                    for forbidden in _FORBIDDEN_FIELDS:
                        if forbidden in normalized_key:
                            issues.append(
                                HandoffValidationIssue(
                                    code="forbidden-field",
                                    message=f"Forbidden field detected: {key}",
                                    severity="error",
                                    item_id=item.item_id,
                                )
                            )
                            break

        return issues

    def _error_result(self, code: str, message: str, context: dict[str, str] | None = None) -> FluxResult:
        error = self.error(code, message, **(context or {}))
        step = self.step("manifest-validate", Status.FAILED, message, errors=[error])
        return FluxResult(
            operation=self.operation,
            status=Status.FAILED,
            steps=[step],
            errors=[error],
            summary={"error_code": code, "dry_run": True},
        ).finish()


class HandoffApplyBridge(FluxService):
    operation = "handoff-apply-bridge"

    def __init__(self) -> None:
        self._manifest_service = HandoffManifestService()

    def bridge(
        self,
        config: FluxConfig,
        manifest_path: str,
        *,
        dry_run: bool = True,
    ) -> FluxResult:
        apply_result = self._manifest_service.apply_manifest(
            config, manifest_path, dry_run=dry_run,
        )

        if apply_result.status == Status.FAILED:
            return apply_result

        report_data = apply_result.summary.get("report", {})
        if dry_run:
            return apply_result

        try:
            safe_workspace_root(
                config.workspace_root,
                protected_roots=config.protected_roots,
            )
        except PathSafetyError as exc:
            return self._error_result(exc.code, exc.message, exc.context)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        report_filename = f"handoff-apply-{timestamp}.json"
        reports_dir = ensure_within_workspace(
            config.workspace_root / "reports",
            config.workspace_root,
            protected_roots=config.protected_roots,
        )
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_target = ensure_within_workspace(
            reports_dir / report_filename,
            config.workspace_root,
            protected_roots=config.protected_roots,
        )

        try:
            import json as _json
            report_target.write_text(
                _json.dumps(report_data, sort_keys=True, separators=(",", ":"), default=str),
                encoding="utf-8",
            )
        except OSError as exc:
            return self._error_result(
                "bridge-report-write-error",
                f"Could not write apply report: {exc}",
                {"path": str(report_target)},
            )

        applied_change = AppliedChange(
            action="write-handoff-apply-report",
            target=str(report_target),
            result="written",
            metadata={"report_filename": report_filename},
        )

        report_artifact = Artifact(
            kind="handoff-apply-report-file",
            description="Written handoff apply bridge report",
            path=report_target,
            metadata={
                "applied": apply_result.summary.get("applied", 0),
                "blocked": apply_result.summary.get("blocked", 0),
                "skipped": apply_result.summary.get("skipped", 0),
            },
        )

        step = self.step(
            "bridge-report-write",
            Status.SUCCESS,
            f"Wrote handoff apply report: {report_filename}",
            artifacts=[report_artifact],
        )

        return FluxResult(
            operation=self.operation,
            status=apply_result.status,
            steps=[step],
            artifacts=[report_artifact],
            applied_changes=[applied_change],
            summary={
                **apply_result.summary,
                "report_file": str(report_target),
                "report_filename": report_filename,
                "bridge_complete": True,
            },
        ).finish()

    def _error_result(self, code: str, message: str, context: dict[str, str] | None = None) -> FluxResult:
        error = self.error(code, message, **(context or {}))
        step = self.step("bridge-error", Status.FAILED, message, errors=[error])
        return FluxResult(
            operation=self.operation,
            status=Status.FAILED,
            steps=[step],
            errors=[error],
            summary={"error_code": code},
        ).finish()


def _safe_manifest_filename(manifest: HandoffManifest) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = f"handoff-{timestamp}.json"
    if not _SAFE_MANIFEST_FILENAME_RE.fullmatch(candidate):
        return f"handoff-manifest-{uuid.uuid4().hex[:8]}.json"
    return candidate


def _resolve_manifest_target(
    workspace_root: Path,
    filename: str,
    *,
    protected_roots: tuple[Path, ...] = (),
) -> Path:
    path = Path(filename)
    if path.name != filename or path.is_absolute() or ".." in path.parts:
        raise PathSafetyError(
            "unsafe-manifest-filename",
            "Manifest filename cannot contain path traversal.",
            {"filename": filename},
        )
    if not _SAFE_MANIFEST_FILENAME_RE.fullmatch(filename):
        raise PathSafetyError(
            "unsafe-manifest-filename",
            "Manifest filename contains unsafe characters.",
            {"filename": filename},
        )
    if not filename.endswith(".json"):
        raise PathSafetyError(
            "manifest-format-mismatch",
            "Manifest filename must end with .json.",
            {"filename": filename},
        )

    resolved_workspace = normalize_path(workspace_root)
    manifests_dir = ensure_within_workspace(
        resolved_workspace / "manifests",
        resolved_workspace,
        protected_roots=protected_roots,
    )

    if manifests_dir.exists() and manifests_dir.is_symlink():
        resolved_manifests = manifests_dir.resolve(strict=True)
        ensure_within_workspace(resolved_manifests, resolved_workspace, protected_roots=protected_roots)

    target = ensure_within_workspace(manifests_dir / filename, resolved_workspace, protected_roots=protected_roots)

    if target.parent != manifests_dir:
        raise PathSafetyError(
            "unsafe-manifest-filename",
            "Manifest filename must resolve directly inside workspace manifests directory.",
            {"filename": filename},
        )

    return target


def _parse_handoff_item(data: dict[str, Any]) -> HandoffItem:
    path_data = data.get("path", {})
    if not isinstance(path_data, dict):
        raise ValueError("Item path must be a JSON object")
    path_ref = HandoffPathRef(
        relative_path=path_data.get("relative_path", ""),
        workspace_area=path_data.get("workspace_area"),
        description=path_data.get("description"),
        metadata=validate_safe_metadata(path_data.get("metadata", {})),
    )
    quality_data = data.get("quality")
    quality_ref = None
    if isinstance(quality_data, dict):
        quality_ref = HandoffQualityRef(
            grade=quality_data.get("grade", ""),
            confidence=quality_data.get("confidence"),
            finding_count=quality_data.get("finding_count", 0),
            objective_failure_count=quality_data.get("objective_failure_count", 0),
            heuristic_warning_count=quality_data.get("heuristic_warning_count", 0),
            metadata=validate_safe_metadata(quality_data.get("metadata", {})),
        )
    routing_data = data.get("routing")
    routing_ref = None
    if isinstance(routing_data, dict):
        routing_ref = HandoffRoutingRef(
            outcome=routing_data.get("outcome", ""),
            action_type=routing_data.get("action_type", ""),
            reason_count=routing_data.get("reason_count", 0),
            metadata=validate_safe_metadata(routing_data.get("metadata", {})),
        )
    candidate_data = data.get("candidate")
    candidate_ref = None
    if isinstance(candidate_data, dict):
        candidate_ref = HandoffCandidateRef(
            candidate_id=candidate_data.get("candidate_id"),
            provider=candidate_data.get("provider"),
            risk=candidate_data.get("risk"),
            score=candidate_data.get("score"),
            metadata=validate_safe_metadata(candidate_data.get("metadata", {})),
        )
    reports_raw = data.get("reports", [])
    reports: list[HandoffReportRef] = []
    if isinstance(reports_raw, list):
        for r in reports_raw:
            if isinstance(r, dict):
                reports.append(
                    HandoffReportRef(
                        kind=r.get("kind", ""),
                        relative_path=r.get("relative_path"),
                        description=r.get("description", ""),
                        metadata=validate_safe_metadata(r.get("metadata", {})),
                    )
                )
    return HandoffItem(
        item_id=data.get("item_id", ""),
        item_type=data.get("item_type", "unknown"),
        status=data.get("status", "unknown"),
        path=path_ref,
        forge_ready=data.get("forge_ready", False),
        query_metadata=validate_safe_metadata(data.get("query_metadata") or {}),
        quality=quality_ref,
        routing=routing_ref,
        candidate=candidate_ref,
        warnings=list(data.get("warnings", [])),
        errors=list(data.get("errors", [])),
        metadata=validate_safe_metadata(data.get("metadata", {})),
        reports=reports,
    )
