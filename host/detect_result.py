"""Class-aware detections — drone vs distractors (M3.4)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from track_estimate import BBox


@dataclass
class Detection:
    """One detector hypothesis this frame (before track lock)."""

    label: str
    confidence: float
    bbox: BBox
    accepted: bool  # True if label is in the target-accept set


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
