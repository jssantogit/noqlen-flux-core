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


def test_handoff_demo_dry_run_works(tmp_path, capsys) -> None:
    workspace = tmp_path / "flux-workspace"

    assert main(["handoff", "demo", "--workspace", str(workspace), "--dry-run"]) == 0

    output = capsys.readouterr().out
    assert "handoff:" in output
    assert "dry_run: True" in output
    assert not (workspace / "manifests").exists()


def test_handoff_demo_apply_works(tmp_path, capsys) -> None:
    workspace = tmp_path / "flux-workspace"

    assert main(["handoff", "demo", "--workspace", str(workspace), "--apply"]) == 0

    output = capsys.readouterr().out
    assert "handoff:" in output
    assert "dry_run: False" in output
    assert (workspace / "manifests").is_dir()
    manifest_files = list((workspace / "manifests").glob("*.json"))
    assert len(manifest_files) == 1


def test_handoff_validate_demo_works(capsys) -> None:
    assert main(["handoff", "validate", "--workspace", "/tmp/noqlen-flux-handoff-test", "--demo"]) == 0

    output = capsys.readouterr().out
    assert "handoff: valid" in output


# --- Slskd search CLI tests ---


def test_search_slskd_track_offline_returns_error(capsys) -> None:
    assert main(["search", "slskd", "track", "--artist", "Example Artist", "--title", "Example Track", "--offline"]) == 1

    output = capsys.readouterr().out
    assert "search: failed" in output
    assert "no active client" in output.lower()


def test_search_slskd_album_offline_returns_error(capsys) -> None:
    assert main(["search", "slskd", "album", "--artist", "Example Artist", "--album", "Example Album", "--offline"]) == 1

    output = capsys.readouterr().out
    assert "search: failed" in output
    assert "no active client" in output.lower()


def test_search_slskd_track_default_is_offline(capsys) -> None:
    assert main(["search", "slskd", "track", "--artist", "Example Artist", "--title", "Example Track"]) == 1

    output = capsys.readouterr().out
    assert "search: failed" in output
    assert "no active client" in output.lower()


def test_search_slskd_album_default_is_offline(capsys) -> None:
    assert main(["search", "slskd", "album", "--artist", "Example Artist", "--album", "Example Album"]) == 1

    output = capsys.readouterr().out
    assert "search: failed" in output
    assert "no active client" in output.lower()


def test_search_slskd_track_allow_network_no_url_returns_error(capsys) -> None:
    assert main(["search", "slskd", "track", "--artist", "Example Artist", "--title", "Example Track", "--allow-network"]) == 1

    output = capsys.readouterr().out
    assert "search: failed" in output
    assert "no active client" in output.lower()


def test_search_slskd_album_allow_network_no_url_returns_error(capsys) -> None:
    assert main(["search", "slskd", "album", "--artist", "Example Artist", "--album", "Example Album", "--allow-network"]) == 1

    output = capsys.readouterr().out
    assert "search: failed" in output
    assert "no active client" in output.lower()


def test_search_slskd_track_api_key_not_printed(capsys, monkeypatch) -> None:
    monkeypatch.setenv("TEST_SLSKD_KEY", "super-secret-key-12345")

    assert main([
        "search", "slskd", "track",
        "--artist", "Example Artist",
        "--title", "Example Track",
        "--allow-network",
        "--url", "http://localhost:5000",
        "--api-key-env", "TEST_SLSKD_KEY",
    ]) == 1

    output = capsys.readouterr().out
    assert "super-secret-key-12345" not in output


def test_search_slskd_album_api_key_not_printed(capsys, monkeypatch) -> None:
    monkeypatch.setenv("TEST_SLSKD_KEY", "super-secret-key-12345")

    assert main([
        "search", "slskd", "album",
        "--artist", "Example Artist",
        "--album", "Example Album",
        "--allow-network",
        "--url", "http://localhost:5000",
        "--api-key-env", "TEST_SLSKD_KEY",
    ]) == 1

    output = capsys.readouterr().out
    assert "super-secret-key-12345" not in output


def test_search_slskd_track_with_score_offline(capsys) -> None:
    assert main([
        "search", "slskd", "track",
        "--artist", "Example Artist",
        "--title", "Example Track",
        "--offline",
        "--score",
    ]) == 1

    output = capsys.readouterr().out
    assert "search: failed" in output
    assert "no active client" in output.lower()


def test_search_slskd_track_mocked_network_succeeds(capsys, monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self) -> bytes:
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        import json
        if req.method == "POST":
            return FakeResponse(b'{"id": "search-1"}')
        if req.method == "GET" and "responses" in str(req.full_url):
            return FakeResponse(json.dumps({
                "responses": [
                    {
                        "username": "test-user",
                        "directory": "Music/Test",
                        "files": [{"filename": "test.flac", "size": 1000, "bitrate": 320, "extension": "flac", "duration": 180}],
                        "locked_files": [],
                    }
                ],
                "response_count": 1,
            }).encode())
        return FakeResponse(b'{"state": "Completed"}')

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    assert main([
        "search", "slskd", "track",
        "--artist", "Example Artist",
        "--title", "Example Track",
        "--allow-network",
        "--url", "http://localhost:5000",
    ]) == 0

    output = capsys.readouterr().out
    assert "search: success" in output
    assert "test-user" in output
    assert "test.flac" in output
    assert ".flac" in output


def test_search_slskd_album_mocked_network_succeeds(capsys, monkeypatch) -> None:
    import json

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self) -> bytes:
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        if req.method == "POST":
            return FakeResponse(b'{"id": "search-1"}')
        if req.method == "GET" and "responses" in str(req.full_url):
            return FakeResponse(json.dumps({
                "responses": [
                    {
                        "username": "album-user",
                        "directory": "Music/Artist/Album",
                        "files": [
                            {"filename": "01 Intro.flac", "size": 1000},
                            {"filename": "02 Track.flac", "size": 2000},
                        ],
                        "locked_files": [
                            {"filename": "03 Locked.flac", "size": 3000},
                        ],
                    }
                ],
                "response_count": 1,
            }).encode())
        return FakeResponse(b'{"state": "Completed"}')

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    assert main([
        "search", "slskd", "album",
        "--artist", "Example Artist",
        "--album", "Example Album",
        "--allow-network",
        "--url", "http://localhost:5000",
    ]) == 0

    output = capsys.readouterr().out
    assert "search: success" in output
    assert "album-user" in output
    assert "01 Intro.flac" in output
    assert "02 Track.flac" in output
    assert "03 Locked.flac" in output
    assert "1 locked" in output


def test_search_slskd_track_mocked_with_score(capsys, monkeypatch) -> None:
    import json

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self) -> bytes:
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        if req.method == "POST":
            return FakeResponse(b'{"id": "search-1"}')
        if req.method == "GET" and "responses" in str(req.full_url):
            return FakeResponse(json.dumps({
                "responses": [
                    {
                        "username": "score-user",
                        "directory": "Music/Test",
                        "files": [{"filename": "track.flac", "size": 1000}],
                        "locked_files": [],
                    }
                ],
                "response_count": 1,
            }).encode())
        return FakeResponse(b'{"state": "Completed"}')

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    assert main([
        "search", "slskd", "track",
        "--artist", "Example Artist",
        "--title", "Example Track",
        "--allow-network",
        "--url", "http://localhost:5000",
        "--score",
    ]) == 0

    output = capsys.readouterr().out
    assert "search: success" in output
    assert "score:" in output


def test_search_slskd_track_mocked_timeout(capsys, monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self) -> bytes:
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        if req.method == "POST":
            return FakeResponse(b'{"id": "search-1"}')
        if req.method == "GET" and "responses" not in str(req.full_url):
            return FakeResponse(b'{"state": "InProgress"}')
        return FakeResponse(b'{"responses": [], "response_count": 0}')

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    assert main([
        "search", "slskd", "track",
        "--artist", "Example Artist",
        "--title", "Example Track",
        "--allow-network",
        "--url", "http://localhost:5000",
        "--max-polls", "2",
    ]) == 0

    output = capsys.readouterr().out
    assert "search:" in output
    assert "timeout" in output.lower() or "warning" in output.lower()


def test_search_slskd_track_mocked_empty_responses(capsys, monkeypatch) -> None:
    import json

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self) -> bytes:
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        if req.method == "POST":
            return FakeResponse(b'{"id": "search-1"}')
        if req.method == "GET" and "responses" in str(req.full_url):
            return FakeResponse(b'{"responses": [], "response_count": 0}')
        return FakeResponse(b'{"state": "Completed"}')

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    assert main([
        "search", "slskd", "track",
        "--artist", "Example Artist",
        "--title", "Example Track",
        "--allow-network",
        "--url", "http://localhost:5000",
    ]) == 0

    output = capsys.readouterr().out
    assert "search:" in output
    assert "no candidates" in output.lower() or "responses: 0" in output


# --- Slskd download plan CLI tests ---


def test_download_plan_slskd_track_offline_returns_error(capsys) -> None:
    assert main(["download", "plan", "slskd", "track", "--artist", "Example Artist", "--title", "Example Track", "--offline"]) == 1

    output = capsys.readouterr().out
    assert "search: failed" in output
    assert "no active client" in output.lower()


def test_download_plan_slskd_album_offline_returns_error(capsys) -> None:
    assert main(["download", "plan", "slskd", "album", "--artist", "Example Artist", "--album", "Example Album", "--offline"]) == 1

    output = capsys.readouterr().out
    assert "search: failed" in output
    assert "no active client" in output.lower()


def test_download_plan_slskd_track_default_is_offline(capsys) -> None:
    assert main(["download", "plan", "slskd", "track", "--artist", "Example Artist", "--title", "Example Track"]) == 1

    output = capsys.readouterr().out
    assert "search: failed" in output
    assert "no active client" in output.lower()


def test_download_plan_slskd_album_default_is_offline(capsys) -> None:
    assert main(["download", "plan", "slskd", "album", "--artist", "Example Artist", "--album", "Example Album"]) == 1

    output = capsys.readouterr().out
    assert "search: failed" in output
    assert "no active client" in output.lower()


def test_download_plan_slskd_track_allow_network_no_url_returns_error(capsys) -> None:
    assert main(["download", "plan", "slskd", "track", "--artist", "Example Artist", "--title", "Example Track", "--allow-network"]) == 1

    output = capsys.readouterr().out
    assert "search: failed" in output
    assert "no active client" in output.lower()


def test_download_plan_slskd_track_api_key_not_printed(capsys, monkeypatch) -> None:
    monkeypatch.setenv("TEST_SLSKD_KEY", "super-secret-key-12345")

    assert main([
        "download", "plan", "slskd", "track",
        "--artist", "Example Artist",
        "--title", "Example Track",
        "--allow-network",
        "--url", "http://localhost:5000",
        "--api-key-env", "TEST_SLSKD_KEY",
    ]) == 1

    output = capsys.readouterr().out
    assert "super-secret-key-12345" not in output


def test_download_plan_slskd_album_api_key_not_printed(capsys, monkeypatch) -> None:
    monkeypatch.setenv("TEST_SLSKD_KEY", "super-secret-key-12345")

    assert main([
        "download", "plan", "slskd", "album",
        "--artist", "Example Artist",
        "--album", "Example Album",
        "--allow-network",
        "--url", "http://localhost:5000",
        "--api-key-env", "TEST_SLSKD_KEY",
    ]) == 1

    output = capsys.readouterr().out
    assert "super-secret-key-12345" not in output


def test_download_plan_slskd_track_mocked_network_succeeds(capsys, monkeypatch) -> None:
    import json

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self) -> bytes:
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        if req.method == "POST":
            return FakeResponse(b'{"id": "search-1"}')
        if req.method == "GET" and "responses" in str(req.full_url):
            return FakeResponse(json.dumps({
                "responses": [
                    {
                        "username": "test-user",
                        "directory": "Music/Test",
                        "files": [{"filename": "test.flac", "size": 1000, "bitrate": 320, "extension": "flac", "duration": 180}],
                        "locked_files": [],
                    }
                ],
                "response_count": 1,
            }).encode())
        return FakeResponse(b'{"state": "Completed"}')

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    assert main([
        "download", "plan", "slskd", "track",
        "--artist", "Example Artist",
        "--title", "Example Track",
        "--allow-network",
        "--url", "http://localhost:5000",
    ]) == 0

    output = capsys.readouterr().out
    assert "search: success" in output
    assert "download-planning: success" in output
    assert "planned items: 1" in output
    assert "test-user" in output
    assert "test.flac" in output


def test_download_plan_slskd_album_mocked_network_succeeds(capsys, monkeypatch) -> None:
    import json

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self) -> bytes:
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        if req.method == "POST":
            return FakeResponse(b'{"id": "search-1"}')
        if req.method == "GET" and "responses" in str(req.full_url):
            return FakeResponse(json.dumps({
                "responses": [
                    {
                        "username": "album-user",
                        "directory": "Music/Artist/Album",
                        "files": [
                            {"filename": "01 Intro.flac", "size": 1000},
                            {"filename": "02 Track.flac", "size": 2000},
                        ],
                        "locked_files": [
                            {"filename": "03 Locked.flac", "size": 3000},
                        ],
                    }
                ],
                "response_count": 1,
            }).encode())
        return FakeResponse(b'{"state": "Completed"}')

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    assert main([
        "download", "plan", "slskd", "album",
        "--artist", "Example Artist",
        "--album", "Example Album",
        "--allow-network",
        "--url", "http://localhost:5000",
    ]) == 0

    output = capsys.readouterr().out
    assert "search: success" in output
    assert "download-planning:" in output
    assert "album-user" in output
    assert "01 Intro.flac" in output
    assert "02 Track.flac" in output


def test_download_plan_slskd_track_mocked_with_score(capsys, monkeypatch) -> None:
    import json

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self) -> bytes:
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        if req.method == "POST":
            return FakeResponse(b'{"id": "search-1"}')
        if req.method == "GET" and "responses" in str(req.full_url):
            return FakeResponse(json.dumps({
                "responses": [
                    {
                        "username": "score-user",
                        "directory": "Music/Test",
                        "files": [{"filename": "track.flac", "size": 1000}],
                        "locked_files": [],
                    }
                ],
                "response_count": 1,
            }).encode())
        return FakeResponse(b'{"state": "Completed"}')

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    assert main([
        "download", "plan", "slskd", "track",
        "--artist", "Example Artist",
        "--title", "Example Track",
        "--allow-network",
        "--url", "http://localhost:5000",
        "--score",
    ]) == 0

    output = capsys.readouterr().out
    assert "search: success" in output
    assert "download-planning:" in output
    assert "score:" in output


def test_download_plan_slskd_track_mocked_score_min_blocks(capsys, monkeypatch) -> None:
    import json

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self) -> bytes:
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        if req.method == "POST":
            return FakeResponse(b'{"id": "search-1"}')
        if req.method == "GET" and "responses" in str(req.full_url):
            return FakeResponse(json.dumps({
                "responses": [
                    {
                        "username": "score-user",
                        "directory": "Music/Test",
                        "files": [{"filename": "track.flac", "size": 1000}],
                        "locked_files": [],
                    }
                ],
                "response_count": 1,
            }).encode())
        return FakeResponse(b'{"state": "Completed"}')

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    assert main([
        "download", "plan", "slskd", "track",
        "--artist", "Example Artist",
        "--title", "Example Track",
        "--allow-network",
        "--url", "http://localhost:5000",
        "--score",
        "--score-min", "99.0",
    ]) == 1

    output = capsys.readouterr().out
    assert "download-planning: failed" in output
    assert "blocked" in output.lower()


def test_download_plan_slskd_track_mocked_max_files_blocks(capsys, monkeypatch) -> None:
    import json

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self) -> bytes:
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        if req.method == "POST":
            return FakeResponse(b'{"id": "search-1"}')
        if req.method == "GET" and "responses" in str(req.full_url):
            return FakeResponse(json.dumps({
                "responses": [
                    {
                        "username": "multi-user",
                        "directory": "Music/Multi",
                        "files": [
                            {"filename": "track1.flac", "size": 1000},
                            {"filename": "track2.flac", "size": 2000},
                        ],
                        "locked_files": [],
                    }
                ],
                "response_count": 1,
            }).encode())
        return FakeResponse(b'{"state": "Completed"}')

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    assert main([
        "download", "plan", "slskd", "track",
        "--artist", "Example Artist",
        "--title", "Example Track",
        "--allow-network",
        "--url", "http://localhost:5000",
        "--max-files", "1",
    ]) == 1

    output = capsys.readouterr().out
    assert "download-planning: failed" in output
    assert "blocked" in output.lower()


def test_download_plan_slskd_track_mocked_max_total_bytes_blocks(capsys, monkeypatch) -> None:
    import json

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self) -> bytes:
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        if req.method == "POST":
            return FakeResponse(b'{"id": "search-1"}')
        if req.method == "GET" and "responses" in str(req.full_url):
            return FakeResponse(json.dumps({
                "responses": [
                    {
                        "username": "big-user",
                        "directory": "Music/Big",
                        "files": [{"filename": "big.flac", "size": 50000000}],
                        "locked_files": [],
                    }
                ],
                "response_count": 1,
            }).encode())
        return FakeResponse(b'{"state": "Completed"}')

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    assert main([
        "download", "plan", "slskd", "track",
        "--artist", "Example Artist",
        "--title", "Example Track",
        "--allow-network",
        "--url", "http://localhost:5000",
        "--max-total-bytes", "1000",
    ]) == 1

    output = capsys.readouterr().out
    assert "download-planning: failed" in output
    assert "blocked" in output.lower()


def test_download_plan_slskd_track_mocked_locked_files_blocked(capsys, monkeypatch) -> None:
    import json

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self) -> bytes:
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        if req.method == "POST":
            return FakeResponse(b'{"id": "search-1"}')
        if req.method == "GET" and "responses" in str(req.full_url):
            return FakeResponse(json.dumps({
                "responses": [
                    {
                        "username": "locked-user",
                        "directory": "Music/Locked",
                        "files": [],
                        "locked_files": [{"filename": "locked.flac", "size": 1000}],
                    }
                ],
                "response_count": 1,
            }).encode())
        return FakeResponse(b'{"state": "Completed"}')

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    assert main([
        "download", "plan", "slskd", "track",
        "--artist", "Example Artist",
        "--title", "Example Track",
        "--allow-network",
        "--url", "http://localhost:5000",
    ]) == 1

    output = capsys.readouterr().out
    assert "download-planning: failed" in output
    assert "blocked" in output.lower()
    assert "locked" in output.lower()


def test_download_plan_slskd_track_mocked_allow_locked_succeeds(capsys, monkeypatch) -> None:
    import json

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self) -> bytes:
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        if req.method == "POST":
            return FakeResponse(b'{"id": "search-1"}')
        if req.method == "GET" and "responses" in str(req.full_url):
            return FakeResponse(json.dumps({
                "responses": [
                    {
                        "username": "locked-user",
                        "directory": "Music/Locked",
                        "files": [],
                        "locked_files": [{"filename": "locked.flac", "size": 1000}],
                    }
                ],
                "response_count": 1,
            }).encode())
        return FakeResponse(b'{"state": "Completed"}')

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    assert main([
        "download", "plan", "slskd", "track",
        "--artist", "Example Artist",
        "--title", "Example Track",
        "--allow-network",
        "--url", "http://localhost:5000",
        "--allow-locked",
    ]) == 0

    output = capsys.readouterr().out
    assert "download-planning:" in output
    assert "planned items: 1" in output


def test_download_plan_slskd_track_mocked_candidate_index_out_of_range(capsys, monkeypatch) -> None:
    import json

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self) -> bytes:
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        if req.method == "POST":
            return FakeResponse(b'{"id": "search-1"}')
        if req.method == "GET" and "responses" in str(req.full_url):
            return FakeResponse(json.dumps({
                "responses": [
                    {
                        "username": "user-one",
                        "directory": "Music/One",
                        "files": [{"filename": "track1.flac", "size": 1000}],
                        "locked_files": [],
                    }
                ],
                "response_count": 1,
            }).encode())
        return FakeResponse(b'{"state": "Completed"}')

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    assert main([
        "download", "plan", "slskd", "track",
        "--artist", "Example Artist",
        "--title", "Example Track",
        "--allow-network",
        "--url", "http://localhost:5000",
        "--candidate-index", "5",
    ]) == 1

    output = capsys.readouterr().out
    assert "download-planning: failed" in output
    assert "out of range" in output.lower()


def test_download_plan_slskd_track_mocked_allowed_extension_blocks(capsys, monkeypatch) -> None:
    import json

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body
        def read(self) -> bytes:
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        if req.method == "POST":
            return FakeResponse(b'{"id": "search-1"}')
        if req.method == "GET" and "responses" in str(req.full_url):
            return FakeResponse(json.dumps({
                "responses": [
                    {
                        "username": "mp3-user",
                        "directory": "Music/Mp3",
                        "files": [{"filename": "track.mp3", "size": 5000000, "extension": "mp3"}],
                        "locked_files": [],
                    }
                ],
                "response_count": 1,
            }).encode())
        return FakeResponse(b'{"state": "Completed"}')

    monkeypatch.setattr("noqlen_flux.providers.slskd.urlopen", fake_urlopen)

    assert main([
        "download", "plan", "slskd", "track",
        "--artist", "Example Artist",
        "--title", "Example Track",
        "--allow-network",
        "--url", "http://localhost:5000",
        "--allowed-extension", "flac",
        "--allowed-extension", "wav",
    ]) == 1

    output = capsys.readouterr().out
    assert "download-planning: failed" in output
    assert "blocked" in output.lower()
