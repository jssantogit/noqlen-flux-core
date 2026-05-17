from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from noqlen_flux.results import _clean


_REDACTED = "[redacted]"


class SecretState(StrEnum):
    ACTIVE = "active"
    ROTATED = "rotated"
    DELETED = "deleted"


@dataclass(slots=True)
class SecretMaterial:
    value: str
    label: str = "secret"
    _revealed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("secret material is required")

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.value.encode("utf-8")).hexdigest()[:16]

    def reveal_once(self, *, allow: bool = False) -> str:
        if not allow:
            raise PermissionError("explicit secret reveal permission is required")
        if self._revealed:
            raise RuntimeError("secret material was already revealed")
        self._revealed = True
        return self.value

    def to_dict(self, *, reveal: bool = False) -> dict[str, Any]:
        return _clean(
            {
                "label": self.label,
                "value": self.reveal_once(allow=True) if reveal else _REDACTED,
                "digest": self.digest,
            }
        )

    def __repr__(self) -> str:
        return f"SecretMaterial(label={self.label!r}, value={_REDACTED!r}, digest={self.digest!r})"


@dataclass(slots=True, frozen=True)
class SecretRef:
    store: str
    key: str
    version: str
    digest: str | None = None
    state: SecretState = SecretState.ACTIVE

    def __post_init__(self) -> None:
        if not self.store.strip() or not self.key.strip() or not self.version.strip():
            raise ValueError("secret store, key, and version are required")
        object.__setattr__(self, "state", SecretState(self.state))

    def to_dict(self) -> dict[str, Any]:
        return _clean(
            {
                "store": self.store,
                "key": self.key,
                "version": self.version,
                "digest": self.digest,
                "state": self.state.value,
            }
        )


@dataclass(slots=True, frozen=True)
class SecretDescriptor:
    ref: SecretRef
    label: str
    created_at: datetime
    rotated_from: SecretRef | None = None

    def to_dict(self) -> dict[str, Any]:
        return _clean(
            {
                "ref": self.ref.to_dict(),
                "label": self.label,
                "created_at": self.created_at.isoformat(),
                "rotated_from": self.rotated_from.to_dict() if self.rotated_from else None,
            }
        )


class InMemorySecretStoreProvider:
    """Safe in-memory secret store for tests and dry-run workflows."""

    def __init__(self, *, store_name: str = "memory") -> None:
        self.store_name = store_name
        self._values: dict[str, str] = {}
        self._descriptors: dict[str, SecretDescriptor] = {}

    def store_secret(self, key: str, material: SecretMaterial, *, label: str | None = None) -> SecretRef:
        ref = SecretRef(store=self.store_name, key=key, version=str(uuid.uuid4()), digest=material.digest)
        self._values[key] = material.value
        self._descriptors[key] = SecretDescriptor(ref=ref, label=label or material.label, created_at=_now())
        return ref

    def get_secret(self, ref: SecretRef) -> SecretMaterial:
        value = self._values.get(ref.key)
        if value is None:
            raise KeyError("secret reference is not active")
        return SecretMaterial(value=value, label=ref.key)

    def rotate_secret(self, ref: SecretRef, material: SecretMaterial, *, dry_run: bool = True) -> SecretRef:
        if dry_run:
            return SecretRef(store=self.store_name, key=ref.key, version="dry-run", digest=material.digest)
        if ref.key not in self._values:
            raise KeyError("secret reference is not active")
        old_ref = SecretRef(store=ref.store, key=ref.key, version=ref.version, digest=ref.digest, state=SecretState.ROTATED)
        new_ref = SecretRef(store=self.store_name, key=ref.key, version=str(uuid.uuid4()), digest=material.digest)
        self._values[ref.key] = material.value
        self._descriptors[ref.key] = SecretDescriptor(ref=new_ref, label=material.label, created_at=_now(), rotated_from=old_ref)
        return new_ref

    def delete_secret(self, ref: SecretRef) -> SecretRef:
        self._values.pop(ref.key, None)
        deleted = SecretRef(store=ref.store, key=ref.key, version=ref.version, digest=ref.digest, state=SecretState.DELETED)
        self._descriptors.pop(ref.key, None)
        return deleted

    def describe_secret(self, ref: SecretRef) -> SecretDescriptor:
        descriptor = self._descriptors.get(ref.key)
        if descriptor is None:
            raise KeyError("secret reference is not active")
        return descriptor


class LocalWorkspaceSecretStoreProvider(InMemorySecretStoreProvider):
    """Workspace-confined local secret store for development provisioning."""

    def __init__(self, workspace: str | Path, *, store_name: str = "workspace") -> None:
        super().__init__(store_name=store_name)
        self.workspace = Path(workspace).expanduser().resolve()
        self.store_dir = (self.workspace / ".flux" / "secrets").resolve()
        if not _is_relative_to(self.store_dir, self.workspace):
            raise ValueError("secret store must stay inside workspace")
        self._load_existing()

    def store_secret(self, key: str, material: SecretMaterial, *, label: str | None = None) -> SecretRef:
        ref = super().store_secret(key, material, label=label)
        self._write_record(key, material.value, self._descriptors[key])
        return ref

    def rotate_secret(self, ref: SecretRef, material: SecretMaterial, *, dry_run: bool = True) -> SecretRef:
        new_ref = super().rotate_secret(ref, material, dry_run=dry_run)
        if not dry_run:
            self._write_record(ref.key, material.value, self._descriptors[ref.key])
        return new_ref

    def delete_secret(self, ref: SecretRef) -> SecretRef:
        deleted = super().delete_secret(ref)
        path = self._record_path(ref.key)
        if path.exists():
            path.unlink()
        return deleted

    def _load_existing(self) -> None:
        if not self.store_dir.exists():
            return
        for path in self.store_dir.glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            ref = SecretRef(**data["ref"])
            self._values[ref.key] = data["value"]
            self._descriptors[ref.key] = SecretDescriptor(ref=ref, label=data["label"], created_at=datetime.fromisoformat(data["created_at"]))

    def _write_record(self, key: str, value: str, descriptor: SecretDescriptor) -> None:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        path = self._record_path(key)
        data = {
            "ref": {
                "store": descriptor.ref.store,
                "key": descriptor.ref.key,
                "version": descriptor.ref.version,
                "digest": descriptor.ref.digest,
                "state": descriptor.ref.state.value,
            },
            "label": descriptor.label,
            "created_at": descriptor.created_at.isoformat(),
            "value": value,
        }
        path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def _record_path(self, key: str) -> Path:
        safe_key = key.replace("/", "_").replace("..", "_")
        path = (self.store_dir / f"{safe_key}.json").resolve()
        if not _is_relative_to(path, self.store_dir):
            raise ValueError("secret path escapes workspace store")
        return path


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False
