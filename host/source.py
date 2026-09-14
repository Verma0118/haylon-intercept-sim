"""Video sources for Capture: webcam, video file, or synthetic frames."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from camera_frame import CameraFrame


class FrameSource(ABC):
    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def read(self) -> Optional[CameraFrame]:
        """Return next CameraFrame, or None on end/failure."""

    @abstractmethod
    def close(self) -> None: ...

    def __enter__(self) -> "FrameSource":
        self.open()
        return self

    def __exit__(self, *args) -> None:
        self.close()


class OpenCvSource(FrameSource):
    """Webcam index or video file path via OpenCV VideoCapture."""

    def __init__(self, source: str | int, loop_file: bool = True) -> None:
        self._source = source
        self._loop_file = loop_file
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame_id = 0
        self._is_file = isinstance(source, str)

    def open(self) -> None:
        self._cap = cv2.VideoCapture(self._source)
        if not self._cap.isOpened():
            raise RuntimeError(f"Could not open capture source: {self._source!r}")

    def read(self) -> Optional[CameraFrame]:
        if self._cap is None:
            raise RuntimeError("Source not open")
        ok, image = self._cap.read()
        if not ok or image is None:
            if self._is_file and self._loop_file:
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, image = self._cap.read()
                if not ok or image is None:
                    return None
            else:
                return None

        # timestamp_ms = host receive/capture time (contracts.md)
        timestamp_ms = time.time() * 1000.0
        h, w = image.shape[:2]
        frame = CameraFrame(
            frame_id=self._frame_id,
            timestamp_ms=timestamp_ms,
            width=int(w),
            height=int(h),
            format="bgr",
            data=image,
        )
        self._frame_id += 1
        return frame

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


class SyntheticSource(FrameSource):
    """Moving color bar — no camera required (CI / cloud agents)."""

    def __init__(
        self,
        width: int = 640,
        height: int = 360,
        fps: float = 30.0,
    ) -> None:
        self._width = width
        self._height = height
        self._period = 1.0 / fps
        self._frame_id = 0
        self._t0 = 0.0
        self._next_due = 0.0

    def open(self) -> None:
        self._t0 = time.perf_counter()
        self._next_due = self._t0

    def read(self) -> Optional[CameraFrame]:
        now = time.perf_counter()
        # Pace to target fps so latency/FPS metrics are meaningful
        if now < self._next_due:
            time.sleep(self._next_due - now)
        self._next_due += self._period

        t = time.perf_counter() - self._t0
        img = np.zeros((self._height, self._width, 3), dtype=np.uint8)
        # Sweeping vertical bar + timestamp text area
        x = int((t * 120) % self._width)
        cv2.rectangle(img, (x, 0), (min(x + 40, self._width - 1), self._height - 1), (40, 200, 80), -1)
        cv2.rectangle(img, (0, 0), (self._width - 1, self._height - 1), (80, 80, 80), 2)

        timestamp_ms = time.time() * 1000.0
        frame = CameraFrame(
            frame_id=self._frame_id,
            timestamp_ms=timestamp_ms,
            width=self._width,
            height=self._height,
            format="bgr",
            data=img,
        )
        self._frame_id += 1
        return frame

    def close(self) -> None:
        return


def make_source(spec: str, loop_file: bool = True) -> FrameSource:
    """
    Parse CLI source spec:
      synthetic       — generated frames
      0 / 1 / ...     — webcam index
      path/to/file    — video file
    """
    if spec == "synthetic":
        return SyntheticSource()
    if spec.isdigit():
        return OpenCvSource(int(spec), loop_file=False)
    path = Path(spec)
    if not path.exists():
        raise FileNotFoundError(f"Video file not found: {spec}")
    return OpenCvSource(str(path), loop_file=loop_file)
