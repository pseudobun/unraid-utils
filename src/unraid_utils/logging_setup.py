"""Logging to stdout and to a persistent file.

The old scripts used bare `print`, untimestamped and unrecorded, so a run that
went wrong left nothing to reconstruct it from. The log directory lives in
appdata rather than the repo: it must survive `git pull`, and it must not be on
the RAM-backed root, which is wiped on reboot.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from .manifest import DEFAULT_STATE_DIR

LOGGER_NAME = "unraid_utils"


def setup(verbose: bool = False, quiet: bool = False,
          state_dir: Path = DEFAULT_STATE_DIR,
          log_file: Path | None = None) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.WARNING if quiet else
                     (logging.DEBUG if verbose else logging.INFO))
    console.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console)

    if log_file is None:
        log_file = (state_dir / "logs" /
                    f"unraid-utils-{datetime.now().strftime('%Y-%m-%d')}.log")  # noqa: DTZ005 - local date: operators look for "today's" log
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(message)s"))
        logger.addHandler(handler)
    except OSError as exc:
        # A missing log destination must not stop the tool from running.
        logger.warning("could not open log file %s: %s", log_file, exc)

    return logger
