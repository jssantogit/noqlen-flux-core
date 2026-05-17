from __future__ import annotations

from noqlen_flux.connections import ProviderConnectionMode
from noqlen_flux.provisioning import ProviderProvisioningPolicy, ProviderProvisioningRequest


def test_provisioning_request_public_dict_is_safe(tmp_path) -> None:
    request = ProviderProvisioningRequest(
        provider="slskd",
        mode=ProviderConnectionMode.MANAGED,
        workspace=tmp_path,
        policy=ProviderProvisioningPolicy(allow_config_write=True, allow_secret_write=True),
    )

    data = request.to_dict()
    assert data["provider"] == "slskd"
    assert data["mode"] == "managed"
    assert "raw-secret" not in str(data).lower()
