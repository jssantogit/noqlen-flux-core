from __future__ import annotations

from noqlen_flux.providers.base import SearchProvider
from noqlen_flux.results import Artifact, FluxError, FluxResult, FluxWarning, Status
from noqlen_flux.search import ProviderHealth, SearchProviderResult, SearchQuery
from noqlen_flux.services.base import FluxService


class SearchService(FluxService):
    operation = "search"

    def search(self, query: SearchQuery, provider: SearchProvider) -> FluxResult:
        provider_result = provider.search(query)
        warnings = _warnings(provider_result.warnings)
        errors = _errors(provider_result.errors)
        status = _status(warnings, errors, provider_result.timeout_reached)
        candidate_payload = [candidate.to_dict() for candidate in provider_result.candidates]
        artifact = Artifact(
            kind="search-candidates",
            description="Logical search candidate result set",
            metadata={"provider": provider_result.provider, "candidates": candidate_payload},
        )
        step = self.step(
            "provider-search",
            status,
            _search_message(provider_result),
            warnings=warnings,
            errors=errors,
            artifacts=[artifact],
        )
        result = FluxResult(
            operation=self.operation,
            status=status,
            steps=[step],
            warnings=warnings,
            errors=errors,
            artifacts=[artifact],
            summary={
                "provider": provider_result.provider,
                "kind": query.kind.value,
                "candidate_count": len(provider_result.candidates),
                "response_count": provider_result.response_count,
                "timeout_reached": provider_result.timeout_reached,
                "candidates": candidate_payload,
            },
        )
        return result.finish()

    def provider_health(self, provider: SearchProvider) -> FluxResult:
        health = provider.health()
        warnings = _warnings(health.warnings)
        errors = _errors(health.errors)
        status = Status.FAILED if not health.available or errors else (Status.WARNING if warnings else Status.SUCCESS)
        step = self.step("provider-health", status, _health_message(health), warnings=warnings, errors=errors)
        result = FluxResult(
            operation="provider-health",
            status=status,
            steps=[step],
            warnings=warnings,
            errors=errors,
            summary=health.to_dict(),
        )
        return result.finish()


def _status(warnings: list[FluxWarning], errors: list[FluxError], timeout_reached: bool) -> Status:
    if errors:
        return Status.FAILED
    if warnings or timeout_reached:
        return Status.WARNING
    return Status.SUCCESS


def _warnings(messages: list[str]) -> list[FluxWarning]:
    return [FluxWarning(code="provider-warning", message=message) for message in messages]


def _errors(messages: list[str]) -> list[FluxError]:
    return [FluxError(code="provider-error", message=message) for message in messages]


def _search_message(provider_result: SearchProviderResult) -> str:
    count = len(provider_result.candidates)
    return f"Provider {provider_result.provider} returned {count} candidate(s)"


def _health_message(health: ProviderHealth) -> str:
    state = "available" if health.available else "unavailable"
    if health.status_message:
        return f"Provider {health.provider} is {state}: {health.status_message}"
    return f"Provider {health.provider} is {state}"
