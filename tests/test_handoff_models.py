import json

import pytest

from noqlen_flux.handoff import (
    HANDOFF_MANIFEST_VERSION,
    HandoffCandidateRef,
    HandoffItem,
    HandoffItemStatus,
    HandoffItemType,
    HandoffManifest,
    HandoffPathRef,
    HandoffQualityRef,
    HandoffReportRef,
    HandoffRoutingRef,
    HandoffSource,
    HandoffValidationIssue,
    HandoffValidationResult,
    _FORBIDDEN_FIELDS,
    validate_relative_path,
    validate_safe_metadata,
)


def test_handoff_manifest_version_is_1() -> None:
    assert HANDOFF_MANIFEST_VERSION == 1


def test_handoff_item_type_enum_values() -> None:
    assert HandoffItemType.TRACK.value == "track"
    assert HandoffItemType.ALBUM.value == "album"
    assert HandoffItemType.UNKNOWN.value == "unknown"


def test_handoff_item_status_enum_values() -> None:
    assert HandoffItemStatus.APPROVED.value == "approved"
    assert HandoffItemStatus.QUARANTINE.value == "quarantine"
    assert HandoffItemStatus.REJECTED.value == "rejected"
    assert HandoffItemStatus.REVIEW.value == "review"
    assert HandoffItemStatus.DELETE_ELIGIBLE.value == "delete_eligible"
    assert HandoffItemStatus.UNKNOWN.value == "unknown"


def test_handoff_item_represents_approved_with_relative_path() -> None:
    item = HandoffItem(
        item_id="item-1",
        item_type=HandoffItemType.TRACK,
        status=HandoffItemStatus.APPROVED,
        path=HandoffPathRef(
            relative_path="approved/item-1.flac",
            workspace_area="approved",
        ),
    )

    assert item.item_id == "item-1"
    assert item.status == HandoffItemStatus.APPROVED
    assert item.path.relative_path == "approved/item-1.flac"


def test_handoff_quality_ref_no_raw_audio_data() -> None:
    ref = HandoffQualityRef(
        grade="excellent",
        confidence=0.95,
        finding_count=0,
        objective_failure_count=0,
        heuristic_warning_count=0,
    )

    payload = ref.to_dict()
    assert payload["grade"] == "excellent"
    assert payload["confidence"] == 0.95
    assert "raw_audio" not in payload
    assert "fingerprint" not in payload


def test_handoff_candidate_ref_no_raw_payload() -> None:
    ref = HandoffCandidateRef(
        candidate_id="cand-1",
        provider="fake",
        risk="low",
        score=0.90,
    )

    payload = ref.to_dict()
    assert payload["candidate_id"] == "cand-1"
    assert payload["provider"] == "fake"
    assert "raw_payload" not in payload
    assert "provider_payload" not in payload


def test_handoff_manifest_to_json_is_stable_and_safe() -> None:
    manifest = HandoffManifest(
        handoff_version=HANDOFF_MANIFEST_VERSION,
        source=HandoffSource(name="noqlen-flux", version="1"),
        items=[],
    )

    json_str = manifest.to_json()
    parsed = json.loads(json_str)

    assert parsed["handoff_version"] == 1
    assert parsed["source"]["name"] == "noqlen-flux"
    assert isinstance(json_str, str)
    assert len(json_str) > 0


def test_handoff_manifest_serializes_safely() -> None:
    manifest = HandoffManifest(
        handoff_version=HANDOFF_MANIFEST_VERSION,
        source=HandoffSource(
            name="noqlen-flux",
            metadata={"purpose": "demo", "status": "test"},
        ),
        items=[],
    )

    payload = manifest.to_dict()
    assert payload["source"]["name"] == "noqlen-flux"
    assert payload["source"]["metadata"]["purpose"] == "demo"


def test_metadata_sensitive_fields_are_redacted() -> None:
    item = HandoffItem(
        item_id="item-1",
        item_type=HandoffItemType.TRACK,
        status=HandoffItemStatus.APPROVED,
        path=HandoffPathRef(relative_path="approved/item-1.flac"),
        metadata={"purpose": "demo", "status": "test"},
    )

    payload = item.to_dict()
    assert payload["metadata"]["purpose"] == "demo"
    assert payload["metadata"]["status"] == "test"


def test_validate_relative_path_accepts_safe_path() -> None:
    result = validate_relative_path("approved/item-1.flac")
    assert result == "approved/item-1.flac"


def test_validate_relative_path_blocks_absolute_path() -> None:
    with pytest.raises(ValueError, match="Absolute paths"):
        validate_relative_path("/etc/passwd")


def test_validate_relative_path_blocks_traversal() -> None:
    with pytest.raises(ValueError, match="Path traversal marker"):
        validate_relative_path("../../../etc/passwd")


def test_validate_safe_metadata_blocks_forbidden_fields() -> None:
    for forbidden in _FORBIDDEN_FIELDS:
        with pytest.raises(ValueError, match="Forbidden field"):
            validate_safe_metadata({forbidden: "value"})


def test_validate_safe_metadata_accepts_clean_metadata() -> None:
    result = validate_safe_metadata({"purpose": "demo", "status": "test"})
    assert result == {"purpose": "demo", "status": "test"}


def test_handoff_path_ref_blocks_absolute_path() -> None:
    with pytest.raises(ValueError, match="Absolute paths"):
        HandoffPathRef(relative_path="/etc/passwd")


def test_handoff_path_ref_blocks_traversal() -> None:
    with pytest.raises(ValueError, match="Path traversal marker"):
        HandoffPathRef(relative_path="../../../tmp/evil")


def test_handoff_manifest_has_version_1() -> None:
    manifest = HandoffManifest()
    assert manifest.handoff_version == HANDOFF_MANIFEST_VERSION


def test_handoff_source_has_created_at() -> None:
    source = HandoffSource(name="noqlen-flux")
    assert source.created_at is not None


def test_handoff_validation_result_serializes() -> None:
    result = HandoffValidationResult(
        valid=True,
        issues=[],
        warnings=[],
        errors=[],
    )

    payload = result.to_dict()
    assert payload["valid"] is True


def test_handoff_validation_issue_serializes() -> None:
    issue = HandoffValidationIssue(
        code="test-issue",
        message="Test issue message",
        severity="error",
        item_id="item-1",
    )

    payload = issue.to_dict()
    assert payload["code"] == "test-issue"
    assert payload["message"] == "Test issue message"
    assert payload["severity"] == "error"
    assert payload["item_id"] == "item-1"


def test_handoff_report_ref_blocks_absolute_path() -> None:
    with pytest.raises(ValueError, match="Absolute paths"):
        HandoffReportRef(kind="test", relative_path="/etc/passwd")


def test_handoff_item_status_converts_from_string() -> None:
    item = HandoffItem(
        item_id="item-1",
        item_type="track",
        status="approved",
        path=HandoffPathRef(relative_path="approved/item-1.flac"),
    )

    assert item.item_type == HandoffItemType.TRACK
    assert item.status == HandoffItemStatus.APPROVED


def test_handoff_manifest_to_dict_is_clean() -> None:
    manifest = HandoffManifest(
        handoff_version=HANDOFF_MANIFEST_VERSION,
        source=HandoffSource(name="noqlen-flux"),
        items=[
            HandoffItem(
                item_id="item-1",
                item_type=HandoffItemType.TRACK,
                status=HandoffItemStatus.APPROVED,
                path=HandoffPathRef(relative_path="approved/item-1.flac"),
            ),
        ],
    )

    payload = manifest.to_dict()
    assert payload["handoff_version"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["item_id"] == "item-1"
    assert payload["items"][0]["path"]["relative_path"] == "approved/item-1.flac"


def test_handoff_manifest_blocks_forbidden_metadata() -> None:
    with pytest.raises(ValueError, match="Forbidden field"):
        HandoffManifest(
            handoff_version=HANDOFF_MANIFEST_VERSION,
            metadata={"full_lyrics": "some lyrics"},
        )


def test_handoff_item_blocks_forbidden_metadata() -> None:
    with pytest.raises(ValueError, match="Forbidden field"):
        HandoffItem(
            item_id="item-1",
            item_type=HandoffItemType.TRACK,
            status=HandoffItemStatus.APPROVED,
            path=HandoffPathRef(relative_path="approved/item-1.flac"),
            metadata={"raw_provider_payload": "data"},
        )


def test_handoff_item_blocks_forbidden_query_metadata() -> None:
    with pytest.raises(ValueError, match="Forbidden field"):
        HandoffItem(
            item_id="item-1",
            item_type=HandoffItemType.TRACK,
            status=HandoffItemStatus.APPROVED,
            path=HandoffPathRef(relative_path="approved/item-1.flac"),
            query_metadata={"fingerprint": "raw-data"},
        )
