"""Entry point for the `mace` console script."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from mace import __version__
from mace.content import Severity, validate_paths


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser.

    Returns
    -------
    argparse.ArgumentParser
        The parser for the `mace` command.
    """
    parser = argparse.ArgumentParser(
        prog="mace",
        description="MACE — build and play text-driven adventure worlds.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"mace {__version__}",
    )
    commands = parser.add_subparsers(dest="command")

    validate = commands.add_parser(
        "validate",
        help="check content packs and report what is wrong with them",
        description=(
            "Load every pack under the given paths and report problems. "
            "Exits non-zero if anything is an error."
        ),
    )
    validate.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path("packs")],
        help="pack directories to check (default: packs/)",
    )
    validate.add_argument(
        "--errors-only",
        action="store_true",
        help="report only what breaks the game, hiding warnings and notes",
    )
    validate.set_defaults(run=run_validate)
    return parser


def run_validate(options: argparse.Namespace) -> int:
    """Run `mace validate`.

    Parameters
    ----------
    options : argparse.Namespace
        Parsed arguments.

    Returns
    -------
    int
        0 when nothing is at error severity, 1 otherwise.
    """
    report = validate_paths(*options.paths)
    include = Severity.ERROR if options.errors_only else None
    stream = sys.stdout if report.ok else sys.stderr
    print(report.format(include=include), file=stream)
    return 0 if report.ok else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Parameters
    ----------
    argv : Sequence[str] | None
        Arguments to parse. Defaults to `sys.argv[1:]`.

    Returns
    -------
    int
        The process exit code.
    """
    parser = build_parser()
    options = parser.parse_args(argv)

    if not hasattr(options, "run"):
        parser.print_help()
        # `play` lands with the engine, later in phase 1. See docs/12-roadmap.md.
        print("\nNo game to play yet — `mace validate` is what works.", file=sys.stderr)
        return 0

    exit_code: int = options.run(options)
    return exit_code
