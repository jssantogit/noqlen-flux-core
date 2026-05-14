from __future__ import annotations

from pathlib import Path

from noqlen_flux.config import FluxConfig
from noqlen_flux.results import AppliedChange, Artifact, FluxResult, PlannedChange, Status
from noqlen_flux.safety import PathSafetyError, ensure_within_workspace, safe_workspace_root
from noqlen_flux.services.base import FluxService


class WorkspaceService(FluxService):
    operation = "workspace"

    def inspect_workspace(self, config: FluxConfig) -> FluxResult:
        result = self.result(Status.SUCCESS, workspace_root=str(config.workspace_root))
        if not self._validate_config(config, result):
            return result.finish(Status.FAILED)

        missing = []
        for name, path in config.layout.items():
            step = self._inspect_directory(name, path, config)
            result.steps.append(step)
            result.errors.extend(step.errors)
            if not path.exists():
                missing.append(name)
        result.summary.update({"missing_directories": missing, "required_directories": len(config.layout.items())})
        if result.errors:
            return result.finish(Status.FAILED)
        return result.finish(Status.SUCCESS)

    def ensure_workspace(self, config: FluxConfig, dry_run: bool | None = None) -> FluxResult:
        effective_dry_run = config.dry_run if dry_run is None else dry_run
        result = self.result(Status.SUCCESS, workspace_root=str(config.workspace_root), dry_run=effective_dry_run)
        if not self._validate_config(config, result):
            return result.finish(Status.FAILED)

        targets = (("workspace-root", config.workspace_root),) + config.layout.items()
        for name, path in targets:
            self._ensure_directory(result, name, path, config, dry_run=effective_dry_run)

        if result.errors:
            return result.finish(Status.FAILED)
        result.summary["planned_changes"] = len(result.planned_changes)
        result.summary["applied_changes"] = len(result.applied_changes)
        return result.finish(Status.SUCCESS)

    def _validate_config(self, config: FluxConfig, result: FluxResult) -> bool:
        try:
            safe_workspace_root(config.workspace_root, protected_roots=config.protected_roots)
            return True
        except PathSafetyError as exc:
            result.errors.append(self.error(exc.code, exc.message, **exc.context))
            result.steps.append(self.step("workspace-root", Status.FAILED, exc.message, errors=result.errors[-1:]))
            return False

    def _inspect_directory(self, name: str, path: Path, config: FluxConfig):
        try:
            ensure_within_workspace(path, config.workspace_root, protected_roots=config.protected_roots)
        except PathSafetyError as exc:
            return self.step(name, Status.FAILED, exc.message, errors=[self.error(exc.code, exc.message, **exc.context)])
        if not path.exists():
            if path.is_symlink():
                error = self.error("unsafe-symlink", "Path is a dangling symlink.", path=str(path))
                return self.step(name, Status.FAILED, error.message, errors=[error])
            return self.step(name, Status.SKIPPED, f"Directory is missing: {name}")
        if not path.is_dir():
            error = self.error("not-directory", "Path exists but is not a directory.", path=str(path))
            return self.step(name, Status.FAILED, error.message, errors=[error])
        return self.step(
            name,
            Status.SUCCESS,
            f"Directory is available: {name}",
            artifacts=[Artifact("directory", f"Workspace directory {name}", path=path)],
        )

    def _ensure_directory(self, result: FluxResult, name: str, path: Path, config: FluxConfig, *, dry_run: bool) -> None:
        try:
            ensure_within_workspace(path, config.workspace_root, protected_roots=config.protected_roots)
        except PathSafetyError as exc:
            error = self.error(exc.code, exc.message, **exc.context)
            result.errors.append(error)
            result.steps.append(self.step(name, Status.FAILED, exc.message, errors=[error]))
            return

        if path.exists() and not path.is_dir():
            error = self.error("not-directory", "Path exists but is not a directory.", path=str(path))
            result.errors.append(error)
            result.steps.append(self.step(name, Status.FAILED, error.message, errors=[error]))
            return

        if path.is_symlink() and not path.exists():
            error = self.error("unsafe-symlink", "Path is a dangling symlink.", path=str(path))
            result.errors.append(error)
            result.steps.append(self.step(name, Status.FAILED, error.message, errors=[error]))
            return

        if path.exists():
            result.steps.append(self.step(name, Status.SKIPPED, f"Directory already exists: {name}"))
            return

        if dry_run:
            result.planned_changes.append(PlannedChange("create-directory", str(path), f"Create workspace directory {name}"))
            result.steps.append(self.step(name, Status.SKIPPED, f"Would create directory: {name}"))
            return

        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            error = self.error("filesystem-error", "Directory could not be created.", path=str(path), reason=str(exc))
            result.errors.append(error)
            result.steps.append(self.step(name, Status.FAILED, error.message, errors=[error]))
            return
        result.applied_changes.append(AppliedChange("create-directory", str(path), "created"))
        result.steps.append(self.step(name, Status.SUCCESS, f"Created directory: {name}"))
