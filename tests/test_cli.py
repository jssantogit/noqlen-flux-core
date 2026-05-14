import pytest

from noqlen_flux.cli import main


def test_help_exits_successfully(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert "noqlen-flux" in output
    assert "doctor" in output


def test_doctor_is_safe_stub(capsys) -> None:
    assert main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "doctor: success" in output
    assert "not implemented" in output


def test_workspace_init_dry_run_works(tmp_path, capsys) -> None:
    workspace = tmp_path / "flux-workspace"

    assert main(["workspace", "init", str(workspace), "--dry-run"]) == 0

    output = capsys.readouterr().out
    assert "workspace: success" in output
    assert "Would create directory: incoming" in output
    assert not workspace.exists()


def test_workspace_init_apply_works(tmp_path, capsys) -> None:
    workspace = tmp_path / "flux-workspace"

    assert main(["workspace", "init", str(workspace), "--apply"]) == 0

    output = capsys.readouterr().out
    assert "workspace: success" in output
    assert "Created directory: incoming" in output
    assert (workspace / "incoming").is_dir()
