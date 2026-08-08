"""Linking safety, including the cross-device case that broke the old tool."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from unraid_utils import fsops
from unraid_utils.fsops import LinkStatus, safe_link
from unraid_utils.paths import PathKindError, as_real


class TestSafeLink:
    def test_creates_a_real_hardlink(self, tmp_path):
        src = tmp_path / "src.mkv"
        src.write_bytes(b"data")
        dst = tmp_path / "lib" / "Season 1" / "src.mkv"

        result = safe_link(as_real(src), as_real(dst), dry_run=False)

        assert result.status is LinkStatus.CREATED
        assert dst.exists()
        assert os.stat(src).st_ino == os.stat(dst).st_ino
        assert os.stat(src).st_nlink == 2

    def test_dry_run_creates_nothing(self, tmp_path):
        src = tmp_path / "src.mkv"
        src.write_bytes(b"data")
        dst = tmp_path / "lib" / "Season 1" / "src.mkv"

        result = safe_link(as_real(src), as_real(dst), dry_run=True)

        assert result.status is LinkStatus.DRY_RUN
        assert not dst.exists()
        assert not dst.parent.exists(), "dry run must not create directories"

    def test_existing_identical_link_is_recognised(self, tmp_path):
        src = tmp_path / "src.mkv"
        src.write_bytes(b"data")
        dst = tmp_path / "dst.mkv"
        os.link(src, dst)

        result = safe_link(as_real(src), as_real(dst), dry_run=False)

        assert result.status is LinkStatus.ALREADY_LINKED
        assert result.ok
        assert not result.counts_as_created

    def test_different_file_at_destination_is_not_clobbered(self, tmp_path):
        """The old code deleted the destination without a working prompt."""
        src = tmp_path / "src.mkv"
        src.write_bytes(b"new")
        dst = tmp_path / "dst.mkv"
        dst.write_bytes(b"PRECIOUS")

        result = safe_link(as_real(src), as_real(dst), dry_run=False)

        assert result.status is LinkStatus.EXISTS_DIFFERENT
        assert dst.read_bytes() == b"PRECIOUS", "destination was destroyed"

    def test_cross_device_is_refused_not_swallowed(self, tmp_path, monkeypatch):
        """EXDEV must be reported. The old tool swallowed it in a bare except
        while its counter had already been incremented, so it claimed links it
        had never made."""
        src = tmp_path / "src.mkv"
        src.write_bytes(b"data")
        dst_dir = tmp_path / "other"
        dst_dir.mkdir()
        dst = dst_dir / "src.mkv"

        monkeypatch.setattr(fsops, "same_device", lambda a, b: False)
        result = safe_link(as_real(src), as_real(dst), dry_run=False)

        assert result.status is LinkStatus.CROSS_DEVICE
        assert not result.ok
        assert not result.counts_as_created
        assert not dst.exists()

    def test_failure_leaves_no_temporary_files(self, tmp_path, monkeypatch):
        src = tmp_path / "src.mkv"
        src.write_bytes(b"data")
        dst = tmp_path / "out" / "src.mkv"

        def boom(a, b):
            raise OSError("replace failed")

        monkeypatch.setattr(os, "replace", boom)
        result = safe_link(as_real(src), as_real(dst), dry_run=False)

        assert result.status is LinkStatus.FAILED
        leftovers = [p for p in dst.parent.iterdir() if ".uutils-" in p.name]
        assert not leftovers, f"temp files left behind: {leftovers}"

    def test_missing_source_fails_cleanly(self, tmp_path):
        result = safe_link(as_real(tmp_path / "nope.mkv"),
                           as_real(tmp_path / "dst.mkv"), dry_run=False)
        assert result.status is LinkStatus.FAILED


class TestPathKinds:
    def test_shfs_path_is_rejected_for_identity_operations(self):
        """shfs synthesises st_dev and st_ino, so link/stat decisions made on a
        /mnt/user path are meaningless."""
        with pytest.raises(PathKindError):
            as_real(Path("/mnt/user/plex/shows/X/Season 1/a.mkv"))

    def test_branch_paths_are_accepted(self):
        assert as_real(Path("/mnt/disk3/plex/shows/X"))
        assert as_real(Path("/mnt/primary/plex/shows/X"))
