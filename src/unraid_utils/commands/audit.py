"""Read-only inspection of the library. Touches nothing.

This exists because the assumption the delete tooling rests on — "the original
is safe to remove because a hardlink into the library exists" — turned out to be
false for ~96% of files. `audit links` measures that directly instead of
assuming it, and is the gate that `tdarr-xref` should be judged against.

`audit parse` reports what the release-name parser cannot understand, so those
files are visible rather than silently mishandled.
"""

from __future__ import annotations

import collections
import os
from pathlib import Path

from ..context import RunContext
from ..media import MediaKind, is_subtitle, is_video, looks_like_junk, parse_release
from ..unraid import branch_of, branches, resolve


def _iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if not name.startswith("."):
                yield Path(dirpath) / name


def links(ctx: RunContext, roots: list[Path]) -> int:
    """Hardlink census: how much of the library has a second directory entry."""
    log = ctx.log
    grand_sole = grand_linked = 0

    for root in roots:
        sole = linked = 0
        sole_bytes = 0
        by_branch: collections.Counter[str] = collections.Counter()

        for path in _iter_files(root):
            if not is_video(path.name):
                continue
            try:
                st = os.stat(path)
            except OSError:
                continue
            # st_nlink passes through shfs correctly, unlike st_ino.
            if st.st_nlink > 1:
                linked += 1
            else:
                sole += 1
                sole_bytes += st.st_size
            for real in resolve(path):
                branch = branch_of(real)
                if branch:
                    by_branch[branch.name] += 1
                break

        total = sole + linked
        grand_sole += sole
        grand_linked += linked
        pct = (100 * linked / total) if total else 0.0
        log.info("")
        log.info("%s", root)
        log.info("  video files          : %d", total)
        log.info("  sole copy (nlink=1)  : %d", sole)
        log.info("  hardlinked (nlink>1) : %d  (%.1f%%)", linked, pct)
        log.info("  sole-copy size       : %.1f GiB", sole_bytes / 2**30)
        if by_branch:
            log.info("  by disk              : %s",
                     ", ".join(f"{k}={v}" for k, v in sorted(by_branch.items())))

    total = grand_sole + grand_linked
    if total:
        log.info("")
        log.info("overall linked share: %.1f%% (%d of %d)",
                 100 * grand_linked / total, grand_linked, total)
        if grand_linked / total < 0.5:
            log.warning(
                "Most files are a sole copy. Any tool that deletes 'originals' "
                "assuming a library hardlink exists would be deleting the only "
                "copy for these.")
    return 0


def parse(ctx: RunContext, roots: list[Path]) -> int:
    """What the parser makes of real filenames, and what it cannot place."""
    log = ctx.log
    kinds: collections.Counter[str] = collections.Counter()
    unknown: list[str] = []

    for root in roots:
        for path in _iter_files(root):
            if not (is_video(path.name) or is_subtitle(path.name)):
                continue
            if looks_like_junk(path.name):
                kinds["junk (skipped)"] += 1
                continue
            info = parse_release(path.name)
            kinds[info.kind] += 1
            if info.kind is MediaKind.UNKNOWN and len(unknown) < 60:
                unknown.append(str(path))

    log.info("")
    for kind, count in kinds.most_common():
        log.info("  %-22s %d", kind, count)
    if unknown:
        log.info("")
        log.info("unparseable (showing %d):", len(unknown))
        for path in unknown:
            log.info("    %s", path)
    return 0


def topology(ctx: RunContext) -> int:
    """The storage branches behind /mnt/user, and how full each is."""
    log = ctx.log
    log.info("")
    log.info("  %-14s %-12s %s", "branch", "device", "free")
    for branch in branches():
        try:
            stat = os.statvfs(branch.mount)
            free = f"{stat.f_bavail * stat.f_frsize / 2**40:.2f} TiB"
        except OSError:
            free = "?"
        log.info("  %-14s %-12s %s", branch.name, branch.device, free)
    log.info("")
    log.info("A hardlink can only be created between paths on the SAME branch.")
    return 0
