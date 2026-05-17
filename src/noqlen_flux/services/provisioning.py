from __future__ import annotations

from noqlen_flux.providers.base import ProviderProvisioner, SecretStoreProvider
from noqlen_flux.provisioning import CredentialRotationRequest, ProviderProvisioningRequest
from noqlen_flux.results import Artifact, FluxError, FluxResult, PlannedChange, AppliedChange, Status


class ProviderProvisioningService:
    """Provider-agnostic provisioning orchestration service."""

    def build_plan(self, request: ProviderProvisioningRequest, provisioner: ProviderProvisioner) -> FluxResult:
        try:
            plan = provisioner.build_provisioning_plan(request)
            return FluxResult(
                operation="provider-provisioning",
                status=Status.SUCCESS,
                planned_changes=[PlannedChange(action="provision", target=request.provider, reason="build provider provisioning plan", metadata=plan.to_dict())],
                summary={"provider": request.provider, "mode": request.mode.value, "restart_required": plan.restart_required, "profile": plan.app_profile.to_dict() if plan.app_profile else None},
                artifacts=[Artifact(kind="app-connection-profile", description="Safe app connection profile", metadata=plan.app_profile.to_dict() if plan.app_profile else {})],
            ).finish()
        except Exception as exc:  # noqa: BLE001
            return self._failed(request.provider, str(exc))

    def apply(self, request: ProviderProvisioningRequest, provisioner: ProviderProvisioner, secret_store: SecretStoreProvider) -> FluxResult:
        try:
            result = provisioner.apply_provisioning(request, secret_store)
            status = Status.FAILED if result.errors else Status.SUCCESS
            changes = []
            if result.applied:
                changes.append(AppliedChange(action="provision", target=request.provider, result="applied", metadata=result.to_dict()))
            else:
                changes.append(PlannedChange(action="provision", target=request.provider, reason="dry-run provider provisioning", metadata=result.to_dict()))
            return FluxResult(
                operation="provider-provisioning",
                status=status,
                planned_changes=[item for item in changes if isinstance(item, PlannedChange)],
                applied_changes=[item for item in changes if isinstance(item, AppliedChange)],
                errors=[FluxError(code="provider-provisioning-failed", message=message) for message in result.errors],
                summary={"provider": request.provider, "mode": request.mode.value, "applied": result.applied, "restart_required": result.plan.restart_required, "profile": result.plan.app_profile.to_dict() if result.plan.app_profile else None},
                artifacts=[Artifact(kind="app-connection-bundle", description="Safe app connection bundle", metadata=result.app_bundle.to_dict() if result.app_bundle else {})],
            ).finish(status)
        except Exception as exc:  # noqa: BLE001
            return self._failed(request.provider, str(exc))

    def rotate_credentials(self, request: CredentialRotationRequest, provisioner: ProviderProvisioner, secret_store: SecretStoreProvider) -> FluxResult:
        try:
            result = provisioner.rotate_credentials(request, secret_store)
            status = Status.FAILED if result.errors else Status.SUCCESS
            change_metadata = result.to_dict()
            return FluxResult(
                operation="provider-credential-rotation",
                status=status,
                planned_changes=[] if result.changed else [PlannedChange(action="rotate-credentials", target=request.provider, reason="dry-run credential rotation", metadata=change_metadata)],
                applied_changes=[AppliedChange(action="rotate-credentials", target=request.provider, result="rotated", metadata=change_metadata)] if result.changed else [],
                errors=[FluxError(code="provider-credential-rotation-failed", message=message) for message in result.errors],
                summary={"provider": request.provider, "changed": result.changed, "restart_required": result.restart_required, "api_key_ref": result.api_key_ref.to_dict() if result.api_key_ref else None},
            ).finish(status)
        except Exception as exc:  # noqa: BLE001
            return self._failed(request.provider, str(exc), operation="provider-credential-rotation")

    def _failed(self, provider: str, message: str, *, operation: str = "provider-provisioning") -> FluxResult:
        return FluxResult(operation=operation, status=Status.FAILED, errors=[FluxError(code="provider-provisioning-failed", message=message)], summary={"provider": provider}).finish(Status.FAILED)
