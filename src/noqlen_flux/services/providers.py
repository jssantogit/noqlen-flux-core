from __future__ import annotations

from typing import Any

from noqlen_flux.providers.base import BaseProvider
from noqlen_flux.providers.status import (
    ProviderAvailability,
    ProviderCapability,
    ProviderCapabilityReport,
    ProviderHealth,
    ProviderStatus,
)
from noqlen_flux.results import Artifact, FluxError, FluxResult, FluxWarning, Severity, Status, StepResult
from noqlen_flux.services.base import FluxService


class ProviderService(FluxService):
    """Service for inspecting provider health, capabilities, and status.

    This service depends only on generic provider contracts.
    It does not access the network, download files, create files,
    or know about any specific backend such as slskd.
    """

    operation = "provider"

    def inspect_provider(self, provider: BaseProvider) -> FluxResult:
        health = provider.health()
        capabilities = provider.capabilities()
        capability_report = _build_capability_report(provider, capabilities)

        warnings = _health_warnings(health)
        errors = _health_errors(health)
        status = _health_status(health, warnings, errors)

        health_step = self.step(
            "provider-health",
            status,
            _health_message(health),
            warnings=warnings,
            errors=errors,
        )

        capability_step = self.step(
            "provider-capabilities",
            Status.SUCCESS,
            _capability_message(capability_report),
            warnings=_capability_warnings(capability_report),
        )

        artifact = Artifact(
            kind="provider-inspect",
            description="Provider health and capability inspection",
            metadata={
                "provider": provider.name,
                "health": health.to_dict(),
                "capabilities": capability_report.to_dict(),
            },
        )

        result = FluxResult(
            operation=self.operation,
            status=status,
            steps=[health_step, capability_step],
            warnings=warnings,
            errors=errors,
            artifacts=[artifact],
            summary={
                "provider": provider.name,
                "health": health.to_dict(),
                "capabilities": capability_report.to_dict(),
            },
        )
        return result.finish()

    def check_provider_health(self, provider: BaseProvider) -> FluxResult:
        health = provider.health()
        warnings = _health_warnings(health)
        errors = _health_errors(health)
        status = _health_status(health, warnings, errors)

        step = self.step(
            "provider-health",
            status,
            _health_message(health),
            warnings=warnings,
            errors=errors,
        )

        artifact = Artifact(
            kind="provider-health",
            description="Provider health check result",
            metadata={"provider": provider.name, "health": health.to_dict()},
        )

        result = FluxResult(
            operation="provider-health",
            status=status,
            steps=[step],
            warnings=warnings,
            errors=errors,
            artifacts=[artifact],
            summary=health.to_dict(),
        )
        return result.finish()

    def check_provider_capabilities(
        self,
        provider: BaseProvider,
        required_capabilities: list[ProviderCapability] | None = None,
    ) -> FluxResult:
        capabilities = provider.capabilities()
        capability_set = set(capabilities)
        required = required_capabilities or []
        unsupported = [cap for cap in required if cap not in capability_set]

        warnings: list[FluxWarning] = []
        errors: list[FluxError] = []

        for cap in unsupported:
            warnings.append(
                self.warning(
                    "capability-missing",
                    f"Provider {provider.name} does not support {cap.value}",
                    capability=cap.value,
                )
            )

        status = Status.FAILED if errors else (Status.WARNING if warnings else Status.SUCCESS)

        capability_report = ProviderCapabilityReport(
            provider=provider.name,
            capabilities=capabilities,
            unsupported_capabilities=unsupported,
            warnings=[w.message for w in warnings],
        )

        step = self.step(
            "provider-capabilities",
            status,
            _capability_message(capability_report),
            warnings=warnings,
            errors=errors,
        )

        artifact = Artifact(
            kind="provider-capabilities",
            description="Provider capability check result",
            metadata={"provider": provider.name, "capabilities": capability_report.to_dict()},
        )

        result = FluxResult(
            operation="provider-capabilities",
            status=status,
            steps=[step],
            warnings=warnings,
            errors=errors,
            artifacts=[artifact],
            summary=capability_report.to_dict(),
        )
        return result.finish()


def _build_capability_report(
    provider: BaseProvider,
    capabilities: list[ProviderCapability],
) -> ProviderCapabilityReport:
    return ProviderCapabilityReport(
        provider=provider.name,
        capabilities=capabilities,
    )


def _health_status(
    health: ProviderHealth,
    warnings: list[FluxWarning],
    errors: list[FluxError],
) -> Status:
    if health.availability == ProviderAvailability.UNAVAILABLE or errors:
        return Status.FAILED
    if health.availability == ProviderAvailability.DEGRADED or warnings:
        return Status.WARNING
    return Status.SUCCESS


def _health_warnings(health: ProviderHealth) -> list[FluxWarning]:
    return [FluxWarning(code="provider-warning", message=msg) for msg in health.warnings]


def _health_errors(health: ProviderHealth) -> list[FluxError]:
    return [FluxError(code="provider-error", message=msg) for msg in health.errors]


def _health_message(health: ProviderHealth) -> str:
    state = health.availability.value
    if health.status_message:
        return f"Provider {health.provider} is {state}: {health.status_message}"
    return f"Provider {health.provider} is {state}"


def _capability_message(report: ProviderCapabilityReport) -> str:
    count = len(report.capabilities)
    unsupported = len(report.unsupported_capabilities)
    parts = [f"Provider {report.provider} declares {count} capability(s)"]
    if unsupported:
        parts.append(f"{unsupported} unsupported")
    return ", ".join(parts)


def _capability_warnings(report: ProviderCapabilityReport) -> list[FluxWarning]:
    return [FluxWarning(code="capability-unsupported", message=msg) for msg in report.warnings]
