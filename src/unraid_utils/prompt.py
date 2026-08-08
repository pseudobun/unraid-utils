"""Interactive confirmation.

The old code had three copies of this helper, each broken the same three ways:
bare Enter meant *yes* (so a stray newline consented to a deletion), invalid
answers recursed instead of looping (RecursionError after ~1000 of them), and
`EOFError` was uncaught, so running under cron or a pipe crashed mid-delete.

One copy, defaulting to no.
"""

from __future__ import annotations

import sys


class Aborted(Exception):
    """The operator declined, or input was unavailable."""


def confirm(question: str, *, default: bool = False, assume_yes: bool = False,
            stream=None) -> bool:
    """Ask a yes/no question. Destructive callers must leave `default` False.

    Returns the answer; `q` raises `Aborted` to stop the whole run. A closed or
    non-interactive stdin also raises rather than assuming consent.
    """
    if assume_yes:
        return True

    stream = stream or sys.stdin
    suffix = "[y/N]" if not default else "[Y/n]"

    if not stream.isatty():
        raise Aborted(
            f"{question} {suffix}: no terminal available to answer. "
            f"Pass --yes to proceed non-interactively.")

    for _ in range(10):
        try:
            reply = input(f"{question} {suffix} (q to abort): ").strip().lower()
        except (EOFError, KeyboardInterrupt) as exc:
            raise Aborted("input closed or interrupted") from exc

        if reply == "":
            return default
        if reply in ("y", "yes"):
            return True
        if reply in ("n", "no"):
            return False
        if reply in ("q", "quit", "abort"):
            raise Aborted("aborted by operator")
        print("Please answer y, n, or q.")

    raise Aborted("too many invalid answers")
