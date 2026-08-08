"""Parser behaviour, including the cases the old implementation got wrong."""

from __future__ import annotations

import pytest

from unraid_utils.media import (
    MediaKind,
    is_audio,
    is_video,
    looks_like_junk,
    normalise_title,
    parse_release,
)


class TestRegressions:
    """Each of these encodes a specific bug that used to destroy data."""

    def test_season_10_is_not_season_1(self):
        """Old dupe_check did int(x[1:].strip("0")), mapping S10 -> 1.

        strip() removes from both ends, so seasons 10/20/30 collapsed onto
        1/2/3 and a S10 pack could be judged a duplicate of S01.
        """
        for season in (10, 20, 30):
            info = parse_release(f"Show.Name.S{season}E01.1080p.WEB-DL.mkv")
            assert info.seasons == (season,), f"S{season} mis-parsed"

    def test_specials_parse_as_season_zero_not_crash(self):
        """S00 used to reach int("") and raise ValueError, killing the run."""
        info = parse_release("Show.Name.S00E01.Christmas.Special.1080p.mkv")
        assert info.kind is MediaKind.SPECIAL
        assert info.seasons == (0,)
        # Season 0 is falsy: truthiness checks are what made the old code
        # treat specials as "unmatched", which on a delete path meant proceed.
        assert info.seasons[0] is not None
        assert not info.seasons[0]

    def test_multi_episode_returns_all_episodes(self):
        for name in ("Show.Name.S01E01E02.1080p.mkv",
                     "Show.Name.S01E01-E02.1080p.mkv"):
            info = parse_release(name)
            assert info.episodes == (1, 2), name
            assert info.episode is None, "ambiguous single-episode accessor"

    def test_multi_season_pack_returns_all_seasons(self):
        """S01-S03 yields a list; the old code assumed an int throughout."""
        info = parse_release("Granite Harbour 2022 S01-S03 1080p WEB-DL x265 BONE")
        assert info.kind is MediaKind.SEASON_RANGE
        assert info.seasons == (1, 2, 3)
        assert info.episode_key() is None, "a range must never match one episode"

    def test_season_pack_is_never_an_episode_match(self):
        """Old code judged a season pack a duplicate of one episode of that
        season, then rmtree'd the whole pack."""
        pack = parse_release("Besa.S01.1080p.WEB-DL.x264-GRP")
        episode = parse_release("Besa.S01E03.1080p.WEB-DL.x264-GRP.mkv")
        assert pack.kind is MediaKind.SEASON_PACK
        assert pack.episode_key() is None
        assert episode.episode_key() is not None
        assert pack.episode_key() != episode.episode_key()

    def test_year_is_not_glued_into_title(self):
        """The dead parser's year regex stopped at 2019, so 2020s releases had
        their year absorbed into the title."""
        info = parse_release("Granite Harbour 2022 S02E01 1080p WEB-DL x265 BONE.mkv")
        assert info.title == "Granite Harbour"
        assert info.year == 2022

    def test_parses_basename_not_path(self):
        """Old hardlinker passed the full path, so a directory component
        containing 1920x1080 supplied the season and files went to Season 20."""
        info = parse_release("/mnt/user/plex/1920x1080/Show.Name.S03E04.mkv")
        assert info.seasons == (3,)

    def test_unparseable_is_a_value_not_an_exception(self):
        """Old code did info["season"] and a KeyError aborted the whole run."""
        info = parse_release("0FB100CF-6505-420C-AF15-937669D50F8C.JPG")
        assert info.kind in (MediaKind.UNKNOWN, MediaKind.MOVIE)
        assert info.seasons == () and info.episodes == ()


class TestClassification:
    def test_audio_release_is_not_treated_as_video(self):
        """downloads/ holds music that parses as a movie with a year."""
        name = "Kendrick Lamar - GNX (2024) [24Bit-48kHz] FLAC.flac"
        assert is_audio(name)
        assert not is_video(name)

    def test_junk_detection(self):
        assert looks_like_junk("sample.mkv")
        assert looks_like_junk("Show.S01E01.sample.mkv")
        assert not looks_like_junk("Show.S01E01.mkv")

    def test_title_normalisation_is_stable(self):
        """The two old scripts disagreed — one exact-matched, one lowercased —
        so they found different duplicates on identical input."""
        assert normalise_title("The Grand Tour") == normalise_title("the grand tour")
        assert normalise_title("Marvel's Daredevil") == normalise_title("Marvels Daredevil")


class TestAgainstRealCorpus:
    def test_snapshot_still_holds(self, ptt_snapshot):
        """Characterization: a bad upstream release fails here loudly."""
        import PTN
        drift = []
        for name, expected in ptt_snapshot["releases"].items():
            actual = PTN.parse(name)
            for key, want in expected.items():
                got = actual.get(key)
                if isinstance(want, list):
                    got = list(got) if isinstance(got, list) else got
                if got != want:
                    drift.append(f"{name}: {key} {want!r} -> {got!r}")
        assert not drift, "parser drift:\n" + "\n".join(drift[:20])

    def test_every_download_parses_without_raising(self, corpus):
        for name in corpus["DOWNLOADS"]:
            parse_release(name)  # must never raise

    @pytest.mark.parametrize("kind_field", ["seasons", "episodes"])
    def test_season_and_episode_are_always_tuples(self, corpus, kind_field):
        """Both fields can come back as int, list or None from the parser."""
        for name in corpus["DOWNLOADS"]:
            value = getattr(parse_release(name), kind_field)
            assert isinstance(value, tuple)
            assert all(isinstance(v, int) for v in value)
