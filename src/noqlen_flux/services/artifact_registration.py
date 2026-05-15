from __future__ import annotations

from typing import Any

from noqlen_flux.artifact_registration import DownloadArtifactRegistration
from noqlen_flux.results import (
    Artifact,
    FluxError,
    FluxResult,
    FluxWarning,
    PlannedChange,
    Severity,
    Status,
    StepResult,
)
from noqlen_flux.services.base import FluxService


class ArtifactRegistrationService(FluxService):
    operation = "artifact-registration"

    def register_artifact(
        self,
        registration: DownloadArtifactRegistration,
        *,
        dry_run: bool = True,
    ) -> FluxResult:
        warnings: list[FluxWarning] = []
        errors: list[FluxError] = []

        for w in registration.warnings:
            warnings.append(
                self.warning(
                    "registration-warning",
                    w,
                    severity=Severity.WARNING,
                    context={"artifact_id": registration.artifact_id},
                )
            )

        for e in registration.errors:
            errors.append(
                self.error(
                    "registration-error",
                    e,
                    context={"artifact_id": registration.artifact_id},
                )
            )

        if errors:
            return self._failed_result(registration, warnings, errors)

        if dry_run:
            return self._dry_run_result(registration, warnings)

        return self._apply_result(registration, warnings)

    def register_from_transfer_status(
        self,
        transfer_id: str,
        queue_item_id: str,
        candidate_id: str,
        provider: str,
        state: str,
        relative_path: str,
        *,
        size_bytes: int | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        dry_run: bool = True,
    ) -> FluxResult:
        try:
            registration = DownloadArtifactRegistration.from_transfer_status(
                transfer_id=transfer_id,
                queue_item_id=queue_item_id,
                candidate_id=candidate_id,
                provider=provider,
                state=state,
                relative_path=relative_path,
                size_bytes=size_bytes,
                warnings=warnings,
                errors=errors,
                metadata=metadata,
            )
        except ValueError as exc:
            return self.result(
                Status.FAILED,
                error=str(exc),
            )

        return self.register_artifact(registration, dry_run=dry_run)

    def register_from_submission(
        self,
        submission_id: str,
        queue_item_id: str,
        candidate_id: str,
        provider: str,
        state: str,
        relative_path: str,
        *,
        size_bytes: int | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        dry_run: bool = True,
    ) -> FluxResult:
        try:
            registration = DownloadArtifactRegistration.from_submission_result(
                submission_id=submission_id,
                queue_item_id=queue_item_id,
                candidate_id=candidate_id,
                provider=provider,
                state=state,
                relative_path=relative_path,
                size_bytes=size_bytes,
                warnings=warnings,
                errors=errors,
                metadata=metadata,
            )
        except ValueError as exc:
            return self.result(
                Status.FAILED,
                error=str(exc),
            )

        return self.register_artifact(registration, dry_run=dry_run)

    def _dry_run_result(
        self,
        registration: DownloadArtifactRegistration,
        warnings: list[FluxWarning],
    ) -> FluxResult:
        planned = PlannedChange(
            action="register-download-artifact",
            target=registration.relative_path,
            reason=f"dry-run: would register download artifact {registration.artifact_id}",
            metadata={
                "artifact_id": registration.artifact_id,
                "candidate_id": registration.candidate_id,
                "queue_item_id": registration.queue_item_id,
                "provider": registration.provider,
                "state": registration.state,
            },
        )

        step = self.step(
            "register-artifact-dry-run",
            Status.SUCCESS if not warnings else Status.WARNING,
            f"Would register artifact {registration.artifact_id} ({registration.state})",
            warnings=warnings,
        )

        artifact = Artifact(
            kind="artifact-registration-plan",
            description=f"Planned artifact registration for {registration.artifact_id}",
            metadata={
                "artifact_id": registration.artifact_id,
                "provider": registration.provider,
                "state": registration.state,
                "relative_path": registration.relative_path,
            },
        )

        return FluxResult(
            operation=self.operation,
            status=step.status,
            steps=[step],
            warnings=warnings,
            artifacts=[artifact],
            planned_changes=[planned],
            summary={
                "artifact_id": registration.artifact_id,
                "candidate_id": registration.candidate_id,
                "provider": registration.provider,
                "state": registration.state,
                "relative_path": registration.relative_path,
            },
        ).finish()

    def _apply_result(
        self,
        registration: DownloadArtifactRegistration,
        warnings: list[FluxWarning],
    ) -> FluxResult:
        step = self.step(
            "register-artifact-apply",
            Status.SUCCESS if not warnings else Status.WARNING,
            f"Registered artifact {registration.artifact_id} ({registration.state})",
            warnings=warnings,
        )

        artifact = Artifact(
            kind="artifact-registration-applied",
            description=f"Registered download artifact {registration.artifact_id}",
            metadata={
                "artifact_id": registration.artifact_id,
                "provider": registration.provider,
                "state": registration.state,
                "relative_path": registration.relative_path,
            },
        )

        return FluxResult(
            operation=self.operation,
            status=step.status,
            steps=[step],
            warnings=warnings,
            artifacts=[artifact],
            summary={
                "artifact_id": registration.artifact_id,
                "candidate_id": registration.candidate_id,
                "provider": registration.provider,
                "state": registration.state,
                "relative_path": registration.relative_path,
            },
        ).finish()

    def _failed_result(
        self,
        registration: DownloadArtifactRegistration,
        warnings: list[FluxWarning],
        errors: list[FluxError],
    ) -> FluxResult:
        step = self.step(
            "register-artifact-failed",
            Status.FAILED,
            f"Failed to register artifact {registration.artifact_id}",
            warnings=warnings,
            errors=errors,
        )

        return FluxResult(
            operation=self.operation,
            status=Status.FAILED,
            steps=[step],
            warnings=warnings,
            errors=errors,
            summary={
                "artifact_id": registration.artifact_id,
                "provider": registration.provider,
                "state": registration.state,
                "error_count": len(errors),
            },
        ).finish()
