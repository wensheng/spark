"""Small command line helpers for Spark operations."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spark")
    parser.add_argument("--version", action="store_true", help="Print Spark version and exit.")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("status", help="Print local Spark runtime status guidance.")
    subparsers.add_parser("doctor", help="Print local Spark runtime status guidance.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(f"Spark {__version__}")
        return 0
    if args.command in {"status", "doctor"}:
        print("Spark status: use Syndicate.diagnostics() or Syndicate.diagnostics_snapshot() for live runtimes.")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
