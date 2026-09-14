"""Rudimentary finger / target detectors → TrackEstimate (M2.2)."""

from __future__ import annotations

import time
import urllib.request
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from track_estimate import BBox, TrackEstimate

_INDEX_TIP = 8

_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)
_MODEL_PATH = Path(__file__).resolve().parent / "models" / "hand_landmarker.task"


def ensure_hand_model(path: Path = _MODEL_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.stat().st_size > 1_000_000:
        return path
    print(f"Downloading hand model → {path} …", flush=True)
    urllib.request.urlretrieve(_MODEL_URL, path)
    return path


def _bearing(x_px: float, y_px: float, w: int, h: int) -> tuple[float, float]:
    fx = max(w * 0.8, 1.0)
    fy = max(h * 0.8, 1.0)
    yaw = float(np.arctan2(x_px - w * 0.5, fx))
    pitch = float(np.arctan2(-(y_px - h * 0.5), fy))
    return yaw, pitch


def _tracking_estimate(
    timestamp_ms: float,
    track_id: int,
    x_px: float,
    y_px: float,
    w: int,
    h: int,
    conf: float,
    box: Optional[tuple[float, float, float, float]] = None,
    range_proxy: Optional[float] = None,
) -> TrackEstimate:
    if box is None:
        half = 28.0
        box = (
            max(0.0, x_px - half),
            max(0.0, y_px - half),
            min(float(w), half * 2),
            min(float(h), half * 2),
        )
    bx, by, bw, bh = box
    return TrackEstimate(
        timestamp_ms=timestamp_ms,
        status="TRACKING",
        track_id=track_id,
        bbox=BBox(bx, by, bw, bh),
        confidence=conf,
        target_xy=(x_px, y_px),
        bearing_rad=_bearing(x_px, y_px, w, h),
        range_proxy=range_proxy,
    )


class _LockState:
    def __init__(self, lost_timeout_s: float) -> None:
        self.lost_timeout_s = lost_timeout_s
        self.track_id = 1
        self.last_seen_s: Optional[float] = None
        self.had_lock = False
        self.smooth_xy: Optional[tuple[float, float]] = None
        self.last_xy: Optional[tuple[float, float]] = None

    def mark_seen(self, xy: tuple[float, float], alpha: float = 0.45) -> tuple[float, float]:
        """EMA-smooth tip coords so the HUD does not thrash frame-to-frame."""
        self.last_seen_s = time.perf_counter()
        self.had_lock = True
        self.last_xy = xy
        if self.smooth_xy is None:
            self.smooth_xy = xy
        else:
            sx, sy = self.smooth_xy
            self.smooth_xy = (alpha * xy[0] + (1 - alpha) * sx, alpha * xy[1] + (1 - alpha) * sy)
        return self.smooth_xy

    def clear_smooth(self) -> None:
        self.smooth_xy = None
        self.last_xy = None

    def empty(self, timestamp_ms: float) -> TrackEstimate:
        # If we lose the target for longer than timeout, drop the spatial lock.
        if self.had_lock and self.last_seen_s is not None:
            if (time.perf_counter() - self.last_seen_s) > self.lost_timeout_s:
                self.clear_smooth()
            return TrackEstimate(
                timestamp_ms=timestamp_ms,
                status="LOST",
                track_id=self.track_id,
                bbox=None,
                confidence=0.0,
            )
        return TrackEstimate(
            timestamp_ms=timestamp_ms,
            status="SEARCHING",
            track_id=None,
            bbox=None,
            confidence=0.0,
        )


class SkinFingerTracker:
    """
    Skin-colored fingertip estimate with anti-confusion heuristics:

    - ignore huge blobs (face / torso)
    - prefer tall, finger-like contours
    - once locked, only search near the last tip (spatial gate)
    - EMA-smooth the reported (x, y)
    """

    def __init__(
        self,
        lost_timeout_s: float = 0.75,
        lock_radius_px: float = 140.0,
        min_area_frac: float = 0.002,
        max_area_frac: float = 0.12,
    ) -> None:
        self._state = _LockState(lost_timeout_s)
        self._lock_radius_px = lock_radius_px
        self._min_area_frac = min_area_frac
        self._max_area_frac = max_area_frac

    def close(self) -> None:
        return

    def update(self, bgr: np.ndarray, timestamp_ms: float) -> TrackEstimate:
        h, w = bgr.shape[:2]
        frame_area = float(h * w)

        ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
        mask = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))

        # If already locked, only look near the last tip — stops face/arm stealing the track.
        gate_center = self._state.last_xy
        if gate_center is not None:
            gate = np.zeros_like(mask)
            cv2.circle(
                gate,
                (int(gate_center[0]), int(gate_center[1])),
                int(self._lock_radius_px),
                255,
                -1,
            )
            mask = cv2.bitwise_and(mask, gate)

        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            return self._state.empty(timestamp_ms)

        min_area = self._min_area_frac * frame_area
        max_area = self._max_area_frac * frame_area
        best = None
        best_score = -1.0

        for c in cnts:
            area = float(cv2.contourArea(c))
            if area < min_area or area > max_area:
                continue
            x, y, bw, bh = cv2.boundingRect(c)
            if bh < 20 or bw < 8:
                continue
            aspect = bh / float(bw)  # fingers are taller than wide when pointing up
            # Tip = highest point (smallest y) on this contour
            tip = c[c[:, :, 1].argmin()][0]
            tip_x, tip_y = float(tip[0]), float(tip[1])

            # Prefer: higher in the frame, finger-like aspect, mid-sized area
            height_score = 1.0 - (tip_y / max(h - 1, 1))  # higher tip → better
            aspect_score = min(aspect / 3.0, 1.0)  # saturate around ~3:1
            size_score = 1.0 - abs(area - 0.03 * frame_area) / (0.03 * frame_area)
            size_score = float(np.clip(size_score, 0.0, 1.0))

            # Strong bonus for staying near the locked tip
            gate_bonus = 0.0
            if gate_center is not None:
                dist = np.hypot(tip_x - gate_center[0], tip_y - gate_center[1])
                gate_bonus = float(np.clip(1.0 - dist / self._lock_radius_px, 0.0, 1.0))

            score = 0.45 * height_score + 0.25 * aspect_score + 0.15 * size_score + 0.35 * gate_bonus
            if score > best_score:
                best_score = score
                best = (tip_x, tip_y, float(x), float(y), float(bw), float(bh), area)

        if best is None:
            return self._state.empty(timestamp_ms)

        tip_x, tip_y, bx, by, bw, bh, area = best
        sm_x, sm_y = self._state.mark_seen((tip_x, tip_y))
        return _tracking_estimate(
            timestamp_ms,
            self._state.track_id,
            sm_x,
            sm_y,
            w,
            h,
            conf=float(np.clip(best_score, 0.0, 1.0)),
            box=(bx, by, bw, bh),
            range_proxy=area,
        )


class FingerTracker:
    """MediaPipe index-fingertip tracker (best quality when the native lib loads)."""

    def __init__(self, lost_timeout_s: float = 0.75) -> None:
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        model = ensure_hand_model()
        options = vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(model)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)
        self._state = _LockState(lost_timeout_s)

    def close(self) -> None:
        self._landmarker.close()

    def update(self, bgr: np.ndarray, timestamp_ms: float) -> TrackEstimate:
        import mediapipe as mp

        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(mp_image, int(timestamp_ms))
        h, w = bgr.shape[:2]

        if result.hand_landmarks:
            lm = result.hand_landmarks[0][_INDEX_TIP]
            x_px = float(lm.x * w)
            y_px = float(lm.y * h)
            conf = 1.0
            if result.handedness:
                conf = float(result.handedness[0][0].score)
            sm_x, sm_y = self._state.mark_seen((x_px, y_px), alpha=0.55)
            return _tracking_estimate(
                timestamp_ms, self._state.track_id, sm_x, sm_y, w, h, conf=conf
            )
        return self._state.empty(timestamp_ms)


class ColorBlobTracker:
    """Bright tape / saturated color blob — most reliable no-ML option."""

    def __init__(self, hue: int = 90, lost_timeout_s: float = 0.75, lock_radius_px: float = 160.0) -> None:
        self._hue = int(hue)
        self._state = _LockState(lost_timeout_s)
        self._lock_radius_px = lock_radius_px

    def close(self) -> None:
        return

    def update(self, bgr: np.ndarray, timestamp_ms: float) -> TrackEstimate:
        h, w = bgr.shape[:2]
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        h0 = self._hue
        lo = np.array([max(0, h0 - 15), 80, 80], dtype=np.uint8)
        hi = np.array([min(179, h0 + 15), 255, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lo, hi)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))

        if self._state.last_xy is not None:
            gate = np.zeros_like(mask)
            cv2.circle(
                gate,
                (int(self._state.last_xy[0]), int(self._state.last_xy[1])),
                int(self._lock_radius_px),
                255,
                -1,
            )
            mask = cv2.bitwise_and(mask, gate)

        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if cnts:
            c = max(cnts, key=cv2.contourArea)
            area = float(cv2.contourArea(c))
            if area >= 200:
                x, y, bw, bh = cv2.boundingRect(c)
                cx, cy = x + bw * 0.5, y + bh * 0.5
                sm_x, sm_y = self._state.mark_seen((float(cx), float(cy)))
                return _tracking_estimate(
                    timestamp_ms,
                    self._state.track_id,
                    sm_x,
                    sm_y,
                    w,
                    h,
                    conf=min(1.0, area / 5000.0),
                    box=(float(x), float(y), float(bw), float(bh)),
                    range_proxy=area,
                )
        return self._state.empty(timestamp_ms)


def make_tracker(mode: str, hue: int = 90, lost_timeout_s: float = 0.75):
    """
    mode:
      skin   — skin blob + heuristics (no MediaPipe)
      finger — MediaPipe index tip (falls back to skin if native lib missing)
      color  — HSV blob (bright tape) — most reliable low-tech option
    """
    if mode == "color":
        return ColorBlobTracker(hue=hue, lost_timeout_s=lost_timeout_s)
    if mode == "skin":
        return SkinFingerTracker(lost_timeout_s=lost_timeout_s)
    if mode == "finger":
        try:
            return FingerTracker(lost_timeout_s=lost_timeout_s)
        except Exception as exc:  # noqa: BLE001
            print(
                f"MediaPipe finger mode unavailable ({exc!r}); falling back to skin mode.",
                flush=True,
            )
            return SkinFingerTracker(lost_timeout_s=lost_timeout_s)
    raise ValueError(f"Unknown tracker mode: {mode!r}")
