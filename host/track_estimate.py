"""TrackEstimate / BBox — matches host/contracts.md."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

TrackStatus = Literal["SEARCHING", "TRACKING", "LOST"]


@dataclass
class BBox:
    """Axis-aligned box in image pixel coordinates (origin top-left)."""

    x: float
    y: float
    w: float
    h: float

    def __post_init__(self) -> None:
        if self.w <= 0 or self.h <= 0:
            raise ValueError("BBox w/h must be > 0")

    @property
    def cx(self) -> float:
        return self.x + self.w * 0.5

    @property
    def cy(self) -> float:
        return self.y + self.h * 0.5


@dataclass
class TrackEstimate:
    """Detect+Track output for the active target (contracts.md)."""

    timestamp_ms: float
    status: TrackStatus
    track_id: Optional[int]
    bbox: Optional[BBox]
    confidence: float
    # Pixel target point (fingertip or midpoint of two tips) — for HUD / early guidance
    target_xy: Optional[tuple[float, float]] = None
    bearing_rad: Optional[tuple[float, float]] = None  # (yaw, pitch)
    range_proxy: Optional[float] = None
    # Optional: individual fingertip pixels (e.g. two-finger lock)
    tips_xy: Optional[tuple[tuple[float, float], ...]] = None
