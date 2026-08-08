# unraid-utils

Media management tools for Unraid. Dry-run by default; every change is logged.

```sh
uv sync
uv run unraid-utils audit links          # read-only: what is a sole copy?
uv run unraid-utils hardlink SRC DEST    # dry run
uv run unraid-utils --execute hardlink SRC DEST
```

## Why v2 exists

The v1 scripts had twelve bugs that could destroy data, and one root cause worth
understanding because it is specific to Unraid.

`/mnt/user` is not a filesystem. It is a FUSE merge (shfs) over `/mnt/disk1..N`
plus any cache pools — on a typical box, seven separate filesystems behind one
namespace. `os.link()` cannot cross them: it fails with `EXDEV`.

v1 let Unraid's allocator choose where the destination went, which meant it
usually landed on a *different* disk from the source. Each of those links failed
— but the failure was swallowed by a bare `except`, and the success counter had
already been incremented before the attempt. The tool reported links it had
never created.

That would be merely annoying, except `tdarr_xref` then deleted "originals" on
the assumption those links existed. Measured on a real library:

| | sole copy (`nlink=1`) | hardlinked |
|---|---|---|
| `plex/shows` video | 9,931 | 447 (4.3%) |

For ~96% of files, "delete the original, the library has a link" meant deleting
the only copy.

## Safety model

- **Dry run is the default.** Nothing changes without `--execute`.
- **Placement is disk-aware.** `hardlink` resolves the source to its real branch
  and creates the destination there, so the link can actually succeed. A
  genuine cross-device case is reported, never silently swallowed.
- **Links are verified.** After creating one, the inode is compared — on real
  branch paths, because shfs synthesises `st_ino` and a comparison through
  `/mnt/user` is meaningless. Only verified links are counted.
- **Linking is atomic.** Link to a temporary name, then `os.replace`. v1 did
  remove-then-link, so a failure left the destination deleted and nothing in
  its place.
- **Everything is recorded** to `/mnt/user/appdata/unraid-utils/` — a JSONL
  manifest plus a timestamped log. Outside the repo, so `git pull` cannot
  disturb it, and off the RAM-backed root, which is wiped on reboot.
- **Paths are allowlisted.** Operations outside `/mnt/user` and the branch
  mounts are refused, as is `/`.

## Commands

### `audit` — read-only, changes nothing

```sh
unraid-utils audit links [ROOTS...]   # hardlink census; what is a sole copy
unraid-utils audit parse [ROOTS...]   # filenames the parser cannot place
unraid-utils audit topology           # the branches behind /mnt/user
```

Start here. It validates path resolution and parsing against the real library
at zero risk, and tells you how much of it is actually linked.

### `hardlink` — link a release into the show library

```sh
unraid-utils hardlink "/mnt/user/plex/downloads/Show.S01..." "/mnt/user/plex/shows/Show"
```

Parses the **basename** only (v1 parsed the whole path, so a directory
containing something like `1920x1080` supplied the season and files were filed
under `Season 20`). Reuses an existing season directory when the show has one —
including `Specials/` and suffixed names like `Season 1 - Phantom Blood` —
rather than creating a second folder that splits the show in Plex.

`--no-subtitles` links video only.

## Not yet ported

`dupes` (release-aware duplicate removal) and `tdarr-xref` are being rebuilt on
the same safety core and are not in this release. The v1 versions are preserved
under [`legacy/`](legacy/) with their known faults documented — **they should
not be run.** `cleaner` has been dropped entirely.

## Requirements

Python 3.11+ and [`uv`](https://docs.astral.sh/uv/). On Unraid both come from
the `dwpython` plugin and survive reboots; anything they *write* does not, so
set a persistent cache:

```sh
export UV_CACHE_DIR=/mnt/user/projects/.uv-cache
export UV_LINK_MODE=copy
```

The sole runtime dependency is
[`parse-torrent-title`](https://github.com/platelminto/parse-torrent-title)
(MIT, zero dependencies). It replaces `parse-torrent-name`, abandoned since
2016, whose year pattern stopped at 2019 — which is why a 2022 release parsed
with its year glued into the title. Both packages install a top-level `PTN`
module and shadow each other, so the tool refuses to start if the old one is
also present.

## Development

```sh
uv sync --extra dev
uv run pytest
```

Tests include a named regression for each of the twelve v1 bugs, asserting the
old behaviour is now impossible, and a characterization snapshot of the parser
against ~230 real release names — so an upstream parser change fails loudly
instead of silently regrouping episodes.
