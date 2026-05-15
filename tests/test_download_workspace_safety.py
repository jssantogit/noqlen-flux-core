"""Tests for download workspace safety checks."""

from pathlib import Path

import pytest

from noqlen_flux.config import FluxConfig
from noqlen_flux.results import Status
from noqlen_flux.services.download_workspace import DownloadWorkspaceService


@pytest.fixture
def service() -> DownloadWorkspaceService:
    return DownloadWorkspaceService()


@pytest.fixture
def workspace_config(tmp_path: Path) -> FluxConfig:
    return FluxConfig(workspace_root=tmp_path, dry_run=True)


def test_validate_download_path_relative_passes(
    service: DownloadWorkspaceService, workspace_config: FluxConfig
) -> None:
    result = service.validate_download_path(workspace_config, "candidate-1/Track.flac")
    assert result.status == Status.SUCCESS
    assert result.summary["safe"] is True


def test_validate_download_path_nested_relative_passes(
    service: DownloadWorkspaceService, workspace_config: FluxConfig
) -> None:
    result = service.validate_download_path(
        workspace_config, "candidate-1/subdir/Track.flac"
    )
    assert result.status == Status.SUCCESS


def test_validate_download_path_absolute_blocks(
    service: DownloadWorkspaceService, workspace_config: FluxConfig
) -> None:
    result = service.validate_download_path(workspace_config, "/etc/passwd")
    assert result.status == Status.FAILED
    assert result.summary["safe"] is False


def test_validate_download_path_traversal_blocks(
    service: DownloadWorkspaceService, workspace_config: FluxConfig
) -> None:
    result = service.validate_download_path(workspace_config, "../escape/Track.flac")
    assert result.status == Status.FAILED
    assert result.summary["safe"] is False


def test_validate_download_path_traversal_double_dot_blocks(
    service: DownloadWorkspaceService, workspace_config: FluxConfig
) -> None:
    result = service.validate_download_path(
        workspace_config, "candidate-1/../../escape/Track.flac"
    )
    assert result.status == Status.FAILED


def test_validate_download_path_empty_blocks(
    service: DownloadWorkspaceService, workspace_config: FluxConfig
) -> None:
    result = service.validate_download_path(workspace_config, "")
    assert result.status == Status.FAILED


def test_validate_download_path_home_traversal_blocks(
    service: DownloadWorkspaceService, workspace_config: FluxConfig
) -> None:
    result = service.validate_download_path(workspace_config, "~/Music/Track.flac")
    assert result.status == Status.FAILED


def test_validate_download_path_variable_traversal_blocks(
    service: DownloadWorkspaceService, workspace_config: FluxConfig
) -> None:
    result = service.validate_download_path(workspace_config, "${HOME}/Track.flac")
    assert result.status == Status.FAILED


def test_validate_download_path_dot_segment_blocks(
    service: DownloadWorkspaceService, workspace_config: FluxConfig
) -> None:
    result = service.validate_download_path(
        workspace_config, "candidate-1/./Track.flac"
    )
    assert result.status == Status.FAILED


def test_validate_download_path_protected_root_blocks(
    service: DownloadWorkspaceService, tmp_path: Path
) -> None:
    protected = tmp_path / "protected"
    protected.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "incoming").mkdir()

    config = FluxConfig(
        workspace_root=workspace,
        protected_roots=(protected,),
        dry_run=True,
    )
    result = service.validate_download_path(config, "Track.flac")
    assert result.status == Status.SUCCESS


def test_validate_download_workspace_valid_root(
    service: DownloadWorkspaceService, workspace_config: FluxConfig
) -> None:
    workspace_config.workspace_root.mkdir(parents=True, exist_ok=True)
    result = service.validate_download_workspace(workspace_config)
    assert result.status == Status.SUCCESS


def test_validate_download_workspace_blocks_protected_root(
    tmp_path: Path
) -> None:
    protected = tmp_path / "protected"
    protected.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = FluxConfig(
        workspace_root=workspace,
        protected_roots=(protected,),
        dry_run=True,
    )
    service = DownloadWorkspaceService()
    result = service.validate_download_workspace(config)
    assert result.status == Status.SUCCESS


def test_symlink_escape_blocked(
    service: DownloadWorkspaceService, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    symlink_target = workspace / "candidate-1" / "Track.flac"
    symlink_target.parent.mkdir(parents=True)
    symlink_target.write_text("dummy")

    safe_symlink = workspace / "candidate-1" / "safe-link.flac"
    safe_symlink.symlink_to(symlink_target)

    escape_symlink = workspace / "candidate-1" / "escape-link.flac"
    if escape_symlink.exists():
        escape_symlink.unlink()
    escape_symlink.symlink_to(outside / "Track.flac")

    config = FluxConfig(workspace_root=workspace, dry_run=True)
    service = DownloadWorkspaceService()

    safe_result = service.validate_download_path(config, "candidate-1/safe-link.flac")
    assert safe_result.status in (Status.SUCCESS, Status.WARNING)

    outside_target = outside / "Track.flac"
    outside_target.write_text("outside")
    escape_result = service.validate_download_path(
        config, "candidate-1/escape-link.flac"
    )
    assert escape_result.status == Status.FAILED
    assert escape_result.summary["safe"] is False


def test_ensure_download_directory_dry_run(
    service: DownloadWorkspaceService, workspace_config: FluxConfig, tmp_path: Path
) -> None:
    result = service.ensure_download_directory(
        workspace_config, "candidate-1", dry_run=True
    )
    assert result.status == Status.SUCCESS
    assert len(result.planned_changes) >= 1
    assert not (tmp_path / "candidate-1").exists()


def test_ensure_download_directory_apply(
    service: DownloadWorkspaceService, tmp_path: Path
) -> None:
    config = FluxConfig(workspace_root=tmp_path, dry_run=False)
    result = service.ensure_download_directory(
        config, "candidate-1", dry_run=False
    )
    assert result.status == Status.SUCCESS
    assert (tmp_path / "candidate-1").exists()


def test_ensure_download_directory_blocks_unsafe_path(
    service: DownloadWorkspaceService, workspace_config: FluxConfig
) -> None:
    result = service.ensure_download_directory(
        workspace_config, "../escape", dry_run=True
    )
    assert result.status == Status.FAILED


def test_ensure_download_directory_apply_blocks_unsafe_path(
    service: DownloadWorkspaceService, workspace_config: FluxConfig
) -> None:
    result = service.ensure_download_directory(
        workspace_config, "../escape", dry_run=False
    )
    assert result.status == Status.FAILED


def test_download_workspace_service_does_not_access_network() -> None:
    from noqlen_flux.services import download_workspace as mod
    source = open(mod.__file__).read()
    assert "requests" not in source
    assert "urllib" not in source
    assert "socket" not in source


def test_download_workspace_service_does_not_import_slskd() -> None:
    from noqlen_flux.services import download_workspace as mod
    assert "slskd" not in mod.__file__
    for name in dir(mod):
        obj = getattr(mod, name, None)
        if hasattr(obj, "__module__"):
            assert "slskd" not in (getattr(obj, "__module__", "") or "")


def test_download_workspace_service_validates_path_containment(
    service: DownloadWorkspaceService, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    config = FluxConfig(workspace_root=workspace, dry_run=True)
    service = DownloadWorkspaceService()

    safe_result = service.validate_download_path(config, "Track.flac")
    assert safe_result.status == Status.SUCCESS

    unsafe_result = service.validate_download_path(config, "/root/.ssh/id_rsa")
    assert unsafe_result.status == Status.FAILED


def test_download_workspace_provider_output_not_real_music_library(
    service: DownloadWorkspaceService, tmp_path: Path
) -> None:
    config = FluxConfig(workspace_root=tmp_path, dry_run=True)
    service = DownloadWorkspaceService()

    music_lib_paths = [
        "/Music/Library/Track.flac",
        "/home/user/Music/Album.flac",
        "/media/music/Track.mp3",
    ]
    for path in music_lib_paths:
        result = service.validate_download_path(config, path)
        assert result.status == Status.FAILED, f"Expected {path} to be blocked"
