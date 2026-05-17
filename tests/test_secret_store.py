from __future__ import annotations

import stat

import pytest

from noqlen_flux.secrets import InMemorySecretStoreProvider, LocalWorkspaceSecretStoreProvider, SecretMaterial, SecretState


def test_in_memory_secret_store_lifecycle() -> None:
    store = InMemorySecretStoreProvider()
    ref = store.store_secret("slskd-api-key", SecretMaterial("first-secret"))

    assert store.describe_secret(ref).ref.key == "slskd-api-key"
    assert store.get_secret(ref).reveal_once(allow=True) == "first-secret"
    dry_ref = store.rotate_secret(ref, SecretMaterial("second-secret"), dry_run=True)
    assert dry_ref.version == "dry-run"
    assert store.get_secret(ref).reveal_once(allow=True) == "first-secret"
    new_ref = store.rotate_secret(ref, SecretMaterial("second-secret"), dry_run=False)
    descriptor = store.describe_secret(new_ref)
    assert descriptor.rotated_from is not None
    assert descriptor.rotated_from.state == SecretState.ROTATED
    assert store.get_secret(new_ref).reveal_once(allow=True) == "second-secret"
    deleted = store.delete_secret(new_ref)
    assert deleted.state == SecretState.DELETED
    with pytest.raises(KeyError):
        store.get_secret(new_ref)


def test_local_workspace_secret_store_confined_and_restricted(tmp_path) -> None:
    store = LocalWorkspaceSecretStoreProvider(tmp_path)
    ref = store.store_secret("slskd-api-key", SecretMaterial("local-secret"))
    files = list((tmp_path / ".flux" / "secrets").glob("*.json"))

    assert len(files) == 1
    assert files[0].resolve().is_relative_to(tmp_path.resolve())
    assert stat.S_IMODE(files[0].stat().st_mode) & 0o077 == 0
    reloaded = LocalWorkspaceSecretStoreProvider(tmp_path)
    assert reloaded.get_secret(ref).reveal_once(allow=True) == "local-secret"
