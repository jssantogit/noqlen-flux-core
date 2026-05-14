from __future__ import annotations

import argparse

from . import __version__
from .config import config_from_env
from .results import FluxResult, Status
from .services import DoctorService, WorkspaceService


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
