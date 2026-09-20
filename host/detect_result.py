"""Class-aware detections — drone vs distractors (M3.4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from track_estimate import BBox


@dataclass
class Detection:
    """One detector hypothesis this frame (before track lock)."""

    label: str
    confidence: float
    bbox: BBox
    accepted: bool  # True if label is in the target-accept set


@dataclass
class DetectTelemetry:
    """Per-frame numbers for HUD / logs (operator-useful, not decoration)."""

    infer_ms: float = 0.0
    status: str = "SEARCHING"
    class_label: Optional[str] = None
    confidence: float = 0.0
    offset_px: Optional[tuple[float, float]] = None
    offset_norm: Optional[tuple[float, float]] = None
    range_proxy: Optional[float] = None
    box_wh: Optional[tuple[float, float]] = None
    lock_age_s: float = 0.0
    track_id: Optional[int] = None
    n_accepted: int = 0
    n_rejected: int = 0
    top_reject: Optional[str] = None  # highest-conf rejected label
    top_reject_conf: float = 0.0
    iou_with_prev: float = 0.0  # association quality when locked


# Default open-vocab prompts for YOLO-World.
# Accept set = what we will TRACK; distractors are drawn but never locked.
DEFAULT_TARGET_LABELS: tuple[str, ...] = (
    "drone",
    "quadcopter",
    "UAV",
    "multirotor",
    "aircraft",  # YOLO-World often maps small UAVs here; refine later
)
DEFAULT_DISTRACTOR_LABELS: tuple[str, ...] = (
    "person",
    "hand",
    "bottle",
    "cup",
    "phone",
    "book",
    "chair",
    "car",
    "bird",
)
