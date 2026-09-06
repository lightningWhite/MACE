"""Entry point for the `mace` console script."""

import argparse
import sys
from collections.abc import Sequence

from mace import __version__


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
    return parser


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
    parser.parse_args(argv)

    # `play` and `validate` land with the content pipeline in phase 1.
    # See docs/12-roadmap.md.
    parser.print_help()
    print("\nNo commands yet — the content pipeline is phase 1.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
