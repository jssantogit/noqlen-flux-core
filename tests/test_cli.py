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


def test_report_demo_dry_run_works(tmp_path, capsys) -> None:
    workspace = tmp_path / "flux-workspace"

    assert main(["report", "demo", "--workspace", str(workspace), "--format", "json", "--dry-run"]) == 0

    output = capsys.readouterr().out
    assert "report: success" in output
    assert "Would write report" in output
    assert not workspace.exists()


def test_report_demo_apply_works(tmp_path, capsys) -> None:
    workspace = tmp_path / "flux-workspace"

    assert main(["report", "demo", "--workspace", str(workspace), "--format", "text", "--apply"]) == 0

    output = capsys.readouterr().out
    assert "report: success" in output
    assert "Wrote report" in output
    assert len(list((workspace / "reports").glob("*.txt"))) == 1


def test_search_fake_track_works(capsys) -> None:
    assert main(["search", "fake", "track", "--artist", "Example Artist", "--title", "Example Track"]) == 0

    output = capsys.readouterr().out
    assert "search: success" in output
    assert "Provider fake returned 1 candidate(s)" in output


def test_search_fake_album_works(capsys) -> None:
    assert main(["search", "fake", "album", "--artist", "Example Artist", "--album", "Example Album"]) == 0

    output = capsys.readouterr().out
    assert "search: success" in output
    assert "Provider fake returned 1 candidate(s)" in output


def test_search_fake_track_with_score_works(capsys) -> None:
    assert main(["search", "fake", "track", "--artist", "Example Artist", "--title", "Example Track", "--score"]) == 0

    output = capsys.readouterr().out
    assert "search: success" in output
    assert "score: fake-track-example" in output
    assert "risk=low" in output


def test_search_fake_album_with_score_works(capsys) -> None:
    assert main(["search", "fake", "album", "--artist", "Example Artist", "--album", "Example Album", "--score"]) == 0

    output = capsys.readouterr().out
    assert "search: success" in output
    assert "score: fake-album-example" in output
    assert "risk=low" in output


def test_musiclab_inspect_works(tmp_path, capsys) -> None:
    workspace = tmp_path / "flux-workspace"

    assert main(["musiclab", "inspect", "--workspace", str(workspace)]) == 0

    output = capsys.readouterr().out
    assert "musiclab: success" in output
    assert "Directory is missing: musiclab" in output
    assert not workspace.exists()


def test_musiclab_init_dry_run_works(tmp_path, capsys) -> None:
    workspace = tmp_path / "flux-workspace"

    assert main(["musiclab", "init", "--workspace", str(workspace), "--dry-run"]) == 0

    output = capsys.readouterr().out
    assert "musiclab: success" in output
    assert "Would create directory: musiclab" in output
    assert not workspace.exists()


def test_musiclab_init_apply_works(tmp_path, capsys) -> None:
    workspace = tmp_path / "flux-workspace"

    assert main(["musiclab", "init", "--workspace", str(workspace), "--apply"]) == 0

    output = capsys.readouterr().out
    assert "musiclab: success" in output
    assert "Created directory: musiclab" in output
    assert (workspace / "musiclab" / "sessions").is_dir()


def test_musiclab_session_create_apply_works(tmp_path, capsys) -> None:
    workspace = tmp_path / "flux-workspace"

    assert main(["musiclab", "session", "create", "--workspace", str(workspace), "--session", "session-a", "--apply"]) == 0

    output = capsys.readouterr().out
    assert "musiclab: success" in output
    assert "Created directory: musiclab-session" in output
    assert (workspace / "musiclab" / "sessions" / "session-a" / "fixtures").is_dir()


def test_musiclab_fixture_create_apply_works(tmp_path, capsys) -> None:
    workspace = tmp_path / "flux-workspace"
    assert main(["musiclab", "session", "create", "--workspace", str(workspace), "--session", "session-a", "--apply"]) == 0
    capsys.readouterr()

    assert (
        main(
            [
                "musiclab",
                "fixture",
                "create",
                "--workspace",
                str(workspace),
                "--session",
                "session-a",
                "--fixture-id",
                "good-candidate",
                "--kind",
                "candidate",
                "--apply",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "musiclab: success" in output
    assert "Wrote fake fixture: good-candidate" in output
    assert (workspace / "musiclab" / "sessions" / "session-a" / "fixtures" / "good-candidate.json").is_file()
