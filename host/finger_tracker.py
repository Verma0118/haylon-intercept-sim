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
    tips_xy: Optional[tuple[tuple[float, float], ...]] = None,
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
        tips_xy=tips_xy,
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
    Skin fingertip estimate tuned to avoid ceiling/face false locks:

    - reject tips near the image border (esp. top)
    - require a hand-like blob with tip *above* its own centroid
    - ignore face/torso-sized areas
    - spatial gate only after a *valid* lock; bad edge locks auto-clear
    - press `r` in the demo to force unlock/reacquire
    """

    def __init__(
        self,
        lost_timeout_s: float = 0.55,
        lock_radius_px: float = 100.0,
        min_area_frac: float = 0.003,
        max_area_frac: float = 0.08,
        edge_margin_frac: float = 0.10,
    ) -> None:
        self._state = _LockState(lost_timeout_s)
        self._lock_radius_px = lock_radius_px
        self._min_area_frac = min_area_frac
        self._max_area_frac = max_area_frac
        self._edge_margin_frac = edge_margin_frac

    def close(self) -> None:
        return

    def reset(self) -> None:
        """Force unlock so the tracker searches again (demo: press `r`)."""
        self._state.had_lock = False
        self._state.last_seen_s = None
        self._state.clear_smooth()

    def _near_border(self, x: float, y: float, w: int, h: int) -> bool:
        m = self._edge_margin_frac
        return (
            y < m * h
            or y > (1.0 - m) * h
            or x < m * w
            or x > (1.0 - m) * w
        )

    def update(self, bgr: np.ndarray, timestamp_ms: float) -> TrackEstimate:
        h, w = bgr.shape[:2]
        frame_area = float(h * w)

        ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
        mask = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))

        # Spatial gate only after a valid lock — and never for border false-locks.
        gate_center = self._state.last_xy
        if gate_center is not None and self._near_border(gate_center[0], gate_center[1], w, h):
            # Stuck on ceiling/edge → drop lock immediately and search whole frame.
            self.reset()
            gate_center = None

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
            if bh < 35 or bw < 10:
                continue
            aspect = bh / float(max(bw, 1))
            if aspect < 1.2:
                # Need a somewhat upright finger/hand silhouette
                continue

            m = cv2.moments(c)
            if m["m00"] <= 1e-3:
                continue
            cx = float(m["m10"] / m["m00"])
            cy = float(m["m01"] / m["m00"])

            # Hand should live in the middle band of the frame (not ceiling).
            if cy < 0.18 * h or cy > 0.92 * h:
                continue

            tip = c[c[:, :, 1].argmin()][0]
            tip_x, tip_y = float(tip[0]), float(tip[1])

            # Tip must be above the blob centroid (pointing up), and not on the border.
            if tip_y > cy - 8:
                continue
            if self._near_border(tip_x, tip_y, w, h):
                continue

            # Score relative to the *hand*, not the top of the screen.
            tip_above = float(np.clip((cy - tip_y) / max(bh, 1), 0.0, 1.0))
            aspect_score = float(np.clip((aspect - 1.2) / 2.0, 0.0, 1.0))
            size_score = 1.0 - abs(area - 0.025 * frame_area) / (0.025 * frame_area)
            size_score = float(np.clip(size_score, 0.0, 1.0))
            # Prefer targets nearer the frame center horizontally (person in front of cam)
            center_score = 1.0 - abs(cx - w * 0.5) / (w * 0.5)
            center_score = float(np.clip(center_score, 0.0, 1.0))

            gate_bonus = 0.0
            if gate_center is not None:
                dist = float(np.hypot(tip_x - gate_center[0], tip_y - gate_center[1]))
                gate_bonus = float(np.clip(1.0 - dist / self._lock_radius_px, 0.0, 1.0))

            score = (
                0.35 * tip_above
                + 0.25 * aspect_score
                + 0.15 * size_score
                + 0.15 * center_score
                + 0.30 * gate_bonus
            )
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

    def reset(self) -> None:
        self._state.had_lock = False
        self._state.last_seen_s = None
        self._state.clear_smooth()

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
            return self._state.empty(timestamp_ms)

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
            return self._state.empty(timestamp_ms)

        bx, by, bw, bh = cv2.boundingRect(hand)
        tips = self._fingertip_peaks(mask, hand, (bx, by, bw, bh))
        if len(tips) < 2:
            return self._state.empty(timestamp_ms)

        (x0, y0), (x1, y1) = tips[0], tips[1]
        mid_x = 0.5 * (x0 + x1)
        mid_y = 0.5 * (y0 + y1)
        sep = abs(x1 - x0)
        # Separation relative to the hand, not the full frame
        if sep < max(18.0, 0.15 * bw) or sep > 0.90 * bw:
            return self._state.empty(timestamp_ms)
        if mid_y < 0.04 * h:
            return self._state.empty(timestamp_ms)

        sm_x, sm_y = self._state.mark_seen((mid_x, mid_y), alpha=0.5)
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


def make_tracker(mode: str, hue: int = 90, lost_timeout_s: float = 0.75):
    """
    mode:
      two    — default; two-finger (peace-sign) lock
      skin   — single skin fingertip heuristics
      finger — MediaPipe index tip (falls back to two if native lib missing)
      color  — HSV blob (bright tape)
    """
    if mode == "color":
        return ColorBlobTracker(hue=hue, lost_timeout_s=lost_timeout_s)
    if mode == "skin":
        return SkinFingerTracker(lost_timeout_s=lost_timeout_s)
    if mode == "two":
        return TwoFingerTracker(lost_timeout_s=lost_timeout_s)
    if mode == "finger":
        try:
            return FingerTracker(lost_timeout_s=lost_timeout_s)
        except Exception as exc:  # noqa: BLE001
            print(
                f"MediaPipe finger mode unavailable ({exc!r}); falling back to two-finger mode.",
                flush=True,
            )
            return TwoFingerTracker(lost_timeout_s=lost_timeout_s)
    raise ValueError(f"Unknown tracker mode: {mode!r}")
