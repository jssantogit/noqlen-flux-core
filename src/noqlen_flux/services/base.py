from __future__ import annotations

from typing import Any

from noqlen_flux.results import Artifact, FluxError, FluxResult, FluxWarning, Severity, Status, StepResult


class FluxService:
    """Small terminal-free base for Flux services."""

    operation = "flux"

    def result(self, status: Status = Status.SUCCESS, **summary: Any) -> FluxResult:
        return FluxResult(operation=self.operation, status=status, summary=summary)

    def step(
        self,
        name: str,
        status: Status = Status.SUCCESS,
        message: str = "",
        *,
        warnings: list[FluxWarning] | None = None,
        errors: list[FluxError] | None = None,
        artifacts: list[Artifact] | None = None,
    ) -> StepResult:
        return StepResult(
            name=name,
            status=status,
            message=message,
            warnings=warnings or [],
            errors=errors or [],
            artifacts=artifacts or [],
        )

    def warning(self, code: str, message: str, *, severity: Severity = Severity.WARNING, **context: Any) -> FluxWarning:
        return FluxWarning(code=code, message=message, severity=severity, context=context)

    def error(self, code: str, message: str, **context: Any) -> FluxError:
        return FluxError(code=code, message=message, context=context)
