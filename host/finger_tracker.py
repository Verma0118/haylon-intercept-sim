"""Rudimentary finger / target detectors → TrackEstimate (M2.2)."""

from __future__ import annotations

import time
import urllib.request
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from track_estimate import BBox, TrackEstimate
from frame_coords import frame_coords_from_image_xy

_INDEX_TIP = 8

_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)
_MODEL_PATH = Path(__file__).resolve().parent / "models" / "hand_landmarker.task"

_FACE_YUNET_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
    "face_detection_yunet_2023mar.onnx"
)
_FACE_YUNET_PATH = (
    Path(__file__).resolve().parent / "models" / "face_detection_yunet_2023mar.onnx"
)


def ensure_hand_model(path: Path = _MODEL_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.stat().st_size > 1_000_000:
        return path
    print(f"Downloading hand model → {path} …", flush=True)
    urllib.request.urlretrieve(_MODEL_URL, path)
    return path


def ensure_face_model(path: Path = _FACE_YUNET_PATH) -> Path:
    """YuNet ONNX for cv2.FaceDetectorYN (works on OpenCV 4.5+ and 5.x)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.stat().st_size > 50_000:
        return path
    print(f"Downloading face model → {path} …", flush=True)
    urllib.request.urlretrieve(_FACE_YUNET_URL, path)
    if not path.is_file() or path.stat().st_size < 50_000:
        raise RuntimeError(f"Face model download failed: {path}")
    return path

def _bearing(x_px: float, y_px: float, w: int, h: int) -> tuple[float, float]:
    return frame_coords_from_image_xy(x_px, y_px, w, h).bearing_rad


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
    tips_xy: Optional[tuple[tuple[float, float], ...]] = None,
    class_label: Optional[str] = None,
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
    fc = frame_coords_from_image_xy(x_px, y_px, w, h)
    return TrackEstimate(
        timestamp_ms=timestamp_ms,
        status="TRACKING",
        track_id=track_id,
        bbox=BBox(bx, by, bw, bh),
        confidence=conf,
        target_xy=fc.image_xy,
        bearing_rad=fc.bearing_rad,
        range_proxy=range_proxy,
        tips_xy=tips_xy,
        offset_px=fc.offset_px,
        offset_norm=fc.offset_norm,
        origin_xy=fc.origin_xy,
        class_label=class_label,
    )


class _LockState:
    def __init__(self, lost_timeout_s: float) -> None:
        self.lost_timeout_s = lost_timeout_s
        self.track_id = 1
        self.last_seen_s: Optional[float] = None
        self.had_lock = False
        self.smooth_xy: Optional[tuple[float, float]] = None
        self.last_xy: Optional[tuple[float, float]] = None
        self._hit_streak = 0
        self._acquire_hits = 2  # need N hits before first TRACKING

    def mark_seen(self, xy: tuple[float, float], alpha: float = 0.45) -> Optional[tuple[float, float]]:
        """EMA-smooth tip coords. Returns None until acquire_hits consecutive sees."""
        self.last_seen_s = time.perf_counter()
        self.last_xy = xy
        self._hit_streak += 1
        if self.smooth_xy is None:
            self.smooth_xy = xy
        else:
            sx, sy = self.smooth_xy
            self.smooth_xy = (alpha * xy[0] + (1 - alpha) * sx, alpha * xy[1] + (1 - alpha) * sy)

        if not self.had_lock and self._hit_streak < self._acquire_hits:
            return None  # still confirming — caller should SEARCHING
        self.had_lock = True
        return self.smooth_xy

    def miss(self) -> None:
        self._hit_streak = 0

    def clear_smooth(self) -> None:
        self.smooth_xy = None
        self.last_xy = None
        self._hit_streak = 0

    def coast_or_empty(
        self,
        timestamp_ms: float,
        w: int,
        h: int,
        conf: float = 0.35,
    ) -> TrackEstimate:
        """
        On a miss: keep TRACKING with the last tip for lost_timeout_s (stops HUD flash),
        then LOST, then SEARCHING.
        """
        self.miss()
        if self.had_lock and self.smooth_xy is not None and self.last_seen_s is not None:
            age = time.perf_counter() - self.last_seen_s
            if age <= self.lost_timeout_s:
                sx, sy = self.smooth_xy
                return _tracking_estimate(
                    timestamp_ms,
                    self.track_id,
                    sx,
                    sy,
                    w,
                    h,
                    conf=conf,
                )
            self.clear_smooth()
            self.had_lock = False
            return TrackEstimate(
                timestamp_ms=timestamp_ms,
                status="LOST",
                track_id=self.track_id,
                bbox=None,
                confidence=0.0,
                origin_xy=(w * 0.5, h * 0.5),
            )
        return TrackEstimate(
            timestamp_ms=timestamp_ms,
            status="SEARCHING",
            track_id=None,
            bbox=None,
            confidence=0.0,
            origin_xy=(w * 0.5, h * 0.5),
        )

    def empty(self, timestamp_ms: float, w: int = 0, h: int = 0) -> TrackEstimate:
        if w > 0 and h > 0:
            return self.coast_or_empty(timestamp_ms, w, h)
        # Legacy path without frame size
        self.miss()
        if self.had_lock and self.last_seen_s is not None:
            if (time.perf_counter() - self.last_seen_s) > self.lost_timeout_s:
                self.clear_smooth()
                self.had_lock = False
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
    OpenCV index-fingertip lock (no MediaPipe).

    Tuned to *hold* a lock instead of flashing:
    - wide skin mask (YCrCb + HSV)
    - optional face punch-out so the tip is not your nose
    - large spatial gate once locked
    - coast on brief misses (keeps TRACKING with last tip)
    """

    def __init__(
        self,
        lost_timeout_s: float = 1.0,
        lock_radius_px: float = 240.0,
        min_area_frac: float = 0.002,
        max_area_frac: float = 0.28,
    ) -> None:
        self._state = _LockState(lost_timeout_s)
        self._state._acquire_hits = 2
        self._lock_radius_px = lock_radius_px
        self._min_area_frac = min_area_frac
        self._max_area_frac = max_area_frac
        self._face = None
        self._face_size: Optional[tuple[int, int]] = None
        try:
            if hasattr(cv2, "FaceDetectorYN_create"):
                model = ensure_face_model()
                self._face = cv2.FaceDetectorYN_create(str(model), "", (320, 320), 0.7, 0.3, 5000)
        except Exception:  # noqa: BLE001
            self._face = None

    def close(self) -> None:
        return

    def reset(self) -> None:
        self._state.had_lock = False
        self._state.last_seen_s = None
        self._state.clear_smooth()

    def _skin_mask(self, bgr: np.ndarray) -> np.ndarray:
        ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
        # Skin chromaticity in YCrCb
        m_y = cv2.inRange(ycrcb, (40, 130, 80), (255, 175, 130))
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        # Reject gray walls/ceiling (low saturation) — that was flooding the mask
        sat_ok = cv2.inRange(hsv, (0, 40, 40), (179, 255, 255))
        m_h = cv2.bitwise_or(
            cv2.inRange(hsv, (0, 40, 50), (25, 200, 255)),
            cv2.inRange(hsv, (160, 40, 50), (179, 200, 255)),
        )
        mask = cv2.bitwise_and(cv2.bitwise_or(m_y, m_h), sat_ok)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
        return mask

    def _punch_face(self, mask: np.ndarray, bgr: np.ndarray) -> np.ndarray:
        if self._face is None:
            return mask
        h, w = mask.shape[:2]
        size = (w, h)
        if size != self._face_size:
            self._face.setInputSize(size)
            self._face_size = size
        try:
            _ret, faces = self._face.detect(bgr)
        except Exception:  # noqa: BLE001
            return mask
        if faces is None:
            return mask
        out = mask.copy()
        for row in faces:
            x, y, bw, bh = map(int, row[:4])
            pad = int(0.25 * max(bw, bh))
            x0, y0 = max(0, x - pad), max(0, y - pad)
            x1, y1 = min(w, x + bw + pad), min(h, y + bh + pad)
            out[y0:y1, x0:x1] = 0
        return out

    def update(self, bgr: np.ndarray, timestamp_ms: float) -> TrackEstimate:
        h, w = bgr.shape[:2]
        frame_area = float(h * w)
        mask = self._punch_face(self._skin_mask(bgr), bgr)

        # Ignore ceiling strip while searching (lights / tiles false tips)
        if self._state.last_xy is None:
            mask[: int(0.12 * h), :] = 0

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
            return self._state.coast_or_empty(timestamp_ms, w, h)

        min_area = self._min_area_frac * frame_area
        max_area = self._max_area_frac * frame_area
        best = None
        best_score = -1.0

        for c in cnts:
            area = float(cv2.contourArea(c))
            if area < min_area or area > max_area:
                continue
            x, y, bw, bh = cv2.boundingRect(c)
            if bh < 28 or bw < 8:
                continue

            m = cv2.moments(c)
            if m["m00"] <= 1e-3:
                continue
            cx = float(m["m10"] / m["m00"])
            cy = float(m["m01"] / m["m00"])

            # Tip = highest contour point (smallest image-y)
            tip = c[c[:, :, 1].argmin()][0]
            tip_x, tip_y = float(tip[0]), float(tip[1])

            # Tip should be above the blob centroid (finger pointing up-ish)
            if tip_y > cy - 4:
                continue
            # Keep tip away from extreme top edge only
            if tip_y < 0.04 * h:
                continue

            tip_above = float(np.clip((cy - tip_y) / max(bh, 1), 0.0, 1.0))
            aspect = bh / float(max(bw, 1))
            aspect_score = float(np.clip(aspect / 2.5, 0.0, 1.0))
            size_score = float(np.clip(area / (0.04 * frame_area), 0.0, 1.0))
            center_score = 1.0 - abs(tip_x - w * 0.5) / (w * 0.5)
            center_score = float(np.clip(center_score, 0.0, 1.0))

            gate_bonus = 0.0
            if gate_center is not None:
                dist = float(np.hypot(tip_x - gate_center[0], tip_y - gate_center[1]))
                gate_bonus = float(np.clip(1.0 - dist / self._lock_radius_px, 0.0, 1.0))

            score = (
                0.40 * tip_above
                + 0.20 * aspect_score
                + 0.15 * size_score
                + 0.10 * center_score
                + 0.35 * gate_bonus
            )
            if score > best_score:
                best_score = score
                best = (tip_x, tip_y, float(x), float(y), float(bw), float(bh), area)

        if best is None:
            return self._state.coast_or_empty(timestamp_ms, w, h)

        tip_x, tip_y, bx, by, bw, bh, area = best
        sm = self._state.mark_seen((tip_x, tip_y), alpha=0.35)
        if sm is None:
            return TrackEstimate(
                timestamp_ms=timestamp_ms,
                status="SEARCHING",
                track_id=None,
                bbox=None,
                confidence=0.0,
                origin_xy=(w * 0.5, h * 0.5),
            )
        sm_x, sm_y = sm
        return _tracking_estimate(
            timestamp_ms,
            self._state.track_id,
            sm_x,
            sm_y,
            w,
            h,
            conf=float(np.clip(0.45 + 0.55 * best_score, 0.0, 1.0)),
            box=(bx, by, bw, bh),
            range_proxy=area,
        )


class FingerTracker:
    """MediaPipe index-fingertip tracker (best quality when the native lib loads)."""

    def __init__(self, lost_timeout_s: float = 1.0) -> None:
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        model = ensure_hand_model()
        options = vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(model)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=0.35,
            min_hand_presence_confidence=0.35,
            min_tracking_confidence=0.35,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)
        self._state = _LockState(lost_timeout_s)
        self._state._acquire_hits = 1  # MediaPipe already stable

    def close(self) -> None:
        self._landmarker.close()

    def reset(self) -> None:
        self._state.had_lock = False
        self._state.last_seen_s = None
        self._state.clear_smooth()

    def update(self, bgr: np.ndarray, timestamp_ms: float) -> TrackEstimate:
        import mediapipe as mp

        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        # MediaPipe wants monotonically increasing ms; wall clock can jump — use perf counter ms.
        ts = int(max(timestamp_ms, time.perf_counter() * 1000.0))
        result = self._landmarker.detect_for_video(mp_image, ts)
        h, w = bgr.shape[:2]

        if result.hand_landmarks:
            lm = result.hand_landmarks[0][_INDEX_TIP]
            x_px = float(lm.x * w)
            y_px = float(lm.y * h)
            conf = 0.9
            if result.handedness:
                conf = float(result.handedness[0][0].score)
            sm = self._state.mark_seen((x_px, y_px), alpha=0.4)
            if sm is None:
                return TrackEstimate(
                    timestamp_ms=timestamp_ms,
                    status="SEARCHING",
                    track_id=None,
                    bbox=None,
                    confidence=0.0,
                    origin_xy=(w * 0.5, h * 0.5),
                )
            sm_x, sm_y = sm
            # Small box around the tip for the HUD
            half = 36.0
            box = (
                max(0.0, sm_x - half),
                max(0.0, sm_y - half),
                min(float(w), half * 2),
                min(float(h), half * 2),
            )
            return _tracking_estimate(
                timestamp_ms, self._state.track_id, sm_x, sm_y, w, h, conf=conf, box=box
            )
        return self._state.coast_or_empty(timestamp_ms, w, h)


class ColorBlobTracker:
    """Bright tape / saturated color blob — most reliable no-ML option."""

    def __init__(self, hue: int = 90, lost_timeout_s: float = 0.75, lock_radius_px: float = 160.0) -> None:
        self._hue = int(hue)
        self._state = _LockState(lost_timeout_s)
        self._lock_radius_px = lock_radius_px

    def close(self) -> None:
        return

    def reset(self) -> None:
        self._state.had_lock = False
        self._state.last_seen_s = None
        self._state.clear_smooth()

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
                sm = self._state.mark_seen((float(cx), float(cy)))
                if sm is None:
                    return TrackEstimate(
                        timestamp_ms=timestamp_ms,
                        status="SEARCHING",
                        track_id=None,
                        bbox=None,
                        confidence=0.0,
                        origin_xy=(w * 0.5, h * 0.5),
                    )
                sm_x, sm_y = sm
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
        return self._state.coast_or_empty(timestamp_ms, w, h)


class TwoFingerTracker:
    """
    Lock onto a two-finger (peace-sign) pose.

    Looks for a skin hand blob with *two* fingertip peaks, then tracks the
    midpoint between them. Much less confused by ceiling/face than single-tip skin mode.
    Hold up index + middle (V shape), palm facing the camera.
    """

    def __init__(
        self,
        lost_timeout_s: float = 0.6,
        lock_radius_px: float = 160.0,
        min_area_frac: float = 0.01,
        max_area_frac: float = 0.45,
    ) -> None:
        self._state = _LockState(lost_timeout_s)
        self._lock_radius_px = lock_radius_px
        self._min_area_frac = min_area_frac
        self._max_area_frac = max_area_frac

    def close(self) -> None:
        return

    def reset(self) -> None:
        self._state.had_lock = False
        self._state.last_seen_s = None
        self._state.clear_smooth()

    def _skin_mask(self, bgr: np.ndarray) -> np.ndarray:
        # Keep Cr away from 128 (neutral gray) or the whole frame floods.
        ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
        mask = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))
        # Mild boost for warm skin under cool lights — still requires saturation.
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        mask2 = cv2.inRange(hsv, (0, 40, 60), (25, 200, 255))
        mask = cv2.bitwise_or(mask, mask2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        return mask

    def _fingertip_peaks(
        self, mask: np.ndarray, contour: np.ndarray, bbox: tuple[int, int, int, int]
    ) -> list[tuple[float, float]]:
        """
        Find two fingertip candidates.

        Prefer separate blobs in the upper part of the hand mask (peace-sign gap).
        Fall back to top-silhouette peaks if needed.
        """
        x, y, bw, bh = bbox
        if bw < 20 or bh < 40:
            return []

        # --- Preferred: two separate finger blobs in the upper hand band ---
        band_h = max(20, int(0.50 * bh))
        band = mask[y : y + band_h, x : x + bw].copy()
        # Clear weak bridges between fingers
        band = cv2.morphologyEx(band, cv2.MORPH_OPEN, np.ones((3, 7), np.uint8))
        finger_cnts, _ = cv2.findContours(band, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        finger_tips: list[tuple[float, float, float]] = []  # x, y, area
        min_finger_area = max(40.0, 0.01 * bw * band_h)
        for fc in finger_cnts:
            area = float(cv2.contourArea(fc))
            if area < min_finger_area:
                continue
            # Remap to full-image coords
            fx, fy, fbw, fbh = cv2.boundingRect(fc)
            tip_x = x + fx + fbw * 0.5
            tip_y = y + fy  # top of this finger blob
            finger_tips.append((tip_x, float(tip_y), area))

        if len(finger_tips) >= 2:
            # Take the two highest tips (smallest y), requiring horizontal separation
            finger_tips.sort(key=lambda t: t[1])
            chosen: list[tuple[float, float]] = []
            min_sep = max(20.0, 0.18 * bw)
            for tip_x, tip_y, _area in finger_tips:
                if all(abs(tip_x - c[0]) >= min_sep for c in chosen):
                    chosen.append((tip_x, tip_y))
                if len(chosen) == 2:
                    chosen.sort(key=lambda p: p[0])
                    return chosen

        # --- Fallback: peaks on the top silhouette ---
        xs = contour[:, 0, 0]
        ys = contour[:, 0, 1]
        top_y = np.full(bw, fill_value=float(y + bh), dtype=np.float32)
        for px, py in zip(xs, ys):
            ix = int(px) - x
            if 0 <= ix < bw:
                top_y[ix] = min(top_y[ix], float(py))
        k = max(5, (bw // 15) | 1)
        smooth = np.convolve(top_y, np.ones(k, dtype=np.float32) / k, mode="same")
        peaks: list[tuple[float, float]] = []
        for i in range(3, bw - 3):
            v = smooth[i]
            if v < smooth[i - 2] and v < smooth[i + 2] and v <= y + 0.55 * bh:
                # prominence vs local neighborhood
                neigh = float(np.max(smooth[max(0, i - k) : i + k + 1]))
                if neigh - v >= 4.0:
                    peaks.append((float(x + i), float(v)))
        if len(peaks) < 2:
            return []
        peaks.sort(key=lambda p: p[1])
        chosen = []
        min_sep = max(20.0, 0.18 * bw)
        for p in peaks:
            if all(abs(p[0] - c[0]) >= min_sep for c in chosen):
                chosen.append(p)
            if len(chosen) == 2:
                chosen.sort(key=lambda q: q[0])
                return chosen
        return []

    def update(self, bgr: np.ndarray, timestamp_ms: float) -> TrackEstimate:
        h, w = bgr.shape[:2]
        frame_area = float(h * w)
        mask = self._skin_mask(bgr)

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
            return self._state.coast_or_empty(timestamp_ms, w, h)

        min_area = self._min_area_frac * frame_area
        max_area = self._max_area_frac * frame_area

        # Prefer the largest plausible hand contour
        hand = None
        hand_area = 0.0
        for c in cnts:
            area = float(cv2.contourArea(c))
            if area < min_area or area > max_area:
                continue
            if area > hand_area:
                hand_area = area
                hand = c
        if hand is None:
            return self._state.coast_or_empty(timestamp_ms, w, h)

        bx, by, bw, bh = cv2.boundingRect(hand)
        tips = self._fingertip_peaks(mask, hand, (bx, by, bw, bh))
        if len(tips) < 2:
            return self._state.coast_or_empty(timestamp_ms, w, h)

        (x0, y0), (x1, y1) = tips[0], tips[1]
        mid_x = 0.5 * (x0 + x1)
        mid_y = 0.5 * (y0 + y1)
        sep = abs(x1 - x0)
        # Separation relative to the hand, not the full frame
        if sep < max(18.0, 0.15 * bw) or sep > 0.90 * bw:
            return self._state.coast_or_empty(timestamp_ms, w, h)
        if mid_y < 0.04 * h:
            return self._state.coast_or_empty(timestamp_ms, w, h)

        sm = self._state.mark_seen((mid_x, mid_y), alpha=0.5)
        if sm is None:
            return self._state.coast_or_empty(timestamp_ms, w, h)
        sm_x, sm_y = sm
        pad = 20.0
        box = (
            max(0.0, min(x0, x1) - pad),
            max(0.0, min(y0, y1) - pad),
            min(float(w), abs(x1 - x0) + 2 * pad),
            min(float(h), abs(y1 - y0) + 2 * pad + 40.0),
        )
        conf = float(np.clip(0.55 + 0.45 * (hand_area / (0.2 * frame_area)), 0.0, 1.0))
        return _tracking_estimate(
            timestamp_ms,
            self._state.track_id,
            sm_x,
            sm_y,
            w,
            h,
            conf=conf,
            box=box,
            range_proxy=hand_area,
            tips_xy=(tips[0], tips[1]),
        )


class PhoneTracker:
    """
    Track a phone held toward the camera as a *very dark* rectangle.

    Contour/blob masks fail in classrooms because the phone merges with dark
    hair/hoodies into one blob. Instead we slide phone-aspect windows over an
    integral image and pick the darkest solid rectangle (typical black phone).
    """

    def __init__(
        self,
        lost_timeout_s: float = 0.7,
        lock_radius_px: float = 240.0,
        search_width: int = 640,
    ) -> None:
        self._state = _LockState(lost_timeout_s)
        self._lock_radius_px = lock_radius_px
        self._search_width = search_width

    def close(self) -> None:
        return

    def reset(self) -> None:
        self._state.had_lock = False
        self._state.last_seen_s = None
        self._state.clear_smooth()

    @staticmethod
    def _rect_mean(integral: np.ndarray, x: int, y: int, bw: int, bh: int) -> float:
        return float(
            integral[y + bh, x + bw]
            - integral[y, x + bw]
            - integral[y + bh, x]
            + integral[y, x]
        ) / float(bw * bh)

    def _search_dark_phone(
        self,
        gray: np.ndarray,
        gate_center: Optional[tuple[float, float]],
        scale: float,
    ) -> Optional[tuple[float, float, float, float, float, float, float]]:
        """Return (score, cx, cy, x, y, bw, bh) in *gray* coordinates."""
        h, w = gray.shape[:2]
        frame_area = float(h * w)
        inv = (255 - gray).astype(np.float32)
        inte = cv2.integral(inv)
        very_dark = (gray < 30).astype(np.uint8)
        dinte = cv2.integral(very_dark)

        lock_r = self._lock_radius_px * scale
        best: Optional[tuple[float, float, float, float, float, float, float]] = None
        best_score = -1.0

        # Portrait first (hold phone upright); also allow landscape.
        orientations = ((True, 1.0), (False, 0.85))
        for portrait, orient_w in orientations:
            for short in range(28, 95, 5):
                for ar in (1.65, 1.85, 2.05, 2.25, 2.45):
                    if portrait:
                        bw, bh = short, int(short * ar)
                    else:
                        bh, bw = short, int(short * ar)
                    area = float(bw * bh)
                    if area < 0.015 * frame_area or area > 0.16 * frame_area:
                        continue
                    if bw >= w - 2 or bh >= h - 2:
                        continue

                    step = max(4, short // 5)
                    y0 = int(0.10 * h)
                    y1 = int(0.88 * h) - bh
                    x0 = int(0.04 * w)
                    x1 = int(0.96 * w) - bw
                    if y1 <= y0 or x1 <= x0:
                        continue

                    for y in range(y0, y1, step):
                        for x in range(x0, x1, step):
                            if gate_center is not None:
                                gcx, gcy = gate_center
                                cx_g = (x + bw * 0.5) / scale
                                cy_g = (y + bh * 0.5) / scale
                                if float(np.hypot(cx_g - gcx, cy_g - gcy)) > lock_r:
                                    continue

                            fill = self._rect_mean(dinte, x, y, bw, bh)
                            if fill < 0.70:
                                continue
                            darkness = self._rect_mean(inte, x, y, bw, bh)
                            # mean gray <= ~40
                            if darkness < 215.0:
                                continue

                            pad = max(10, short // 3)
                            rx0, ry0 = max(0, x - pad), max(0, y - pad)
                            rx1, ry1 = min(w, x + bw + pad), min(h, y + bh + pad)
                            ring_a = float((rx1 - rx0) * (ry1 - ry0) - bw * bh)
                            if ring_a < 1.0:
                                continue
                            outer = float(
                                inte[ry1, rx1]
                                - inte[ry0, rx1]
                                - inte[ry1, rx0]
                                + inte[ry0, rx0]
                            )
                            ring = (outer - darkness * bw * bh) / ring_a
                            contrast = darkness - ring
                            if contrast < 12.0:
                                continue

                            aspect_sc = 1.0 - abs(ar - 2.05) / 1.2
                            aspect_sc = float(np.clip(aspect_sc, 0.0, 1.0))
                            size_sc = 1.0 - abs(area / frame_area - 0.05) / 0.07
                            size_sc = float(np.clip(size_sc, 0.0, 1.0))

                            gate_bonus = 0.0
                            if gate_center is not None:
                                gcx, gcy = gate_center
                                dist = float(
                                    np.hypot(
                                        (x + bw * 0.5) / scale - gcx,
                                        (y + bh * 0.5) / scale - gcy,
                                    )
                                )
                                gate_bonus = float(np.clip(1.0 - dist / max(lock_r, 1.0), 0.0, 1.0))

                            score = (
                                fill
                                * (darkness / 255.0)
                                * (0.55 + 0.45 * aspect_sc)
                                * (0.75 + 0.25 * size_sc)
                                * orient_w
                                * (1.0 + 0.35 * gate_bonus)
                            )
                            if score > best_score:
                                best_score = score
                                best = (
                                    score,
                                    x + bw * 0.5,
                                    y + bh * 0.5,
                                    float(x),
                                    float(y),
                                    float(bw),
                                    float(bh),
                                )

        return best

    def _search_bright_screen(
        self,
        bgr: np.ndarray,
        gate_center: Optional[tuple[float, float]],
        scale: float,
    ) -> Optional[tuple[float, float, float, float, float, float, float]]:
        """Fallback: lit phone screen as a bright low-sat rectangle."""
        h, w = bgr.shape[:2]
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        bright = cv2.inRange(hsv, (0, 0, 190), (180, 70, 255))
        if bright.mean() > 0.28 * 255:
            return None
        bright = cv2.morphologyEx(bright, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        cnts, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best = None
        best_score = -1.0
        frame_area = float(h * w)
        lock_r = self._lock_radius_px * scale
        for c in cnts:
            area = float(cv2.contourArea(c))
            if area < 0.015 * frame_area or area > 0.25 * frame_area:
                continue
            rect = cv2.minAreaRect(c)
            (cx, cy), (rw, rh), _ = rect
            if min(rw, rh) < 1:
                continue
            aspect = max(rw, rh) / min(rw, rh)
            if aspect < 1.45 or aspect > 2.7:
                continue
            rectangularity = area / max(rw * rh, 1.0)
            if rectangularity < 0.55:
                continue
            if gate_center is not None:
                gcx, gcy = gate_center
                if float(np.hypot(cx / scale - gcx, cy / scale - gcy)) > lock_r:
                    continue
            x, y, bw, bh = cv2.boundingRect(c)
            score = 0.5 * rectangularity + 0.5 * (1.0 - abs(aspect - 2.05) / 1.2)
            if score > best_score:
                best_score = score
                best = (score * 0.75, float(cx), float(cy), float(x), float(y), float(bw), float(bh))
        return best

    def update(self, bgr: np.ndarray, timestamp_ms: float) -> TrackEstimate:
        h, w = bgr.shape[:2]
        scale = 1.0
        small = bgr
        if w > self._search_width:
            scale = self._search_width / float(w)
            small = cv2.resize(bgr, (self._search_width, max(1, int(h * scale))))

        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gate_center = self._state.last_xy

        hit = self._search_dark_phone(gray, gate_center, scale)
        if hit is None:
            hit = self._search_bright_screen(small, gate_center, scale)
        if hit is None:
            return self._state.coast_or_empty(timestamp_ms, w, h)

        score, cx, cy, x, y, bw, bh = hit
        # Map search coords → full-frame pixels
        inv = 1.0 / scale
        cx, cy = cx * inv, cy * inv
        x, y, bw, bh = x * inv, y * inv, bw * inv, bh * inv

        sm = self._state.mark_seen((cx, cy), alpha=0.45)
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


class FaceTracker:
    """
    OpenCV YuNet face lock — reliable “something is tracked” demo.

    Sit in front of the laptop camera; a green box should lock on your face
    and print live (x, y). No phone / tape required.
    """

    def __init__(self, lost_timeout_s: float = 0.7, lock_radius_px: float = 220.0) -> None:
        if not hasattr(cv2, "FaceDetectorYN_create"):
            raise RuntimeError(
                "This OpenCV build has no FaceDetectorYN. "
                "Upgrade opencv-python to >=4.5 (or reinstall in your venv)."
            )
        model = ensure_face_model()
        # Input size is updated per-frame in update().
        self._detector = cv2.FaceDetectorYN_create(str(model), "", (320, 320), 0.7, 0.3, 5000)
        self._state = _LockState(lost_timeout_s)
        self._lock_radius_px = lock_radius_px
        self._last_size: Optional[tuple[int, int]] = None

    def close(self) -> None:
        return

    def reset(self) -> None:
        self._state.had_lock = False
        self._state.last_seen_s = None
        self._state.clear_smooth()

    def update(self, bgr: np.ndarray, timestamp_ms: float) -> TrackEstimate:
        h, w = bgr.shape[:2]
        size = (w, h)
        if size != self._last_size:
            self._detector.setInputSize(size)
            self._last_size = size

        _retval, faces = self._detector.detect(bgr)
        # faces: Nx15 array or None — [x,y,w,h, score, …landmarks]
        if faces is None or len(faces) == 0:
            return self._state.coast_or_empty(timestamp_ms, w, h)

        gate_center = self._state.last_xy
        best = None
        best_score = -1.0
        for row in faces:
            x, y, bw, bh = float(row[0]), float(row[1]), float(row[2]), float(row[3])
            det_score = float(row[4]) if len(row) > 4 else 0.8
            if bw < 24 or bh < 24:
                continue
            cx = x + bw * 0.5
            cy = y + bh * 0.5
            area = bw * bh
            if gate_center is not None:
                dist = float(np.hypot(cx - gate_center[0], cy - gate_center[1]))
                if dist > self._lock_radius_px * 1.5:
                    continue
                gate_bonus = float(np.clip(1.0 - dist / self._lock_radius_px, 0.0, 1.0))
            else:
                gate_bonus = 0.0
            size_sc = float(np.clip(area / (0.12 * h * w), 0.0, 1.0))
            center_sc = float(np.clip(1.0 - abs(cx - w * 0.5) / (w * 0.5), 0.0, 1.0))
            score = 0.55 * det_score + 0.20 * size_sc + 0.15 * center_sc + 0.25 * gate_bonus
            if score > best_score:
                best_score = score
                best = (cx, cy, x, y, bw, bh, area)

        if best is None:
            return self._state.coast_or_empty(timestamp_ms, w, h)

        cx, cy, x, y, bw, bh, area = best
        sm = self._state.mark_seen((cx, cy), alpha=0.4)
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
            conf=float(np.clip(best_score, 0.0, 1.0)),
            box=(x, y, bw, bh),
            range_proxy=area,
        )


class MotionTracker:
    """
    Largest moving blob — wave your hand and it locks.

    Useful when face/phone detectors struggle (backlight, distance).
    """

    def __init__(
        self,
        lost_timeout_s: float = 0.6,
        lock_radius_px: float = 200.0,
        min_area_frac: float = 0.008,
    ) -> None:
        self._state = _LockState(lost_timeout_s)
        self._lock_radius_px = lock_radius_px
        self._min_area_frac = min_area_frac
        self._prev_gray: Optional[np.ndarray] = None

    def close(self) -> None:
        return

    def reset(self) -> None:
        self._state.had_lock = False
        self._state.last_seen_s = None
        self._state.clear_smooth()
        self._prev_gray = None

    def update(self, bgr: np.ndarray, timestamp_ms: float) -> TrackEstimate:
        h, w = bgr.shape[:2]
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (9, 9), 0)

        if self._prev_gray is None:
            self._prev_gray = gray
            return self._state.coast_or_empty(timestamp_ms, w, h)

        diff = cv2.absdiff(self._prev_gray, gray)
        self._prev_gray = gray
        _, mask = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))

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
        min_area = self._min_area_frac * h * w
        best = None
        best_area = 0.0
        for c in cnts:
            area = float(cv2.contourArea(c))
            if area < min_area or area > 0.45 * h * w:
                continue
            if area > best_area:
                x, y, bw, bh = cv2.boundingRect(c)
                best_area = area
                best = (x + bw * 0.5, y + bh * 0.5, float(x), float(y), float(bw), float(bh), area)

        if best is None:
            return self._state.coast_or_empty(timestamp_ms, w, h)

        cx, cy, x, y, bw, bh, area = best
        sm = self._state.mark_seen((cx, cy), alpha=0.35)
        if sm is None:
            return self._state.coast_or_empty(timestamp_ms, w, h)
        sm_x, sm_y = sm
        conf = float(np.clip(area / (0.08 * h * w), 0.2, 1.0))
        return _tracking_estimate(
            timestamp_ms,
            self._state.track_id,
            sm_x,
            sm_y,
            w,
            h,
            conf=conf,
            box=(x, y, bw, bh),
            range_proxy=area,
        )


def make_tracker(
    mode: str,
    hue: int = 90,
    lost_timeout_s: float = 0.75,
    weights: Optional[str] = None,
    accept_labels: Optional[list[str]] = None,
):
    """
    mode:
      hand   — OpenCV Zoo palm+handpose → index fingertip
      yolo   — YOLOv8 pose wrist fallback
      drone  — class-aware: YOLO-World or fine-tuned drone weights
      bottle — desk demo: lock water bottle / cup (easy to wave for guide)
      skin / finger / face / motion / phone / two / color — legacy
    """
    if mode == "hand":
        from hand_landmark import HandLandmarkTracker

        return HandLandmarkTracker(lost_timeout_s=lost_timeout_s)
    if mode == "drone":
        from drone_detector import DroneObjectTracker

        return DroneObjectTracker(
            lost_timeout_s=lost_timeout_s,
            weights=weights,
            target_labels=accept_labels,
        )
    if mode == "bottle":
        from detect_result import BOTTLE_DEMO_LABELS
        from drone_detector import DroneObjectTracker

        labels = accept_labels or list(BOTTLE_DEMO_LABELS)
        # Easier lock for desk demo; person still rejected.
        return DroneObjectTracker(
            lost_timeout_s=lost_timeout_s,
            weights=weights,
            conf=0.20,
            min_lock_conf=0.22,
            acquire_hits=2,
            target_labels=labels,
            distractor_labels=("person", "hand", "phone", "book", "chair", "car"),
        )
    if mode == "yolo":
        from yolo_tracker import YoloHandTracker

        return YoloHandTracker(lost_timeout_s=lost_timeout_s)
    if mode == "finger":
        try:
            tracker = FingerTracker(lost_timeout_s=lost_timeout_s)
            print("backend: MediaPipe index fingertip", flush=True)
            return tracker
        except Exception as exc:  # noqa: BLE001
            print(
                f"pip mediapipe unavailable ({exc!r}); using OpenCV Zoo hand landmarks.",
                flush=True,
            )
            from hand_landmark import HandLandmarkTracker

            return HandLandmarkTracker(lost_timeout_s=lost_timeout_s)
    if mode == "skin":
        return SkinFingerTracker(lost_timeout_s=lost_timeout_s)
    if mode == "face":
        return FaceTracker(lost_timeout_s=lost_timeout_s)
    if mode == "motion":
        return MotionTracker(lost_timeout_s=lost_timeout_s)
    if mode == "phone":
        return PhoneTracker(lost_timeout_s=lost_timeout_s)
    if mode == "color":
        return ColorBlobTracker(hue=hue, lost_timeout_s=lost_timeout_s)
    if mode == "two":
        return TwoFingerTracker(lost_timeout_s=lost_timeout_s)
    raise ValueError(f"Unknown tracker mode: {mode!r}")
