"""Append-only JSONL record of everything that changed the filesystem.

The old scripts kept no record at all, so after a bad run there was no way to
know what had been lost. Every mutating operation writes here, and `undo`
reads it back.

Records are written in two phases — intent before the operation, outcome after.
The Unraid mover runs hourly and can relocate a file between those two points,
so `undo` reconciles against what it actually finds on disk rather than
trusting these records to still describe reality.
"""

from __future__ import annotations

import json
import os
import socket
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_STATE_DIR = Path("/mnt/user/appdata/unraid-utils")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(slots=True)
class Record:
    run_id: str
    phase: str          # "intent" | "outcome"
    action: str         # "link" | "delete" | "restore"
    status: str
    source: str = ""
    dest: str = ""
    size: int = 0
    detail: str = ""
    timestamp: str = field(default_factory=_now)
    host: str = field(default_factory=socket.gethostname)


class ManifestWriter:
    """Appends records, one JSON object per line, flushed immediately.

    Flushing per record matters: if the process dies mid-run the manifest must
    still describe everything already done.
    """

    def __init__(self, run_id: str, state_dir: Path = DEFAULT_STATE_DIR,
                 enabled: bool = True):
        self.run_id = run_id
        self.enabled = enabled
        self.path = state_dir / "manifest" / f"{datetime.now().strftime('%Y-%m')}.jsonl"  # noqa: DTZ005 - local month for the filename; record timestamps are UTC
        if enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record: Record) -> None:
        if not self.enabled:
            return
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def intent(self, action: str, source: Path | str = "", dest: Path | str = "",
               size: int = 0, detail: str = "") -> None:
        self.write(Record(self.run_id, "intent", action, "pending",
                          str(source), str(dest), size, detail))

    def outcome(self, action: str, status: str, source: Path | str = "",
                dest: Path | str = "", size: int = 0, detail: str = "") -> None:
        self.write(Record(self.run_id, "outcome", action, status,
                          str(source), str(dest), size, detail))


def iter_records(state_dir: Path = DEFAULT_STATE_DIR, run_id: str | None = None):
    """Yield records, newest file last. Corrupt lines are skipped, not fatal."""
    manifest_dir = state_dir / "manifest"
    if not manifest_dir.is_dir():
        return
    for path in sorted(manifest_dir.glob("*.jsonl")):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if run_id is None or rec.get("run_id") == run_id:
                    yield rec
