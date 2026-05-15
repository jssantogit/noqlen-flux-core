from __future__ import annotations

from pathlib import Path
from typing import Any

from noqlen_flux.config import FluxConfig
from noqlen_flux.results import (
    Artifact,
    FluxError,
    FluxResult,
    FluxWarning,
    PlannedChange,
    Severity,
    Status,
)
from noqlen_flux.safety import (
    PathSafetyError,
    ensure_not_protected,
    ensure_within_workspace,
    is_safe_relative_path,
    safe_workspace_root,
    validate_safe_relative_path,
)
from noqlen_flux.services.base import FluxService


class DownloadWorkspaceService(FluxService):
    operation = "download-workspace-safety"

    def validate_download_path(
        self,
        config: FluxConfig,
        relative_path: str,
        *,
        allow_create_dirs: bool = False,
    ) -> FluxResult:
        warnings: list[FluxWarning] = []
        errors: list[FluxError] = []
        planned_changes: list[PlannedChange] = []

        if not relative_path or not isinstance(relative_path, str):
            errors.append(
                self.error(
                    "invalid-path",
                    "Download path is empty or invalid",
                    context={"path": str(relative_path)},
                )
            )
            return self._build_result(config, "validate", relative_path, warnings, errors, planned_changes)

        if not is_safe_relative_path(relative_path):
            errors.append(
                self.error(
                    "unsafe-path",
                    f"Download path contains traversal markers or is absolute: {relative_path}",
                    context={"path": relative_path},
                )
            )
            return self._build_result(config, "validate", relative_path, warnings, errors, planned_changes)

        normalized = relative_path.replace("\\", "/")
        parts = normalized.split("/")
        if "." in parts or ".." in parts:
            errors.append(
                self.error(
                    "unsafe-path",
                    f"Download path contains dot-only or parent segments: {relative_path}",
                    context={"path": relative_path},
                )
            )
            return self._build_result(config, "validate", relative_path, warnings, errors, planned_changes)

        try:
            resolved_root = safe_workspace_root(
                config.workspace_root, protected_roots=config.protected_roots
            )
        except PathSafetyError as exc:
            errors.append(
                self.error(
                    exc.code,
                    exc.message,
                    context=exc.context,
                )
            )
            return self._build_result(config, "validate", relative_path, warnings, errors, planned_changes)

        try:
            validated = validate_safe_relative_path(relative_path)
        except ValueError as exc:
            errors.append(
                self.error(
                    "unsafe-path",
                    str(exc),
                    context={"path": relative_path},
                )
            )
            return self._build_result(config, "validate", relative_path, warnings, errors, planned_changes)

        full_path = resolved_root / validated

        try:
            ensure_within_workspace(
                full_path,
                config.workspace_root,
                protected_roots=config.protected_roots,
            )
        except PathSafetyError as exc:
            errors.append(
                self.error(
                    exc.code,
                    exc.message,
                    context=exc.context,
                )
            )
            return self._build_result(config, "validate", relative_path, warnings, errors, planned_changes)

        is_symlink = False
        try:
            if full_path.exists() and full_path.is_symlink():
                is_symlink = True
                resolved_symlink = full_path.resolve(strict=False)
                try:
                    ensure_within_workspace(
                        resolved_symlink,
                        config.workspace_root,
                        protected_roots=config.protected_roots,
                    )
                except PathSafetyError as exc:
                    errors.append(
                        self.error(
                            "symlink-escape",
                            f"Download path is a symlink that resolves outside the workspace: {exc.message}",
                            context={
                                "path": relative_path,
                                "resolved_to": str(resolved_symlink),
                            },
                        )
                    )
                    return self._build_result(config, "validate", relative_path, warnings, errors, planned_changes)
        except OSError:
            pass

        if is_symlink:
            warnings.append(
                self.warning(
                    "symlink-detected",
                    f"Download path is a symlink: {relative_path}",
                    context={"path": relative_path, "resolved": str(resolved_symlink)},
                )
            )

        if allow_create_dirs and not full_path.exists():
            planned_changes.append(
                PlannedChange(
                    action="ensure-download-directory",
                    target=str(full_path),
                    reason=f"Would create download directory for: {relative_path}",
                )
            )

        return self._build_result(
            config, "validate", relative_path, warnings, errors, planned_changes,
            is_symlink=is_symlink,
        )

    def validate_download_workspace(
        self,
        config: FluxConfig,
    ) -> FluxResult:
        warnings: list[FluxWarning] = []
        errors: list[FluxError] = []
        planned_changes: list[PlannedChange] = []

        try:
            safe_workspace_root(
                config.workspace_root, protected_roots=config.protected_roots
            )
        except PathSafetyError as exc:
            errors.append(
                self.error(
                    exc.code,
                    exc.message,
                    context=exc.context,
                )
            )
            return self._build_result(config, "workspace-validate", str(config.workspace_root), warnings, errors, planned_changes)

        planned_changes.append(
            PlannedChange(
                action="validate-download-workspace",
                target=str(config.workspace_root),
                reason="Download workspace root is safe and contained",
            )
        )

        return self._build_result(
            config, "workspace-validate", str(config.workspace_root), warnings, errors, planned_changes,
        )

    def ensure_download_directory(
        self,
        config: FluxConfig,
        relative_path: str,
        *,
        dry_run: bool = True,
    ) -> FluxResult:
        if dry_run:
            return self.validate_download_path(
                config, relative_path, allow_create_dirs=True,
            )

        validation_result = self.validate_download_path(
            config, relative_path, allow_create_dirs=True,
        )
        if validation_result.status == Status.FAILED:
            return validation_result

        validated = validate_safe_relative_path(relative_path)
        if validated is None:
            return self.result(
                Status.FAILED,
                error="Download path is unsafe",
            )

        try:
            resolved_root = safe_workspace_root(
                config.workspace_root, protected_roots=config.protected_roots
            )
            target_dir = resolved_root / validated
            target_dir.mkdir(parents=True, exist_ok=True)
        except PathSafetyError as exc:
            return self.result(
                Status.FAILED,
                error=exc.message,
            )
        except OSError as exc:
            return self.result(
                Status.FAILED,
                error=f"Cannot create download directory: {exc}",
            )

        return self.result(
            Status.SUCCESS,
            download_dir=str(target_dir),
            relative_path=validated,
        )

    def _build_result(
        self,
        config: FluxConfig,
        action: str,
        relative_path: str,
        warnings: list[FluxWarning],
        errors: list[FluxError],
        planned_changes: list[PlannedChange],
        *,
        is_symlink: bool = False,
    ) -> FluxResult:
        status = Status.FAILED if errors else (Status.WARNING if warnings else Status.SUCCESS)

        artifact = Artifact(
            kind="download-workspace-safety",
            description=f"Download workspace safety check for: {relative_path}",
            metadata={
                "workspace_root": str(config.workspace_root),
                "relative_path": relative_path,
                "safe": len(errors) == 0,
                "is_symlink": is_symlink,
            },
        )

        step = self.step(
            action,
            status,
            f"Download workspace safety validation: {relative_path}",
            warnings=warnings,
            errors=errors,
            artifacts=[artifact],
        )

        result = FluxResult(
            operation=self.operation,
            status=status,
            steps=[step],
            warnings=warnings,
            errors=errors,
            artifacts=[artifact],
            planned_changes=planned_changes,
            summary={
                "workspace_root": str(config.workspace_root),
                "relative_path": relative_path,
                "safe": len(errors) == 0,
                "is_symlink": is_symlink,
            },
        )
        return result.finish()
