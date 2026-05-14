"""Provider adapter contracts and safe test providers."""

from .base import BaseProvider, SearchProvider, TransferProvider
from .fake import FakeSearchProvider
from .fake_transfer import FakeTransferProvider
from .status import (
    ProviderAvailability,
    ProviderCapability,
    ProviderCapabilityReport,
    ProviderHealth,
    ProviderKind,
    ProviderStatus,
)

__all__ = [
    "BaseProvider",
    "FakeSearchProvider",
    "FakeTransferProvider",
    "ProviderAvailability",
    "ProviderCapability",
    "ProviderCapabilityReport",
    "ProviderHealth",
    "ProviderKind",
    "ProviderStatus",
    "SearchProvider",
    "TransferProvider",
]
