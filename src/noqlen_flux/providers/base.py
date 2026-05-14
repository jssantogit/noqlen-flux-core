from __future__ import annotations

from abc import ABC, abstractmethod

from noqlen_flux.search import ProviderHealth, SearchProviderResult, SearchQuery
from noqlen_flux.transfers import QueuePlan, TransferRequest, TransferStatus


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


class TransferProvider(ABC):
    """Generic transfer provider contract for Flux services.

    Implementations (e.g. future SlskdProvider, NativeSoulseekProvider)
    must fulfill this contract without requiring core changes.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> ProviderHealth:
        raise NotImplementedError

    @abstractmethod
    def plan_queue(self, request: TransferRequest) -> QueuePlan:
        raise NotImplementedError

    @abstractmethod
    def get_status(self, queue_item_id: str) -> TransferStatus:
        raise NotImplementedError
