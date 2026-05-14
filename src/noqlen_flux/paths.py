from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class WorkspaceLayout:
    incoming: Path
    approved: Path
    quarantine: Path
    rejected: Path
    reports: Path
    manifests: Path
    cache: Path
    tmp: Path

    @classmethod
    def from_root(cls, workspace_root: Path) -> WorkspaceLayout:
        return cls(
            incoming=workspace_root / "incoming",
            approved=workspace_root / "approved",
            quarantine=workspace_root / "quarantine",
            rejected=workspace_root / "rejected",
            reports=workspace_root / "reports",
            manifests=workspace_root / "manifests",
            cache=workspace_root / "cache",
            tmp=workspace_root / "tmp",
        )

    def items(self) -> tuple[tuple[str, Path], ...]:
        return (
            ("incoming", self.incoming),
            ("approved", self.approved),
            ("quarantine", self.quarantine),
            ("rejected", self.rejected),
            ("reports", self.reports),
            ("manifests", self.manifests),
            ("cache", self.cache),
            ("tmp", self.tmp),
        )
