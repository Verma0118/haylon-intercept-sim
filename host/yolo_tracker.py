"""YOLOv8 pose tracking via Ultralytics (lightweight yolov8n-pose)."""

from __future__ import annotations

import numpy as np

from finger_tracker import _LockState, _tracking_estimate
from track_estimate import TrackEstimate

# COCO-pose indices
_L_ELBOW, _R_ELBOW = 7, 8
_L_WRIST, _R_WRIST = 9, 10


class YoloHandTracker:
    """
    YOLOv8-pose tracker.

    Uses wrist keypoints and extends elbow→wrist to approximate an
    index-fingertip when the arm is pointed at the camera.
    """

    def __init__(self, lost_timeout_s: float = 1.0, conf: float = 0.25) -> None:
        from ultralytics import YOLO

        self._conf = conf
        self._state = _LockState(lost_timeout_s)
        self._state._acquire_hits = 1
        self._model = YOLO("yolov8n-pose.pt")  # auto-download ~6MB
        print("backend: YOLOv8-pose (wrist → fingertip extend)", flush=True)

    def close(self) -> None:
        return

    def reset(self) -> None:
        self._state.had_lock = False
        self._state.last_seen_s = None
        self._state.clear_smooth()

    def update(self, bgr: np.ndarray, timestamp_ms: float) -> TrackEstimate:
        h, w = bgr.shape[:2]
        results = self._model.predict(bgr, conf=self._conf, verbose=False, imgsz=640)
        if not results or results[0].keypoints is None or len(results[0].keypoints) == 0:
            return self._state.coast_or_empty(timestamp_ms, w, h)

        kps = results[0].keypoints.data.cpu().numpy()
        best = None
        best_score = -1.0

        for person in kps:
            for elbow_i, wrist_i in ((_R_ELBOW, _R_WRIST), (_L_ELBOW, _L_WRIST)):
                if wrist_i >= len(person) or elbow_i >= len(person):
                    continue
                wx, wy, wconf = map(float, person[wrist_i][:3])
                ex, ey, econf = map(float, person[elbow_i][:3])
                if wconf < 0.35 or wx <= 1 or wy <= 1:
                    continue
                # Extend past the wrist along elbow→wrist (pointing hand)
                if econf >= 0.25 and ex > 1 and ey > 1:
                    vx, vy = wx - ex, wy - ey
                    tip_x, tip_y = wx + 0.55 * vx, wy + 0.55 * vy
                else:
                    tip_x, tip_y = wx, wy
                tip_x = float(np.clip(tip_x, 0, w - 1))
                tip_y = float(np.clip(tip_y, 0, h - 1))
                score = wconf
                if score > best_score:
                    best_score = score
                    half = 42.0
                    best = (
                        tip_x,
                        tip_y,
                        max(0.0, tip_x - half),
                        max(0.0, tip_y - half),
                        half * 2,
                        half * 2,
                        score,
                    )

        if best is None:
            return self._state.coast_or_empty(timestamp_ms, w, h)

        tip_x, tip_y, x, y, bw, bh, score = best
        sm = self._state.mark_seen((tip_x, tip_y), alpha=0.35)
        if sm is None:
            return self._state.coast_or_empty(timestamp_ms, w, h)
        sm_x, sm_y = sm
        return _tracking_estimate(
            timestamp_ms,
            self._state.track_id,
            sm_x,
            sm_y,
            w,
            h,
            conf=float(np.clip(score, 0.0, 1.0)),
            box=(x, y, bw, bh),
            range_proxy=bw * bh,
        )
