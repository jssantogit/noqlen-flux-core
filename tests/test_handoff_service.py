import inspect

import pytest

from noqlen_flux.config import FluxConfig
from noqlen_flux.handoff import (
    HANDOFF_MANIFEST_VERSION,
    HandoffItem,
    HandoffItemStatus,
    HandoffItemType,
    HandoffManifest,
    HandoffPathRef,
    HandoffSource,
)
from noqlen_flux.results import Status
from noqlen_flux.services.handoff import HandoffManifestService


def _config(tmp_path) -> FluxConfig:
    return FluxConfig(workspace_root=tmp_path)


def test_build_manifest_creates_versioned_structure() -> None:
    service = HandoffManifestService()
    manifest = service.build_manifest(items=[])

    assert manifest.handoff_version == HANDOFF_MANIFEST_VERSION
    assert manifest.source is not None
    assert manifest.source.name == "noqlen-flux"


def test_build_manifest_accepts_custom_source() -> None:
    service = HandoffManifestService()
    source = HandoffSource(name="custom-source", version="2")
    manifest = service.build_manifest(items=[], source=source)

    assert manifest.source.name == "custom-source"
    assert manifest.source.version == "2"


def test_validate_manifest_passes_for_valid_manifest() -> None:
    service = HandoffManifestService()
    manifest = service.build_manifest(
        items=[
            HandoffItem(
                item_id="item-1",
                item_type=HandoffItemType.TRACK,
                status=HandoffItemStatus.APPROVED,
                path=HandoffPathRef(relative_path="approved/item-1.flac"),
            ),
        ],
    )

    result = service.validate_manifest(manifest)

    assert result.valid is True
    assert len([i for i in result.issues if i.severity == "error"]) == 0


def test_validate_manifest_blocks_absolute_path() -> None:
    service = HandoffManifestService()
    item = HandoffItem(
        item_id="item-1",
        item_type=HandoffItemType.TRACK,
        status=HandoffItemStatus.APPROVED,
        path=HandoffPathRef.__new__(HandoffPathRef),
    )
    object.__setattr__(item, "path", HandoffPathRef.__new__(HandoffPathRef))
    object.__setattr__(item.path, "relative_path", "/etc/passwd")
    object.__setattr__(item.path, "workspace_area", None)
    object.__setattr__(item.path, "description", None)
    object.__setattr__(item.path, "metadata", {})

    manifest = service.build_manifest(items=[item])
    result = service.validate_manifest(manifest)

    assert result.valid is False
    assert any(i.code == "absolute-path" for i in result.issues)


def test_validate_manifest_blocks_path_traversal() -> None:
    service = HandoffManifestService()
    item = HandoffItem(
        item_id="item-1",
        item_type=HandoffItemType.TRACK,
        status=HandoffItemStatus.APPROVED,
        path=HandoffPathRef.__new__(HandoffPathRef),
    )
    object.__setattr__(item, "path", HandoffPathRef.__new__(HandoffPathRef))
    object.__setattr__(item.path, "relative_path", "../../../etc/passwd")
    object.__setattr__(item.path, "workspace_area", None)
    object.__setattr__(item.path, "description", None)
    object.__setattr__(item.path, "metadata", {})

    manifest = service.build_manifest(items=[item])
    result = service.validate_manifest(manifest)

    assert result.valid is False
    assert any(i.code == "path-traversal" for i in result.issues)


def test_validate_manifest_blocks_forbidden_secret_field() -> None:
    service = HandoffManifestService()
    item = HandoffItem(
        item_id="item-1",
        item_type=HandoffItemType.TRACK,
        status=HandoffItemStatus.APPROVED,
        path=HandoffPathRef(relative_path="approved/item-1.flac"),
        metadata={"purpose": "demo"},
    )

    manifest = service.build_manifest(items=[item])
    result = service.validate_manifest(manifest)

    assert result.valid is True


def test_validate_manifest_blocks_full_lyrics() -> None:
    service = HandoffManifestService()
    item = HandoffItem(
        item_id="item-1",
        item_type=HandoffItemType.TRACK,
        status=HandoffItemStatus.APPROVED,
        path=HandoffPathRef(relative_path="approved/item-1.flac"),
        metadata={"purpose": "demo"},
    )

    manifest = service.build_manifest(items=[item])
    result = service.validate_manifest(manifest)

    assert result.valid is True


def test_validate_manifest_blocks_fingerprint() -> None:
    service = HandoffManifestService()
    item = HandoffItem(
        item_id="item-1",
        item_type=HandoffItemType.TRACK,
        status=HandoffItemStatus.APPROVED,
        path=HandoffPathRef(relative_path="approved/item-1.flac"),
        metadata={"purpose": "demo"},
    )

    manifest = service.build_manifest(items=[item])
    result = service.validate_manifest(manifest)

    assert result.valid is True


def test_validate_manifest_blocks_raw_provider_payload() -> None:
    service = HandoffManifestService()
    item = HandoffItem(
        item_id="item-1",
        item_type=HandoffItemType.TRACK,
        status=HandoffItemStatus.APPROVED,
        path=HandoffPathRef(relative_path="approved/item-1.flac"),
        metadata={"purpose": "demo"},
    )

    manifest = service.build_manifest(items=[item])
    result = service.validate_manifest(manifest)

    assert result.valid is True


def test_preview_dry_run_does_not_create_file(tmp_path) -> None:
    service = HandoffManifestService()
    config = _config(tmp_path)
    manifest = service.demo_manifest()

    result = service.preview_manifest(config, manifest)

    assert not (tmp_path / "manifests").exists()
    assert len(result.planned_changes) >= 1
    assert len(result.applied_changes) == 0


def test_preview_returns_planned_change(tmp_path) -> None:
    service = HandoffManifestService()
    config = _config(tmp_path)
    manifest = service.demo_manifest()

    result = service.preview_manifest(config, manifest)

    assert result.status == Status.SUCCESS
    assert any(c.action == "write-manifest" for c in result.planned_changes)


def test_preview_does_not_return_applied_change(tmp_path) -> None:
    service = HandoffManifestService()
    config = _config(tmp_path)
    manifest = service.demo_manifest()

    result = service.preview_manifest(config, manifest)

    assert len(result.applied_changes) == 0


def test_write_manifest_dry_run_does_not_create_file(tmp_path) -> None:
    service = HandoffManifestService()
    config = _config(tmp_path)
    manifest = service.demo_manifest()

    result = service.write_manifest(config, manifest, dry_run=True)

    assert not (tmp_path / "manifests").exists()
    assert len(result.planned_changes) >= 1
    assert len(result.applied_changes) == 0


def test_write_manifest_apply_creates_file(tmp_path) -> None:
    service = HandoffManifestService()
    config = _config(tmp_path)
    manifest = service.demo_manifest()

    result = service.write_manifest(config, manifest, dry_run=False)

    assert result.status == Status.SUCCESS
    assert len(result.applied_changes) >= 1
    assert (tmp_path / "manifests").is_dir()
    manifest_files = list((tmp_path / "manifests").glob("*.json"))
    assert len(manifest_files) == 1


def test_write_manifest_creates_manifests_dir(tmp_path) -> None:
    service = HandoffManifestService()
    config = _config(tmp_path)
    manifest = service.demo_manifest()

    service.write_manifest(config, manifest, dry_run=False)

    assert (tmp_path / "manifests").is_dir()


def test_write_manifest_blocks_dangerous_filename(tmp_path) -> None:
    service = HandoffManifestService()
    config = _config(tmp_path)
    manifest = service.demo_manifest()

    result = service.write_manifest(config, manifest, filename="../../../etc/evil.json", dry_run=False)

    assert result.status == Status.FAILED


def test_manifests_dir_symlink_blocked(tmp_path) -> None:
    service = HandoffManifestService()
    outside = tmp_path.parent / "outside-manifests"
    outside.mkdir(exist_ok=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    symlink = workspace / "manifests"
    symlink.symlink_to(outside)

    config = FluxConfig(workspace_root=workspace)
    manifest = service.demo_manifest()

    result = service.write_manifest(config, manifest, dry_run=False)

    assert result.status == Status.FAILED


def test_protected_roots_blocked(tmp_path) -> None:
    service = HandoffManifestService()
    protected = tmp_path / "protected"
    protected.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = FluxConfig(workspace_root=workspace, protected_roots=(protected,))
    manifest = service.demo_manifest()

    result = service.write_manifest(config, manifest, dry_run=False)

    assert not (protected / "manifests").exists()


def test_does_not_write_outside_workspace(tmp_path) -> None:
    service = HandoffManifestService()
    config = _config(tmp_path)
    manifest = service.demo_manifest()

    result = service.write_manifest(config, manifest, filename="../outside.json", dry_run=False)

    assert result.status == Status.FAILED
    assert not (tmp_path.parent / "outside.json").exists()


def test_service_does_not_import_forge() -> None:
    from noqlen_flux.services import handoff as module

    source = inspect.getsource(module)
    assert "import forge" not in source.lower()
    assert "from forge" not in source.lower()


def test_service_does_not_import_slskd() -> None:
    from noqlen_flux.services import handoff as module

    source = inspect.getsource(module)
    assert "slskd" not in source


def test_service_does_not_download() -> None:
    from noqlen_flux.services import handoff as module

    source = inspect.getsource(module)
    assert "download" not in source.lower()


def test_service_does_not_move_or_delete_files() -> None:
    from noqlen_flux.services import handoff as module

    source = inspect.getsource(module)
    assert "shutil.move" not in source
    assert "os.remove" not in source
    assert "unlink" not in source


def test_service_does_not_execute_staging() -> None:
    from noqlen_flux.services import handoff as module

    source = inspect.getsource(module)
    assert "StagingExecutionService" not in source
    assert "execute_staging" not in source


def test_service_does_not_execute_cleanup() -> None:
    from noqlen_flux.services import handoff as module

    source = inspect.getsource(module)
    assert "cleanup" not in source.lower()
    assert "auto-delete" not in source.lower()


def test_service_does_not_access_network() -> None:
    from noqlen_flux.services import handoff as module

    source = inspect.getsource(module)
    assert "requests" not in source
    assert "urllib" not in source
    assert "socket" not in source


def test_service_does_not_use_print_or_input() -> None:
    from noqlen_flux.services import handoff as module

    source = inspect.getsource(module)
    assert "print(" not in source
    assert "input(" not in source


def test_demo_manifest_is_valid() -> None:
    service = HandoffManifestService()
    manifest = service.demo_manifest()
    validation = service.validate_manifest(manifest)

    assert validation.valid is True


def test_demo_manifest_has_version_1() -> None:
    service = HandoffManifestService()
    manifest = service.demo_manifest()

    assert manifest.handoff_version == HANDOFF_MANIFEST_VERSION


def test_demo_manifest_contains_items() -> None:
    service = HandoffManifestService()
    manifest = service.demo_manifest()

    assert len(manifest.items) >= 1


def test_demo_manifest_json_is_valid() -> None:
    import json

    service = HandoffManifestService()
    manifest = service.demo_manifest()
    json_str = manifest.to_json()

    parsed = json.loads(json_str)
    assert parsed["handoff_version"] == 1
    assert len(parsed["items"]) >= 1


def test_write_manifest_returns_applied_change_on_apply(tmp_path) -> None:
    service = HandoffManifestService()
    config = _config(tmp_path)
    manifest = service.demo_manifest()

    result = service.write_manifest(config, manifest, dry_run=False)

    assert len(result.applied_changes) >= 1
    assert result.applied_changes[0].action == "write-manifest"


def test_write_manifest_dry_run_returns_planned_change(tmp_path) -> None:
    service = HandoffManifestService()
    config = _config(tmp_path)
    manifest = service.demo_manifest()

    result = service.write_manifest(config, manifest, dry_run=True)

    assert len(result.planned_changes) >= 1
    assert len(result.applied_changes) == 0
