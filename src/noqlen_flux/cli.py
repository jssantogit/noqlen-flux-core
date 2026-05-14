from __future__ import annotations

import argparse

from . import __version__
from .config import config_from_env
from .reports import ReportFormat
from .results import FluxResult, Status
from .services import DoctorService, ReportService, WorkspaceService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="noqlen-flux",
        description="Noqlen Flux Core bootstrap CLI. No real download or library operation is implemented.",
    )
    parser.add_argument("--version", action="version", version=f"noqlen-flux {__version__}")

    subparsers = parser.add_subparsers(dest="command")
    doctor = subparsers.add_parser("doctor", help="Show safe bootstrap status")
    doctor.set_defaults(func=run_doctor)

    workspace = subparsers.add_parser("workspace", help="Inspect or initialize a safe Flux workspace")
    workspace_subparsers = workspace.add_subparsers(dest="workspace_command")

    workspace_inspect = workspace_subparsers.add_parser("inspect", help="Inspect a Flux workspace layout")
    workspace_inspect.add_argument("path", help="Workspace root path")
    workspace_inspect.set_defaults(func=run_workspace_inspect)

    workspace_init = workspace_subparsers.add_parser("init", help="Plan or create Flux workspace directories")
    workspace_init.add_argument("path", help="Workspace root path")
    mode = workspace_init.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Plan changes without creating directories")
    mode.add_argument("--apply", action="store_true", help="Create missing workspace directories")
    workspace_init.set_defaults(func=run_workspace_init)

    report = subparsers.add_parser("report", help="Plan or write safe report artifacts")
    report_subparsers = report.add_subparsers(dest="report_command")

    report_demo = report_subparsers.add_parser("demo", help="Generate a safe demo report result")
    report_demo.add_argument("--workspace", required=True, help="Workspace root path")
    report_demo.add_argument("--format", choices=[item.value for item in ReportFormat], default=ReportFormat.JSON.value)
    report_mode = report_demo.add_mutually_exclusive_group()
    report_mode.add_argument("--dry-run", action="store_true", help="Plan report writing without creating a file")
    report_mode.add_argument("--apply", action="store_true", help="Write the report inside workspace/reports")
    report_demo.set_defaults(func=run_report_demo)

    return parser


def run_doctor(_args: argparse.Namespace) -> int:
    result = DoctorService().run()
    print(_render_result(result))
    return _exit_code(result.status)


def run_workspace_inspect(args: argparse.Namespace) -> int:
    result = WorkspaceService().inspect_workspace(config_from_env(args.path, dry_run=True))
    print(_render_result(result))
    return _exit_code(result.status)


def run_workspace_init(args: argparse.Namespace) -> int:
    dry_run = not args.apply
    result = WorkspaceService().ensure_workspace(config_from_env(args.path, dry_run=dry_run), dry_run=dry_run)
    print(_render_result(result))
    return _exit_code(result.status)


def run_report_demo(args: argparse.Namespace) -> int:
    dry_run = not args.apply
    service = ReportService()
    config = config_from_env(args.workspace, dry_run=dry_run)
    source = service.demo_result()
    if dry_run:
        result = service.preview_report(config, source, args.format)
    else:
        result = service.write_report(config, source, args.format)
    print(_render_result(result))
    return _exit_code(result.status)


def _render_result(result: FluxResult) -> str:
    lines = [f"Noqlen Flux Core {result.operation}: {result.status.value}"]
    lines.extend(step.message for step in result.steps if step.message)
    lines.extend(f"planned: {change.action} {change.target}" for change in result.planned_changes)
    lines.extend(f"applied: {change.action} {change.target}" for change in result.applied_changes)
    lines.extend(f"error: {error.code}: {error.message}" for error in result.errors)
    return "\n".join(lines)


def _exit_code(status: Status) -> int:
    if status == Status.FAILED:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
