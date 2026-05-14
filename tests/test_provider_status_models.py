from datetime import datetime, timezone

from noqlen_flux.providers.status import (
    ProviderAvailability,
    ProviderCapability,
    ProviderCapabilityReport,
    ProviderHealth,
    ProviderKind,
    ProviderStatus,
)


def test_provider_kind_values() -> None:
    assert ProviderKind.FAKE.value == "fake"
    assert ProviderKind.LAB.value == "lab"
    assert ProviderKind.EXTERNAL.value == "external"
    assert ProviderKind.NATIVE.value == "native"
    assert ProviderKind.UNKNOWN.value == "unknown"


def test_provider_capability_values() -> None:
    assert ProviderCapability.SEARCH.value == "search"
    assert ProviderCapability.DOWNLOAD_PLANNING.value == "download_planning"
    assert ProviderCapability.QUEUE_PLANNING.value == "queue_planning"
    assert ProviderCapability.TRANSFER_STATUS.value == "transfer_status"
    assert ProviderCapability.HEALTH.value == "health"
    assert ProviderCapability.ARTIFACTS.value == "artifacts"
    assert ProviderCapability.UNKNOWN.value == "unknown"


def test_provider_availability_values() -> None:
    assert ProviderAvailability.AVAILABLE.value == "available"
    assert ProviderAvailability.DEGRADED.value == "degraded"
    assert ProviderAvailability.UNAVAILABLE.value == "unavailable"
    assert ProviderAvailability.UNKNOWN.value == "unknown"


def test_provider_health_serializes() -> None:
    health = ProviderHealth(
        provider="test-provider",
        kind=ProviderKind.FAKE,
        availability=ProviderAvailability.AVAILABLE,
        status_message="all good",
        capabilities=[ProviderCapability.SEARCH, ProviderCapability.HEALTH],
        warnings=["minor warning"],
        errors=[],
        metadata={"extra": "data"},
    )

    data = health.to_dict()

    assert data["provider"] == "test-provider"
    assert data["kind"] == "fake"
    assert data["availability"] == "available"
    assert data["status_message"] == "all good"
    assert data["capabilities"] == ["search", "health"]
    assert data["warnings"] == ["minor warning"]
    assert data["errors"] == []
    assert data["metadata"]["extra"] == "data"


def test_provider_health_requires_provider() -> None:
    try:
        ProviderHealth(provider="  ")
        assert False, "should have raised"
    except ValueError:
        pass


def test_provider_health_defaults() -> None:
    health = ProviderHealth(provider="minimal")

    assert health.kind == ProviderKind.UNKNOWN
    assert health.availability == ProviderAvailability.UNKNOWN
    assert health.capabilities == []
    assert health.warnings == []
    assert health.errors == []
    assert health.metadata == {}


def test_provider_status_serializes() -> None:
    health = ProviderHealth(
        provider="test",
        kind=ProviderKind.FAKE,
        availability=ProviderAvailability.AVAILABLE,
    )
    status = ProviderStatus(
        provider="test",
        health=health,
        active_transfers=3,
        queued_items=7,
    )

    data = status.to_dict()

    assert data["provider"] == "test"
    assert data["health"]["provider"] == "test"
    assert data["active_transfers"] == 3
    assert data["queued_items"] == 7
    assert "last_checked_at" in data


def test_provider_status_auto_sets_timestamp() -> None:
    health = ProviderHealth(provider="test")
    status = ProviderStatus(provider="test", health=health)

    assert status.last_checked_at is not None
    assert isinstance(status.last_checked_at, datetime)


def test_provider_status_requires_provider() -> None:
    health = ProviderHealth(provider="ok")
    try:
        ProviderStatus(provider="  ", health=health)
        assert False, "should have raised"
    except ValueError:
        pass


def test_provider_capability_report_lists_unsupported() -> None:
    report = ProviderCapabilityReport(
        provider="test",
        capabilities=[ProviderCapability.SEARCH],
        unsupported_capabilities=[ProviderCapability.DOWNLOAD_PLANNING, ProviderCapability.HEALTH],
        warnings=["download_planning not supported"],
    )

    data = report.to_dict()

    assert data["capabilities"] == ["search"]
    assert data["unsupported_capabilities"] == ["download_planning", "health"]
    assert data["warnings"] == ["download_planning not supported"]


def test_provider_capability_report_requires_provider() -> None:
    try:
        ProviderCapabilityReport(provider="  ")
        assert False, "should have raised"
    except ValueError:
        pass


def test_provider_capability_report_defaults() -> None:
    report = ProviderCapabilityReport(provider="minimal")

    assert report.capabilities == []
    assert report.unsupported_capabilities == []
    assert report.warnings == []
    assert report.metadata == {}


def test_provider_health_metadata_is_safe() -> None:
    health = ProviderHealth(
        provider="test",
        metadata={"display_name": "safe_value", "nested": {"also_safe": True}},
    )

    data = health.to_dict()
    assert data["metadata"]["display_name"] == "safe_value"
    assert data["metadata"]["nested"]["also_safe"] is True


def test_provider_status_does_not_require_backend() -> None:
    health = ProviderHealth(
        provider="standalone",
        kind=ProviderKind.FAKE,
        availability=ProviderAvailability.AVAILABLE,
        capabilities=[ProviderCapability.HEALTH],
    )
    status = ProviderStatus(
        provider="standalone",
        health=health,
    )

    assert status.provider == "standalone"
    assert status.active_transfers is None
    assert status.queued_items is None
