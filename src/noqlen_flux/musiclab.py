from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from noqlen_flux.results import Artifact, FluxWarning
from noqlen_flux.safety import PathSafetyError, ensure_within_workspace


SafeMetadata = dict[str, Any]


@dataclass(slots=True, frozen=True)
class MusicLabLayout:
    lab_root: Path
    sessions_dir: Path
    fixtures_dir: Path
    reports_dir: Path
    tmp_dir: Path

    @classmethod
    def from_workspace(cls, workspace_root: Path) -> MusicLabLayout:
        lab_root = workspace_root / "musiclab"
        return cls(
            lab_root=lab_root,
            sessions_dir=lab_root / "sessions",
            fixtures_dir=lab_root / "fixtures",
            reports_dir=lab_root / "reports",
            tmp_dir=lab_root / "tmp",
        )

    def items(self) -> tuple[tuple[str, Path], ...]:
        return (
            ("musiclab", self.lab_root),
            ("musiclab-sessions", self.sessions_dir),
            ("musiclab-fixtures", self.fixtures_dir),
            ("musiclab-reports", self.reports_dir),
            ("musiclab-tmp", self.tmp_dir),
        )


@dataclass(slots=True, frozen=True)
class MusicLabSession:
    session_id: str
    workspace_root: Path
    lab_root: Path
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    purpose: str | None = None
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class MusicLabFixture:
    fixture_id: str
    kind: str
    description: str
    relative_path: str | None = None
    metadata: SafeMetadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class MusicLabCalibrationReport:
    session_id: str
    title: str
    summary: SafeMetadata
    fixtures: list[MusicLabFixture] = field(default_factory=list)
    warnings: list[FluxWarning] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")
_SENSITIVE_KEYS = ("authorization", "cookie", "key", "password", "private", "secret", "token")


def validate_musiclab_id(value: str, *, field_name: str) -> str:
    path = Path(value)
    if path.name != value or path.is_absolute() or ".." in path.parts:
        raise PathSafetyError(
            f"unsafe-{field_name}",
            f"{field_name} cannot contain path traversal.",
            {field_name: value},
        )
    if not _SAFE_ID_RE.fullmatch(value):
        raise PathSafetyError(
            f"unsafe-{field_name}",
            f"{field_name} contains unsafe characters.",
            {field_name: value},
        )
    return value


def session_layout(lab_layout: MusicLabLayout, session_id: str) -> tuple[tuple[str, Path], ...]:
    session_root = lab_layout.sessions_dir / session_id
    return (
        ("musiclab-session", session_root),
        ("musiclab-session-fixtures", session_root / "fixtures"),
        ("musiclab-session-reports", session_root / "reports"),
        ("musiclab-session-tmp", session_root / "tmp"),
    )


def ensure_musiclab_path(path: Path, workspace_root: Path, *, protected_roots: tuple[Path, ...] = ()) -> Path:
    resolved = ensure_within_workspace(path, workspace_root, protected_roots=protected_roots)
    if path.exists() and path.is_symlink():
        symlink_target = path.resolve(strict=True)
        ensure_within_workspace(symlink_target, workspace_root, protected_roots=protected_roots)
    return resolved


def _clean(value: Any, *, key: str = "") -> Any:
    if _is_sensitive_key(key):
        return "[redacted]"
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return _clean(asdict(value), key=key)
    if isinstance(value, dict):
        return {str(item_key): _clean(item_value, key=str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item, key=key) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("_", "-")
    return any(part in normalized for part in _SENSITIVE_KEYS)
