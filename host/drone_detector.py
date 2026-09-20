"""YOLO-World class-aware detector — lock only on drone-family labels (M3.4).

Hand / skin / phone trackers find *something*. This module asks *what* it is:
only labels in the accept set become TRACKING; person/bottle/etc. stay rejected.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from detect_result import (
    DEFAULT_DISTRACTOR_LABELS,
    DEFAULT_TARGET_LABELS,
    Detection,
)
from finger_tracker import _LockState, _tracking_estimate
from track_estimate import BBox, TrackEstimate

_WEIGHTS_CANDIDATES = (
    Path(__file__).resolve().parent / "yolov8s-worldv2.pt",
    Path(__file__).resolve().parent / "weights" / "yolov8s-worldv2.pt",
    Path("yolov8s-worldv2.pt"),
)


def _find_weights(explicit: Optional[str] = None) -> str:
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            raise FileNotFoundError(f"YOLO-World weights not found: {p}")
        return str(p)
    for c in _WEIGHTS_CANDIDATES:
        if c.is_file():
            return str(c)
    # Ultralytics will download if missing
    return "yolov8s-worldv2.pt"


class DroneObjectTracker:
    """
    Open-vocab detector that only locks on drone-like classes.

    - `last_detections`: all boxes this frame (accepted + rejected) for HUD
    - TrackEstimate.class_label set when TRACKING a drone-family hit
    """

    def __init__(
        self,
        lost_timeout_s: float = 1.0,
        conf: float = 0.25,
        target_labels: Optional[Sequence[str]] = None,
        distractor_labels: Optional[Sequence[str]] = None,
        weights: Optional[str] = None,
    ) -> None:
        from ultralytics import YOLO

        self._conf = conf
        self._targets = tuple(target_labels or DEFAULT_TARGET_LABELS)
        self._distractors = tuple(distractor_labels or DEFAULT_DISTRACTOR_LABELS)
        # Dedup while preserving order
        seen: set[str] = set()
        prompts: list[str] = []
        for lab in list(self._targets) + list(self._distractors):
            key = lab.lower()
            if key not in seen:
                seen.add(key)
                prompts.append(lab)
        self._prompts = prompts
        self._accept = {t.lower() for t in self._targets}

        wpath = _find_weights(weights)
        self._model = YOLO(wpath)
        self._model.set_classes(list(self._prompts))
        self._state = _LockState(lost_timeout_s)
        self._state._acquire_hits = 2
        self._last_label: Optional[str] = None
        self.last_detections: list[Detection] = []
        print(
            f"backend: YOLO-World class-aware  accept={list(self._targets)}  "
            f"weights={wpath}",
            flush=True,
        )

    def close(self) -> None:
        return

    def reset(self) -> None:
        self._state.had_lock = False
        self._state.last_seen_s = None
        self._state.clear_smooth()
        self._last_label = None
        self.last_detections = []

    def update(self, bgr: np.ndarray, timestamp_ms: float) -> TrackEstimate:
        h, w = bgr.shape[:2]
        result = self._model.predict(bgr, conf=self._conf, verbose=False)[0]
        dets: list[Detection] = []
        best: Optional[tuple[float, Detection]] = None  # score, det

        if result.boxes is not None and len(result.boxes) > 0:
            for box in result.boxes:
                cls_i = int(box.cls.item())
                conf = float(box.conf.item())
                label = result.names.get(cls_i, str(cls_i))
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
                bw = max(1.0, x2 - x1)
                bh = max(1.0, y2 - y1)
                accepted = label.lower() in self._accept
                det = Detection(
                    label=label,
                    confidence=conf,
                    bbox=BBox(x1, y1, bw, bh),
                    accepted=accepted,
                )
                dets.append(det)
                if accepted and (best is None or conf > best[0]):
                    best = (conf, det)

        self.last_detections = dets

        if best is None:
            est = self._state.coast_or_empty(timestamp_ms, w, h)
            if est.status == "TRACKING" and self._last_label:
                est.class_label = self._last_label
            return est

        _conf, det = best
        cx = det.bbox.cx
        cy = det.bbox.cy
        sm = self._state.mark_seen((cx, cy), alpha=0.4)
        if sm is None:
            return TrackEstimate(
                timestamp_ms=timestamp_ms,
                status="SEARCHING",
                track_id=None,
                bbox=det.bbox,
                confidence=det.confidence,
                origin_xy=(w * 0.5, h * 0.5),
                class_label=None,
            )

        self._last_label = det.label
        sm_x, sm_y = sm
        est = _tracking_estimate(
            timestamp_ms,
            self._state.track_id,
            sm_x,
            sm_y,
            w,
            h,
            conf=det.confidence,
            box=(det.bbox.x, det.bbox.y, det.bbox.w, det.bbox.h),
            range_proxy=det.bbox.w * det.bbox.h,
        )
        est.class_label = det.label
        return est
