from __future__ import annotations

import argparse

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="noqlen-flux",
        description="Noqlen Flux Core bootstrap CLI. No real download or library operation is implemented.",
    )
    parser.add_argument("--version", action="version", version=f"noqlen-flux {__version__}")

    subparsers = parser.add_subparsers(dest="command")
    doctor = subparsers.add_parser("doctor", help="Show safe bootstrap status")
    doctor.set_defaults(func=run_doctor)

    return parser


def run_doctor(_args: argparse.Namespace) -> int:
    print("Noqlen Flux Core bootstrap: OK")
    print("Network, downloads, imports, cleanup, and library writes are not implemented.")
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
