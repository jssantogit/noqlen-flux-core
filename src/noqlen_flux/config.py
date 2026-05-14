from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from noqlen_flux.paths import WorkspaceLayout
from noqlen_flux.safety import normalize_path


@dataclass(slots=True, frozen=True)
class FluxConfig:
    workspace_root: Path
    dry_run: bool = True
    protected_roots: tuple[Path, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace_root", normalize_path(self.workspace_root))
        object.__setattr__(
            self,
            "protected_roots",
            tuple(normalize_path(root) for root in self.protected_roots),
        )

    @property
    def layout(self) -> WorkspaceLayout:
        return WorkspaceLayout.from_root(self.workspace_root)


def config_from_env(workspace_root: str | Path, *, dry_run: bool = True) -> FluxConfig:
    raw_protected_roots = os.environ.get("NOQLEN_FLUX_PROTECTED_ROOTS", "")
    protected_roots = tuple(Path(item) for item in raw_protected_roots.split(os.pathsep) if item)
    return FluxConfig(Path(workspace_root), dry_run=dry_run, protected_roots=protected_roots)
