from __future__ import annotations

import uuid
from typing import Any

from noqlen_flux.config import FluxConfig
from noqlen_flux.downloads import (
    DownloadConstraint,
    DownloadIntent,
    DownloadItem,
    DownloadPlan,
    DownloadPlanArtifact,
    DownloadRequest,
)
from noqlen_flux.results import Artifact, FluxError, FluxResult, FluxWarning, PlannedChange, Severity, Status, StepResult
from noqlen_flux.scoring import CandidateScore
from noqlen_flux.search import CandidateFile, SearchCandidate
from noqlen_flux.services.base import FluxService


class DownloadPlanningService(FluxService):
    operation = "download-planning"

    def plan_download(
        self,
        request: DownloadRequest,
        config: FluxConfig | None = None,
    ) -> FluxResult:
        warnings: list[FluxWarning] = []
        errors: list[FluxError] = []
        block_reasons: list[str] = []
        items: list[DownloadItem] = []
        plan_warnings: list[str] = []

        candidate_files = self._reconstruct_candidate_files(request)

        if not candidate_files:
            block_reasons.append("candidate has no files")
            return self._blocked_result(request, block_reasons, warnings, errors)

        score_check = self._check_score(request, config)
        if score_check is not None:
            block_reasons.append(score_check)
            return self._blocked_result(request, block_reasons, warnings, errors)

        locked_files = [f for f in candidate_files if f.locked]
        if locked_files and not request.constraints.allow_locked:
            if len(locked_files) == len(candidate_files):
                block_reasons.append("all files are locked and allow_locked is false")
                return self._blocked_result(request, block_reasons, warnings, errors)
            plan_warnings.append("some files are locked and will be excluded")
            warnings.append(
                self.warning(
                    "locked-files-excluded",
                    "Locked files are excluded from the plan because allow_locked is false.",
                    severity=Severity.WARNING,
                    locked_count=len(locked_files),
                )
            )

        visible_files = [f for f in candidate_files if not f.locked or request.constraints.allow_locked]

        extension_check = self._check_extensions(visible_files, request.constraints)
        if extension_check is not None:
            block_reasons.append(extension_check)
            return self._blocked_result(request, block_reasons, warnings, errors)

        if request.constraints.max_files is not None and len(visible_files) > request.constraints.max_files:
            block_reasons.append(
                f"candidate has {len(visible_files)} files but max_files is {request.constraints.max_files}"
            )
            return self._blocked_result(request, block_reasons, warnings, errors)

        total_bytes = sum(f.size_bytes or 0 for f in visible_files)
        if request.constraints.max_total_bytes is not None and total_bytes > request.constraints.max_total_bytes:
            block_reasons.append(
                f"total size {total_bytes} bytes exceeds max_total_bytes {request.constraints.max_total_bytes}"
            )
            return self._blocked_result(request, block_reasons, warnings, errors)

        for candidate_file in visible_files:
            if request.constraints.allow_locked and candidate_file.locked:
                plan_warnings.append(f"file {candidate_file.filename!r} is locked")
                warnings.append(
                    self.warning(
                        "locked-file-included",
                        f"Locked file {candidate_file.filename!r} is included in the plan.",
                        severity=Severity.WARNING,
                    )
                )

            target_path = self._build_target_path(request, candidate_file)
            if not _is_safe_relative_path(target_path):
                block_reasons.append(f"unsafe target path for {candidate_file.filename!r}")
                return self._blocked_result(request, block_reasons, warnings, errors)

            item = DownloadItem(
                item_id=str(uuid.uuid4()),
                candidate_id=request.candidate_id,
                filename=candidate_file.filename,
                target_relative_path=target_path,
                size_bytes=candidate_file.size_bytes,
                locked=candidate_file.locked,
            )
            items.append(item)

        if not items:
            block_reasons.append("no files available after constraint filtering")
            return self._blocked_result(request, block_reasons, warnings, errors)

        target_root = self._target_root(request)
        plan = DownloadPlan(
            plan_id=str(uuid.uuid4()),
            request_id=request.request_id,
            candidate_id=request.candidate_id,
            intent=request.intent,
            items=items,
            target_relative_root=target_root,
            total_size_bytes=total_bytes,
            warnings=plan_warnings,
            blocked=False,
            block_reasons=[],
        )

        planned_changes = [
            PlannedChange(
                action="plan-download",
                target=item.target_relative_path,
                reason=f"planned download item from candidate {request.candidate_id}",
                metadata={"item_id": item.item_id, "filename": item.filename},
            )
            for item in items
        ]

        artifact = Artifact(
            kind="download-plan",
            description="Logical download plan with no execution",
            metadata={
                "plan_id": plan.plan_id,
                "candidate_id": plan.candidate_id,
                "intent": plan.intent.value,
                "item_count": len(plan.items),
                "total_size_bytes": plan.total_size_bytes,
                "target_relative_root": plan.target_relative_root,
            },
        )

        step_status = Status.WARNING if (warnings or plan_warnings) else Status.SUCCESS
        step = self.step(
            "plan-download",
            step_status,
            f"Planned {len(items)} download item(s) for candidate {request.candidate_id}",
            warnings=warnings,
            errors=errors,
            artifacts=[artifact],
        )

        result = FluxResult(
            operation=self.operation,
            status=step_status,
            steps=[step],
            warnings=warnings,
            errors=errors,
            artifacts=[artifact],
            planned_changes=planned_changes,
            summary={
                "plan_id": plan.plan_id,
                "request_id": plan.request_id,
                "candidate_id": plan.candidate_id,
                "intent": plan.intent.value,
                "item_count": len(plan.items),
                "total_size_bytes": plan.total_size_bytes,
                "target_relative_root": plan.target_relative_root,
                "warnings": plan.warnings,
                "blocked": plan.blocked,
                "block_reasons": plan.block_reasons,
            },
        )
        return result.finish()

    def _reconstruct_candidate_files(self, request: DownloadRequest) -> list[CandidateFile]:
        files: list[CandidateFile] = []
        for file_data in request.candidate_files:
            files.append(
                CandidateFile(
                    filename=file_data.get("filename", ""),
                    size_bytes=file_data.get("size_bytes"),
                    declared_bitrate=file_data.get("declared_bitrate"),
                    extension=file_data.get("extension"),
                    duration_seconds=file_data.get("duration_seconds"),
                    locked=file_data.get("locked", False),
                    metadata=file_data.get("metadata", {}),
                )
            )
        return files

    def _check_score(self, request: DownloadRequest, config: FluxConfig | None) -> str | None:
        if request.constraints.require_score_min is None:
            return None
        if request.score_total is None:
            return "score is required but not available"
        if request.score_total < request.constraints.require_score_min:
            return (
                f"score {request.score_total} is below require_score_min {request.constraints.require_score_min}"
            )
        return None

    def _check_extensions(
        self, files: list[CandidateFile], constraints: DownloadConstraint
    ) -> str | None:
        if not constraints.allowed_extensions:
            return None
        for f in files:
            ext = (f.extension or "").casefold()
            if ext and ext not in constraints.allowed_extensions:
                return f"extension {ext!r} is not allowed"
        return None

    def _build_target_path(self, request: DownloadRequest, candidate_file: CandidateFile) -> str:
        if request.intent == DownloadIntent.ALBUM:
            return f"{request.candidate_id}/{candidate_file.filename}"
        return f"{request.candidate_id}/{candidate_file.filename}"

    def _target_root(self, request: DownloadRequest) -> str:
        if request.intent == DownloadIntent.ALBUM:
            return f"incoming/albums/{request.candidate_id}"
        return f"incoming/tracks/{request.candidate_id}"

    def _blocked_result(
        self,
        request: DownloadRequest,
        block_reasons: list[str],
        warnings: list[FluxWarning],
        errors: list[FluxError],
    ) -> FluxResult:
        plan = DownloadPlan(
            plan_id=str(uuid.uuid4()),
            request_id=request.request_id,
            candidate_id=request.candidate_id,
            intent=request.intent,
            items=[],
            blocked=True,
            block_reasons=block_reasons,
        )

        artifact = Artifact(
            kind="download-plan-blocked",
            description="Download plan was blocked by constraints or safety checks",
            metadata={
                "plan_id": plan.plan_id,
                "candidate_id": plan.candidate_id,
                "blocked": True,
                "block_reasons": plan.block_reasons,
            },
        )

        step = self.step(
            "plan-download",
            Status.FAILED,
            f"Download plan blocked for candidate {request.candidate_id}",
            warnings=warnings,
            errors=errors,
            artifacts=[artifact],
        )

        result = FluxResult(
            operation=self.operation,
            status=Status.FAILED,
            steps=[step],
            warnings=warnings,
            errors=errors,
            artifacts=[artifact],
            summary={
                "plan_id": plan.plan_id,
                "request_id": plan.request_id,
                "candidate_id": plan.candidate_id,
                "intent": plan.intent.value,
                "item_count": 0,
                "blocked": True,
                "block_reasons": plan.block_reasons,
            },
        )
        return result.finish()


def _is_safe_relative_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    parts = normalized.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            return False
    if normalized.startswith("/") or normalized.startswith(".."):
        return False
    return True
