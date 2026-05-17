from __future__ import annotations

from noqlen_flux.connections import ProviderConnectionMode
from noqlen_flux.providers.fake_provisioning import FakeProvisionerProvider
from noqlen_flux.provisioning import ProviderProvisioningPolicy, ProviderProvisioningRequest
from noqlen_flux.secrets import InMemorySecretStoreProvider
from noqlen_flux.services.provisioning import ProviderProvisioningService
from noqlen_flux.results import Status


def test_provider_provisioning_service_is_provider_agnostic(tmp_path) -> None:
    service = ProviderProvisioningService()
    request = ProviderProvisioningRequest(
        provider="fake",
        mode=ProviderConnectionMode.MANAGED,
        workspace=tmp_path,
        policy=ProviderProvisioningPolicy(allow_secret_write=True),
        dry_run=False,
    )
    result = service.apply(request, FakeProvisionerProvider(), InMemorySecretStoreProvider())

    assert result.status == Status.SUCCESS
    assert result.summary["provider"] == "fake"
    assert "fake-provider-secret-material" not in result.to_json()
