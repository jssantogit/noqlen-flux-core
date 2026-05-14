from pathlib import Path

import pytest

from noqlen_flux.safety import (
    PathSafetyError,
    ensure_not_protected,
    ensure_within_workspace,
    is_within_path,
    validate_safe_relative_path,
)


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


def test_validate_safe_relative_path_returns_none_for_none() -> None:
    assert validate_safe_relative_path(None) is None


def test_validate_safe_relative_path_accepts_safe_path() -> None:
    result = validate_safe_relative_path("approved/item-1.flac")
    assert result == "approved/item-1.flac"


def test_validate_safe_relative_path_blocks_empty() -> None:
    with pytest.raises(ValueError, match="Empty path"):
        validate_safe_relative_path("")


def test_validate_safe_relative_path_blocks_absolute() -> None:
    with pytest.raises(ValueError, match="Absolute paths"):
        validate_safe_relative_path("/etc/passwd")


def test_validate_safe_relative_path_blocks_traversal() -> None:
    with pytest.raises(ValueError, match="Path traversal marker"):
        validate_safe_relative_path("../../../etc/passwd")


def test_validate_safe_relative_path_blocks_tilde() -> None:
    with pytest.raises(ValueError, match="Path traversal marker"):
        validate_safe_relative_path("~/escape.txt")


def test_validate_safe_relative_path_blocks_dollar() -> None:
    with pytest.raises(ValueError, match="Path traversal marker"):
        validate_safe_relative_path("$HOME/escape.txt")


def test_validate_safe_relative_path_blocks_brace() -> None:
    with pytest.raises(ValueError, match="Path traversal marker"):
        validate_safe_relative_path("{var}/escape.txt")


def test_validate_safe_relative_path_blocks_parent_traversal() -> None:
    with pytest.raises(ValueError, match="Path traversal marker"):
        validate_safe_relative_path("foo/../bar")


def test_validate_safe_relative_path_normalizes_backslashes() -> None:
    result = validate_safe_relative_path("approved\\item-1.flac")
    assert result == "approved/item-1.flac"


def test_validate_safe_relative_path_custom_field_name() -> None:
    with pytest.raises(ValueError, match="relative_path: Empty path"):
        validate_safe_relative_path("", field_name="relative_path")
