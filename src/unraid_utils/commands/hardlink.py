"""Hardlink a downloaded release into the show library.

The rewrite's central fix. Given a source file, it chooses a destination on the
*same disk* as that source, because `os.link` cannot cross the filesystems that
`/mnt/user` merges. The old version let shfs's allocator choose, which on this
server put the destination on a different disk roughly five times out of six —
each of those failing with EXDEV, being swallowed, and still counted as success.

Placement rules, in order:
  * parse the basename only (never the path — a directory containing something
    like `1920x1080` used to supply the season);
  * reuse an existing season directory if the show already has one, including
    `Specials/` and suffixed names such as `Season 1 - Subtitle`;
  * only then create `Season N` on the source's branch.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ..context import RunContext
from ..fsops import LinkStatus, safe_link
from ..media import (
    MediaInfo,
    MediaKind,
    is_subtitle,
    is_video,
    looks_like_junk,
    parse_release,
)
from ..naming import season_dir_for
from ..paths import as_real, is_user_path
from ..unraid import branch_of, relative_to_user, resolve


@dataclass(slots=True)
class Plan:
    source: Path
    dest: Path
    season: int
    info: MediaInfo
    note: str = ""


def _season_for(info: MediaInfo) -> int | None:
    """Which season a file belongs to, or None if we should not guess.

    Note `is not None` throughout: season 0 (specials) is falsy, and truthiness
    checks are exactly what made the old code mishandle them.
    """
    if info.kind is MediaKind.SPECIAL:
        return 0
    if info.kind is MediaKind.EPISODE and len(info.seasons) == 1:
        return info.seasons[0]
    if info.kind is MediaKind.SEASON_PACK and len(info.seasons) == 1:
        return info.seasons[0]
    return None


def build_plan(ctx: RunContext, source_root: Path, show_dir: Path,
               include_subtitles: bool = True) -> tuple[list[Plan], list[tuple[Path, str]]]:
    """Work out every link to make. Creates nothing."""
    plans: list[Plan] = []
    skipped: list[tuple[Path, str]] = []

    for dirpath, dirnames, filenames in os.walk(source_root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in sorted(filenames):
            path = Path(dirpath) / name
            wanted = is_video(name) or (include_subtitles and is_subtitle(name))
            if not wanted:
                continue
            if looks_like_junk(name):
                skipped.append((path, "sample/extra"))
                continue

            info = parse_release(name)
            season = _season_for(info)
            from_parent = False
            if season is None:
                # Some releases carry no season in the filename at all — a
                # whole season of `Ja, Chef! - 1. del.mp4` inside a folder
                # named `...S04...`. Fall back to the immediate parent, and
                # only ever to fill a gap: this can never override a season the
                # filename stated, which is what made v1 file things under
                # `Season 20` after matching `1920x1080` somewhere in the path.
                season = _season_for(parse_release(Path(dirpath).name))
                from_parent = season is not None
            if season is None:
                skipped.append((path, f"no single season ({info.kind})"))
                continue

            # Resolve the source to a real disk before deciding anything.
            reals = resolve(path)
            if not reals:
                skipped.append((path, "cannot resolve to a branch"))
                continue
            real_source = reals[0]
            branch = branch_of(real_source)
            if branch is None:
                skipped.append((path, "not on a known branch"))
                continue

            # Put the show directory on the source's branch so the link can work.
            rel = relative_to_user(show_dir) if is_user_path(show_dir) else None
            if rel is not None:
                show_on_branch = as_real(branch.mount / rel)
            else:
                show_on_branch = as_real(show_dir)

            season_dir, existed = season_dir_for(show_on_branch, season)
            dest = Path(season_dir) / name
            note = "existing season dir" if existed else "new season dir"
            if from_parent:
                note += ", season from parent folder"
            plans.append(Plan(Path(real_source), dest, season, info,
                              f"{note} on {branch.name}"))

    return plans, skipped


def run(ctx: RunContext, source_root: Path, show_dir: Path,
        include_subtitles: bool = True) -> int:
    log = ctx.log
    ctx.check_allowed(source_root)
    ctx.check_allowed(show_dir)

    plans, skipped = build_plan(ctx, source_root, show_dir, include_subtitles)
    log.info("%s: %d candidate(s), %d skipped", ctx.mode, len(plans), len(skipped))

    for path, why in skipped:
        log.debug("  skip %s (%s)", path.name, why)

    counts: dict[str, int] = {}
    failures = 0

    for plan in plans:
        ctx.manifest.intent("link", plan.source, plan.dest)
        result = safe_link(as_real(plan.source), as_real(plan.dest),
                           dry_run=ctx.dry_run)
        counts[result.status] = counts.get(result.status, 0) + 1
        ctx.manifest.outcome("link", result.status, plan.source, plan.dest,
                             detail=result.detail)

        if result.status is LinkStatus.CREATED:
            log.info("  linked   %s -> %s", plan.source.name, plan.dest.parent.name)
        elif result.status is LinkStatus.DRY_RUN:
            log.info("  would link  %s\n              -> %s  (%s)",
                     plan.source, plan.dest, plan.note)
        elif result.status is LinkStatus.ALREADY_LINKED:
            log.debug("  already  %s", plan.dest.name)
        elif result.status is LinkStatus.CROSS_DEVICE:
            failures += 1
            log.error("  EXDEV    %s: %s", plan.source.name, result.detail)
        elif result.status is LinkStatus.EXISTS_DIFFERENT:
            failures += 1
            log.warning("  conflict %s already exists and differs", plan.dest)
        else:
            failures += 1
            log.error("  failed   %s: %s", plan.source.name, result.detail)

    log.info("")
    for status, count in sorted(counts.items()):
        log.info("  %-18s %d", status, count)

    if ctx.dry_run:
        log.info("")
        log.info("Dry run — nothing was changed. Re-run with --execute to apply.")
    return 1 if failures else 0
