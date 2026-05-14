from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from noqlen_flux.config import FluxConfig
from noqlen_flux.musiclab import (
    MusicLabFixture,
    MusicLabLayout,
    MusicLabSession,
    ensure_musiclab_path,
    session_layout,
    validate_musiclab_id,
)
from noqlen_flux.results import AppliedChange, Artifact, FluxResult, PlannedChange, Status
from noqlen_flux.safety import PathSafetyError, safe_workspace_root
from noqlen_flux.services.base import FluxService


class MusicLabService(FluxService):
    operation = "musiclab"

    def inspect_lab(self, config: FluxConfig) -> FluxResult:
        result = self.result(Status.SUCCESS, workspace_root=str(config.workspace_root), dry_run=True, action="inspect")
        layout = self._layout(config, result)
        if layout is None:
            return result.finish(Status.FAILED)

        missing = []
        for name, path in layout.items():
            self._inspect_path(result, name, path, config)
            if not path.exists():
                missing.append(name)

        if result.errors:
            return result.finish(Status.FAILED)
        result.summary.update({"missing_directories": missing, "required_directories": len(layout.items())})
        return result.finish(Status.SUCCESS)

    def init_lab(self, config: FluxConfig, dry_run: bool = True) -> FluxResult:
        result = self.result(Status.SUCCESS, workspace_root=str(config.workspace_root), dry_run=dry_run, action="init")
        layout = self._layout(config, result)
        if layout is None:
            return result.finish(Status.FAILED)

        for name, path in layout.items():
            self._ensure_directory(result, name, path, config, dry_run=dry_run)

        if result.errors:
            return result.finish(Status.FAILED)
        result.summary.update({"planned_changes": len(result.planned_changes), "applied_changes": len(result.applied_changes)})
        return result.finish(Status.SUCCESS)

    def create_session(
        self,
        config: FluxConfig,
        session_id: str | None = None,
        purpose: str | None = None,
        dry_run: bool = True,
    ) -> FluxResult:
        result = self.result(Status.SUCCESS, workspace_root=str(config.workspace_root), dry_run=dry_run, action="session-create")
        layout = self._layout(config, result)
        if layout is None:
            return result.finish(Status.FAILED)
        safe_session_id = self._safe_id(session_id or self._new_session_id(), "session-id", result)
        if safe_session_id is None:
            return result.finish(Status.FAILED)

        targets = (
            ("musiclab", layout.lab_root),
            ("musiclab-sessions", layout.sessions_dir),
        ) + session_layout(layout, safe_session_id)
        for name, path in targets:
            self._ensure_directory(result, name, path, config, dry_run=dry_run)

        session_root = layout.sessions_dir / safe_session_id
        session = MusicLabSession(
            session_id=safe_session_id,
            workspace_root=config.workspace_root,
            lab_root=layout.lab_root,
            purpose=purpose,
            metadata={"network": False, "downloads": False, "library_writes": False},
        )
        report_path = session_root / "reports" / "calibration-report.json"
        result.artifacts.append(
            Artifact(
                "musiclab-session",
                "MusicLab session directory",
                path=session_root,
                metadata={"session": session.to_dict(), "planned": dry_run},
            )
        )
        result.artifacts.append(
            Artifact("report", "MusicLab calibration report location", path=report_path, metadata={"planned": True})
        )

        if result.errors:
            return result.finish(Status.FAILED)
        result.summary.update({"session_id": safe_session_id, "planned_changes": len(result.planned_changes), "applied_changes": len(result.applied_changes)})
        return result.finish(Status.SUCCESS)

    def create_fake_fixture(
        self,
        config: FluxConfig,
        session_id: str,
        fixture_id: str,
        kind: str,
        dry_run: bool = True,
    ) -> FluxResult:
        result = self.result(Status.SUCCESS, workspace_root=str(config.workspace_root), dry_run=dry_run, action="fixture-create")
        layout = self._layout(config, result)
        if layout is None:
            return result.finish(Status.FAILED)
        safe_session_id = self._safe_id(session_id, "session-id", result)
        safe_fixture_id = self._safe_id(fixture_id, "fixture-id", result)
        safe_kind = self._safe_id(kind, "fixture-kind", result)
        if safe_session_id is None or safe_fixture_id is None or safe_kind is None:
            return result.finish(Status.FAILED)

        session_root = layout.sessions_dir / safe_session_id
        fixture_path = session_root / "fixtures" / f"{safe_fixture_id}.json"
        try:
            ensure_musiclab_path(session_root, config.workspace_root, protected_roots=config.protected_roots)
            ensure_musiclab_path(fixture_path.parent, config.workspace_root, protected_roots=config.protected_roots)
            ensure_musiclab_path(fixture_path, config.workspace_root, protected_roots=config.protected_roots)
        except PathSafetyError as exc:
            self._append_error(result, "musiclab-fixture", exc)
            return result.finish(Status.FAILED)

        fixture = MusicLabFixture(
            fixture_id=safe_fixture_id,
            kind=safe_kind,
            description="Controlled fake MusicLab fixture; no audio, download, network, or library access.",
            relative_path=f"sessions/{safe_session_id}/fixtures/{safe_fixture_id}.json",
            metadata={"fake": True, "network": False, "downloads": False, "audio": False},
        )
        content = json.dumps(fixture.to_dict(), sort_keys=True, indent=2) + "\n"

        if dry_run:
            result.planned_changes.append(PlannedChange("write-fixture", str(fixture_path), "Create controlled fake MusicLab fixture"))
            result.steps.append(self.step("musiclab-fixture", Status.SKIPPED, f"Would write fake fixture: {safe_fixture_id}"))
            result.artifacts.append(Artifact("musiclab-fixture", "Planned fake MusicLab fixture", path=fixture_path, metadata={"planned": True}))
            result.summary.update({"session_id": safe_session_id, "fixture_id": safe_fixture_id, "planned_changes": 1, "applied_changes": 0})
            return result.finish(Status.SUCCESS)

        if not session_root.is_dir():
            error = self.error("missing-session", "MusicLab session directory does not exist.", session_id=safe_session_id)
            result.errors.append(error)
            result.steps.append(self.step("musiclab-fixture", Status.FAILED, error.message, errors=[error]))
            return result.finish(Status.FAILED)
        if fixture_path.exists() and fixture_path.is_symlink():
            error = self.error("unsafe-symlink", "Fixture path must not be a symlink.", path=str(fixture_path))
            result.errors.append(error)
            result.steps.append(self.step("musiclab-fixture", Status.FAILED, error.message, errors=[error]))
            return result.finish(Status.FAILED)

        try:
            fixture_path.parent.mkdir(parents=True, exist_ok=True)
            fixture_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            error = self.error("filesystem-error", "Fake fixture could not be written.", path=str(fixture_path), reason=str(exc))
            result.errors.append(error)
            result.steps.append(self.step("musiclab-fixture", Status.FAILED, error.message, errors=[error]))
            return result.finish(Status.FAILED)

        result.applied_changes.append(AppliedChange("write-fixture", str(fixture_path), "written"))
        result.artifacts.append(Artifact("musiclab-fixture", "Written fake MusicLab fixture", path=fixture_path, metadata={"planned": False}))
        result.steps.append(self.step("musiclab-fixture", Status.SUCCESS, f"Wrote fake fixture: {safe_fixture_id}"))
        result.summary.update({"session_id": safe_session_id, "fixture_id": safe_fixture_id, "planned_changes": 0, "applied_changes": 1})
        return result.finish(Status.SUCCESS)

    def _layout(self, config: FluxConfig, result: FluxResult) -> MusicLabLayout | None:
        try:
            safe_workspace_root(config.workspace_root, protected_roots=config.protected_roots)
            layout = MusicLabLayout.from_workspace(config.workspace_root)
            ensure_musiclab_path(layout.lab_root, config.workspace_root, protected_roots=config.protected_roots)
            return layout
        except PathSafetyError as exc:
            self._append_error(result, "musiclab-root", exc)
            return None

    def _inspect_path(self, result: FluxResult, name: str, path: Path, config: FluxConfig) -> None:
        try:
            ensure_musiclab_path(path, config.workspace_root, protected_roots=config.protected_roots)
        except PathSafetyError as exc:
            self._append_error(result, name, exc)
            return
        if not path.exists():
            if path.is_symlink():
                error = self.error("unsafe-symlink", "Path is a dangling symlink.", path=str(path))
                result.errors.append(error)
                result.steps.append(self.step(name, Status.FAILED, error.message, errors=[error]))
                return
            result.steps.append(self.step(name, Status.SKIPPED, f"Directory is missing: {name}"))
            return
        if not path.is_dir():
            error = self.error("not-directory", "Path exists but is not a directory.", path=str(path))
            result.errors.append(error)
            result.steps.append(self.step(name, Status.FAILED, error.message, errors=[error]))
            return
        result.steps.append(self.step(name, Status.SUCCESS, f"Directory is available: {name}", artifacts=[Artifact("directory", f"MusicLab directory {name}", path=path)]))

    def _ensure_directory(self, result: FluxResult, name: str, path: Path, config: FluxConfig, *, dry_run: bool) -> None:
        try:
            ensure_musiclab_path(path, config.workspace_root, protected_roots=config.protected_roots)
        except PathSafetyError as exc:
            self._append_error(result, name, exc)
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
            result.planned_changes.append(PlannedChange("create-directory", str(path), f"Create MusicLab directory {name}"))
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

    def _safe_id(self, value: str, field_name: str, result: FluxResult) -> str | None:
        try:
            return validate_musiclab_id(value, field_name=field_name)
        except PathSafetyError as exc:
            self._append_error(result, field_name, exc)
            return None

    def _append_error(self, result: FluxResult, step_name: str, exc: PathSafetyError) -> None:
        error = self.error(exc.code, exc.message, **exc.context)
        result.errors.append(error)
        result.steps.append(self.step(step_name, Status.FAILED, exc.message, errors=[error]))

    def _new_session_id(self) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"session-{stamp}-{uuid4().hex[:8]}"
