from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from noqlen_flux.cleanup import (
    CleanupActionType,
    CleanupCandidate,
    CleanupCandidateKind,
    CleanupDecision,
    CleanupExecutionAction,
    CleanupExecutionItem,
    CleanupExecutionItemState,
    CleanupExecutionPolicy,
    CleanupExecutionRequest,
    CleanupExecutionResult,
    DEFAULT_CONSERVATIVE_EXECUTION_POLICY,
)
from noqlen_flux.config import FluxConfig
from noqlen_flux.results import AppliedChange, Artifact, FluxError, FluxResult, FluxWarning, PlannedChange, Severity, Status
from noqlen_flux.safety import PathSafetyError, ensure_within_workspace
from noqlen_flux.services.base import FluxService

_PROHIBITED_TARGETS = (
    "approved",
    "import-ready",
    "handoff-ready",
    "library",
    "archive",
)

_REMOVE_ACTIONS = frozenset({
    CleanupExecutionAction.REMOVE_TEMP_REPORT,
    CleanupExecutionAction.REMOVE_STAGING_TEMP,
    CleanupExecutionAction.CLEAN_INVALID_MANIFEST,
    CleanupExecutionAction.CLEAN_INCOMPLETE_ARTIFACT,
})

_MOVE_ACTIONS = frozenset({
    CleanupExecutionAction.MOVE_TO_TRASH,
    CleanupExecutionAction.MOVE_TO_REJECTED_RETAINED,
})


class CleanupExecutionService(FluxService):
    operation = "cleanup-execution"

    def execute_cleanup(
        self,
        request: CleanupExecutionRequest,
        config: FluxConfig,
        *,
        dry_run: bool = True,
        policy: CleanupExecutionPolicy | None = None,
    ) -> FluxResult:
        selected_policy = policy or request.policy or DEFAULT_CONSERVATIVE_EXECUTION_POLICY
        items: list[CleanupExecutionItem] = []
        planned_changes: list[PlannedChange] = []
        applied_changes: list[AppliedChange] = []
        all_warnings: list[FluxWarning] = []
        all_errors: list[FluxError] = []
        executed = 0
        blocked = 0
        skipped = 0
        failed = 0
        total_bytes = 0
        destructive = False

        decisions_map = {d.candidate_id: d for d in request.decisions}
        candidate_map = {c.candidate_id: c for c in request.candidates}

        candidate_ids: list[str] = []
        seen: set[str] = set()
        for did in request.decisions:
            if did.candidate_id not in seen:
                candidate_ids.append(did.candidate_id)
                seen.add(did.candidate_id)
        for cid in request.candidates:
            if cid.candidate_id not in seen:
                candidate_ids.append(cid.candidate_id)
                seen.add(cid.candidate_id)

        for candidate_id in candidate_ids:
            candidate = candidate_map.get(candidate_id)
            decision = decisions_map.get(candidate_id)
            item = self._resolve_execution_item(candidate, decision, selected_policy, config)

            if item.state == CleanupExecutionItemState.BLOCKED:
                blocked += 1
                all_warnings.append(
                    self.warning(
                        "cleanup-blocked",
                        f"Item {item.item_id}: {item.reason}",
                        severity=Severity.WARNING,
                        item_id=item.item_id,
                    )
                )
            elif item.state == CleanupExecutionItemState.FAILED:
                failed += 1
                if item.errors:
                    all_errors.append(
                        self.error(
                            "cleanup-failed",
                            f"Item {item.item_id}: {', '.join(item.errors)}",
                            item_id=item.item_id,
                        )
                    )
            elif item.state == CleanupExecutionItemState.SKIPPED:
                skipped += 1
            elif item.state == CleanupExecutionItemState.EXECUTED:
                if not dry_run:
                    apply_item = self._apply_execution_item(item, config, selected_policy)
                    item = apply_item
                    if apply_item.state == CleanupExecutionItemState.EXECUTED:
                        executed += 1
                    elif apply_item.state == CleanupExecutionItemState.BLOCKED:
                        blocked += 1
                        all_warnings.append(
                            self.warning(
                                "cleanup-blocked",
                                f"Item {apply_item.item_id}: {apply_item.reason}",
                                severity=Severity.WARNING,
                                item_id=apply_item.item_id,
                            )
                        )
                    elif apply_item.state == CleanupExecutionItemState.FAILED:
                        failed += 1
                        if apply_item.errors:
                            all_errors.append(
                                self.error(
                                    "cleanup-failed",
                                    f"Item {apply_item.item_id}: {', '.join(apply_item.errors)}",
                                    item_id=apply_item.item_id,
                                )
                            )
                    else:
                        skipped += 1
                else:
                    executed += 1

            items.append(item)

            if item.state == CleanupExecutionItemState.BLOCKED:
                if item.action == CleanupExecutionAction.BLOCKED:
                    planned_changes.append(
                        PlannedChange(
                            action="cleanup-blocked",
                            target=item.relative_path or item.item_id,
                            reason=item.reason or "Blocked by cleanup execution policy.",
                            metadata={"item_id": item.item_id, "kind": item.kind.value},
                        )
                    )
            elif item.state == CleanupExecutionItemState.SKIPPED:
                planned_changes.append(
                    PlannedChange(
                        action="cleanup-skipped",
                        target=item.relative_path or item.item_id,
                        reason=item.reason or "Skipped.",
                        metadata={"item_id": item.item_id, "kind": item.kind.value},
                    )
                )
            elif item.state == CleanupExecutionItemState.FAILED:
                planned_changes.append(
                    PlannedChange(
                        action="cleanup-failed",
                        target=item.relative_path or item.item_id,
                        reason=item.reason or "Failed to execute.",
                        metadata={"item_id": item.item_id, "kind": item.kind.value},
                    )
                )
            elif item.state == CleanupExecutionItemState.EXECUTED:
                if not dry_run:
                    applied_changes.append(
                        AppliedChange(
                            action=f"cleanup-{item.action.value}",
                            target=item.relative_path or item.item_id,
                            result="executed",
                            metadata={"item_id": item.item_id, "kind": item.kind.value},
                        )
                    )
                else:
                    planned_changes.append(
                        PlannedChange(
                            action=f"plan-cleanup-{item.action.value}",
                            target=item.relative_path or item.item_id,
                            reason=item.reason or "Would execute cleanup action.",
                            metadata={"item_id": item.item_id, "kind": item.kind.value},
                        )
                    )

        has_destructive = executed > 0 and any(
            i.kind in (CleanupCandidateKind.REJECTED, CleanupCandidateKind.DELETE_ELIGIBLE)
            for i in items
            if i.state == CleanupExecutionItemState.EXECUTED
        )
        if has_destructive:
            destructive = True

        execution_result = CleanupExecutionResult(
            result_id=str(uuid.uuid4()),
            request_id=request.request_id,
            items=items,
            total_candidates=len(candidate_ids),
            executed_count=executed,
            blocked_count=blocked,
            skipped_count=skipped,
            failed_count=failed,
            total_bytes_removed=total_bytes,
            destructive_action_detected=destructive,
            safety_checks_passed=not destructive and failed == 0,
            warnings=[w.message for w in all_warnings],
            errors=[e.message for e in all_errors],
            metadata={
                "policy": selected_policy.name,
                "dry_run": dry_run,
                "workspace_root": "[workspace-root]",
            },
        )

        artifact = Artifact(
            kind="cleanup-execution-result",
            description=f"Cleanup execution result (mode={'dry-run' if dry_run else 'apply'})",
            metadata={
                "result_id": execution_result.result_id,
                "executed": executed,
                "blocked": blocked,
                "skipped": skipped,
                "failed": failed,
                "destructive_action_detected": destructive,
            },
        )

        step_status = Status.FAILED if (failed > 0 or destructive) else Status.WARNING if blocked > 0 else Status.SUCCESS
        mode_label = "dry-run" if dry_run else "apply"
        step_message = f"Cleanup execution: {len(items)} candidate(s) processed ({mode_label})"

        step = self.step(
            "execute-cleanup",
            step_status,
            step_message,
            warnings=all_warnings,
            errors=all_errors,
            artifacts=[artifact],
        )

        return FluxResult(
            operation=self.operation,
            status=step_status,
            steps=[step],
            warnings=all_warnings,
            errors=all_errors,
            artifacts=[artifact],
            planned_changes=planned_changes,
            applied_changes=applied_changes,
            summary={
                "result_id": execution_result.result_id,
                "request_id": request.request_id,
                "total_candidates": len(candidate_ids),
                "executed": executed,
                "blocked": blocked,
                "skipped": skipped,
                "failed": failed,
                "destructive_action_detected": destructive,
                "mode": mode_label,
                "policy": selected_policy.to_dict(),
                "execution_result": execution_result.to_dict(),
            },
        ).finish()

    def _resolve_execution_item(
        self,
        candidate: CleanupCandidate | None,
        decision: CleanupDecision | None,
        policy: CleanupExecutionPolicy,
        config: FluxConfig,
    ) -> CleanupExecutionItem:
        item_id = str(uuid.uuid4())
        decision_id = decision.candidate_id if decision else "unknown"
        candidate_id = candidate.candidate_id if candidate else "unknown"
        kind = candidate.kind if candidate else CleanupCandidateKind.UNKNOWN
        relative_path = candidate.relative_path if candidate else None

        if candidate is None:
            return CleanupExecutionItem(
                item_id=item_id,
                decision_id=decision_id,
                candidate_id=candidate_id,
                kind=kind,
                relative_path=relative_path,
                action=CleanupExecutionAction.SKIPPED,
                state=CleanupExecutionItemState.SKIPPED,
                reason="No candidate data available.",
                metadata={"skipped": True},
            )

        if decision is None:
            return CleanupExecutionItem(
                item_id=item_id,
                decision_id=decision_id,
                candidate_id=candidate_id,
                kind=kind,
                relative_path=relative_path,
                action=CleanupExecutionAction.SKIPPED,
                state=CleanupExecutionItemState.SKIPPED,
                reason="No decision available for candidate.",
                metadata={"skipped": True},
            )

        action_type = decision.action_type

        if action_type in (CleanupActionType.KEEP, CleanupActionType.REVIEW, CleanupActionType.NONE):
            return CleanupExecutionItem(
                item_id=item_id,
                decision_id=decision_id,
                candidate_id=candidate_id,
                kind=kind,
                relative_path=relative_path,
                action=CleanupExecutionAction.SKIPPED,
                state=CleanupExecutionItemState.SKIPPED,
                reason=f"Decision action is {action_type.value}; no cleanup execution needed.",
                metadata={"decision_action": action_type.value},
            )

        if not _is_path_within_workspace(relative_path, config.workspace_root):
            return CleanupExecutionItem(
                item_id=item_id,
                decision_id=decision_id,
                candidate_id=candidate_id,
                kind=kind,
                relative_path=relative_path,
                action=CleanupExecutionAction.BLOCKED,
                state=CleanupExecutionItemState.BLOCKED,
                reason="Path validation failed: target outside workspace or safety check failed.",
                errors=["Path outside workspace or safety validation failed."],
                metadata={"path_blocked": True},
            )

        if _is_prohibited_target(relative_path):
            return CleanupExecutionItem(
                item_id=item_id,
                decision_id=decision_id,
                candidate_id=candidate_id,
                kind=kind,
                relative_path=relative_path,
                action=CleanupExecutionAction.BLOCKED,
                state=CleanupExecutionItemState.BLOCKED,
                reason="Target is a protected area (approved, import-ready, library, archive). Cleanup cannot touch these.",
                errors=["Protected target area blocked."],
                metadata={"prohibited_target": True},
            )

        if kind in (CleanupCandidateKind.REJECTED, CleanupCandidateKind.DELETE_ELIGIBLE):
            if not policy.allow_delete:
                return CleanupExecutionItem(
                    item_id=item_id,
                    decision_id=decision_id,
                    candidate_id=candidate_id,
                    kind=kind,
                    relative_path=relative_path,
                    action=CleanupExecutionAction.BLOCKED,
                    state=CleanupExecutionItemState.BLOCKED,
                    reason=f"Prohibited kind '{kind.value}' blocked. Cleanup does not perform delete operations on rejected/delete_eligible by default.",
                    errors=[f"Prohibited kind '{kind.value}' requires explicit allow_delete=True, --apply, and confirmation."],
                    metadata={"prohibited_kind": True, "allow_delete": policy.allow_delete},
                )

        mapped_action = _map_kind_to_execution_action(kind, policy)
        if mapped_action is None:
            return CleanupExecutionItem(
                item_id=item_id,
                decision_id=decision_id,
                candidate_id=candidate_id,
                kind=kind,
                relative_path=relative_path,
                action=CleanupExecutionAction.SKIPPED,
                state=CleanupExecutionItemState.SKIPPED,
                reason=f"No execution mapping for kind '{kind.value}' with current policy.",
                metadata={"unmapped_kind": True},
            )

        if mapped_action == CleanupExecutionAction.BLOCKED:
            return CleanupExecutionItem(
                item_id=item_id,
                decision_id=decision_id,
                candidate_id=candidate_id,
                kind=kind,
                relative_path=relative_path,
                action=CleanupExecutionAction.BLOCKED,
                state=CleanupExecutionItemState.BLOCKED,
                reason=f"Execution action mapped to BLOCKED for kind '{kind.value}'.",
                metadata={"mapped_blocked": True},
            )

        return CleanupExecutionItem(
            item_id=item_id,
            decision_id=decision_id,
            candidate_id=candidate_id,
            kind=kind,
            relative_path=relative_path,
            action=mapped_action,
            state=CleanupExecutionItemState.EXECUTED,
            reason=f"Executing cleanup action {mapped_action.value} for candidate kind {kind.value}.",
            metadata={"action": mapped_action.value},
        )

    def _apply_execution_item(
        self,
        item: CleanupExecutionItem,
        config: FluxConfig,
        policy: CleanupExecutionPolicy,
    ) -> CleanupExecutionItem:
        if item.relative_path is None:
            return CleanupExecutionItem(
                item_id=item.item_id,
                decision_id=item.decision_id,
                candidate_id=item.candidate_id,
                kind=item.kind,
                relative_path=None,
                action=CleanupExecutionAction.SKIPPED,
                state=CleanupExecutionItemState.SKIPPED,
                reason="No relative path; nothing to apply.",
                metadata={"no_path": True},
            )

        try:
            resolved_path = _resolve_safe_workspace_path(item.relative_path, config.workspace_root, config.protected_roots)
        except (PathSafetyError, ValueError) as exc:
            return CleanupExecutionItem(
                item_id=item.item_id,
                decision_id=item.decision_id,
                candidate_id=item.candidate_id,
                kind=item.kind,
                relative_path=item.relative_path,
                action=CleanupExecutionAction.BLOCKED,
                state=CleanupExecutionItemState.BLOCKED,
                reason=f"Path safety check failed: {exc}",
                errors=[str(exc)],
                metadata={"path_blocked": True},
            )

        if _is_prohibited_target(item.relative_path):
            return CleanupExecutionItem(
                item_id=item.item_id,
                decision_id=item.decision_id,
                candidate_id=item.candidate_id,
                kind=item.kind,
                relative_path=item.relative_path,
                action=CleanupExecutionAction.BLOCKED,
                state=CleanupExecutionItemState.BLOCKED,
                reason="Target is a protected area. Cannot apply cleanup.",
                metadata={"prohibited_target": True},
            )

        if item.action in _REMOVE_ACTIONS:
            return _execute_remove(item, resolved_path)
        if item.action in _MOVE_ACTIONS:
            return _execute_move_to_workspace(item, resolved_path, config)

        return CleanupExecutionItem(
            item_id=item.item_id,
            decision_id=item.decision_id,
            candidate_id=item.candidate_id,
            kind=item.kind,
            relative_path=item.relative_path,
            action=item.action,
            state=CleanupExecutionItemState.EXECUTED,
            reason=f"Applied cleanup action {item.action.value}.",
            metadata={"applied": True},
        )


def _execute_remove(item: CleanupExecutionItem, resolved_path: Path) -> CleanupExecutionItem:
    if resolved_path.is_symlink():
        return CleanupExecutionItem(
            item_id=item.item_id,
            decision_id=item.decision_id,
            candidate_id=item.candidate_id,
            kind=item.kind,
            relative_path=item.relative_path,
            action=CleanupExecutionAction.BLOCKED,
            state=CleanupExecutionItemState.BLOCKED,
            reason="Symlink removal blocked.",
            errors=["Symlink targets cannot be removed."],
            metadata={"symlink_blocked": True},
        )

    if not resolved_path.exists():
        return CleanupExecutionItem(
            item_id=item.item_id,
            decision_id=item.decision_id,
            candidate_id=item.candidate_id,
            kind=item.kind,
            relative_path=item.relative_path,
            action=item.action,
            state=CleanupExecutionItemState.SKIPPED,
            reason="Target does not exist; nothing to remove.",
            metadata={"not_found": True},
        )

    try:
        if resolved_path.is_dir():
            shutil.rmtree(str(resolved_path))
        else:
            os.unlink(str(resolved_path))
        return CleanupExecutionItem(
            item_id=item.item_id,
            decision_id=item.decision_id,
            candidate_id=item.candidate_id,
            kind=item.kind,
            relative_path=item.relative_path,
            action=item.action,
            state=CleanupExecutionItemState.EXECUTED,
            reason=f"Removed: {item.relative_path}",
            metadata={"removed": True},
        )
    except OSError as exc:
        return CleanupExecutionItem(
            item_id=item.item_id,
            decision_id=item.decision_id,
            candidate_id=item.candidate_id,
            kind=item.kind,
            relative_path=item.relative_path,
            action=CleanupExecutionAction.BLOCKED,
            state=CleanupExecutionItemState.FAILED,
            reason=f"Failed to remove: {exc}",
            errors=[str(exc)],
            metadata={"os_error": True},
        )


def _execute_move_to_workspace(
    item: CleanupExecutionItem, resolved_path: Path, config: FluxConfig,
) -> CleanupExecutionItem:
    target_base = item.action.value.replace("move_to_", "")
    target_relative = f"{target_base}/{resolved_path.name}"
    target_resolved = config.workspace_root / target_relative

    try:
        ensure_within_workspace(target_resolved, config.workspace_root, protected_roots=config.protected_roots)
    except PathSafetyError as exc:
        return CleanupExecutionItem(
            item_id=item.item_id,
            decision_id=item.decision_id,
            candidate_id=item.candidate_id,
            kind=item.kind,
            relative_path=item.relative_path,
            action=CleanupExecutionAction.BLOCKED,
            state=CleanupExecutionItemState.BLOCKED,
            reason=f"Move target validation failed: {exc}",
            errors=[str(exc)],
            metadata={"target_blocked": True},
        )

    if resolved_path.is_symlink():
        return CleanupExecutionItem(
            item_id=item.item_id,
            decision_id=item.decision_id,
            candidate_id=item.candidate_id,
            kind=item.kind,
            relative_path=item.relative_path,
            action=CleanupExecutionAction.BLOCKED,
            state=CleanupExecutionItemState.BLOCKED,
            reason="Symlink move blocked.",
            errors=["Symlink targets cannot be moved."],
            metadata={"symlink_blocked": True},
        )

    if not resolved_path.exists():
        return CleanupExecutionItem(
            item_id=item.item_id,
            decision_id=item.decision_id,
            candidate_id=item.candidate_id,
            kind=item.kind,
            relative_path=item.relative_path,
            action=item.action,
            state=CleanupExecutionItemState.SKIPPED,
            reason="Source does not exist; nothing to move.",
            metadata={"not_found": True},
        )

    try:
        target_resolved.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(resolved_path), str(target_resolved))
        return CleanupExecutionItem(
            item_id=item.item_id,
            decision_id=item.decision_id,
            candidate_id=item.candidate_id,
            kind=item.kind,
            relative_path=target_relative,
            action=item.action,
            state=CleanupExecutionItemState.EXECUTED,
            reason=f"Moved: {item.relative_path} -> {target_relative}",
            metadata={"moved_to": target_relative},
        )
    except OSError as exc:
        return CleanupExecutionItem(
            item_id=item.item_id,
            decision_id=item.decision_id,
            candidate_id=item.candidate_id,
            kind=item.kind,
            relative_path=item.relative_path,
            action=CleanupExecutionAction.BLOCKED,
            state=CleanupExecutionItemState.FAILED,
            reason=f"Failed to move: {exc}",
            errors=[str(exc)],
            metadata={"os_error": True},
        )


def _is_path_within_workspace(relative_path: str | None, workspace_root: Path) -> bool:
    if relative_path is None:
        return True
    try:
        candidate = workspace_root / relative_path
        ensure_within_workspace(candidate, workspace_root)
        return True
    except (PathSafetyError, ValueError):
        return False


def _is_prohibited_target(relative_path: str | None) -> bool:
    if relative_path is None:
        return False
    lowered = relative_path.lower().replace("\\", "/")
    for prohibited in _PROHIBITED_TARGETS:
        if lowered.startswith(prohibited) or f"/{prohibited}" in lowered:
            return True
    return False


def _resolve_safe_workspace_path(
    relative_path: str,
    workspace_root: Path,
    protected_roots: tuple[Path, ...] = (),
) -> Path:
    if relative_path.startswith("/") or relative_path.startswith("\\"):
        raise PathSafetyError("absolute-path", "Absolute paths are not allowed.", {"path": relative_path})
    candidate = workspace_root / relative_path
    resolved = ensure_within_workspace(candidate, workspace_root, protected_roots=protected_roots)
    if candidate.is_symlink():
        from noqlen_flux.safety import normalize_path
        resolved_target = normalize_path(candidate)
        if not resolved_target.is_relative_to(normalize_path(workspace_root)):
            raise PathSafetyError("symlink-escape", "Symlink resolves outside the workspace.", {"path": str(candidate)})
    return resolved


def _map_kind_to_execution_action(
    kind: CleanupCandidateKind,
    policy: CleanupExecutionPolicy,
) -> CleanupExecutionAction | None:
    if kind == CleanupCandidateKind.TEMPORARY:
        return CleanupExecutionAction.REMOVE_STAGING_TEMP if policy.allow_remove_staging_temp else CleanupExecutionAction.BLOCKED
    if kind == CleanupCandidateKind.STALE_REPORT:
        return CleanupExecutionAction.REMOVE_TEMP_REPORT if policy.allow_remove_temp_reports else CleanupExecutionAction.BLOCKED
    if kind == CleanupCandidateKind.STALE_MANIFEST:
        return CleanupExecutionAction.CLEAN_INVALID_MANIFEST if policy.allow_clean_invalid_manifests else CleanupExecutionAction.BLOCKED
    if kind == CleanupCandidateKind.ORPHANED:
        return CleanupExecutionAction.CLEAN_INCOMPLETE_ARTIFACT if policy.allow_clean_incomplete_artifacts else CleanupExecutionAction.BLOCKED
    if kind == CleanupCandidateKind.REJECTED:
        if policy.allow_move_to_rejected_retained:
            return CleanupExecutionAction.MOVE_TO_REJECTED_RETAINED
        return CleanupExecutionAction.BLOCKED
    if kind == CleanupCandidateKind.DELETE_ELIGIBLE:
        return CleanupExecutionAction.BLOCKED
    return None


def build_execution_request_from_plan(
    cleanup_plan_id: str,
    workspace_root: str,
    decisions: list[CleanupDecision],
    candidates: list[CleanupCandidate],
    policy: CleanupExecutionPolicy | None = None,
) -> CleanupExecutionRequest:
    return CleanupExecutionRequest(
        request_id=str(uuid.uuid4()),
        cleanup_plan_id=cleanup_plan_id,
        workspace_root=workspace_root,
        policy=policy or DEFAULT_CONSERVATIVE_EXECUTION_POLICY,
        decisions=decisions,
        candidates=candidates,
    )
