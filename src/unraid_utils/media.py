"""Release-name parsing, with the ambiguity made explicit.

Wraps `parse-torrent-title` (imported as `PTN`). The old code used
`parse-torrent-name`, dead since 2016, whose year regex stopped at 2019 — which
is why `Granite Harbour 2022 S02E01` parsed with the year glued into the title.

Three rules this module exists to enforce:

1. **Parse the basename, never the full path.** The old code passed the whole
   path, so any directory component containing something like `1920x1080`
   supplied the season and files were filed under `Season 20`.
2. **Season 0 and episode 0 are real.** Specials parse to `season=0`, which is
   falsy — the old code's `if season:` guards silently skipped them and treated
   them as unmatched, which on a delete path meant "proceed".
3. **Unparseable is a value, not an exception.** The old code did `info["season"]`
   and a `KeyError` aborted the whole run mid-way. Callers get `MediaKind.UNKNOWN`
   and decide for themselves.

Verified against `parse-torrent-title` 2.8.2 on the real library corpus:
`season` is `int | list[int] | None` (multi-season packs such as `S01-S03`
return `[1, 2, 3]`), `episode` is `int | list[int] | None` (multi-episode files
return `[1, 2]`), and `excess` is sometimes `str` and sometimes `list`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import PTN

VIDEO_EXTENSIONS = frozenset({
    ".mkv", ".mp4", ".m4v", ".avi", ".ts", ".mov", ".wmv", ".webm", ".mpg",
    ".mpeg", ".m2ts", ".iso",
})
SUBTITLE_EXTENSIONS = frozenset({".srt", ".ass", ".ssa", ".sub", ".idx", ".vtt"})

# Downloads also hold music releases (`Kendrick Lamar - GNX (2024) [FLAC]`),
# which parse to a plausible title + year and would otherwise match a movie row.
AUDIO_EXTENSIONS = frozenset({".flac", ".mp3", ".m4a", ".wav", ".ape", ".ogg",
                              ".opus", ".aac", ".dsf"})

# Junk that should never be linked into a library as if it were an episode.
JUNK_STEMS = ("sample", "trailer", "rarbg", "proof", "screens")


class MediaKind(StrEnum):
    EPISODE = "episode"              # season + episode(s)
    SEASON_PACK = "season_pack"      # one season, no episode
    SEASON_RANGE = "season_range"    # S01-S03: several seasons, no episode
    SPECIAL = "special"              # season 0
    MOVIE = "movie"                  # title (+year), no season/episode
    UNKNOWN = "unknown"              # nothing trustworthy came back


@dataclass(frozen=True, slots=True)
class MediaInfo:
    kind: MediaKind
    title: str
    seasons: tuple[int, ...] = ()
    episodes: tuple[int, ...] = ()
    year: int | None = None
    resolution: str | None = None
    quality: str | None = None
    codec: str | None = None
    remux: bool = False
    hdr: bool = False
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def season(self) -> int | None:
        """The single season, when there is exactly one."""
        return self.seasons[0] if len(self.seasons) == 1 else None

    @property
    def episode(self) -> int | None:
        return self.episodes[0] if len(self.episodes) == 1 else None

    @property
    def is_episodic(self) -> bool:
        return self.kind in (MediaKind.EPISODE, MediaKind.SPECIAL)

    def episode_key(self) -> tuple[str, int, int] | None:
        """Identity for 'the same episode', or None when not a single episode.

        Deliberately returns None for season packs and ranges: the old code
        treated a season pack as a duplicate of one episode of that season and
        deleted the whole pack.
        """
        if not self.is_episodic or len(self.seasons) != 1 or len(self.episodes) != 1:
            return None
        return (normalise_title(self.title), self.seasons[0], self.episodes[0])


def normalise_title(title: str) -> str:
    """Case- and punctuation-insensitive title key.

    The two old scripts disagreed — one compared titles exactly, the other
    lowercased — so they found different duplicates on the same input.
    """
    return "".join(c for c in title.lower() if c.isalnum() or c.isspace()).strip()


def _as_tuple(value) -> tuple[int, ...]:
    """Normalise PTN's int | list[int] | None into a tuple.

    Both `season` and `episode` can be lists: `S01-S03` -> [1, 2, 3] and
    `S01E01E02` -> [1, 2].
    """
    if value is None:
        return ()
    if isinstance(value, int):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(int(v) for v in value if isinstance(v, int))
    return ()


def is_video(name: str) -> bool:
    return Path(name).suffix.lower() in VIDEO_EXTENSIONS


def is_subtitle(name: str) -> bool:
    return Path(name).suffix.lower() in SUBTITLE_EXTENSIONS


def is_audio(name: str) -> bool:
    return Path(name).suffix.lower() in AUDIO_EXTENSIONS


def looks_like_junk(name: str) -> bool:
    stem = Path(name).stem.lower()
    return any(j in stem for j in JUNK_STEMS)


def parse_release(name: str | Path) -> MediaInfo:
    """Parse a release name. Always uses the basename."""
    basename = os.path.basename(str(name))
    try:
        raw = PTN.parse(basename)
    except Exception:  # noqa: BLE001 - a third-party parser fault must never abort a whole run
        return MediaInfo(MediaKind.UNKNOWN, title=basename, raw={})

    title = (raw.get("title") or "").strip()
    seasons = _as_tuple(raw.get("season"))
    episodes = _as_tuple(raw.get("episode"))

    if not title:
        kind = MediaKind.UNKNOWN
    elif seasons == (0,):
        kind = MediaKind.SPECIAL
    elif len(seasons) > 1:
        kind = MediaKind.SEASON_RANGE
    elif seasons and episodes:
        kind = MediaKind.EPISODE
    elif seasons:
        kind = MediaKind.SEASON_PACK
    elif episodes:
        # Episode without a season: absolute numbering or a daily. Not safe to
        # place or to match on, so it stays explicitly unknown.
        kind = MediaKind.UNKNOWN
    else:
        kind = MediaKind.MOVIE

    return MediaInfo(
        kind=kind,
        title=title,
        seasons=seasons,
        episodes=episodes,
        year=raw.get("year") if isinstance(raw.get("year"), int) else None,
        resolution=raw.get("resolution"),
        quality=raw.get("quality"),
        codec=raw.get("codec"),
        remux=bool(raw.get("remux")),
        hdr=bool(raw.get("hdr")),
        raw=raw,
    )


def assert_correct_parser() -> None:
    """Fail loudly if the dead parser is also installed.

    `parse-torrent-name` and `parse-torrent-title` both install a top-level
    `PTN` package and silently shadow each other; which one wins depends on
    install order, and the dead one mis-parses most of this library.
    """
    from importlib.metadata import distributions

    names = {d.metadata["Name"].lower() for d in distributions()
             if d.metadata and d.metadata.get("Name")}
    if "parse-torrent-name" in names:
        raise RuntimeError(
            "Both 'parse-torrent-name' and 'parse-torrent-title' provide a "
            "top-level PTN package and shadow each other.\n"
            "Uninstall the dead one:  uv pip uninstall parse-torrent-name"
        )
    if "parse-torrent-title" not in names:
        raise RuntimeError("parse-torrent-title is not installed")
