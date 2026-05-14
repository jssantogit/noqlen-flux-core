from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from noqlen_flux.results import _clean

SafeMetadata = dict[str, Any]


class ProviderKind(StrEnum):
    FAKE = "fake"
    LAB = "lab"
    EXTERNAL = "external"
    NATIVE = "native"
    UNKNOWN = "unknown"


class ProviderCapability(StrEnum):
    SEARCH = "search"
    DOWNLOAD_PLANNING = "download_planning"
    QUEUE_PLANNING = "queue_planning"
    TRANSFER_STATUS = "transfer_status"
    HEALTH = "health"
    ARTIFACTS = "artifacts"
    UNKNOWN = "unknown"


class ProviderAvailability(StrEnum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(slots=True, frozen=True)
class ProviderHealth:
    provider: str
    kind: ProviderKind = ProviderKind.UNKNOWN
    availability: ProviderAvailability = ProviderAvailability.UNKNOWN
    status_message: str | None = None
    capabilities: list[ProviderCapability] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("provider is required")
        object.__setattr__(self, "kind", ProviderKind(self.kind))
        object.__setattr__(self, "availability", ProviderAvailability(self.availability))
        object.__setattr__(
            self,
            "capabilities",
            [ProviderCapability(c) for c in self.capabilities],
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True, frozen=True)
class ProviderStatus:
    provider: str
    health: ProviderHealth
    active_transfers: int | None = None
    queued_items: int | None = None
    last_checked_at: datetime | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("provider is required")
        if self.last_checked_at is None:
            object.__setattr__(self, "last_checked_at", datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["health"] = self.health.to_dict()
        if self.last_checked_at is not None:
            data["last_checked_at"] = self.last_checked_at.isoformat()
        return _clean(data)


@dataclass(slots=True, frozen=True)
class ProviderCapabilityReport:
    provider: str
    capabilities: list[ProviderCapability] = field(default_factory=list)
    unsupported_capabilities: list[ProviderCapability] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: SafeMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("provider is required")
        object.__setattr__(
            self,
            "capabilities",
            [ProviderCapability(c) for c in self.capabilities],
        )
        object.__setattr__(
            self,
            "unsupported_capabilities",
            [ProviderCapability(c) for c in self.unsupported_capabilities],
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))
