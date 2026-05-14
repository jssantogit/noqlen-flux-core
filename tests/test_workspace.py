from pathlib import Path

from noqlen_flux.config import FluxConfig
from noqlen_flux.results import Status
from noqlen_flux.services import WorkspaceService


EXPECTED_DIRS = ("incoming", "approved", "quarantine", "rejected", "reports", "manifests", "cache", "tmp")


def test_ensure_workspace_dry_run_does_not_create_directories(tmp_path: Path) -> None:
    workspace = tmp_path / "flux-workspace"

    result = WorkspaceService().ensure_workspace(FluxConfig(workspace), dry_run=True)

    assert result.status == Status.SUCCESS
    assert not workspace.exists()
    assert len(result.planned_changes) == len(EXPECTED_DIRS) + 1
    assert result.applied_changes == []


def test_ensure_workspace_apply_creates_expected_directories(tmp_path: Path) -> None:
    workspace = tmp_path / "flux-workspace"

    result = WorkspaceService().ensure_workspace(FluxConfig(workspace, dry_run=False), dry_run=False)

    assert result.status == Status.SUCCESS
    for directory in EXPECTED_DIRS:
        assert (workspace / directory).is_dir()
    assert len(result.applied_changes) == len(EXPECTED_DIRS) + 1


def test_ensure_workspace_apply_is_idempotent(tmp_path: Path) -> None:
    workspace = tmp_path / "flux-workspace"
    service = WorkspaceService()

    first = service.ensure_workspace(FluxConfig(workspace, dry_run=False), dry_run=False)
    second = service.ensure_workspace(FluxConfig(workspace, dry_run=False), dry_run=False)

    assert first.status == Status.SUCCESS
    assert second.status == Status.SUCCESS
    assert second.applied_changes == []
    assert all(step.status == Status.SKIPPED for step in second.steps)


def test_workspace_service_blocks_symlink_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "flux-workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "incoming").symlink_to(outside, target_is_directory=True)

    result = WorkspaceService().ensure_workspace(FluxConfig(workspace, dry_run=False), dry_run=False)

    assert result.status == Status.FAILED
    assert any(error.code == "path-outside-workspace" for error in result.errors)


def test_workspace_service_blocks_protected_root(tmp_path: Path) -> None:
    workspace = tmp_path / "protected" / "flux-workspace"

    result = WorkspaceService().ensure_workspace(
        FluxConfig(workspace, dry_run=False, protected_roots=(tmp_path / "protected",)),
        dry_run=False,
    )

    assert result.status == Status.FAILED
    assert result.errors[0].code == "protected-root"
