from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

_TRAVERSAL_MARKERS = ("..", "~", "$", "{", "}")


@dataclass(slots=True, frozen=True)
class PathSafetyError(Exception):
    code: str
    message: str
    context: dict[str, str] = field(default_factory=dict)


def validate_safe_relative_path(value: str | None, *, field_name: str = "path") -> str | None:
    if value is None:
        return None
    if not value:
        raise ValueError(f"{field_name}: Empty path.")
    if value.startswith("/") or value.startswith("\\"):
        raise ValueError(f"{field_name}: Absolute paths are not allowed.")
    for marker in _TRAVERSAL_MARKERS:
        if marker in value:
            raise ValueError(f"{field_name}: Path traversal marker '{marker}' is not allowed.")
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if ".." in parts or "." in parts:
        raise ValueError(f"{field_name}: Parent directory or dot-only traversal is not allowed.")
    return normalized


def is_safe_relative_path(value: str) -> bool:
    if not value:
        return False
    if value.startswith("/") or value.startswith("\\"):
        return False
    for marker in _TRAVERSAL_MARKERS:
        if marker in value:
            return False
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if ".." in parts or "." in parts:
        return False
    return True


def normalize_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def is_within_path(path: str | Path, root: str | Path) -> bool:
    resolved_path = normalize_path(path)
    resolved_root = normalize_path(root)
    return resolved_path == resolved_root or resolved_path.is_relative_to(resolved_root)


def ensure_not_protected(path: str | Path, protected_roots: tuple[Path, ...] = ()) -> Path:
    resolved_path = normalize_path(path)
    for protected_root in protected_roots:
        resolved_protected = normalize_path(protected_root)
        if resolved_path == resolved_protected or resolved_path.is_relative_to(resolved_protected):
            raise PathSafetyError(
                "protected-root",
                "Path is inside a protected root.",
                {"path": str(resolved_path), "protected_root": str(resolved_protected)},
            )
    return resolved_path


def ensure_within_workspace(
    target: str | Path,
    workspace_root: str | Path,
    *,
    protected_roots: tuple[Path, ...] = (),
) -> Path:
    resolved_workspace = ensure_not_protected(workspace_root, protected_roots)
    resolved_target = ensure_not_protected(target, protected_roots)
    if resolved_target == resolved_workspace or resolved_target.is_relative_to(resolved_workspace):
        return resolved_target
    raise PathSafetyError(
        "path-outside-workspace",
        "Path resolves outside the workspace root.",
        {"path": str(resolved_target), "workspace_root": str(resolved_workspace)},
    )


def safe_workspace_root(workspace_root: str | Path, *, protected_roots: tuple[Path, ...] = ()) -> Path:
    resolved = ensure_not_protected(workspace_root, protected_roots)
    for protected_root in protected_roots:
        resolved_protected = normalize_path(protected_root)
        if resolved_protected.is_relative_to(resolved):
            raise PathSafetyError(
                "protected-root-contained",
                "Workspace root would contain a protected root.",
                {"workspace_root": str(resolved), "protected_root": str(resolved_protected)},
            )
    return resolved
