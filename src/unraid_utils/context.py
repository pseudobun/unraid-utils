"""Run-wide state, threaded from one place.

Dry-run, the manifest and the allowlisted roots are global safety properties.
Keeping them in a single object passed down from the argument parser means a
command cannot accidentally default to acting — the only way to get
`dry_run=False` is for the parser to have seen `--execute`.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .manifest import DEFAULT_STATE_DIR, ManifestWriter

# Nothing outside these prefixes may ever be modified, whatever a caller asks.
DEFAULT_ALLOWED_ROOTS = (Path("/mnt/user"), Path("/mnt/disk1"), Path("/mnt/disk2"),
                         Path("/mnt/disk3"), Path("/mnt/disk4"), Path("/mnt/disk5"),
                         Path("/mnt/disk6"), Path("/mnt/primary"))


def new_run_id() -> str:
    return f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-{os.getpid()}"  # noqa: DTZ005 - local time: run ids are read alongside local log timestamps


class OutsideAllowedRoot(RuntimeError):
    """A path outside the allowlist was passed to a mutating operation."""


@dataclass(slots=True)
class RunContext:
    dry_run: bool = True
    assume_yes: bool = False
    run_id: str = field(default_factory=new_run_id)
    state_dir: Path = DEFAULT_STATE_DIR
    allowed_roots: tuple[Path, ...] = DEFAULT_ALLOWED_ROOTS
    log: logging.Logger = field(default_factory=lambda: logging.getLogger("unraid_utils"))
    manifest: ManifestWriter | None = None

    def __post_init__(self) -> None:
        if self.manifest is None:
            # Only record runs that can actually change something.
            self.manifest = ManifestWriter(self.run_id, self.state_dir,
                                           enabled=not self.dry_run)

    def check_allowed(self, path: Path) -> Path:
        """Reject anything outside the allowlist, and `/` explicitly."""
        resolved = Path(os.path.abspath(path))
        if resolved == Path("/") or resolved.parent == resolved:
            raise OutsideAllowedRoot(f"refusing to operate on {resolved}")
        for root in self.allowed_roots:
            if resolved == root or root in resolved.parents:
                return resolved
        raise OutsideAllowedRoot(
            f"{resolved} is outside the allowed roots "
            f"({', '.join(str(r) for r in self.allowed_roots)})")

    @property
    def mode(self) -> str:
        return "DRY RUN" if self.dry_run else "EXECUTE"
