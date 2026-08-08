"""Test fixtures.

The important one is `fake_array`: a tmp_path tree that mimics Unraid's several
storage branches behind one merged namespace. It lets the EXDEV path be tested
without a second physical disk, by substituting the branch-discovery function.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def corpus() -> dict[str, list[str]]:
    """Real show, season-directory and download names taken from the server."""
    sections: dict[str, list[str]] = {}
    current = None
    for line in (FIXTURES / "corpus.txt").read_text().splitlines():
        if line.startswith("###"):
            current = line.strip("#")
            sections[current] = []
        elif line.strip() and current:
            sections[current].append(line)
    return sections


@pytest.fixture
def ptt_snapshot() -> dict:
    """Characterization snapshot of parse-torrent-title on the real corpus.

    If an upstream release changes how anything here parses, the test fails
    rather than silently regrouping episodes.
    """
    return json.loads((FIXTURES / "ptt_snapshot.json").read_text())


class FakeBranch:
    def __init__(self, mount: Path):
        self.mount = mount
        self.device = os.stat(mount).st_dev

    @property
    def name(self) -> str:
        return self.mount.name


@pytest.fixture
def fake_array(tmp_path, monkeypatch):
    """Three storage branches under one merged root.

    Real directories on one filesystem, so `st_dev` is genuinely equal; tests
    that need a *cross-device* failure monkeypatch `same_device` instead, since
    tmpfs cannot give us two devices.
    """
    from unraid_utils import paths, unraid

    user = tmp_path / "user"
    branch_dirs = []
    for name in ("disk1", "disk2", "primary"):
        d = tmp_path / name
        d.mkdir()
        branch_dirs.append(d)
    user.mkdir()

    monkeypatch.setattr(paths, "USER_MOUNT", user)
    monkeypatch.setattr(unraid, "USER_MOUNT", user)
    fake_branches = tuple(FakeBranch(d) for d in branch_dirs)
    monkeypatch.setattr(unraid, "branches", lambda: fake_branches)

    # is_user_path/as_real are bound to the module-level constant, so patch the
    # predicate too rather than relying on the constant alone.
    monkeypatch.setattr(paths, "is_user_path",
                        lambda p: p == user or user in Path(p).parents)
    monkeypatch.setattr(unraid, "is_user_path", paths.is_user_path)

    class Array:
        def __init__(self):
            self.root = tmp_path
            self.user = user
            self.disk1, self.disk2, self.primary = branch_dirs

        def make_file(self, branch: Path, rel: str, size: int = 64) -> Path:
            path = branch / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x" * size)
            return path

    return Array()
