"""Shared helper for M0 stubs: every unimplemented stage fails loudly, naming its session."""

from typing import NoReturn


def not_yet(session: str, what: str) -> NoReturn:
    """Raise NotImplementedError naming the milestone session that implements `what`."""
    raise NotImplementedError(f"{what} is implemented in {session} (see docs/MILESTONES.md).")
