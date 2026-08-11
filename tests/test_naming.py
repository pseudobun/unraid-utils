"""Season-directory resolution against the library's real folder names."""

from __future__ import annotations

from pathlib import Path

from unraid_utils.naming import (
    default_season_dirname,
    find_season_dir,
    season_dir_for,
    season_from_dirname,
)
from unraid_utils.paths import RealPath


class TestSeasonFromDirname:
    def test_plain_and_padded(self):
        assert season_from_dirname("Season 1") == 1
        assert season_from_dirname("Season 01") == 1
        assert season_from_dirname("season 12") == 12

    def test_suffixed_names_still_resolve(self):
        """This library really contains names like these; creating a bare
        `Season 1` beside one would split the show in Plex."""
        assert season_from_dirname("Season 1 - Phantom Blood & Battle Tendency") == 1
        assert season_from_dirname("Season 3 - Diamond is Unbreakable") == 3

    def test_specials(self):
        assert season_from_dirname("Specials") == 0
        assert season_from_dirname("specials") == 0

    def test_non_season_directories(self):
        for name in ("Extras", "Featurettes", "photos", "videos", "Org", "Web"):
            assert season_from_dirname(name) is None

    def test_every_real_season_dirname_resolves(self, corpus):
        unresolved = [d for d in corpus["SEASONDIRS"]
                      if season_from_dirname(d) is None]
        assert not unresolved, f"unrecognised season dirs: {unresolved}"


class TestDefaultNaming:
    def test_matches_library_convention(self):
        # Unpadded, matching the 37 existing `Season N` directories.
        assert default_season_dirname(1) == "Season 1"
        assert default_season_dirname(12) == "Season 12"

    def test_season_zero_becomes_specials(self):
        assert default_season_dirname(0) == "Specials"


class TestSeasonDirFor:
    def test_reuses_existing_directory(self, tmp_path):
        show = tmp_path / "JoJo"
        existing = show / "Season 1 - Phantom Blood & Battle Tendency"
        existing.mkdir(parents=True)

        path, existed = season_dir_for(RealPath(show), 1)

        assert existed is True
        assert path == RealPath(existing), "must not invent a second Season 1"

    def test_creates_conventional_name_when_absent(self, tmp_path):
        show = tmp_path / "Show"
        show.mkdir()

        path, existed = season_dir_for(RealPath(show), 2)

        assert existed is False
        assert Path(path).name == "Season 2"
        assert not Path(path).exists(), "resolution must not create anything"

    def test_specials_reused(self, tmp_path):
        show = tmp_path / "Show"
        (show / "Specials").mkdir(parents=True)

        path, existed = season_dir_for(RealPath(show), 0)

        assert existed is True
        assert Path(path).name == "Specials"

    def test_missing_show_dir_is_not_an_error(self, tmp_path):
        assert find_season_dir(RealPath(tmp_path / "absent"), 1) is None


class TestCrossBranchPlacement:
    """A season directory must land on the caller's branch, whatever branch an
    existing one happens to be on.

    Found by a dry run: `find_season_dir` searched every branch and returned the
    existing `Season 12` on disk6, but the source file was on disk3 — so
    "reuse the existing directory" defeated "place it on the source's disk" and
    produced a cross-device link that cannot succeed. Borrowing the *name* while
    rooting it on the source's branch satisfies both; shfs merges directories
    that share a name.
    """

    def test_borrows_the_name_but_stays_on_this_branch(self, tmp_path, monkeypatch):
        from unraid_utils import naming

        disk_a, disk_b = tmp_path / "disk1", tmp_path / "disk2"
        show_rel = "plex/shows/JoJo"
        (disk_a / show_rel / "Season 1 - Phantom Blood").mkdir(parents=True)
        (disk_b / show_rel).mkdir(parents=True)

        class B:
            def __init__(self, mount):
                self.mount = mount
            @property
            def name(self):
                return self.mount.name

        monkeypatch.setattr(naming, "branches", lambda: (B(disk_a), B(disk_b)))
        monkeypatch.setattr(naming, "branch_of",
                            lambda p: B(disk_b) if disk_b in Path(p).parents
                            or p == disk_b else B(disk_a))
        monkeypatch.setattr(
            naming, "sibling_on_branch",
            lambda real, br: RealPath(br.mount / Path(real).relative_to(
                disk_b if disk_b in Path(real).parents else disk_a)))

        path, existed = season_dir_for(RealPath(disk_b / show_rel), 1)

        assert Path(path).name == "Season 1 - Phantom Blood", "name not reused"
        assert disk_b in Path(path).parents, "must stay on the given branch"
        assert existed is False, "does not yet exist on this branch"
