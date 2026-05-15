from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import datetime, timezone
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
from noqlen_flux.routing import (
    DEFAULT_ROUTING_APPLY_POLICY,
    RoutingApplyPolicy,
    RoutingOutcome,
)
from noqlen_flux.services.base import FluxService
from noqlen_flux.services.fileops import SafeFileOperationService
from noqlen_flux.staging import (
    DEFAULT_STAGING_EXECUTION_POLICY,
    StagingApplyReport,
    StagingActionType,
    StagingArea,
    StagingExecutionPolicy,
    StagingExecutionSummary,
    StagingItem,
    StagingPlan,
)


class StagingExecutionService(FluxService):
    operation = "staging-execution"

    def execute_staging_plan(
        self,
        staging_plan: StagingPlan,
        config: FluxConfig,
        *,
        dry_run: bool = True,
        policy: StagingExecutionPolicy | None = None,
    ) -> FluxResult:
        selected_policy = policy or DEFAULT_STAGING_EXECUTION_POLICY

        if dry_run:
            return self._execute_dry_run(staging_plan, config, selected_policy)

        return self._execute_apply(staging_plan, config, selected_policy)

    def apply_staging(
        self,
        staging_plan: StagingPlan,
        config: FluxConfig,
        *,
        apply_policy: RoutingApplyPolicy | None = None,
        staging_policy: StagingExecutionPolicy | None = None,
    ) -> FluxResult:
        if not config.dry_run and (apply_policy is None or staging_policy is None):
            return FluxResult(
                operation=self.operation,
                status=Status.FAILED,
                errors=[
                    FluxError(
                        code="missing-apply-policy",
                        message="Staging apply requires explicit routing apply and staging execution policies.",
                    )
                ],
                summary={"required_policies": ["apply_policy", "staging_policy"]},
            )

        selected_apply_policy = apply_policy or DEFAULT_ROUTING_APPLY_POLICY
        selected_staging_policy = staging_policy or DEFAULT_STAGING_EXECUTION_POLICY

        if selected_apply_policy.apply_explicit and config.dry_run:
            return self._execute_dry_run_with_apply_policy(
                staging_plan, config, selected_staging_policy, selected_apply_policy,
            )

        if config.dry_run:
            return self._execute_dry_run_with_apply_policy(
                staging_plan, config, selected_staging_policy, selected_apply_policy,
            )

        validation = self._validate_against_apply_policy(staging_plan, config, selected_apply_policy)
        if validation is not None:
            return validation

        raw_result = self._execute_apply(staging_plan, config, selected_staging_policy)

        report = self._build_safety_report(
            staging_plan, raw_result, selected_staging_policy, selected_apply_policy,
            mode="apply",
        )
        raw_result.artifacts.append(
            Artifact(
                kind="staging-apply-safety-report",
                description="Safety report for staging apply operation",
                metadata={"report": report.to_dict()},
            )
        )
        raw_result.summary["safety_report"] = report.to_dict()
        return raw_result

    def _validate_against_apply_policy(
        self,
        staging_plan: StagingPlan,
        config: FluxConfig,
        apply_policy: RoutingApplyPolicy,
    ) -> FluxResult | None:
        blocked_items: list[str] = []
        safety_notes: list[str] = []

        for item in staging_plan.items:
            if item.target_area == StagingArea.DELETE_ELIGIBLE:
                if not apply_policy.allow_delete_eligible and not apply_policy.allow_mark_delete_eligible:
                    blocked_items.append(
                        f"Item {item.item_id}: delete_eligible blocked by apply policy (no delete/mark allowed)"
                    )
                    safety_notes.append(
                        f"Blocked delete_eligible for {item.item_id}: policy forbids delete and mark-delete operations"
                    )
                    continue

            if item.target_area == StagingArea.QUARANTINE:
                if not apply_policy.allow_move_to_quarantine:
                    blocked_items.append(
                        f"Item {item.item_id}: quarantine blocked by apply policy"
                    )
                    continue

            if item.target_area == StagingArea.REJECTED:
                if not apply_policy.allow_move_to_rejected:
                    blocked_items.append(
                        f"Item {item.item_id}: rejected blocked by apply policy"
                    )
                    continue

            if item.target_area == StagingArea.APPROVED:
                if not apply_policy.allow_move_to_approved:
                    blocked_items.append(
                        f"Item {item.item_id}: approved blocked by apply policy"
                    )
                    continue

        if blocked_items:
            return self.result(
                Status.FAILED,
                error_count=len(blocked_items),
                blocked_items=blocked_items,
                safety_notes=safety_notes,
                message=f"Staging apply blocked: {len(blocked_items)} item(s) rejected by routing apply policy",
                error="\n".join(blocked_items),
            )

        return None

    def _execute_dry_run_with_apply_policy(
        self,
        staging_plan: StagingPlan,
        config: FluxConfig,
        staging_policy: StagingExecutionPolicy,
        apply_policy: RoutingApplyPolicy,
    ) -> FluxResult:
        plan_result = self.build_file_operation_plan(staging_plan, config, policy=staging_policy)

        operation_count = plan_result.summary.get("operation_count", 0)

        report = self._build_safety_report(
            staging_plan, plan_result, staging_policy, apply_policy,
            mode="dry-run",
        )

        artifact = Artifact(
            kind="staging-execution-result",
            description="Staging execution result (dry-run with routing apply policy)",
            metadata={
                "source_staging_plan_id": staging_plan.plan_id,
                "total_items": len(staging_plan.items),
                "mode": "dry-run",
                "policy": staging_policy.name,
                "apply_policy": apply_policy.name,
            },
        )

        has_warnings = len(plan_result.warnings) > 0
        has_errors = len(plan_result.errors) > 0

        if has_errors:
            step_status = Status.FAILED
        elif has_warnings:
            step_status = Status.WARNING
        else:
            step_status = Status.SUCCESS

        step_message = f"Staging apply: {len(staging_plan.items)} item(s) processed (dry-run, policy={apply_policy.name})"

        step = self.step(
            "apply-staging-plan",
            step_status,
            step_message,
            warnings=plan_result.warnings,
            errors=plan_result.errors,
            artifacts=[artifact],
        )

        result = FluxResult(
            operation=self.operation,
            status=step_status,
            steps=[step],
            warnings=plan_result.warnings,
            errors=plan_result.errors,
            artifacts=[artifact],
            planned_changes=plan_result.planned_changes,
            applied_changes=[],
            summary={
                "source_staging_plan_id": staging_plan.plan_id,
                "total_items": len(staging_plan.items),
                "mode": "dry-run",
                "apply_policy": apply_policy.to_dict(),
                "staging_policy": staging_policy.to_dict(),
                "safety_report": report.to_dict(),
                "applied_count": 0,
                "planned_count": operation_count,
                "blocked_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
            },
        )
        result.artifacts.append(
            Artifact(
                kind="staging-apply-safety-report",
                description="Safety report for staging apply dry-run",
                metadata={"report": report.to_dict()},
            )
        )
        return result.finish()

    def _build_safety_report(
        self,
        staging_plan: StagingPlan,
        result: FluxResult,
        staging_policy: StagingExecutionPolicy,
        apply_policy: RoutingApplyPolicy,
        mode: str,
    ) -> StagingApplyReport:
        summary = result.summary
        planned_count = summary.get("planned_count", summary.get("operation_count", 0))
        applied_count = summary.get("applied_count", 0)
        blocked_count = summary.get("blocked_count", 0)
        skipped_count = summary.get("skipped_count", 0)
        failed_count = summary.get("failed_count", 0)

        operations: list[dict[str, Any]] = []
        for change in result.planned_changes:
            operations.append({
                "action": change.action,
                "target": change.target,
                "reason": change.reason,
                "metadata": change.metadata,
            })
        for change in result.applied_changes:
            operations.append({
                "action": change.action,
                "target": change.target,
                "result": change.result,
                "metadata": change.metadata,
            })

        safety_checks: list[dict[str, Any]] = [
            {"check": "dry_run_default", "passed": apply_policy.dry_run_default, "note": "Dry-run is the default mode"},
            {"check": "apply_explicit", "passed": apply_policy.apply_explicit, "note": "Apply must be explicitly requested"},
            {"check": "workspace_only", "passed": apply_policy.workspace_only, "note": "All operations confined to workspace"},
            {"check": "block_absolute_path", "passed": apply_policy.block_absolute_path, "note": "Absolute paths are blocked"},
            {"check": "block_traversal", "passed": apply_policy.block_traversal, "note": "Path traversal markers are blocked"},
            {"check": "block_symlink_escape", "passed": apply_policy.block_symlink_escape, "note": "Symlink escape is blocked"},
            {"check": "block_protected_roots", "passed": apply_policy.block_protected_roots, "note": "Protected roots are blocked"},
            {"check": "no_delete", "passed": not staging_policy.allow_delete and not apply_policy.allow_delete_eligible, "note": "No delete operations exist"},
            {"check": "no_auto_delete", "passed": True, "note": "Auto-delete is never performed"},
            {"check": "no_library_writes", "passed": True, "note": "No real music library is accessed"},
            {"check": "no_forge_integration", "passed": True, "note": "No Forge integration is active"},
        ]

        blocked_ops: list[dict[str, Any]] = []
        skipped_ops: list[dict[str, Any]] = []

        for item in staging_plan.items:
            if item.target_area == StagingArea.DELETE_ELIGIBLE:
                blocked_ops.append({
                    "item_id": item.item_id,
                    "target_area": item.target_area.value,
                    "reason": "delete_eligible is blocked by policy (no delete, no auto-delete)",
                    "applied": False,
                })

        notes: list[str] = []
        if mode == "dry-run":
            notes.append("Dry-run mode: no filesystem changes were made")
        else:
            notes.append("Apply mode: workspace-only operations were executed")
        notes.append("Delete operations do not exist in this version")
        notes.append("Auto-delete is never performed")
        notes.append(f"Policy: {apply_policy.name} v{apply_policy.version}")

        return StagingApplyReport.from_execution_result(
            report_id=str(uuid.uuid4()),
            source_staging_plan_id=staging_plan.plan_id,
            mode=mode,
            timestamp=datetime.now(timezone.utc).isoformat(),
            policy_name=apply_policy.name,
            total_items=len(staging_plan.items),
            planned_count=planned_count,
            applied_count=applied_count,
            blocked_count=blocked_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            operations=operations,
            safety_checks=safety_checks,
            blocked_operations=blocked_ops,
            skipped_operations=skipped_ops,
            warnings=[w.message for w in result.warnings],
            errors=[e.message for e in result.errors],
            notes=notes,
            metadata={"apply_policy": apply_policy.name, "staging_policy": staging_policy.name},
        )

    def _execute_dry_run(
        self,
        staging_plan: StagingPlan,
        config: FluxConfig,
        policy: StagingExecutionPolicy,
    ) -> FluxResult:
        plan_result = self.build_file_operation_plan(staging_plan, config, policy=policy)

        operation_count = plan_result.summary.get("operation_count", 0)

        execution_summary = StagingExecutionSummary(
            total_items=len(staging_plan.items),
            planned_count=operation_count,
            applied_count=0,
            blocked_count=0,
            skipped_count=0,
            warnings=[w.message for w in plan_result.warnings],
            errors=[e.message for e in plan_result.errors],
            metadata={
                "mode": "dry-run",
                "policy": policy.name,
                "source_staging_plan_id": staging_plan.plan_id,
            },
        )

        artifact = Artifact(
            kind="staging-execution-result",
            description="Staging execution result (dry-run)",
            metadata={
                "source_staging_plan_id": staging_plan.plan_id,
                "total_items": len(staging_plan.items),
                "mode": "dry-run",
                "policy": policy.name,
            },
        )

        has_warnings = len(plan_result.warnings) > 0
        has_errors = len(plan_result.errors) > 0

        if has_errors:
            step_status = Status.FAILED
        elif has_warnings:
            step_status = Status.WARNING
        else:
            step_status = Status.SUCCESS

        step_message = f"Staging execution: {len(staging_plan.items)} item(s) processed (dry-run)"

        step = self.step(
            "execute-staging-plan",
            step_status,
            step_message,
            warnings=plan_result.warnings,
            errors=plan_result.errors,
            artifacts=[artifact],
        )

        return FluxResult(
            operation=self.operation,
            status=step_status,
            steps=[step],
            warnings=plan_result.warnings,
            errors=plan_result.errors,
            artifacts=[artifact],
            planned_changes=plan_result.planned_changes,
            applied_changes=[],
            summary={
                "source_staging_plan_id": staging_plan.plan_id,
                "total_items": len(staging_plan.items),
                "mode": "dry-run",
                "policy": policy.to_dict(),
                "execution_summary": execution_summary.to_dict(),
                "applied_count": 0,
                "planned_count": operation_count,
                "blocked_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
            },
        ).finish()

    def _execute_apply(
        self,
        staging_plan: StagingPlan,
        config: FluxConfig,
        policy: StagingExecutionPolicy,
    ) -> FluxResult:
        file_op_result = self._build_and_execute_file_operations(
            staging_plan, config, staging_policy=policy,
        )

        if file_op_result.status == Status.FAILED:
            return self._wrap_failed_result(staging_plan, file_op_result, policy, dry_run=False)

        return self._wrap_success_result(staging_plan, file_op_result, policy, dry_run=False)

    def build_file_operation_plan(
        self,
        staging_plan: StagingPlan,
        config: FluxConfig,
        *,
        policy: StagingExecutionPolicy | None = None,
    ) -> FluxResult:
        selected_policy = policy or DEFAULT_STAGING_EXECUTION_POLICY
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
            metadata={
                "policy": selected_policy.name,
                "source_staging_plan_id": staging_plan.plan_id,
            },
        )

        artifact = Artifact(
            kind="file-operation-plan",
            description="File operation plan derived from staging plan (planned-only, no execution)",
            metadata={
                "plan_id": plan.plan_id,
                "operation_count": len(operations),
                "policy": selected_policy.name,
                "source_staging_plan_id": staging_plan.plan_id,
            },
        )

        step_status = Status.WARNING if all_warnings else Status.SUCCESS
        step_message = f"File operation plan: {len(operations)} operation(s) derived from staging plan"

        step = self.step(
            "build-file-operation-plan",
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
                "source_staging_plan_id": staging_plan.plan_id,
                "file_operation_plan": plan.to_dict(),
            },
        ).finish()

    def _build_and_execute_file_operations(
        self,
        staging_plan: StagingPlan,
        config: FluxConfig,
        *,
        staging_policy: StagingExecutionPolicy,
    ) -> FluxResult:
        file_policy = FileExecutionPolicy(
            name=staging_policy.name,
            version=staging_policy.version,
            description=staging_policy.description,
            allow_move=staging_policy.allow_move,
            allow_copy=staging_policy.allow_copy,
            allow_mkdir=staging_policy.create_workspace_dirs,
            allow_delete=staging_policy.allow_delete,
            allow_overwrite=staging_policy.allow_overwrite,
            metadata=dict(staging_policy.metadata),
        )

        operations: list[FileOperation] = []
        for item in staging_plan.items:
            op = _staging_item_to_file_operation(item, staging_policy)
            operations.append(op)

        mkdir_ops = _ensure_workspace_dirs(staging_plan, staging_policy)
        all_ops = mkdir_ops + operations

        plan = FileOperationPlan(
            plan_id=str(uuid.uuid4()),
            operations=all_ops,
            metadata={
                "source_staging_plan_id": staging_plan.plan_id,
                "policy": staging_policy.name,
            },
        )

        fileops_service = SafeFileOperationService()
        return fileops_service.execute_plan(plan, config, dry_run=False, policy=file_policy)

    def _wrap_success_result(
        self,
        staging_plan: StagingPlan,
        file_op_result: FluxResult,
        policy: StagingExecutionPolicy,
        dry_run: bool,
    ) -> FluxResult:
        mode_label = "dry-run" if dry_run else "apply"
        summary = file_op_result.summary
        applied_count = summary.get("applied_count", 0)
        planned_count = summary.get("planned_count", 0)
        blocked_count = summary.get("blocked_count", 0)
        skipped_count = summary.get("skipped_count", 0)
        failed_count = summary.get("failed_count", 0)

        execution_summary = StagingExecutionSummary(
            total_items=len(staging_plan.items),
            planned_count=planned_count,
            applied_count=applied_count,
            blocked_count=blocked_count,
            skipped_count=skipped_count,
            warnings=[w.message for w in file_op_result.warnings],
            errors=[e.message for e in file_op_result.errors],
            metadata={
                "mode": mode_label,
                "policy": policy.name,
                "source_staging_plan_id": staging_plan.plan_id,
            },
        )

        artifact = Artifact(
            kind="staging-execution-result",
            description=f"Staging execution result ({mode_label})",
            metadata={
                "source_staging_plan_id": staging_plan.plan_id,
                "total_items": len(staging_plan.items),
                "mode": mode_label,
                "policy": policy.name,
            },
        )

        has_errors = failed_count > 0
        has_warnings = blocked_count > 0 or skipped_count > 0

        if has_errors:
            step_status = Status.FAILED
        elif has_warnings:
            step_status = Status.WARNING
        else:
            step_status = Status.SUCCESS

        step_message = f"Staging execution: {len(staging_plan.items)} item(s) processed ({mode_label})"

        step = self.step(
            "execute-staging-plan",
            step_status,
            step_message,
            warnings=file_op_result.warnings,
            errors=file_op_result.errors,
            artifacts=[artifact],
        )

        return FluxResult(
            operation=self.operation,
            status=step_status,
            steps=[step],
            warnings=file_op_result.warnings,
            errors=file_op_result.errors,
            artifacts=[artifact],
            planned_changes=file_op_result.planned_changes,
            applied_changes=file_op_result.applied_changes,
            summary={
                "source_staging_plan_id": staging_plan.plan_id,
                "total_items": len(staging_plan.items),
                "mode": mode_label,
                "policy": policy.to_dict(),
                "execution_summary": execution_summary.to_dict(),
                "applied_count": applied_count,
                "planned_count": planned_count,
                "blocked_count": blocked_count,
                "skipped_count": skipped_count,
                "failed_count": failed_count,
            },
        ).finish()

    def _wrap_failed_result(
        self,
        staging_plan: StagingPlan,
        file_op_result: FluxResult,
        policy: StagingExecutionPolicy,
        dry_run: bool,
    ) -> FluxResult:
        mode_label = "dry-run" if dry_run else "apply"

        execution_summary = StagingExecutionSummary(
            total_items=len(staging_plan.items),
            warnings=[w.message for w in file_op_result.warnings],
            errors=[e.message for e in file_op_result.errors],
            metadata={
                "mode": mode_label,
                "policy": policy.name,
                "source_staging_plan_id": staging_plan.plan_id,
            },
        )

        artifact = Artifact(
            kind="staging-execution-result",
            description=f"Staging execution failed ({mode_label})",
            metadata={
                "source_staging_plan_id": staging_plan.plan_id,
                "total_items": len(staging_plan.items),
                "mode": mode_label,
                "policy": policy.name,
            },
        )

        step = self.step(
            "execute-staging-plan",
            Status.FAILED,
            f"Staging execution failed: {len(file_op_result.errors)} error(s)",
            warnings=file_op_result.warnings,
            errors=file_op_result.errors,
            artifacts=[artifact],
        )

        return FluxResult(
            operation=self.operation,
            status=Status.FAILED,
            steps=[step],
            warnings=file_op_result.warnings,
            errors=file_op_result.errors,
            artifacts=[artifact],
            planned_changes=file_op_result.planned_changes,
            applied_changes=file_op_result.applied_changes,
            summary={
                "source_staging_plan_id": staging_plan.plan_id,
                "total_items": len(staging_plan.items),
                "mode": mode_label,
                "policy": policy.to_dict(),
                "execution_summary": execution_summary.to_dict(),
            },
        ).finish()


def _staging_item_to_file_operation(
    item: StagingItem,
    policy: StagingExecutionPolicy,
) -> FileOperation:
    op_id = f"stg-fileop-{item.item_id}-{uuid.uuid4().hex[:8]}"

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


def _ensure_workspace_dirs(
    staging_plan: StagingPlan,
    policy: StagingExecutionPolicy,
) -> list[FileOperation]:
    if not policy.create_workspace_dirs:
        return []

    areas_needed: set[str] = set()
    for item in staging_plan.items:
        if item.action_type in (StagingActionType.COPY, StagingActionType.MOVE, StagingActionType.MARK_DELETE_ELIGIBLE):
            areas_needed.add(item.target_area.value)

    ops: list[FileOperation] = []
    for area in sorted(areas_needed):
        ops.append(
            FileOperation(
                operation_id=f"stg-mkdir-{area}-{uuid.uuid4().hex[:8]}",
                operation_type=FileOperationType.MKDIR,
                target_relative_path=area,
                reason=f"Ensure staging directory: {area}",
                metadata={"staging_area": area},
            )
        )
    return ops
