from __future__ import annotations

from abc import ABC, abstractmethod

from noqlen_flux.connections import ProviderConnectionProfile
from noqlen_flux.providers.status import ProviderCapability, ProviderHealth
from noqlen_flux.provisioning import (
    CredentialRotationRequest,
    CredentialRotationResult,
    ProviderProvisioningPlan,
    ProviderProvisioningRequest,
    ProviderProvisioningResult,
)
from noqlen_flux.search import SearchProviderResult, SearchQuery
from noqlen_flux.secrets import SecretDescriptor, SecretMaterial, SecretRef
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


class SecretStoreProvider(ABC):
    """Generic secret store contract for provider provisioning."""

    @abstractmethod
    def store_secret(self, key: str, material: SecretMaterial, *, label: str | None = None) -> SecretRef:
        raise NotImplementedError

    @abstractmethod
    def get_secret(self, ref: SecretRef) -> SecretMaterial:
        raise NotImplementedError

    @abstractmethod
    def rotate_secret(self, ref: SecretRef, material: SecretMaterial, *, dry_run: bool = True) -> SecretRef:
        raise NotImplementedError

    @abstractmethod
    def delete_secret(self, ref: SecretRef) -> SecretRef:
        raise NotImplementedError

    @abstractmethod
    def describe_secret(self, ref: SecretRef) -> SecretDescriptor:
        raise NotImplementedError


class ProviderProvisioner(BaseProvider):
    """Generic provider provisioning contract for app connection setup."""

    @abstractmethod
    def build_provisioning_plan(self, request: ProviderProvisioningRequest) -> ProviderProvisioningPlan:
        raise NotImplementedError

    @abstractmethod
    def apply_provisioning(self, request: ProviderProvisioningRequest, secret_store: SecretStoreProvider) -> ProviderProvisioningResult:
        raise NotImplementedError

    @abstractmethod
    def rotate_credentials(self, request: CredentialRotationRequest, secret_store: SecretStoreProvider) -> CredentialRotationResult:
        raise NotImplementedError

    @abstractmethod
    def validate_connection_profile(self, profile: ProviderConnectionProfile, secret_store: SecretStoreProvider) -> ProviderProvisioningResult:
        raise NotImplementedError
