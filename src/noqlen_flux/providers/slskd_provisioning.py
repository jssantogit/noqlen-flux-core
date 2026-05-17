from __future__ import annotations

import os
import secrets as py_secrets
from pathlib import Path

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
from noqlen_flux.results import _clean
from noqlen_flux.secrets import SecretMaterial, SecretRef


_MIN_API_KEY_LENGTH = 32
_DEFAULT_BASE_URL = "http://127.0.0.1:5030"


class SlskdProvisioner(ProviderProvisioner):
    """Isolated slskd provisioning adapter.

    This provider only prepares files and secret references. It does not start,
    stop, restart, or contact a real slskd instance.
    """

    @property
    def name(self) -> str:
        return "slskd"

    def capabilities(self) -> list[ProviderCapability]:
        return [ProviderCapability.HEALTH]

    def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, kind=ProviderKind.EXTERNAL, availability=ProviderAvailability.AVAILABLE, status_message="provisioning adapter only")

    def build_provisioning_plan(self, request: ProviderProvisioningRequest) -> ProviderProvisioningPlan:
        if request.mode == ProviderConnectionMode.MANAGED:
            workspace = self._require_workspace(request.workspace)
            config_path = self._managed_env_path(workspace)
            profile = ProviderConnectionProfile(
                provider=self.name,
                mode=ProviderConnectionMode.MANAGED,
                base_url=request.base_url or _DEFAULT_BASE_URL,
                auth_mode=ProviderAuthMode.API_KEY,
                api_key_ref=request.api_key_ref,
                metadata={"managed_by": "noqlen-flux", "network_access": False},
            )
            return ProviderProvisioningPlan(
                provider=self.name,
                mode=request.mode,
                workspace=workspace,
                config_paths=[str(config_path)],
                app_profile=profile,
                restart_required=True,
                metadata={"writes_config": bool(request.policy.allow_config_write and not request.dry_run)},
            )

        profile = ProviderConnectionProfile(
            provider=self.name,
            mode=ProviderConnectionMode.EXTERNAL,
            base_url=request.base_url,
            auth_mode=ProviderAuthMode.API_KEY,
            api_key_ref=request.api_key_ref,
            metadata={"managed_by": "external", "config_control": False},
        )
        return ProviderProvisioningPlan(provider=self.name, mode=request.mode, workspace=request.workspace, app_profile=profile, restart_required=False, metadata={"writes_config": False})

    def apply_provisioning(self, request: ProviderProvisioningRequest, secret_store: SecretStoreProvider) -> ProviderProvisioningResult:
        try:
            if request.mode == ProviderConnectionMode.EXTERNAL:
                return self._apply_external(request, secret_store)
            return self._apply_managed(request, secret_store)
        except (OSError, ValueError, KeyError) as exc:
            plan = self.build_provisioning_plan(request)
            return ProviderProvisioningResult(provider=self.name, mode=request.mode, applied=False, plan=plan, errors=[str(exc)])

    def rotate_credentials(self, request: CredentialRotationRequest, secret_store: SecretStoreProvider) -> CredentialRotationResult:
        try:
            ref = request.api_key_ref or self._load_workspace_ref(request.workspace)
            if ref is None:
                return CredentialRotationResult(provider=self.name, changed=False, restart_required=False, errors=["missing slskd API key reference"])
            material = self.generate_api_key()
            new_ref = secret_store.rotate_secret(ref, material, dry_run=request.dry_run)
            return CredentialRotationResult(provider=self.name, changed=not request.dry_run, restart_required=True, api_key_ref=new_ref)
        except (OSError, ValueError, KeyError) as exc:
            return CredentialRotationResult(provider=self.name, changed=False, restart_required=False, errors=[str(exc)])

    def validate_connection_profile(self, profile: ProviderConnectionProfile, secret_store: SecretStoreProvider) -> ProviderProvisioningResult:
        errors: list[str] = []
        if profile.auth_mode == ProviderAuthMode.API_KEY and profile.api_key_ref is None:
            errors.append("missing slskd API key reference")
        if profile.api_key_ref is not None:
            try:
                secret_store.describe_secret(profile.api_key_ref)
            except KeyError:
                errors.append("slskd API key reference is not available")
        plan = ProviderProvisioningPlan(provider=self.name, mode=profile.mode, app_profile=profile)
        return ProviderProvisioningResult(provider=self.name, mode=profile.mode, applied=False, plan=plan, errors=errors)

    def generate_api_key(self) -> SecretMaterial:
        value = py_secrets.token_urlsafe(48)
        if len(value) < _MIN_API_KEY_LENGTH:
            raise ValueError("generated slskd API key is shorter than the safe minimum")
        return SecretMaterial(value=value, label="slskd API key")

    def _apply_managed(self, request: ProviderProvisioningRequest, secret_store: SecretStoreProvider) -> ProviderProvisioningResult:
        workspace = self._require_workspace(request.workspace)
        plan = self.build_provisioning_plan(request)
        ref = request.api_key_ref
        descriptors = []
        if request.dry_run:
            return ProviderProvisioningResult(provider=self.name, mode=request.mode, applied=False, plan=plan, app_bundle=AppConnectionBundle(profile=plan.app_profile, restart_required=True))
        if not request.policy.allow_secret_write:
            raise ValueError("managed slskd apply requires secret write policy")
        ref = secret_store.store_secret("slskd-api-key", self.generate_api_key(), label="slskd API key")
        descriptors.append(secret_store.describe_secret(ref))
        profile = ProviderConnectionProfile(provider=self.name, mode=request.mode, base_url=request.base_url or _DEFAULT_BASE_URL, auth_mode=ProviderAuthMode.API_KEY, api_key_ref=ref, metadata={"managed_by": "noqlen-flux", "network_access": False})
        if request.policy.allow_config_write:
            self._write_managed_env(workspace, ref)
        plan = ProviderProvisioningPlan(provider=self.name, mode=request.mode, workspace=workspace, config_paths=[str(self._managed_env_path(workspace))], app_profile=profile, restart_required=True, metadata={"writes_config": request.policy.allow_config_write})
        return ProviderProvisioningResult(provider=self.name, mode=request.mode, applied=True, plan=plan, app_bundle=AppConnectionBundle(profile=profile, secret_descriptors=descriptors, restart_required=True))

    def _apply_external(self, request: ProviderProvisioningRequest, secret_store: SecretStoreProvider) -> ProviderProvisioningResult:
        if not request.base_url:
            plan = self.build_provisioning_plan(request)
            return ProviderProvisioningResult(provider=self.name, mode=request.mode, applied=False, plan=plan, errors=["external slskd requires base URL"])
        ref = request.api_key_ref
        descriptors = []
        if ref is None:
            if not request.api_key_env:
                plan = self.build_provisioning_plan(request)
                return ProviderProvisioningResult(provider=self.name, mode=request.mode, applied=False, plan=plan, errors=["external slskd requires API key env or secret reference"])
            value = os.environ.get(request.api_key_env)
            if not value:
                plan = self.build_provisioning_plan(request)
                return ProviderProvisioningResult(provider=self.name, mode=request.mode, applied=False, plan=plan, errors=["external slskd API key env is not set"])
            if not request.dry_run:
                if not request.policy.allow_secret_write:
                    raise ValueError("external slskd apply requires secret write policy")
                ref = secret_store.store_secret("slskd-external-api-key", SecretMaterial(value, label="external slskd API key"), label="external slskd API key")
                descriptors.append(secret_store.describe_secret(ref))
        profile = ProviderConnectionProfile(provider=self.name, mode=request.mode, base_url=request.base_url, auth_mode=ProviderAuthMode.API_KEY, api_key_ref=ref, metadata={"managed_by": "external", "config_control": False})
        plan = ProviderProvisioningPlan(provider=self.name, mode=request.mode, workspace=request.workspace, app_profile=profile, restart_required=False, metadata={"writes_config": False})
        return ProviderProvisioningResult(provider=self.name, mode=request.mode, applied=not request.dry_run, plan=plan, app_bundle=AppConnectionBundle(profile=profile, secret_descriptors=descriptors, restart_required=False))

    def _write_managed_env(self, workspace: Path, ref: SecretRef) -> None:
        path = self._managed_env_path(workspace)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# Generated by Noqlen Flux for managed slskd. Contains references only.\n"
            f"SLSKD_API_KEY_REF={ref.store}:{ref.key}:{ref.version}\n",
            encoding="utf-8",
        )
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def _load_workspace_ref(self, workspace: Path | None) -> SecretRef | None:
        if workspace is None:
            return None
        path = self._managed_env_path(self._require_workspace(workspace))
        if not path.exists():
            return None
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("SLSKD_API_KEY_REF="):
                _, raw = line.split("=", 1)
                store, key, version = raw.split(":", 2)
                return SecretRef(store=store, key=key, version=version)
        return None

    def _managed_env_path(self, workspace: Path) -> Path:
        path = (workspace / "providers" / "slskd" / "slskd.env").resolve()
        if not _is_relative_to(path, workspace):
            raise ValueError("managed slskd config path escapes workspace")
        return path

    def _require_workspace(self, workspace: Path | None) -> Path:
        if workspace is None:
            raise ValueError("managed slskd requires workspace")
        return Path(workspace).expanduser().resolve()


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False
