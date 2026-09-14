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
        box = (max(0.0, x_px - half), max(0.0, y_px - half), min(float(w), half * 2), min(float(h), half * 2))
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

    def mark_seen(self) -> None:
        self.last_seen_s = time.perf_counter()
        self.had_lock = True

    def empty(self, timestamp_ms: float) -> TrackEstimate:
        if self.had_lock:
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
    No-extra-deps fingertip estimate: find a skin-colored blob and take its
    topmost point as the “finger tip”. Rudimentary but good enough to prove
    coordinates update as you move your hand.
    """

    def __init__(self, lost_timeout_s: float = 0.75) -> None:
        self._state = _LockState(lost_timeout_s)

    def close(self) -> None:
        return

    def update(self, bgr: np.ndarray, timestamp_ms: float) -> TrackEstimate:
        h, w = bgr.shape[:2]
        ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
        # Typical skin Cr/Cb band (works for many lighting conditions; not perfect)
        mask = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            return self._state.empty(timestamp_ms)

        c = max(cnts, key=cv2.contourArea)
        area = float(cv2.contourArea(c))
        if area < 800:
            return self._state.empty(timestamp_ms)

        # Fingertip ≈ highest point of the contour (smallest y)
        tip = tuple(c[c[:, :, 1].argmin()][0])
        x_px, y_px = float(tip[0]), float(tip[1])
        x, y, bw, bh = cv2.boundingRect(c)
        self._state.mark_seen()
        return _tracking_estimate(
            timestamp_ms,
            self._state.track_id,
            x_px,
            y_px,
            w,
            h,
            conf=min(1.0, area / 20000.0),
            box=(float(x), float(y), float(bw), float(bh)),
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
            self._state.mark_seen()
            return _tracking_estimate(
                timestamp_ms, self._state.track_id, x_px, y_px, w, h, conf=conf
            )
        return self._state.empty(timestamp_ms)


class ColorBlobTracker:
    """Bright tape / saturated color blob fallback."""

    def __init__(self, hue: int = 90, lost_timeout_s: float = 0.75) -> None:
        self._hue = int(hue)
        self._state = _LockState(lost_timeout_s)

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
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if cnts:
            c = max(cnts, key=cv2.contourArea)
            area = float(cv2.contourArea(c))
            if area >= 200:
                x, y, bw, bh = cv2.boundingRect(c)
                cx, cy = x + bw * 0.5, y + bh * 0.5
                self._state.mark_seen()
                return _tracking_estimate(
                    timestamp_ms,
                    self._state.track_id,
                    float(cx),
                    float(cy),
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
      skin   — default; skin blob + topmost point as fingertip (no MediaPipe)
      finger — MediaPipe index tip (falls back to skin if native lib missing)
      color  — HSV blob (bright tape)
    """
    if mode == "color":
        return ColorBlobTracker(hue=hue, lost_timeout_s=lost_timeout_s)
    if mode == "skin":
        return SkinFingerTracker(lost_timeout_s=lost_timeout_s)
    if mode == "finger":
        try:
            return FingerTracker(lost_timeout_s=lost_timeout_s)
        except Exception as exc:  # noqa: BLE001 — surface fallback clearly
            print(
                f"MediaPipe finger mode unavailable ({exc!r}); falling back to skin mode.",
                flush=True,
            )
            return SkinFingerTracker(lost_timeout_s=lost_timeout_s)
    raise ValueError(f"Unknown tracker mode: {mode!r}")
