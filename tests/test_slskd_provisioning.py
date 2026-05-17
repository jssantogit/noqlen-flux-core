from __future__ import annotations

from pathlib import Path

from noqlen_flux.connections import ProviderConnectionMode
from noqlen_flux.providers.slskd_provisioning import SlskdProvisioner
from noqlen_flux.provisioning import CredentialRotationRequest, ProviderProvisioningPolicy, ProviderProvisioningRequest
from noqlen_flux.secrets import InMemorySecretStoreProvider, LocalWorkspaceSecretStoreProvider


def test_slskd_generated_api_key_has_safe_length() -> None:
    material = SlskdProvisioner().generate_api_key()

    assert len(material.reveal_once(allow=True)) >= 32


def test_managed_dry_run_writes_nothing(tmp_path: Path) -> None:
    request = ProviderProvisioningRequest(provider="slskd", mode=ProviderConnectionMode.MANAGED, workspace=tmp_path, dry_run=True)
    result = SlskdProvisioner().apply_provisioning(request, InMemorySecretStoreProvider())

    assert result.errors == []
    assert result.applied is False
    assert result.plan.restart_required is True
    assert not (tmp_path / "providers").exists()


def test_managed_apply_writes_inside_workspace_and_stores_secret(tmp_path: Path) -> None:
    store = LocalWorkspaceSecretStoreProvider(tmp_path)
    request = ProviderProvisioningRequest(
        provider="slskd",
        mode=ProviderConnectionMode.MANAGED,
        workspace=tmp_path,
        policy=ProviderProvisioningPolicy(allow_config_write=True, allow_secret_write=True),
        dry_run=False,
    )
    result = SlskdProvisioner().apply_provisioning(request, store)

    assert result.errors == []
    assert result.applied is True
    assert result.plan.app_profile.api_key_ref is not None
    assert (tmp_path / "providers" / "slskd" / "slskd.env").is_file()
    assert str(tmp_path) in result.plan.config_paths[0]
    assert "SLSKD_API_KEY_REF=" in (tmp_path / "providers" / "slskd" / "slskd.env").read_text()
    assert "slskd-api-key" not in str(result.to_dict()).lower()


def test_external_without_credential_fails_controlled() -> None:
    request = ProviderProvisioningRequest(provider="slskd", mode=ProviderConnectionMode.EXTERNAL, base_url="http://127.0.0.1:5030")
    result = SlskdProvisioner().apply_provisioning(request, InMemorySecretStoreProvider())

    assert result.applied is False
    assert result.errors == ["external slskd requires API key env or secret reference"]


def test_external_with_api_key_env_is_safe_and_writes_no_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_SLSKD_API_KEY", "external-secret-value")
    request = ProviderProvisioningRequest(
        provider="slskd",
        mode=ProviderConnectionMode.EXTERNAL,
        workspace=tmp_path,
        base_url="http://127.0.0.1:5030",
        api_key_env="TEST_SLSKD_API_KEY",
        dry_run=True,
    )
    result = SlskdProvisioner().apply_provisioning(request, InMemorySecretStoreProvider())

    assert result.errors == []
    assert result.plan.restart_required is False
    assert result.plan.metadata["writes_config"] is False
    assert not (tmp_path / "providers").exists()
    assert "external-secret-value" not in str(result.to_dict())


def test_rotation_dry_run_and_apply(tmp_path: Path) -> None:
    provisioner = SlskdProvisioner()
    store = LocalWorkspaceSecretStoreProvider(tmp_path)
    apply_request = ProviderProvisioningRequest(
        provider="slskd",
        mode=ProviderConnectionMode.MANAGED,
        workspace=tmp_path,
        policy=ProviderProvisioningPolicy(allow_config_write=True, allow_secret_write=True),
        dry_run=False,
    )
    provisioner.apply_provisioning(apply_request, store)

    dry = provisioner.rotate_credentials(CredentialRotationRequest(provider="slskd", workspace=tmp_path, dry_run=True), store)
    applied = provisioner.rotate_credentials(CredentialRotationRequest(provider="slskd", workspace=tmp_path, dry_run=False), store)

    assert dry.changed is False
    assert dry.restart_required is True
    assert applied.changed is True
    assert applied.restart_required is True
