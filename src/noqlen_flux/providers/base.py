from __future__ import annotations

from abc import ABC, abstractmethod

from noqlen_flux.search import ProviderHealth, SearchProviderResult, SearchQuery


class SearchProvider(ABC):
    """Generic search provider contract for Flux services."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def search(self, query: SearchQuery) -> SearchProviderResult:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> ProviderHealth:
        raise NotImplementedError
