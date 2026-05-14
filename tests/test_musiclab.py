import json
from pathlib import Path

from noqlen_flux.config import FluxConfig
from noqlen_flux.musiclab import MusicLabFixture, MusicLabLayout, MusicLabSession
from noqlen_flux.results import Status
from noqlen_flux.services import MusicLabService


MUSICLAB_DIRS = ("sessions", "fixtures", "reports", "tmp")
SESSION_DIRS = ("fixtures", "reports", "tmp")


def test_musiclab_session_serializes_safe_data(tmp_path: Path) -> None:
    session = MusicLabSession(
        session_id="safe-session",
        workspace_root=tmp_path / "workspace",
        lab_root=tmp_path / "workspace" / "musiclab",
        purpose="scoring calibration",
        metadata={"api_token": "secret", "safe": True},
    )

    payload = session.to_dict()

    assert payload["session_id"] == "safe-session"
    assert payload["workspace_root"].endswith("workspace")
    assert payload["metadata"]["api_token"] == "[redacted]"
    assert payload["metadata"]["safe"] is True


def test_musiclab_fixture_does_not_require_real_path() -> None:
    fixture = MusicLabFixture("good-candidate", "candidate", "controlled fake fixture")

    payload = fixture.to_dict()

    assert payload["fixture_id"] == "good-candidate"
    assert payload["relative_path"] is None


def test_inspect_lab_does_not_create_directories(tmp_path: Path) -> None:
    workspace = tmp_path / "flux-workspace"

    result = MusicLabService().inspect_lab(FluxConfig(workspace))

    assert result.status == Status.SUCCESS
    assert not workspace.exists()
    assert result.planned_changes == []
    assert result.applied_changes == []


def test_init_lab_dry_run_does_not_create_directories(tmp_path: Path) -> None:
    workspace = tmp_path / "flux-workspace"

    result = MusicLabService().init_lab(FluxConfig(workspace), dry_run=True)

    assert result.status == Status.SUCCESS
    assert not workspace.exists()
    assert len(result.planned_changes) == 5
    assert result.applied_changes == []


def test_init_lab_apply_creates_musiclab_layout(tmp_path: Path) -> None:
    workspace = tmp_path / "flux-workspace"

    result = MusicLabService().init_lab(FluxConfig(workspace, dry_run=False), dry_run=False)

    assert result.status == Status.SUCCESS
    assert (workspace / "musiclab").is_dir()
    for directory in MUSICLAB_DIRS:
        assert (workspace / "musiclab" / directory).is_dir()
    assert len(result.applied_changes) == 5


def test_init_lab_apply_is_idempotent(tmp_path: Path) -> None:
    workspace = tmp_path / "flux-workspace"
    service = MusicLabService()

    first = service.init_lab(FluxConfig(workspace, dry_run=False), dry_run=False)
    second = service.init_lab(FluxConfig(workspace, dry_run=False), dry_run=False)

    assert first.status == Status.SUCCESS
    assert second.status == Status.SUCCESS
    assert second.applied_changes == []
    assert all(step.status == Status.SKIPPED for step in second.steps)


def test_create_session_dry_run_does_not_create_directories(tmp_path: Path) -> None:
    workspace = tmp_path / "flux-workspace"

    result = MusicLabService().create_session(FluxConfig(workspace), session_id="session-a", dry_run=True)

    assert result.status == Status.SUCCESS
    assert not workspace.exists()
    assert len(result.planned_changes) == 6
    assert result.summary["session_id"] == "session-a"


def test_create_session_apply_creates_session_and_subdirectories(tmp_path: Path) -> None:
    workspace = tmp_path / "flux-workspace"

    result = MusicLabService().create_session(FluxConfig(workspace, dry_run=False), session_id="session-a", purpose="quality", dry_run=False)

    session_root = workspace / "musiclab" / "sessions" / "session-a"
    assert result.status == Status.SUCCESS
    assert session_root.is_dir()
    for directory in SESSION_DIRS:
        assert (session_root / directory).is_dir()
    assert any(artifact.kind == "musiclab-session" for artifact in result.artifacts)


def test_session_id_traversal_is_blocked(tmp_path: Path) -> None:
    result = MusicLabService().create_session(FluxConfig(tmp_path / "workspace"), session_id="../escape", dry_run=True)

    assert result.status == Status.FAILED
    assert any(error.code == "unsafe-session-id" for error in result.errors)
    assert not (tmp_path / "escape").exists()


def test_fixture_id_traversal_is_blocked(tmp_path: Path) -> None:
    workspace = tmp_path / "flux-workspace"
    service = MusicLabService()
    service.create_session(FluxConfig(workspace, dry_run=False), session_id="session-a", dry_run=False)

    result = service.create_fake_fixture(
        FluxConfig(workspace, dry_run=False),
        session_id="session-a",
        fixture_id="../escape",
        kind="candidate",
        dry_run=False,
    )

    assert result.status == Status.FAILED
    assert any(error.code == "unsafe-fixture-id" for error in result.errors)
    assert not (tmp_path / "escape.json").exists()


def test_create_fake_fixture_dry_run_does_not_write_file(tmp_path: Path) -> None:
    workspace = tmp_path / "flux-workspace"
    service = MusicLabService()
    service.create_session(FluxConfig(workspace, dry_run=False), session_id="session-a", dry_run=False)

    result = service.create_fake_fixture(FluxConfig(workspace), "session-a", "good-candidate", "candidate", dry_run=True)

    fixture_path = workspace / "musiclab" / "sessions" / "session-a" / "fixtures" / "good-candidate.json"
    assert result.status == Status.SUCCESS
    assert result.planned_changes
    assert not fixture_path.exists()


def test_create_fake_fixture_apply_writes_controlled_json_inside_session(tmp_path: Path) -> None:
    workspace = tmp_path / "flux-workspace"
    service = MusicLabService()
    service.create_session(FluxConfig(workspace, dry_run=False), session_id="session-a", dry_run=False)

    result = service.create_fake_fixture(FluxConfig(workspace, dry_run=False), "session-a", "good-candidate", "candidate", dry_run=False)

    fixture_path = workspace / "musiclab" / "sessions" / "session-a" / "fixtures" / "good-candidate.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert result.status == Status.SUCCESS
    assert payload["fixture_id"] == "good-candidate"
    assert payload["metadata"]["downloads"] is False
    assert payload["metadata"]["audio"] is False


def test_musiclab_symlink_escape_is_blocked(tmp_path: Path) -> None:
    workspace = tmp_path / "flux-workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "musiclab").symlink_to(outside, target_is_directory=True)

    result = MusicLabService().init_lab(FluxConfig(workspace, dry_run=False), dry_run=False)

    assert result.status == Status.FAILED
    assert any(error.code == "path-outside-workspace" for error in result.errors)


def test_musiclab_session_symlink_escape_is_blocked(tmp_path: Path) -> None:
    workspace = tmp_path / "flux-workspace"
    outside = tmp_path / "outside"
    layout = MusicLabLayout.from_workspace(workspace)
    (layout.sessions_dir).mkdir(parents=True)
    outside.mkdir()
    (layout.sessions_dir / "session-a").symlink_to(outside, target_is_directory=True)

    result = MusicLabService().create_session(FluxConfig(workspace, dry_run=False), session_id="session-a", dry_run=False)

    assert result.status == Status.FAILED
    assert any(error.code == "path-outside-workspace" for error in result.errors)


def test_musiclab_protected_roots_are_blocked(tmp_path: Path) -> None:
    workspace = tmp_path / "protected" / "flux-workspace"

    result = MusicLabService().init_lab(
        FluxConfig(workspace, dry_run=False, protected_roots=(tmp_path / "protected",)),
        dry_run=False,
    )

    assert result.status == Status.FAILED
    assert result.errors[0].code == "protected-root"
