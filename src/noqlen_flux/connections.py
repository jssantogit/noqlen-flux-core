from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from noqlen_flux.results import _clean
from noqlen_flux.secrets import SecretDescriptor, SecretRef


class ProviderConnectionMode(StrEnum):
    MANAGED = "managed"
    EXTERNAL = "external"


class ProviderAuthMode(StrEnum):
    API_KEY = "api_key"
    NONE = "none"


@dataclass(slots=True, frozen=True)
class ProviderConnectionProfile:
    provider: str
    mode: ProviderConnectionMode
    base_url: str | None = None
    auth_mode: ProviderAuthMode = ProviderAuthMode.NONE
    api_key_ref: SecretRef | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("provider is required")
        object.__setattr__(self, "mode", ProviderConnectionMode(self.mode))
        object.__setattr__(self, "auth_mode", ProviderAuthMode(self.auth_mode))

    def to_dict(self) -> dict[str, Any]:
        return _clean(
            {
                "provider": self.provider,
                "mode": self.mode.value,
                "base_url": self.base_url,
                "auth_mode": self.auth_mode.value,
                "api_key_ref": self.api_key_ref.to_dict() if self.api_key_ref else None,
                "metadata": self.metadata,
            }
        )


@dataclass(slots=True, frozen=True)
class AppConnectionBundle:
    profile: ProviderConnectionProfile
    secret_descriptors: list[SecretDescriptor] = field(default_factory=list)
    restart_required: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, *, include_secret_material: bool = False) -> dict[str, Any]:
        if include_secret_material:
            raise PermissionError("app connection bundles do not expose raw secret material")
        return _clean(
            {
                "profile": self.profile.to_dict(),
                "secret_descriptors": [item.to_dict() for item in self.secret_descriptors],
                "restart_required": self.restart_required,
                "metadata": self.metadata,
            }
        )
