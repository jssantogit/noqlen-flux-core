from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from noqlen_flux.connections import AppConnectionBundle, ProviderConnectionMode, ProviderConnectionProfile
from noqlen_flux.results import _clean
from noqlen_flux.secrets import SecretRef


@dataclass(slots=True, frozen=True)
class ProviderProvisioningPolicy:
    allow_config_write: bool = False
    allow_secret_write: bool = False
    restart_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _clean({"allow_config_write": self.allow_config_write, "allow_secret_write": self.allow_secret_write, "restart_allowed": self.restart_allowed})


@dataclass(slots=True, frozen=True)
class ProviderProvisioningRequest:
    provider: str
    mode: ProviderConnectionMode
    workspace: Path | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    api_key_ref: SecretRef | None = None
    policy: ProviderProvisioningPolicy = field(default_factory=ProviderProvisioningPolicy)
    dry_run: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", ProviderConnectionMode(self.mode))

    def to_dict(self) -> dict[str, Any]:
        return _clean(
            {
                "provider": self.provider,
                "mode": self.mode.value,
                "workspace": str(self.workspace) if self.workspace else None,
                "base_url": self.base_url,
                "api_key_env": self.api_key_env,
                "api_key_ref": self.api_key_ref.to_dict() if self.api_key_ref else None,
                "policy": self.policy.to_dict(),
                "dry_run": self.dry_run,
            }
        )


@dataclass(slots=True, frozen=True)
class ProviderProvisioningPlan:
    provider: str
    mode: ProviderConnectionMode
    workspace: Path | None = None
    config_paths: list[str] = field(default_factory=list)
    app_profile: ProviderConnectionProfile | None = None
    restart_required: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean(
            {
                "provider": self.provider,
                "mode": self.mode.value,
                "workspace": str(self.workspace) if self.workspace else None,
                "config_paths": self.config_paths,
                "app_profile": self.app_profile.to_dict() if self.app_profile else None,
                "restart_required": self.restart_required,
                "metadata": self.metadata,
            }
        )


@dataclass(slots=True, frozen=True)
class ProviderProvisioningResult:
    provider: str
    mode: ProviderConnectionMode
    applied: bool
    plan: ProviderProvisioningPlan
    app_bundle: AppConnectionBundle | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _clean(
            {
                "provider": self.provider,
                "mode": self.mode.value,
                "applied": self.applied,
                "plan": self.plan.to_dict(),
                "app_bundle": self.app_bundle.to_dict() if self.app_bundle else None,
                "errors": self.errors,
            }
        )


@dataclass(slots=True, frozen=True)
class CredentialRotationRequest:
    provider: str
    workspace: Path | None = None
    api_key_ref: SecretRef | None = None
    dry_run: bool = True


@dataclass(slots=True, frozen=True)
class CredentialRotationResult:
    provider: str
    changed: bool
    restart_required: bool
    api_key_ref: SecretRef | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _clean(
            {
                "provider": self.provider,
                "changed": self.changed,
                "restart_required": self.restart_required,
                "api_key_ref": self.api_key_ref.to_dict() if self.api_key_ref else None,
                "errors": self.errors,
            }
        )
