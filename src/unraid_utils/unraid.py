"""Unraid storage topology: turning `/mnt/user` paths into real disk paths.

This is the module the EXDEV fix rests on. `os.link()` fails with EXDEV across
filesystems, and on this server `/mnt/user` merges seven of them. Historically
that meant most hardlinks silently failed while the caller reported success —
the links that did survive were the ones where the destination happened to land
on the source's disk.

Two consequences shape everything here:

* A destination directory must be created on the *source's* disk, not wherever
  shfs's allocator would put it.
* A file can legitimately exist on two branches at once. Unraid's mover copies
  cache -> array and only then removes the cache copy, so mid-flight both are
  real, separate inodes. Callers must be told about all of them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .paths import USER_MOUNT, RealPath, UserPath, as_real, is_user_path

# Identify branches by filesystem type rather than by name. On this server
# /mnt also holds `addons`, `disks`, `remotes` and `rootshare` (all tmpfs) and
# `user`/`user0` (both fuse.shfs) — none of which are storage branches, and a
# name blocklist silently misses whatever Unraid adds next.
_NOT_BRANCH_FSTYPES = frozenset({
    "tmpfs", "ramfs", "devtmpfs", "fuse.shfs", "shfs", "overlay", "squashfs",
    "proc", "sysfs", "cgroup", "cgroup2", "nsfs", "autofs",
})

_MOUNTS = Path("/proc/mounts")


@dataclass(frozen=True, slots=True)
class Branch:
    mount: Path
    device: int

    @property
    def name(self) -> str:
        return self.mount.name


def _mounted_branches() -> dict[Path, str]:
    """Mount points directly under /mnt that are real filesystems."""
    found: dict[Path, str] = {}
    try:
        lines = _MOUNTS.read_text().splitlines()
    except OSError:
        return found
    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        # /proc/mounts octal-escapes spaces and similar in the mount point.
        mount = Path(parts[1].encode().decode("unicode_escape"))
        fstype = parts[2]
        if mount.parent != Path("/mnt"):
            continue
        if fstype in _NOT_BRANCH_FSTYPES:
            continue
        found[mount] = fstype
    return found


@lru_cache(maxsize=1)
def branches() -> tuple[Branch, ...]:
    """Discover real storage branches behind /mnt/user, ordered disk1..N then pools."""
    seen: dict[Path, Branch] = {}
    for mount in _mounted_branches():
        try:
            seen[mount] = Branch(mount, os.stat(mount).st_dev)
        except OSError:
            continue

    def sort_key(b: Branch) -> tuple[int, str]:
        # disk1, disk2, ... first (numerically), then pools alphabetically.
        if b.name.startswith("disk") and b.name[4:].isdigit():
            return (0, f"{int(b.name[4:]):04d}")
        return (1, b.name)

    return tuple(sorted(seen.values(), key=sort_key))


def relative_to_user(path: Path) -> Path | None:
    """`/mnt/user/plex/shows/X` -> `plex/shows/X`."""
    if not is_user_path(path):
        return None
    try:
        return path.relative_to(USER_MOUNT)
    except ValueError:
        return None


def resolve(path: Path) -> list[RealPath]:
    """All real branch locations of a path.

    Returns every branch where it exists — usually one, but two while the mover
    is mid-flight (cache and array copies are separate inodes). A path that is
    already a branch path resolves to itself.
    """
    if not is_user_path(path):
        return [as_real(path)] if path.exists() else []

    rel = relative_to_user(path)
    if rel is None:
        return []
    found = []
    for branch in branches():
        candidate = branch.mount / rel
        if candidate.exists():
            found.append(as_real(candidate))
    return found


def resolve_one(path: Path) -> RealPath | None:
    """The single real location, or None if absent. Ambiguity is the caller's problem."""
    hits = resolve(path)
    return hits[0] if hits else None


def branch_of(real: RealPath) -> Branch | None:
    """Which branch a real path lives on (by prefix, not by stat)."""
    for branch in branches():
        if real == branch.mount or branch.mount in real.parents:
            return branch
    return None


def device_of(path: Path) -> int | None:
    """`st_dev` of an existing path, or of its nearest existing parent."""
    probe = path
    while True:
        try:
            return os.stat(probe).st_dev
        except FileNotFoundError:
            if probe.parent == probe:
                return None
            probe = probe.parent
        except OSError:
            return None


def same_device(a: Path, b: Path) -> bool:
    """Whether a hardlink between these two could possibly succeed."""
    da, db = device_of(a), device_of(b)
    return da is not None and da == db


def sibling_on_branch(real: RealPath, branch: Branch) -> RealPath:
    """The equivalent of `real` on another branch, preserving the share-relative path."""
    src_branch = branch_of(real)
    if src_branch is None:
        raise ValueError(f"{real} is not on a known branch")
    return as_real(branch.mount / real.relative_to(src_branch.mount))


def user_equivalent(real: RealPath) -> UserPath | None:
    """Map a branch path back to its `/mnt/user` view."""
    branch = branch_of(real)
    if branch is None:
        return None
    return UserPath(USER_MOUNT / real.relative_to(branch.mount))
