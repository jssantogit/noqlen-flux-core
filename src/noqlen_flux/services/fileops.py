from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from noqlen_flux.config import FluxConfig
from noqlen_flux.fileops import (
    DEFAULT_FILE_EXECUTION_POLICY,
    FileExecutionPolicy,
    FileOperation,
    FileOperationPlan,
    FileOperationResult,
    FileOperationState,
    FileOperationType,
)
from noqlen_flux.results import AppliedChange, Artifact, FluxError, FluxResult, FluxWarning, PlannedChange, Severity, Status
from noqlen_flux.safety import PathSafetyError, ensure_not_protected, ensure_within_workspace, normalize_path
from noqlen_flux.services.base import FluxService
from noqlen_flux.staging import StagingActionType, StagingItem, StagingPlan


class SafeFileOperationService(FluxService):
    operation = "fileops"

    def plan_from_staging(
        self,
        staging_plan: StagingPlan,
        config: FluxConfig,
        policy: FileExecutionPolicy | None = None,
    ) -> FluxResult:
        selected_policy = policy or DEFAULT_FILE_EXECUTION_POLICY
        operations: list[FileOperation] = []
        planned_changes: list[PlannedChange] = []
        all_warnings: list[FluxWarning] = []
        all_errors: list[FluxError] = []

        for item in staging_plan.items:
            op = _staging_item_to_file_operation(item, selected_policy)
            operations.append(op)

            if op.operation_type == FileOperationType.NONE:
                all_warnings.append(
                    self.warning(
                        "no-operation",
                        f"Item {item.item_id}: no file operation planned.",
                        severity=Severity.INFO,
                        item_id=item.item_id,
                    )
                )

            change = PlannedChange(
                action=f"plan-{op.operation_type.value}",
                target=op.target_relative_path or op.source_relative_path or op.operation_id,
                reason=op.reason,
                metadata={
                    "operation_id": op.operation_id,
                    "operation_type": op.operation_type.value,
                    "item_id": item.item_id,
                },
            )
            planned_changes.append(change)

        plan = FileOperationPlan(
            plan_id=str(uuid.uuid4()),
            operations=operations,
            warnings=[w.message for w in all_warnings],
            errors=[e.message for e in all_errors],
            metadata={"policy": selected_policy.name},
        )

        artifact = Artifact(
            kind="file-operation-plan",
            description="File operation plan derived from staging plan (planned-only, no execution)",
            metadata={
                "plan_id": plan.plan_id,
                "operation_count": len(operations),
                "policy": selected_policy.name,
            },
        )

        step_status = Status.WARNING if all_warnings else Status.SUCCESS
        step_message = f"File operation plan: {len(operations)} operation(s) derived from staging plan"

        step = self.step(
            "plan-file-operations",
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
            summary={
                "plan_id": plan.plan_id,
                "operation_count": len(operations),
                "policy": selected_policy.to_dict(),
                "file_operation_plan": plan.to_dict(),
            },
        ).finish()

    def execute_plan(
        self,
        file_operation_plan: FileOperationPlan,
        config: FluxConfig,
        *,
        dry_run: bool = True,
        policy: FileExecutionPolicy | None = None,
    ) -> FluxResult:
        selected_policy = policy or DEFAULT_FILE_EXECUTION_POLICY
        results: list[FileOperationResult] = []
        planned_changes: list[PlannedChange] = []
        applied_changes: list[AppliedChange] = []
        all_warnings: list[FluxWarning] = []
        all_errors: list[FluxError] = []

        for op in file_operation_plan.operations:
            op_result = self._execute_operation(op, config, dry_run=dry_run, policy=selected_policy)
            results.append(op_result)

            if op_result.state == FileOperationState.FAILED:
                all_errors.extend(
                    self.error(
                        "file-op-failed",
                        f"Operation {op.operation_id}: {err}",
                        operation_id=op.operation_id,
                    )
                    for err in op_result.errors
                )
            elif op_result.state == FileOperationState.BLOCKED:
                all_warnings.append(
                    self.warning(
                        "file-op-blocked",
                        f"Operation {op.operation_id}: {op_result.message}",
                        severity=Severity.WARNING,
                        operation_id=op.operation_id,
                    )
                )

            if op_result.state == FileOperationState.PLANNED or op_result.state == FileOperationState.SKIPPED:
                planned_changes.append(
                    PlannedChange(
                        action=f"plan-{op.operation_type.value}",
                        target=op_result.target_relative_path or op_result.source_relative_path or op.operation_id,
                        reason=op_result.message or op.reason,
                        metadata={
                            "operation_id": op.operation_id,
                            "state": op_result.state.value,
                        },
                    )
                )
            elif op_result.state == FileOperationState.APPLIED:
                applied_changes.append(
                    AppliedChange(
                        action=f"applied-{op.operation_type.value}",
                        target=op_result.target_relative_path or op_result.source_relative_path or op.operation_id,
                        result=op_result.message,
                        metadata={
                            "operation_id": op.operation_id,
                            "state": op_result.state.value,
                        },
                    )
                )

        has_errors = any(r.state == FileOperationState.FAILED for r in results)
        has_warnings = any(r.state in (FileOperationState.BLOCKED, FileOperationState.SKIPPED) for r in results)

        if has_errors:
            step_status = Status.FAILED
        elif has_warnings:
            step_status = Status.WARNING
        else:
            step_status = Status.SUCCESS

        mode_label = "dry-run" if dry_run else "apply"
        step_message = f"File operations: {len(results)} operation(s) processed ({mode_label})"

        artifact = Artifact(
            kind="file-operation-result",
            description=f"File operation execution result ({mode_label})",
            metadata={
                "plan_id": file_operation_plan.plan_id,
                "operation_count": len(results),
                "mode": mode_label,
                "policy": selected_policy.name,
            },
        )

        step = self.step(
            "execute-file-operations",
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
                "plan_id": file_operation_plan.plan_id,
                "operation_count": len(results),
                "mode": mode_label,
                "applied_count": sum(1 for r in results if r.state == FileOperationState.APPLIED),
                "planned_count": sum(1 for r in results if r.state == FileOperationState.PLANNED),
                "skipped_count": sum(1 for r in results if r.state == FileOperationState.SKIPPED),
                "blocked_count": sum(1 for r in results if r.state == FileOperationState.BLOCKED),
                "failed_count": sum(1 for r in results if r.state == FileOperationState.FAILED),
                "policy": selected_policy.to_dict(),
            },
        ).finish()

    def _execute_operation(
        self,
        operation: FileOperation,
        config: FluxConfig,
        *,
        dry_run: bool = True,
        policy: FileExecutionPolicy | None = None,
    ) -> FileOperationResult:
        selected_policy = policy or DEFAULT_FILE_EXECUTION_POLICY

        if operation.operation_type == FileOperationType.NONE:
            return FileOperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                state=FileOperationState.SKIPPED,
                source_relative_path=operation.source_relative_path,
                target_relative_path=operation.target_relative_path,
                message="No operation type specified.",
                metadata={"policy": selected_policy.name},
            )

        if operation.operation_type == FileOperationType.MKDIR:
            return self._execute_mkdir(operation, config, dry_run=dry_run, policy=selected_policy)

        if operation.operation_type == FileOperationType.COPY:
            if not selected_policy.allow_copy:
                return FileOperationResult(
                    operation_id=operation.operation_id,
                    operation_type=operation.operation_type,
                    state=FileOperationState.BLOCKED,
                    source_relative_path=operation.source_relative_path,
                    target_relative_path=operation.target_relative_path,
                    message="Copy is not allowed by policy.",
                    metadata={"policy": selected_policy.name},
                )
            return self._execute_copy(operation, config, dry_run=dry_run, policy=selected_policy)

        if operation.operation_type == FileOperationType.MOVE:
            if not selected_policy.allow_move:
                return FileOperationResult(
                    operation_id=operation.operation_id,
                    operation_type=operation.operation_type,
                    state=FileOperationState.BLOCKED,
                    source_relative_path=operation.source_relative_path,
                    target_relative_path=operation.target_relative_path,
                    message="Move is not allowed by policy.",
                    metadata={"policy": selected_policy.name},
                )
            return self._execute_move(operation, config, dry_run=dry_run, policy=selected_policy)

        if operation.operation_type == FileOperationType.MARK:
            return self._execute_mark(operation, config, dry_run=dry_run, policy=selected_policy)

        return FileOperationResult(
            operation_id=operation.operation_id,
            operation_type=operation.operation_type,
            state=FileOperationState.FAILED,
            message=f"Unknown operation type: {operation.operation_type.value}",
            metadata={"policy": selected_policy.name},
        )

    def _execute_mkdir(
        self,
        operation: FileOperation,
        config: FluxConfig,
        *,
        dry_run: bool,
        policy: FileExecutionPolicy,
    ) -> FileOperationResult:
        if not policy.allow_mkdir:
            return FileOperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                state=FileOperationState.BLOCKED,
                target_relative_path=operation.target_relative_path,
                message="Mkdir is not allowed by policy.",
                metadata={"policy": policy.name},
            )

        if not operation.target_relative_path:
            return FileOperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                state=FileOperationState.FAILED,
                message="No target path specified for mkdir.",
                metadata={"policy": policy.name},
            )

        try:
            resolved = _resolve_relative_path(
                operation.target_relative_path,
                config.workspace_root,
                config.protected_roots,
            )
        except PathSafetyError as exc:
            return FileOperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                state=FileOperationState.BLOCKED,
                target_relative_path=operation.target_relative_path,
                message=f"Safety check failed: {exc.message}",
                metadata={"policy": policy.name, "safety_code": exc.code},
            )

        if dry_run:
            if resolved.exists():
                return FileOperationResult(
                    operation_id=operation.operation_id,
                    operation_type=operation.operation_type,
                    state=FileOperationState.SKIPPED,
                    target_relative_path=operation.target_relative_path,
                    message=f"Directory already exists: {operation.target_relative_path}",
                    metadata={"policy": policy.name},
                )
            return FileOperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                state=FileOperationState.PLANNED,
                target_relative_path=operation.target_relative_path,
                message=f"Would create directory: {operation.target_relative_path}",
                metadata={"policy": policy.name},
            )

        if resolved.exists():
            return FileOperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                state=FileOperationState.SKIPPED,
                target_relative_path=operation.target_relative_path,
                message=f"Directory already exists: {operation.target_relative_path}",
                metadata={"policy": policy.name},
            )

        resolved.mkdir(parents=True, exist_ok=True)
        return FileOperationResult(
            operation_id=operation.operation_id,
            operation_type=operation.operation_type,
            state=FileOperationState.APPLIED,
            target_relative_path=operation.target_relative_path,
            message=f"Created directory: {operation.target_relative_path}",
            metadata={"policy": policy.name},
        )

    def _execute_copy(
        self,
        operation: FileOperation,
        config: FluxConfig,
        *,
        dry_run: bool,
        policy: FileExecutionPolicy,
    ) -> FileOperationResult:
        if not operation.source_relative_path or not operation.target_relative_path:
            return FileOperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                state=FileOperationState.FAILED,
                message="Both source and target paths are required for copy.",
                metadata={"policy": policy.name},
            )

        try:
            resolved_source = _resolve_relative_path(
                operation.source_relative_path,
                config.workspace_root,
                config.protected_roots,
            )
            resolved_target = _resolve_relative_path(
                operation.target_relative_path,
                config.workspace_root,
                config.protected_roots,
            )
        except PathSafetyError as exc:
            return FileOperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                state=FileOperationState.BLOCKED,
                source_relative_path=operation.source_relative_path,
                target_relative_path=operation.target_relative_path,
                message=f"Safety check failed: {exc.message}",
                metadata={"policy": policy.name, "safety_code": exc.code},
            )

        if not resolved_source.exists():
            return FileOperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                state=FileOperationState.FAILED,
                source_relative_path=operation.source_relative_path,
                target_relative_path=operation.target_relative_path,
                message=f"Source does not exist: {operation.source_relative_path}",
                metadata={"policy": policy.name},
            )

        if resolved_source.is_symlink():
            return FileOperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                state=FileOperationState.BLOCKED,
                source_relative_path=operation.source_relative_path,
                target_relative_path=operation.target_relative_path,
                message="Symlink source is not allowed.",
                metadata={"policy": policy.name},
            )

        if resolved_target.exists() and not policy.allow_overwrite:
            return FileOperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                state=FileOperationState.BLOCKED,
                source_relative_path=operation.source_relative_path,
                target_relative_path=operation.target_relative_path,
                message=f"Target already exists and overwrite is not allowed: {operation.target_relative_path}",
                metadata={"policy": policy.name},
            )

        if dry_run:
            return FileOperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                state=FileOperationState.PLANNED,
                source_relative_path=operation.source_relative_path,
                target_relative_path=operation.target_relative_path,
                message=f"Would copy: {operation.source_relative_path} -> {operation.target_relative_path}",
                metadata={"policy": policy.name},
            )

        resolved_target.parent.mkdir(parents=True, exist_ok=True)
        if resolved_source.is_file():
            shutil.copy2(str(resolved_source), str(resolved_target))
        elif resolved_source.is_dir():
            shutil.copytree(str(resolved_source), str(resolved_target), dirs_exist_ok=policy.allow_overwrite)
        else:
            return FileOperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                state=FileOperationState.FAILED,
                source_relative_path=operation.source_relative_path,
                target_relative_path=operation.target_relative_path,
                message=f"Source is not a file or directory: {operation.source_relative_path}",
                metadata={"policy": policy.name},
            )

        return FileOperationResult(
            operation_id=operation.operation_id,
            operation_type=operation.operation_type,
            state=FileOperationState.APPLIED,
            source_relative_path=operation.source_relative_path,
            target_relative_path=operation.target_relative_path,
            message=f"Copied: {operation.source_relative_path} -> {operation.target_relative_path}",
            metadata={"policy": policy.name},
        )

    def _execute_move(
        self,
        operation: FileOperation,
        config: FluxConfig,
        *,
        dry_run: bool,
        policy: FileExecutionPolicy,
    ) -> FileOperationResult:
        if not operation.source_relative_path or not operation.target_relative_path:
            return FileOperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                state=FileOperationState.FAILED,
                message="Both source and target paths are required for move.",
                metadata={"policy": policy.name},
            )

        try:
            resolved_source = _resolve_relative_path(
                operation.source_relative_path,
                config.workspace_root,
                config.protected_roots,
            )
            resolved_target = _resolve_relative_path(
                operation.target_relative_path,
                config.workspace_root,
                config.protected_roots,
            )
        except PathSafetyError as exc:
            return FileOperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                state=FileOperationState.BLOCKED,
                source_relative_path=operation.source_relative_path,
                target_relative_path=operation.target_relative_path,
                message=f"Safety check failed: {exc.message}",
                metadata={"policy": policy.name, "safety_code": exc.code},
            )

        if not resolved_source.exists():
            return FileOperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                state=FileOperationState.FAILED,
                source_relative_path=operation.source_relative_path,
                target_relative_path=operation.target_relative_path,
                message=f"Source does not exist: {operation.source_relative_path}",
                metadata={"policy": policy.name},
            )

        if resolved_source.is_symlink():
            return FileOperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                state=FileOperationState.BLOCKED,
                source_relative_path=operation.source_relative_path,
                target_relative_path=operation.target_relative_path,
                message="Symlink source is not allowed.",
                metadata={"policy": policy.name},
            )

        if resolved_target.exists() and not policy.allow_overwrite:
            return FileOperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                state=FileOperationState.BLOCKED,
                source_relative_path=operation.source_relative_path,
                target_relative_path=operation.target_relative_path,
                message=f"Target already exists and overwrite is not allowed: {operation.target_relative_path}",
                metadata={"policy": policy.name},
            )

        if dry_run:
            return FileOperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                state=FileOperationState.PLANNED,
                source_relative_path=operation.source_relative_path,
                target_relative_path=operation.target_relative_path,
                message=f"Would move: {operation.source_relative_path} -> {operation.target_relative_path}",
                metadata={"policy": policy.name},
            )

        resolved_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(resolved_source), str(resolved_target))

        return FileOperationResult(
            operation_id=operation.operation_id,
            operation_type=operation.operation_type,
            state=FileOperationState.APPLIED,
            source_relative_path=operation.source_relative_path,
            target_relative_path=operation.target_relative_path,
            message=f"Moved: {operation.source_relative_path} -> {operation.target_relative_path}",
            metadata={"policy": policy.name},
        )

    def _execute_mark(
        self,
        operation: FileOperation,
        config: FluxConfig,
        *,
        dry_run: bool,
        policy: FileExecutionPolicy,
    ) -> FileOperationResult:
        if not operation.target_relative_path:
            return FileOperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                state=FileOperationState.FAILED,
                message="Target path is required for mark.",
                metadata={"policy": policy.name},
            )

        try:
            _resolve_relative_path(
                operation.target_relative_path,
                config.workspace_root,
                config.protected_roots,
            )
        except PathSafetyError as exc:
            return FileOperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                state=FileOperationState.BLOCKED,
                target_relative_path=operation.target_relative_path,
                message=f"Safety check failed: {exc.message}",
                metadata={"policy": policy.name, "safety_code": exc.code},
            )

        if dry_run:
            return FileOperationResult(
                operation_id=operation.operation_id,
                operation_type=operation.operation_type,
                state=FileOperationState.PLANNED,
                target_relative_path=operation.target_relative_path,
                message=f"Would mark as delete-eligible: {operation.target_relative_path}",
                metadata={"policy": policy.name},
            )

        return FileOperationResult(
            operation_id=operation.operation_id,
            operation_type=operation.operation_type,
            state=FileOperationState.APPLIED,
            target_relative_path=operation.target_relative_path,
            message=f"Marked as delete-eligible: {operation.target_relative_path}. No file was deleted.",
            metadata={"policy": policy.name},
        )


def _staging_item_to_file_operation(
    item: StagingItem,
    policy: FileExecutionPolicy,
) -> FileOperation:
    op_id = f"fileop-{item.item_id}-{uuid.uuid4().hex[:8]}"

    if item.action_type == StagingActionType.MOVE:
        if policy.allow_move:
            return FileOperation(
                operation_id=op_id,
                operation_type=FileOperationType.MOVE,
                source_relative_path=item.source_relative_path,
                target_relative_path=item.target_relative_path,
                reason=f"Staging: {item.routing_outcome} -> {item.target_area.value}",
                metadata={"item_id": item.item_id, "staging_area": item.target_area.value},
            )
        return FileOperation(
            operation_id=op_id,
            operation_type=FileOperationType.NONE,
            source_relative_path=item.source_relative_path,
            target_relative_path=item.target_relative_path,
            reason=f"Staging: {item.routing_outcome} -> {item.target_area.value} (move blocked by policy)",
            metadata={"item_id": item.item_id, "staging_area": item.target_area.value, "blocked": True},
        )

    if item.action_type == StagingActionType.COPY:
        if policy.allow_copy:
            return FileOperation(
                operation_id=op_id,
                operation_type=FileOperationType.COPY,
                source_relative_path=item.source_relative_path,
                target_relative_path=item.target_relative_path,
                reason=f"Staging: {item.routing_outcome} -> {item.target_area.value}",
                metadata={"item_id": item.item_id, "staging_area": item.target_area.value},
            )
        return FileOperation(
            operation_id=op_id,
            operation_type=FileOperationType.NONE,
            source_relative_path=item.source_relative_path,
            target_relative_path=item.target_relative_path,
            reason=f"Staging: {item.routing_outcome} -> {item.target_area.value} (copy blocked by policy)",
            metadata={"item_id": item.item_id, "staging_area": item.target_area.value, "blocked": True},
        )

    if item.action_type == StagingActionType.MARK_DELETE_ELIGIBLE:
        return FileOperation(
            operation_id=op_id,
            operation_type=FileOperationType.MARK,
            target_relative_path=item.target_relative_path,
            reason=f"Staging: {item.routing_outcome} -> {item.target_area.value} (mark only, no delete)",
            metadata={"item_id": item.item_id, "staging_area": item.target_area.value},
        )

    return FileOperation(
        operation_id=op_id,
        operation_type=FileOperationType.NONE,
        source_relative_path=item.source_relative_path,
        target_relative_path=item.target_relative_path,
        reason=f"Staging: {item.routing_outcome} -> {item.target_area.value} (plan-only)",
        metadata={"item_id": item.item_id, "staging_area": item.target_area.value},
    )


def _resolve_relative_path(
    relative_path: str,
    workspace_root: Path,
    protected_roots: tuple[Path, ...] = (),
) -> Path:
    if relative_path.startswith("/") or relative_path.startswith("\\"):
        raise PathSafetyError(
            "absolute-path",
            "Absolute paths are not allowed.",
            {"path": relative_path},
        )

    candidate = workspace_root / relative_path
    resolved = ensure_within_workspace(candidate, workspace_root, protected_roots=protected_roots)

    if candidate.is_symlink():
        resolved_target = normalize_path(candidate)
        if not resolved_target.is_relative_to(normalize_path(workspace_root)):
            raise PathSafetyError(
                "symlink-escape",
                "Symlink resolves outside the workspace.",
                {"path": str(candidate), "resolved": str(resolved_target)},
            )

    return resolved
