"""Provider boundary tests.

Ensure that central Flux services do NOT import slskd or any
provider-specific adapter. Core services must depend only on
generic contracts (BaseProvider, SearchProvider, TransferProvider).
"""

import importlib
import inspect
import pkgutil

import noqlen_flux.services as services_pkg


def _all_service_modules() -> list:
    modules = []
    for importer, modname, ispkg in pkgutil.walk_packages(
        services_pkg.__path__,
        prefix=services_pkg.__name__ + ".",
    ):
        try:
            mod = importlib.import_module(modname)
            modules.append(mod)
        except Exception:  # noqa: BLE001
            pass
    return modules


def test_no_service_imports_slskd_provider() -> None:
    forbidden_imports = (
        "from noqlen_flux.providers.slskd",
        "from noqlen_flux.providers import slskd",
        "import noqlen_flux.providers.slskd",
        "from .slskd",
        "from ..slskd",
    )
    for mod in _all_service_modules():
        source_file = inspect.getfile(mod)
        source = open(source_file).read()
        for term in forbidden_imports:
            assert term not in source, f"{mod.__name__} imports slskd provider"


def test_no_service_imports_network_libraries() -> None:
    forbidden = ("requests", "httpx", "aiohttp", "urllib.request")
    for mod in _all_service_modules():
        source_file = inspect.getfile(mod)
        source = open(source_file).read()
        for lib in forbidden:
            assert f"import {lib}" not in source, f"{mod.__name__} imports {lib}"
            assert f"from {lib}" not in source, f"{mod.__name__} imports from {lib}"


def test_services_can_import_base_provider_contracts() -> None:
    from noqlen_flux.providers.base import BaseProvider, SearchProvider, TransferProvider
    from noqlen_flux.providers.status import ProviderHealth

    provider_import_patterns = (
        "from noqlen_flux.providers.base",
        "from noqlen_flux.providers.status",
        "from noqlen_flux.providers.fake",
        "from noqlen_flux.providers import",
        "from .base",
        "from .status",
        "from .fake",
    )
    for mod in _all_service_modules():
        source_file = inspect.getfile(mod)
        source = open(source_file).read()
        has_provider_import = any(p in source for p in provider_import_patterns)
        if has_provider_import:
            pass


def test_slskd_adapter_is_isolated_in_providers() -> None:
    from noqlen_flux.providers import slskd as slskd_module

    source_file = inspect.getfile(slskd_module)
    assert "providers" in source_file
    assert "slskd" in source_file


def test_slskd_does_not_import_central_services() -> None:
    from noqlen_flux.providers import slskd as slskd_module

    source = open(slskd_module.__file__).read()
    services_imports = (
        "noqlen_flux.services.",
        "from noqlen_flux.services",
        "import services",
    )
    for term in services_imports:
        assert term not in source, f"slskd adapter imports central service: {term}"
