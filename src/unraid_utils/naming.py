"""Where an episode belongs inside a show folder.

The old code did `f"Season {n}"` unconditionally. That is wrong on this library
in two ways: specials live in `Specials/`, and some season folders carry a
suffix (`Season 1 - Phantom Blood & Battle Tendency`). Creating a bare
`Season 1` next to an existing suffixed one splits the show in Plex.

So resolution is **match-existing-first**: look at what the show folder already
uses — across every branch, since a show is typically spread over several disks
— and only invent a name when nothing matches.
"""

from __future__ import annotations

import re
from pathlib import Path

from .paths import RealPath
from .unraid import branch_of, branches, sibling_on_branch

# `Season 1`, `Season 01`, `Season 1 - Subtitle`, `season 3`
_SEASON_DIR = re.compile(r"^season\s*0*(\d+)\b", re.IGNORECASE)
_SPECIALS_DIR = re.compile(r"^specials?$", re.IGNORECASE)


def season_from_dirname(name: str) -> int | None:
    """Season number a directory name denotes, or None."""
    if _SPECIALS_DIR.match(name):
        return 0
    m = _SEASON_DIR.match(name)
    return int(m.group(1)) if m else None


def default_season_dirname(season: int) -> str:
    """What to create when the show folder has no matching directory yet.

    Unpadded `Season N` matches this library's existing convention; season 0
    becomes `Specials`, which is what Plex expects.
    """
    return "Specials" if season == 0 else f"Season {season}"


def find_season_dirname(show_dir: RealPath, season: int) -> str | None:
    """The *name* an existing season directory uses, searched across branches.

    Only the name is returned, never the path. A show is typically spread over
    several disks, so the existing directory may be on a different branch from
    the source file — and a hardlink cannot cross branches. Reusing the name
    while rooting it on the caller's branch satisfies both constraints: shfs
    merges identically-named directories, so Plex still sees one folder.
    """
    candidates: list[Path] = [Path(show_dir)]
    branch = branch_of(show_dir)
    if branch is not None:
        for other in branches():
            if other.mount != branch.mount:
                try:
                    candidates.append(Path(sibling_on_branch(show_dir, other)))
                except ValueError:
                    continue

    for base in candidates:
        if not base.is_dir():
            continue
        try:
            entries = sorted(base.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir() and season_from_dirname(entry.name) == season:
                return entry.name
    return None


def find_season_dir(show_dir: RealPath, season: int) -> RealPath | None:
    """An existing season directory on this specific branch, if there is one."""
    name = None
    base = Path(show_dir)
    if base.is_dir():
        try:
            for entry in sorted(base.iterdir()):
                if entry.is_dir() and season_from_dirname(entry.name) == season:
                    name = entry.name
                    break
        except OSError:
            return None
    return RealPath(base / name) if name else None


def season_dir_for(show_dir: RealPath, season: int) -> tuple[RealPath, bool]:
    """Where this season's files go, always on `show_dir`'s own branch.

    Returns (path, exists_on_this_branch). The name is borrowed from whatever
    the show already uses anywhere — including `Specials` and suffixed names
    like `Season 1 - Subtitle` — so we never create a second, differently-named
    folder for the same season. But the path stays on the branch we were given,
    because the caller chose that branch to match the source file's disk.
    """
    on_this_branch = find_season_dir(show_dir, season)
    if on_this_branch is not None:
        return on_this_branch, True

    name = find_season_dirname(show_dir, season) or default_season_dirname(season)
    return RealPath(Path(show_dir) / name), False
