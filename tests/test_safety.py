from pathlib import Path

import pytest

from noqlen_flux.safety import PathSafetyError, ensure_not_protected, ensure_within_workspace, is_within_path


def test_path_inside_workspace_is_allowed(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "incoming" / "file.flac"

    assert ensure_within_workspace(target, workspace) == target.resolve(strict=False)
    assert is_within_path(target, workspace)


def test_path_traversal_outside_workspace_is_blocked(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "incoming" / ".." / ".." / "escape"

    with pytest.raises(PathSafetyError) as exc:
        ensure_within_workspace(target, workspace)

    assert exc.value.code == "path-outside-workspace"


def test_symlink_escape_is_blocked(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "incoming").symlink_to(outside, target_is_directory=True)

    with pytest.raises(PathSafetyError) as exc:
        ensure_within_workspace(workspace / "incoming" / "file.flac", workspace)

    assert exc.value.code == "path-outside-workspace"


def test_protected_root_is_blocked(tmp_path: Path) -> None:
    protected = tmp_path / "protected"
    target = protected / "workspace"

    with pytest.raises(PathSafetyError) as exc:
        ensure_not_protected(target, (protected,))

    assert exc.value.code == "protected-root"
