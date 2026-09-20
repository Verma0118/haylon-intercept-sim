"""Mock TX bridge — write ChannelFrames to a JSONL file (M2.2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, TextIO

from guidance_cmd import ChannelFrame


class MockTx:
    """
    Stand-in for the ELRS TX packet pipe.

    Each ChannelFrame is one JSON line. A later live bridge will swap this
    for CRSF/serial without changing StickMap or Guide.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fp: TextIO = self.path.open("w", encoding="utf-8")
        self.frames = 0

    def send(self, frame: ChannelFrame) -> None:
        row = {
            "timestamp_ms": frame.timestamp_ms,
            "channels_us": [round(c, 1) for c in frame.channels[:8]],
        }
        self._fp.write(json.dumps(row) + "\n")
        self._fp.flush()
        self.frames += 1

    def close(self) -> None:
        self._fp.close()


def read_mock_tx(path: str | Path) -> list[dict]:
    """Round-trip helper for tests / exit checks."""
    rows = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows
