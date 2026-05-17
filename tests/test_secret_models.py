from __future__ import annotations

import pytest

from noqlen_flux.connections import AppConnectionBundle, ProviderAuthMode, ProviderConnectionMode, ProviderConnectionProfile
from noqlen_flux.secrets import SecretMaterial, SecretRef


def test_secret_material_redacts_repr_and_public_dict() -> None:
    material = SecretMaterial("raw-secret-value", label="api")

    assert "raw-secret-value" not in repr(material)
    assert material.to_dict()["value"] == "[redacted]"
    assert "raw-secret-value" not in str(material.to_dict())


def test_secret_material_explicit_one_time_reveal() -> None:
    material = SecretMaterial("raw-secret-value")


    with pytest.raises(PermissionError):
        material.reveal_once()
    assert material.reveal_once(allow=True) == "raw-secret-value"
    with pytest.raises(RuntimeError):
        material.reveal_once(allow=True)


def test_connection_profile_and_bundle_do_not_expose_raw_secret() -> None:
    ref = SecretRef(store="memory", key="slskd-api-key", version="1", digest="abcd")
    profile = ProviderConnectionProfile(
        provider="slskd",
        mode=ProviderConnectionMode.MANAGED,
        base_url="http://127.0.0.1:5030",
        auth_mode=ProviderAuthMode.API_KEY,
        api_key_ref=ref,
    )
    bundle = AppConnectionBundle(profile=profile)

    assert "raw-secret" not in str(profile.to_dict())
    assert "raw-secret" not in str(bundle.to_dict())
    with pytest.raises(PermissionError):
        bundle.to_dict(include_secret_material=True)
