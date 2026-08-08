"""Filesystem operations that can lose data, in one place.

Every hardlink and every deletion in this package goes through here, so the
safety properties are stated once instead of re-derived per command.

`safe_link` exists because the old hardlinker had three separate faults that
compounded: it incremented its success counter *before* attempting the link,
swallowed the resulting EXDEV in a bare `except Exception`, and on conflict did
`os.remove` followed by `os.link` — so a failure left the destination deleted
and nothing in its place. The net effect was a tool that reported links it had
never made, which the delete tooling downstream then trusted.
"""

from __future__ import annotations

import errno
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .paths import RealPath, as_real
from .unraid import branch_of, same_device


class LinkStatus(StrEnum):
    CREATED = "created"
    ALREADY_LINKED = "already_linked"   # destination is the same inode; nothing to do
    EXISTS_DIFFERENT = "exists_different"  # destination exists and is another file
    CROSS_DEVICE = "cross_device"       # EXDEV: source and destination on different disks
    FAILED = "failed"
    DRY_RUN = "dry_run"


@dataclass(frozen=True, slots=True)
class LinkResult:
    status: LinkStatus
    source: Path
    dest: Path
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status in (LinkStatus.CREATED, LinkStatus.ALREADY_LINKED,
                               LinkStatus.DRY_RUN)

    @property
    def counts_as_created(self) -> bool:
        """Only a verified new link. Used for reporting, so it must not lie."""
        return self.status is LinkStatus.CREATED


def _same_inode(a: RealPath, b: RealPath) -> bool:
    """Identity comparison — valid only on real branch paths.

    shfs synthesises st_ino, so this would be meaningless through /mnt/user.
    `as_real` enforces that at the type boundary.
    """
    try:
        sa, sb = os.stat(a), os.stat(b)
    except OSError:
        return False
    return (sa.st_dev, sa.st_ino) == (sb.st_dev, sb.st_ino)


def safe_link(source: RealPath, dest: RealPath, *, dry_run: bool = True,
              overwrite: bool = False) -> LinkResult:
    """Hardlink `source` to `dest`, atomically, verifying the result.

    Both paths must be real branch paths. Refuses across devices rather than
    silently copying: on Unraid a cross-branch "link" would either fail or, if
    a caller fell back to copying, duplicate tens of gigabytes onto a full array.
    """
    source = as_real(Path(source))
    dest = as_real(Path(dest))

    if not source.exists():
        return LinkResult(LinkStatus.FAILED, source, dest, "source does not exist")

    if dest.exists():
        if _same_inode(source, dest):
            return LinkResult(LinkStatus.ALREADY_LINKED, source, dest)
        if not overwrite:
            return LinkResult(LinkStatus.EXISTS_DIFFERENT, source, dest,
                              "destination exists and is a different file")

    # Check before acting: a clear refusal beats an EXDEV traceback, and tells
    # the caller to place the destination on the source's disk instead.
    dest_parent = dest.parent
    if dest_parent.exists() and not same_device(source, dest_parent):
        src_branch = branch_of(source)
        dst_branch = branch_of(as_real(dest_parent))
        return LinkResult(
            LinkStatus.CROSS_DEVICE, source, dest,
            f"source on {src_branch.name if src_branch else '?'}, "
            f"destination on {dst_branch.name if dst_branch else '?'}")

    if dry_run:
        return LinkResult(LinkStatus.DRY_RUN, source, dest)

    try:
        dest_parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return LinkResult(LinkStatus.FAILED, source, dest, f"mkdir: {exc}")

    # Link to a temporary name in the destination directory, then rename over.
    # os.replace is atomic, so the destination is never absent: on any failure
    # the original is still there, unlike the old remove-then-link.
    tmp = dest.with_name(f".{dest.name}.uutils-{os.getpid()}.tmp")
    try:
        os.link(source, tmp)
    except OSError as exc:
        if exc.errno == errno.EXDEV:
            return LinkResult(LinkStatus.CROSS_DEVICE, source, dest, str(exc))
        return LinkResult(LinkStatus.FAILED, source, dest, str(exc))

    try:
        os.replace(tmp, dest)
    except OSError as exc:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return LinkResult(LinkStatus.FAILED, source, dest, f"replace: {exc}")

    # Verify rather than assume. This is the check whose absence let the old
    # tool report links that did not exist.
    if not _same_inode(source, dest):
        return LinkResult(LinkStatus.FAILED, source, dest,
                          "post-link verification failed: inodes differ")

    return LinkResult(LinkStatus.CREATED, source, dest)


def plan_link_destination(source: RealPath, show_dir_user: Path,
                          season: int) -> tuple[RealPath, str] | None:
    """Pick a show directory on the *source's* disk, so the link can succeed.

    Returns (show_dir_on_source_branch, reason) or None if the source is not on
    a known branch. Deliberately does not create anything.
    """
    from .unraid import relative_to_user

    branch = branch_of(source)
    if branch is None:
        return None
    rel = relative_to_user(show_dir_user)
    if rel is None:
        return None
    return as_real(branch.mount / rel), branch.name


def link_count(path: Path) -> int:
    """`st_nlink`, which — unlike st_ino — does pass through shfs correctly."""
    try:
        return os.stat(path).st_nlink
    except OSError:
        return 0
