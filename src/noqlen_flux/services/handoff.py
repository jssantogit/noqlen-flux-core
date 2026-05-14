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
    _TRAVERSAL_MARKERS,
    _is_safe_relative_path,
    validate_relative_path,
)
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

        if not _is_safe_relative_path(item.path.relative_path):
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

        for data_dict in [item.metadata, item.query_metadata or {}]:
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
