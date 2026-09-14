"""CameraFrame — matches host/contracts.md."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

PixelFormat = Literal["rgb", "bgr", "gray", "encoded"]


@dataclass
class CameraFrame:
    """One video frame entering Capture (contracts.md)."""

    frame_id: int
    timestamp_ms: float
    width: int
    height: int
    format: PixelFormat
    data: Any  # numpy array (BGR/RGB/gray) or encoded bytes

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("CameraFrame width/height must be > 0")
        if self.frame_id < 0:
            raise ValueError("frame_id must be >= 0")
