"""Provider adapter contracts and safe test providers."""

from .base import SearchProvider
from .fake import FakeSearchProvider

__all__ = ["FakeSearchProvider", "SearchProvider"]
