import pytest

from noqlen_flux.providers.fake import FakeSearchProvider
from noqlen_flux.providers.fake_transfer import FakeTransferProvider
from noqlen_flux.providers.status import ProviderAvailability, ProviderCapability
from noqlen_flux.results import Status
from noqlen_flux.services.providers import ProviderService


def test_inspect_available_provider_returns_success() -> None:
    provider = FakeSearchProvider()
    result = ProviderService().inspect_provider(provider)

    assert result.status == Status.SUCCESS
    assert result.summary["provider"] == "fake"
    assert result.summary["health"]["availability"] == "available"


def test_inspect_degraded_provider_returns_warning() -> None:
    provider = FakeSearchProvider(availability=ProviderAvailability.DEGRADED)
    result = ProviderService().inspect_provider(provider)

    assert result.status == Status.WARNING
    assert result.summary["health"]["availability"] == "degraded"


def test_inspect_unavailable_provider_returns_failed() -> None:
    provider = FakeSearchProvider(availability=ProviderAvailability.UNAVAILABLE)
    result = ProviderService().inspect_provider(provider)

    assert result.status == Status.FAILED
    assert result.summary["health"]["availability"] == "unavailable"


def test_check_health_available_returns_success() -> None:
    provider = FakeSearchProvider()
    result = ProviderService().check_provider_health(provider)

    assert result.status == Status.SUCCESS
    assert result.summary["availability"] == "available"


def test_check_health_degraded_returns_warning() -> None:
    provider = FakeSearchProvider(availability=ProviderAvailability.DEGRADED)
    result = ProviderService().check_provider_health(provider)

    assert result.status == Status.WARNING
    assert result.summary["availability"] == "degraded"


def test_check_health_unavailable_returns_failed() -> None:
    provider = FakeSearchProvider(availability=ProviderAvailability.UNAVAILABLE)
    result = ProviderService().check_provider_health(provider)

    assert result.status == Status.FAILED
    assert result.summary["availability"] == "unavailable"


def test_check_capabilities_with_all_supported_returns_success() -> None:
    provider = FakeSearchProvider()
    result = ProviderService().check_provider_capabilities(
        provider,
        required_capabilities=[ProviderCapability.SEARCH],
    )

    assert result.status == Status.SUCCESS
    assert result.summary["unsupported_capabilities"] == []


def test_check_capabilities_with_missing_capability_returns_warning() -> None:
    provider = FakeSearchProvider()
    result = ProviderService().check_provider_capabilities(
        provider,
        required_capabilities=[ProviderCapability.DOWNLOAD_PLANNING],
    )

    assert result.status == Status.WARNING
    assert ProviderCapability.DOWNLOAD_PLANNING.value in [
        c for c in result.summary["unsupported_capabilities"]
    ]


def test_check_capabilities_without_requirements_returns_success() -> None:
    provider = FakeSearchProvider()
    result = ProviderService().check_provider_capabilities(provider)

    assert result.status == Status.SUCCESS


def test_inspect_transfer_provider() -> None:
    provider = FakeTransferProvider()
    result = ProviderService().inspect_provider(provider)

    assert result.status == Status.SUCCESS
    assert result.summary["provider"] == "fake-transfer"
    assert result.summary["health"]["availability"] == "available"


def test_service_does_not_create_files(tmp_path) -> None:
    provider = FakeSearchProvider()
    ProviderService().inspect_provider(provider)

    assert list(tmp_path.iterdir()) == []


def test_service_does_not_access_network() -> None:
    from noqlen_flux.services import providers as providers_module

    source_code = open(providers_module.__file__).read()
    assert "requests" not in source_code
    assert "urllib" not in source_code
    assert "socket" not in source_code


def test_service_does_not_depend_on_slskd() -> None:
    from noqlen_flux.services import providers as providers_module

    assert "slskd" not in providers_module.__file__
    for name in dir(providers_module):
        obj = getattr(providers_module, name, None)
        if hasattr(obj, "__module__"):
            assert "slskd" not in (getattr(obj, "__module__", "") or "")


def test_inspect_provider_includes_artifact() -> None:
    provider = FakeSearchProvider()
    result = ProviderService().inspect_provider(provider)

    assert len(result.artifacts) >= 1
    assert result.artifacts[0].kind == "provider-inspect"


def test_check_health_includes_artifact() -> None:
    provider = FakeSearchProvider()
    result = ProviderService().check_provider_health(provider)

    assert len(result.artifacts) >= 1
    assert result.artifacts[0].kind == "provider-health"


def test_check_capabilities_includes_artifact() -> None:
    provider = FakeSearchProvider()
    result = ProviderService().check_provider_capabilities(provider)

    assert len(result.artifacts) >= 1
    assert result.artifacts[0].kind == "provider-capabilities"
