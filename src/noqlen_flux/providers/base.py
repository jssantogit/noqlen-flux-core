from __future__ import annotations

from abc import ABC, abstractmethod

from noqlen_flux.providers.status import ProviderCapability, ProviderHealth
from noqlen_flux.search import SearchProviderResult, SearchQuery
from noqlen_flux.transfers import QueuePlan, TransferExecutionRequest, TransferRequest, TransferSubmissionResult, TransferStatus


class BaseProvider(ABC):
    """Common base contract for all Flux providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def capabilities(self) -> list[ProviderCapability]:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> ProviderHealth:
        raise NotImplementedError


class SearchProvider(BaseProvider):
    """Generic search provider contract for Flux services."""

    @abstractmethod
    def search(self, query: SearchQuery) -> SearchProviderResult:
        raise NotImplementedError


class TransferProvider(BaseProvider):
    """Generic transfer provider contract for Flux services.

    Implementations (e.g. future SlskdProvider, NativeSoulseekProvider)
    must fulfill this contract without requiring core changes.
    """

    @abstractmethod
    def plan_queue(self, request: TransferRequest) -> QueuePlan:
        raise NotImplementedError

    @abstractmethod
    def get_status(self, queue_item_id: str) -> TransferStatus:
        raise NotImplementedError


class QueueExecutionProvider(BaseProvider):
    """Generic queue execution provider contract for Flux services.

    Implementations (e.g. future SlskdProvider, NativeSoulseekProvider)
    must fulfill this contract without requiring core changes.
    """

    @abstractmethod
    def submit_queue(self, request: TransferExecutionRequest) -> TransferSubmissionResult:
        raise NotImplementedError
