"""OpenCV Zoo MediaPipe-style hand landmarks (index tip) via cv2.dnn.

Uses models from https://github.com/opencv/opencv_zoo — no pip `mediapipe`
package (that often breaks on Mac Python 3.9).
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from finger_tracker import _LockState, _tracking_estimate
from track_estimate import TrackEstimate

_MODELS = Path(__file__).resolve().parent / "models"
_ZOO = Path(__file__).resolve().parent / "third_party" / "opencv_zoo"
_PALM_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "palm_detection_mediapipe/palm_detection_mediapipe_2023feb.onnx"
)
_HAND_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "handpose_estimation_mediapipe/handpose_estimation_mediapipe_2023feb.onnx"
)
_PALM_PATH = _MODELS / "palm_detection_mediapipe_2023feb.onnx"
_HAND_PATH = _MODELS / "handpose_estimation_mediapipe_2023feb.onnx"

# MediaPipe hand landmark index tip
_INDEX_TIP = 8


def _download(url: str, path: Path, min_bytes: int = 100_000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.stat().st_size >= min_bytes:
        return path
    print(f"Downloading {path.name} …", flush=True)
    urllib.request.urlretrieve(url, path)
    if not path.is_file() or path.stat().st_size < min_bytes:
        raise RuntimeError(f"Download failed or too small: {path}")
    return path


def ensure_hand_models() -> tuple[Path, Path]:
    return _download(_PALM_URL, _PALM_PATH, 1_000_000), _download(_HAND_URL, _HAND_PATH, 1_000_000)


class HandLandmarkTracker:
    """
    Accurate index-fingertip lock using OpenCV Zoo palm + hand-pose ONNX.

    Hold your hand toward the camera (palm or back). Green marker tracks
    landmark 8 (index fingertip).
    """

    def __init__(self, lost_timeout_s: float = 1.0, conf_threshold: float = 0.6) -> None:
        if not hasattr(cv2, "dnn"):
            raise RuntimeError(
                "This cv2 build has no cv2.dnn (needed for hand landmarks).\n"
                "Your OpenCV install is broken/headless. Fix with:\n"
                "  python -m pip uninstall -y opencv-python opencv-python-headless opencv-contrib-python\n"
                "  python -m pip install --force-reinstall \"opencv-python==4.10.0.84\"\n"
                "  python -c \"import cv2; print(cv2.__version__, hasattr(cv2,'dnn'), hasattr(cv2,'imshow'))\"\n"
                "Expect: 4.10.0 True True"
            )
        if str(_ZOO) not in sys.path:
            sys.path.insert(0, str(_ZOO))
        from mp_handpose import MPHandPose  # type: ignore
        from mp_palmdet import MPPalmDet  # type: ignore

        palm_path, hand_path = ensure_hand_models()
        backend = cv2.dnn.DNN_BACKEND_OPENCV
        target = cv2.dnn.DNN_TARGET_CPU
        self._palm = MPPalmDet(
            modelPath=str(palm_path),
            nmsThreshold=0.3,
            scoreThreshold=0.5,
            topK=50,
            backendId=backend,
            targetId=target,
        )
        self._hand = MPHandPose(
            modelPath=str(hand_path),
            confThreshold=conf_threshold,
            backendId=backend,
            targetId=target,
        )
        self._state = _LockState(lost_timeout_s)
        self._state._acquire_hits = 1
        print("backend: OpenCV Zoo hand landmarks (index tip)", flush=True)

    def close(self) -> None:
        return

    def reset(self) -> None:
        self._state.had_lock = False
        self._state.last_seen_s = None
        self._state.clear_smooth()

    def update(self, bgr: np.ndarray, timestamp_ms: float) -> TrackEstimate:
        h, w = bgr.shape[:2]
        palms = self._palm.infer(bgr)
        best = None
        best_conf = -1.0

        for palm in palms:
            hand = self._hand.infer(bgr, palm)
            if hand is None:
                continue
            conf = float(hand[-1])
            if conf < best_conf:
                continue
            landmarks = hand[4:67].reshape(21, 3)
            tip = landmarks[_INDEX_TIP]
            tip_x, tip_y = float(tip[0]), float(tip[1])
            if not (0 <= tip_x < w and 0 <= tip_y < h):
                continue
            bbox = hand[0:4]
            x1, y1, x2, y2 = map(float, bbox)
            best_conf = conf
            best = (tip_x, tip_y, x1, y1, max(1.0, x2 - x1), max(1.0, y2 - y1), conf)

        if best is None:
            return self._state.coast_or_empty(timestamp_ms, w, h)

        tip_x, tip_y, x, y, bw, bh, conf = best
        sm = self._state.mark_seen((tip_x, tip_y), alpha=0.4)
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
            conf=float(np.clip(conf, 0.0, 1.0)),
            box=(x, y, bw, bh),
            range_proxy=bw * bh,
        )
