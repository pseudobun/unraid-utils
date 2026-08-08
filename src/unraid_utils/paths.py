"""Two kinds of path, kept apart on purpose.

Unraid presents `/mnt/user` as one namespace, but it is a FUSE (shfs) merge over
several real filesystems: `/mnt/disk1..N` plus any cache pools. shfs synthesises
BOTH `st_dev` and `st_ino`, so the same file looks like this:

    /mnt/disk6/plex/.../x.mkv   dev=2310  ino=8589934730
    /mnt/user/plex/.../x.mkv    dev=46    ino=650207204791550090

Any identity or device decision made on a `/mnt/user` path is therefore
meaningless — comparing a user-path inode against a branch-path inode never
matches, and two user-path inodes are shfs-derived values with undocumented
collision behaviour. `st_nlink`, by contrast, does pass through correctly.

So the codebase keeps the two apart as distinct types: a `UserPath` is user
input, good for discovery and globbing; a `RealPath` is a resolved location on
one actual disk, and is the only thing allowed near `stat`, `link` or `rename`.
Mixing them is meant to be a type error rather than a silent wrong answer.
"""

from __future__ import annotations

from pathlib import Path
from typing import NewType

# A path under the shfs merge (/mnt/user/...). Accept as input; resolve before use.
UserPath = NewType("UserPath", Path)

# A path on one real branch (/mnt/disk3/..., /mnt/primary/...). Safe to stat.
RealPath = NewType("RealPath", Path)

USER_MOUNT = Path("/mnt/user")


class PathKindError(TypeError):
    """A shfs path was used where a real branch path is required, or vice versa."""


def is_user_path(path: Path) -> bool:
    return path == USER_MOUNT or USER_MOUNT in path.parents


def as_user(path: Path | str) -> UserPath:
    return UserPath(Path(path))


def as_real(path: Path | str) -> RealPath:
    """Assert a path is not under the shfs merge, then tag it as real."""
    p = Path(path)
    if is_user_path(p):
        raise PathKindError(
            f"{p} is under {USER_MOUNT} (shfs). Resolve it to a branch path "
            f"first — stat/link/rename on shfs paths give synthesised device "
            f"and inode values."
        )
    return RealPath(p)


def require_real(path: Path) -> RealPath:
    """Guard for functions that must not be handed a merged path."""
    return as_real(path)


def share_of(path: Path) -> str | None:
    """First path component below the mount point — the Unraid share name.

    `/mnt/disk6/plex/shows/X` -> `plex`;  `/mnt/user/plex/shows/X` -> `plex`.
    """
    parts = path.parts
    if len(parts) < 4 or parts[1] != "mnt":
        return None
    return parts[3]
