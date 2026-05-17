from __future__ import annotations

from noqlen_flux.cli import main


def test_cli_provider_provision_slskd_managed_dry_run(tmp_path, capsys) -> None:
    assert main(["provider", "provision", "slskd", "--managed", "--workspace", str(tmp_path), "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "provider-provisioning: success" in output
    assert "restart_required: True" in output
    assert not (tmp_path / "providers").exists()


def test_cli_provider_provision_slskd_managed_apply_redacts_key(tmp_path, capsys) -> None:
    assert main(["provider", "provision", "slskd", "--managed", "--workspace", str(tmp_path), "--apply"]) == 0
    output = capsys.readouterr().out
    assert "provider-provisioning: success" in output
    assert "api_key_ref:" in output
    assert "SLSKD_API_KEY" not in output
    assert (tmp_path / "providers" / "slskd" / "slskd.env").is_file()


def test_cli_provider_provision_slskd_external_dry_run(monkeypatch, capsys) -> None:
    monkeypatch.setenv("TEST_SLSKD_API_KEY", "test-secret-value-for-cli-only")
    assert main(["provider", "provision", "slskd", "--external", "--url", "http://127.0.0.1:5030", "--api-key-env", "TEST_SLSKD_API_KEY", "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "provider-provisioning: success" in output
    assert "test-secret-value-for-cli-only" not in output


def test_cli_provider_credentials_rotate(tmp_path, capsys) -> None:
    assert main(["provider", "provision", "slskd", "--managed", "--workspace", str(tmp_path), "--apply"]) == 0
    capsys.readouterr()
    assert main(["provider", "credentials", "rotate", "slskd", "--workspace", str(tmp_path), "--dry-run"]) == 0
    dry = capsys.readouterr().out
    assert "provider-credential-rotation: success" in dry
    assert main(["provider", "credentials", "rotate", "slskd", "--workspace", str(tmp_path), "--apply"]) == 0
    applied = capsys.readouterr().out
    assert "provider-credential-rotation: success" in applied
