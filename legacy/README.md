# Legacy v1 scripts — do not run

Kept for reference while their replacements are built. Each has faults that can
destroy data; they are here so the rewrite can be checked against them, not so
they can be used.

## `hardlinker/main.py` — replaced by `unraid-utils hardlink`

- Incremented its success counter *before* attempting each link, then swallowed
  the resulting `EXDEV` in a bare `except Exception`. On a multi-disk array most
  links fail, so it routinely reported links it had never created.
- `os.remove` followed by `os.link` on conflict: not atomic, so a failure left
  the destination deleted and nothing in its place.
- Parsed the full path rather than the basename, so a directory component
  containing something like `1920x1080` supplied the season.
- `info["season"]` outside the `try`, so one unparseable file aborted the run.

## `dupe_check/main.py` — replacement pending

- `int(x[1:].strip("0"))` mapped season 10 to 1 and raised `ValueError` on `S00`.
- A season pack could be judged a duplicate of a single episode of that season,
  then removed with `shutil.rmtree` — losing the whole season.
- Files whose episode number did not parse (absolute numbering, dailies,
  three-digit episodes) collapsed into "duplicates" of each other.
- The `force` confirmation's return value was discarded: answering "n" still
  proceeded.
- Selected by mtime alone, so a re-grabbed 720p copy deleted a 2160p REMUX.
- Mutated the list it was iterating, silently skipping entries.

## `tdarr_xref/main.py` — replacement pending

- Any entry that was not a directory and not `.mkv`/`.mp4` was staged for
  deletion with no title or episode check at all.
- The recursion passed `is_parent=True` unconditionally, disabling the title
  check for every level below the top.
- Guards were written as "delete unless a mismatch is proven", so a missing or
  zero season/episode permitted deletion rather than blocking it.
- One branch returned a string where every other returned a list; `list += str`
  then expanded it into single-character paths, one of which could be `/`,
  reaching `shutil.rmtree`.
- Deleted originals on the strength of a CSV field alone, never checking that
  the transcoded output existed.
- `split("/")[3] == "movies"` misclassified every row for a `/mnt/user/plex/...`
  layout.

## `cleaner/` — removed

Renamed everything in the current working directory with no argument and no
confirmation, used `os.rename` (which silently destroys an existing
destination), and deleted dashes rather than replacing them, so `Spider-Man`
became `SpiderMan`. Its README described behaviour it did not implement.
