from __future__ import annotations

from noqlen_flux.connections import AppConnectionBundle, ProviderAuthMode, ProviderConnectionMode, ProviderConnectionProfile
from noqlen_flux.providers.base import ProviderProvisioner, SecretStoreProvider
from noqlen_flux.providers.status import ProviderAvailability, ProviderCapability, ProviderHealth, ProviderKind
from noqlen_flux.provisioning import (
    CredentialRotationRequest,
    CredentialRotationResult,
    ProviderProvisioningPlan,
    ProviderProvisioningRequest,
    ProviderProvisioningResult,
)
from noqlen_flux.secrets import SecretMaterial


class FakeProvisionerProvider(ProviderProvisioner):
    @property
    def name(self) -> str:
        return "fake-provisioner"

    def capabilities(self) -> list[ProviderCapability]:
        return [ProviderCapability.HEALTH]

    def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, kind=ProviderKind.LAB, availability=ProviderAvailability.AVAILABLE)

    def build_provisioning_plan(self, request: ProviderProvisioningRequest) -> ProviderProvisioningPlan:
        profile = ProviderConnectionProfile(
            provider=request.provider,
            mode=request.mode,
            base_url=request.base_url or "http://127.0.0.1:1",
            auth_mode=ProviderAuthMode.API_KEY,
            api_key_ref=request.api_key_ref,
        )
        return ProviderProvisioningPlan(
            provider=request.provider,
            mode=request.mode,
            workspace=request.workspace,
            app_profile=profile,
            restart_required=request.mode == ProviderConnectionMode.MANAGED,
        )

    def apply_provisioning(self, request: ProviderProvisioningRequest, secret_store: SecretStoreProvider) -> ProviderProvisioningResult:
        plan = self.build_provisioning_plan(request)
        ref = request.api_key_ref
        if request.mode == ProviderConnectionMode.MANAGED and not request.dry_run:
            ref = secret_store.store_secret("fake-provider-api-key", SecretMaterial("fake-provider-secret-material"), label="Fake provider API key")
            plan = ProviderProvisioningPlan(
                provider=plan.provider,
                mode=plan.mode,
                workspace=plan.workspace,
                app_profile=ProviderConnectionProfile(provider=request.provider, mode=request.mode, base_url=plan.app_profile.base_url if plan.app_profile else None, auth_mode=ProviderAuthMode.API_KEY, api_key_ref=ref),
                restart_required=plan.restart_required,
            )
        bundle = AppConnectionBundle(profile=plan.app_profile, restart_required=plan.restart_required) if plan.app_profile else None
        return ProviderProvisioningResult(provider=request.provider, mode=request.mode, applied=not request.dry_run, plan=plan, app_bundle=bundle)

    def rotate_credentials(self, request: CredentialRotationRequest, secret_store: SecretStoreProvider) -> CredentialRotationResult:
        if request.api_key_ref is None:
            return CredentialRotationResult(provider=request.provider, changed=False, restart_required=False, errors=["missing secret reference"])
        ref = secret_store.rotate_secret(request.api_key_ref, SecretMaterial("fake-rotated-secret-material"), dry_run=request.dry_run)
        return CredentialRotationResult(provider=request.provider, changed=not request.dry_run, restart_required=True, api_key_ref=ref)

    def validate_connection_profile(self, profile: ProviderConnectionProfile, secret_store: SecretStoreProvider) -> ProviderProvisioningResult:
        plan = ProviderProvisioningPlan(provider=profile.provider, mode=profile.mode, app_profile=profile)
        return ProviderProvisioningResult(provider=profile.provider, mode=profile.mode, applied=False, plan=plan)
