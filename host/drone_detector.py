"""YOLO-World class-aware detector — lock only on drone-family labels (M3.4+).

Hand / skin / phone trackers find *something*. This module asks *what* it is:
only labels in the accept set become TRACKING; person/bottle/etc. stay rejected.

Polish (M3.3-adjacent): IoU association so the lock does not jump to a new
box every frame, plus DetectTelemetry for an operator HUD.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from detect_result import (
    DEFAULT_DISTRACTOR_LABELS,
    DEFAULT_TARGET_LABELS,
    DetectTelemetry,
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
    return "yolov8s-worldv2.pt"


def _iou(a: BBox, b: BBox) -> float:
    ax2, ay2 = a.x + a.w, a.y + a.h
    bx2, by2 = b.x + b.w, b.y + b.h
    ix1, iy1 = max(a.x, b.x), max(a.y, b.y)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    union = a.w * a.h + b.w * b.h - inter
    return float(inter / union) if union > 0 else 0.0


class DroneObjectTracker:
    """
    Open-vocab detector that only locks on drone-like classes.

    - `last_detections`: all boxes this frame (accepted + rejected) for HUD
    - `telemetry`: operator numbers updated every `update()`
    - TrackEstimate.class_label set when TRACKING a drone-family hit
    """

    def __init__(
        self,
        lost_timeout_s: float = 1.0,
        conf: float = 0.25,
        min_lock_conf: float = 0.30,
        iou_match: float = 0.15,
        acquire_hits: int = 3,
        imgsz: int = 640,
        target_labels: Optional[Sequence[str]] = None,
        distractor_labels: Optional[Sequence[str]] = None,
        weights: Optional[str] = None,
    ) -> None:
        from ultralytics import YOLO

        self._conf = conf
        self._min_lock_conf = min_lock_conf
        self._iou_match = iou_match
        self._imgsz = imgsz
        self._targets = tuple(target_labels or DEFAULT_TARGET_LABELS)
        self._distractors = tuple(distractor_labels or DEFAULT_DISTRACTOR_LABELS)
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
        self._state._acquire_hits = max(1, acquire_hits)
        self._last_label: Optional[str] = None
        self._last_bbox: Optional[BBox] = None
        self._lock_started_s: Optional[float] = None
        self.last_detections: list[Detection] = []
        self.telemetry = DetectTelemetry()
        print(
            f"backend: YOLO-World class-aware  accept={list(self._targets)}  "
            f"conf>={conf} lock>={min_lock_conf} imgsz={imgsz}  weights={wpath}",
            flush=True,
        )

    def close(self) -> None:
        return

    def reset(self) -> None:
        self._state.had_lock = False
        self._state.last_seen_s = None
        self._state.clear_smooth()
        self._last_label = None
        self._last_bbox = None
        self._lock_started_s = None
        self.last_detections = []
        self.telemetry = DetectTelemetry()

    def _pick_best(self, accepted: list[Detection]) -> tuple[Optional[Detection], float]:
        """Prefer IoU continuity with previous lock; else highest conf above min_lock."""
        candidates = [d for d in accepted if d.confidence >= self._min_lock_conf]
        if not candidates:
            candidates = list(accepted)
        if not candidates:
            return None, 0.0

        if self._last_bbox is not None and self._state.had_lock:
            scored = [(_iou(self._last_bbox, d.bbox), d) for d in candidates]
            scored.sort(key=lambda t: (t[0], t[1].confidence), reverse=True)
            best_iou, best = scored[0]
            if best_iou >= self._iou_match:
                return best, best_iou
            # No spatial match — fall through to pure conf (possible reacquire)

        best = max(candidates, key=lambda d: d.confidence)
        iou = _iou(self._last_bbox, best.bbox) if self._last_bbox else 0.0
        return best, iou

    def _fill_telemetry(
        self,
        track: TrackEstimate,
        infer_ms: float,
        iou: float,
        dets: list[Detection],
    ) -> None:
        rejected = [d for d in dets if not d.accepted]
        accepted = [d for d in dets if d.accepted]
        top_rej = max(rejected, key=lambda d: d.confidence) if rejected else None
        lock_age = 0.0
        if track.status == "TRACKING" and self._lock_started_s is not None:
            lock_age = max(0.0, time.perf_counter() - self._lock_started_s)

        box_wh = None
        if track.bbox is not None:
            box_wh = (track.bbox.w, track.bbox.h)

        self.telemetry = DetectTelemetry(
            infer_ms=infer_ms,
            status=track.status,
            class_label=track.class_label,
            confidence=track.confidence,
            offset_px=track.offset_px,
            offset_norm=track.offset_norm,
            range_proxy=track.range_proxy,
            box_wh=box_wh,
            lock_age_s=lock_age,
            track_id=track.track_id,
            n_accepted=len(accepted),
            n_rejected=len(rejected),
            top_reject=top_rej.label if top_rej else None,
            top_reject_conf=top_rej.confidence if top_rej else 0.0,
            iou_with_prev=iou,
        )

    def update(self, bgr: np.ndarray, timestamp_ms: float) -> TrackEstimate:
        h, w = bgr.shape[:2]
        t0 = time.perf_counter()
        result = self._model.predict(
            bgr, conf=self._conf, imgsz=self._imgsz, verbose=False
        )[0]
        infer_ms = (time.perf_counter() - t0) * 1000.0

        dets: list[Detection] = []
        if result.boxes is not None and len(result.boxes) > 0:
            for box in result.boxes:
                cls_i = int(box.cls.item())
                conf = float(box.conf.item())
                label = result.names.get(cls_i, str(cls_i))
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
                bw = max(1.0, x2 - x1)
                bh = max(1.0, y2 - y1)
                accepted = label.lower() in self._accept
                dets.append(
                    Detection(
                        label=label,
                        confidence=conf,
                        bbox=BBox(x1, y1, bw, bh),
                        accepted=accepted,
                    )
                )

        self.last_detections = dets
        accepted = [d for d in dets if d.accepted]
        best, iou = self._pick_best(accepted)

        if best is None:
            est = self._state.coast_or_empty(timestamp_ms, w, h)
            if est.status == "TRACKING" and self._last_label:
                est.class_label = self._last_label
                if self._last_bbox is not None:
                    est.bbox = self._last_bbox
                    est.range_proxy = self._last_bbox.w * self._last_bbox.h
            if est.status != "TRACKING":
                self._lock_started_s = None
                if est.status == "LOST":
                    self._last_bbox = None
            self._fill_telemetry(est, infer_ms, 0.0, dets)
            return est

        cx, cy = best.bbox.cx, best.bbox.cy
        sm = self._state.mark_seen((cx, cy), alpha=0.35)
        if sm is None:
            est = TrackEstimate(
                timestamp_ms=timestamp_ms,
                status="SEARCHING",
                track_id=None,
                bbox=best.bbox,
                confidence=best.confidence,
                origin_xy=(w * 0.5, h * 0.5),
                class_label=None,
            )
            self._fill_telemetry(est, infer_ms, iou, dets)
            return est

        if self._lock_started_s is None:
            self._lock_started_s = time.perf_counter()

        self._last_label = best.label
        self._last_bbox = best.bbox
        sm_x, sm_y = sm
        est = _tracking_estimate(
            timestamp_ms,
            self._state.track_id,
            sm_x,
            sm_y,
            w,
            h,
            conf=best.confidence,
            box=(best.bbox.x, best.bbox.y, best.bbox.w, best.bbox.h),
            range_proxy=best.bbox.w * best.bbox.h,
            class_label=best.label,
        )
        self._fill_telemetry(est, infer_ms, iou, dets)
        return est
