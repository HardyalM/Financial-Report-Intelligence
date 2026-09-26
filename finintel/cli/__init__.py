"""`finintel` command line. Subcommands arrive with their milestones (inspect: M1)."""

import sys


def main(argv: list[str] | None = None) -> int:
    """Entry point for the `finintel` console script."""
    args = sys.argv[1:] if argv is None else argv
    print(
        "finintel: no commands yet. `inspect` arrives in M1 (see docs/MILESTONES.md).",
        file=sys.stderr,
    )
    return 2 if args else 0
