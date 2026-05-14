import pytest

from noqlen_flux.cli import main


def test_help_exits_successfully(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert "noqlen-flux" in output
    assert "doctor" in output
    assert "quality" in output


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


def test_download_plan_fake_track_works(capsys) -> None:
    assert main(["download", "plan", "fake", "track", "--artist", "Example Artist", "--title", "Example Track"]) == 0

    output = capsys.readouterr().out
    assert "download-planning: success" in output
    assert "items: 1" in output


def test_download_plan_fake_album_works(capsys) -> None:
    assert main(["download", "plan", "fake", "album", "--artist", "Example Artist", "--album", "Example Album"]) == 0

    output = capsys.readouterr().out
    assert "download-planning: success" in output
    assert "items: 2" in output


def test_transfer_plan_fake_track_works(capsys) -> None:
    assert main(["transfer", "plan", "fake", "track", "--artist", "Example Artist", "--title", "Example Track"]) == 0

    output = capsys.readouterr().out
    assert "transfer-planning: success" in output
    assert "items: 1" in output
    assert "state: ready" in output


def test_transfer_plan_fake_album_works(capsys) -> None:
    assert main(["transfer", "plan", "fake", "album", "--artist", "Example Artist", "--album", "Example Album"]) == 0

    output = capsys.readouterr().out
    assert "transfer-planning: success" in output
    assert "items: 2" in output
    assert "state: ready" in output


def test_transfer_plan_fake_track_with_score_works(capsys) -> None:
    assert main(["transfer", "plan", "fake", "track", "--artist", "Example Artist", "--title", "Example Track", "--score"]) == 0

    output = capsys.readouterr().out
    assert "transfer-planning: success" in output


def test_transfer_plan_fake_album_with_score_works(capsys) -> None:
    assert main(["transfer", "plan", "fake", "album", "--artist", "Example Artist", "--album", "Example Album", "--score"]) == 0

    output = capsys.readouterr().out
    assert "transfer-planning: success" in output


def test_quality_fake_excellent_works(capsys) -> None:
    assert main(["quality", "fake", "excellent"]) == 0

    output = capsys.readouterr().out
    assert "quality: success" in output
    assert "grade: excellent" in output


def test_quality_fake_medium_works(capsys) -> None:
    assert main(["quality", "fake", "medium"]) == 0

    output = capsys.readouterr().out
    assert "quality: success" in output
    assert "grade: medium" in output


def test_quality_fake_bad_works(capsys) -> None:
    assert main(["quality", "fake", "bad"]) == 0

    output = capsys.readouterr().out
    assert "quality: warning" in output
    assert "grade: bad" in output


def test_quality_fake_unknown_works(capsys) -> None:
    assert main(["quality", "fake", "unknown"]) == 0

    output = capsys.readouterr().out
    assert "quality: success" in output
    assert "grade: unknown" in output


def test_quality_fake_custom_item_id_works(capsys) -> None:
    assert main(["quality", "fake", "excellent", "--item-id", "custom-item-1"]) == 0

    output = capsys.readouterr().out
    assert "quality: success" in output
    assert "grade: excellent" in output


def test_routing_fake_excellent_works(capsys) -> None:
    assert main(["routing", "fake", "excellent"]) == 0

    output = capsys.readouterr().out
    assert "routing: success" in output
    assert "approved: 1" in output


def test_routing_fake_medium_works(capsys) -> None:
    assert main(["routing", "fake", "medium"]) == 0

    output = capsys.readouterr().out
    assert "routing: success" in output
    assert "approved: 1" in output


def test_routing_fake_bad_objective_works(capsys) -> None:
    assert main(["routing", "fake", "bad-objective"]) == 0

    output = capsys.readouterr().out
    assert "routing: warning" in output
    assert "rejected: 1" in output


def test_routing_fake_bad_heuristic_works(capsys) -> None:
    assert main(["routing", "fake", "bad-heuristic"]) == 0

    output = capsys.readouterr().out
    assert "routing: warning" in output
    assert "quarantine: 1" in output


def test_routing_fake_unknown_works(capsys) -> None:
    assert main(["routing", "fake", "unknown"]) == 0

    output = capsys.readouterr().out
    assert "routing: warning" in output
    assert "review: 1" in output


def test_staging_fake_approved_works(capsys) -> None:
    assert main(["staging", "fake", "approved"]) == 0

    output = capsys.readouterr().out
    assert "staging: success" in output
    assert "staging approved: 1" in output


def test_staging_fake_quarantine_works(capsys) -> None:
    assert main(["staging", "fake", "quarantine"]) == 0

    output = capsys.readouterr().out
    assert "staging: success" in output
    assert "staging quarantine: 1" in output


def test_staging_fake_rejected_works(capsys) -> None:
    assert main(["staging", "fake", "rejected"]) == 0

    output = capsys.readouterr().out
    assert "staging: success" in output
    assert "staging rejected: 1" in output


def test_staging_fake_delete_eligible_works(capsys) -> None:
    assert main(["staging", "fake", "delete-eligible"]) == 0

    output = capsys.readouterr().out
    assert "staging: warning" in output
    assert "staging rejected: 1" in output


def test_staging_fake_review_works(capsys) -> None:
    assert main(["staging", "fake", "review"]) == 0

    output = capsys.readouterr().out
    assert "staging: success" in output
    assert "staging review: 1" in output


def test_fileops_demo_dry_run_works(tmp_path, capsys) -> None:
    workspace = tmp_path / "flux-workspace"

    assert main(["fileops", "demo", "--workspace", str(workspace), "--dry-run"]) == 0

    output = capsys.readouterr().out
    assert "fileops: success" in output
    assert "mode: dry-run" in output
    assert not workspace.exists()


def test_fileops_demo_apply_works(tmp_path, capsys) -> None:
    workspace = tmp_path / "flux-workspace"

    assert main(["fileops", "demo", "--workspace", str(workspace), "--apply"]) == 0

    output = capsys.readouterr().out
    assert "fileops: success" in output
    assert "mode: apply" in output
    assert (workspace / "incoming").is_dir()
    assert (workspace / "approved").is_dir()


def test_staging_execute_fake_approved_dry_run_works(tmp_path, capsys) -> None:
    workspace = tmp_path / "flux-workspace"

    assert main(["staging", "execute", "fake-approved", "--workspace", str(workspace), "--dry-run"]) == 0

    output = capsys.readouterr().out
    assert "staging-execution: success" in output
    assert "mode: dry-run" in output
    assert not workspace.exists()


def test_staging_execute_fake_approved_apply_works(tmp_path, capsys) -> None:
    workspace = tmp_path / "flux-workspace"

    assert main(["staging", "execute", "fake-approved", "--workspace", str(workspace), "--apply"]) == 0

    output = capsys.readouterr().out
    assert "staging-execution:" in output
    assert "mode: apply" in output
    assert (workspace / "incoming").is_dir()
    assert (workspace / "approved").is_dir()


def test_staging_execute_fake_quarantine_dry_run_works(tmp_path, capsys) -> None:
    workspace = tmp_path / "flux-workspace"

    assert main(["staging", "execute", "fake-quarantine", "--workspace", str(workspace), "--dry-run"]) == 0

    output = capsys.readouterr().out
    assert "staging-execution:" in output
    assert "mode: dry-run" in output
    assert not workspace.exists()


def test_staging_execute_fake_rejected_dry_run_works(tmp_path, capsys) -> None:
    workspace = tmp_path / "flux-workspace"

    assert main(["staging", "execute", "fake-rejected", "--workspace", str(workspace), "--dry-run"]) == 0

    output = capsys.readouterr().out
    assert "staging-execution:" in output
    assert "mode: dry-run" in output
    assert not workspace.exists()


def test_staging_execute_fake_delete_eligible_dry_run_works(tmp_path, capsys) -> None:
    workspace = tmp_path / "flux-workspace"

    assert main(["staging", "execute", "fake-delete-eligible", "--workspace", str(workspace), "--dry-run"]) == 0

    output = capsys.readouterr().out
    assert "staging-execution:" in output
    assert "mode: dry-run" in output
    assert not workspace.exists()
