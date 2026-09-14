"""Capture runner: CameraFrame stream + FPS / latency overlay (M2.1)."""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional

import cv2

from source import FrameSource, make_source


@dataclass
class CaptureStats:
    """Rolling FPS and end-to-end latency (capture stamp → now)."""

    window_s: float = 2.0
    _times: Deque[float] = field(default_factory=deque)
    _latencies_ms: Deque[float] = field(default_factory=deque)
    frames: int = 0

    def observe(self, frame_timestamp_ms: float, now_s: Optional[float] = None) -> None:
        now = time.perf_counter() if now_s is None else now_s
        now_ms = time.time() * 1000.0
        latency = max(0.0, now_ms - frame_timestamp_ms)
        self._times.append(now)
        self._latencies_ms.append(latency)
        self.frames += 1
        cutoff = now - self.window_s
        while self._times and self._times[0] < cutoff:
            self._times.popleft()
            self._latencies_ms.popleft()

    @property
    def fps(self) -> float:
        if len(self._times) < 2:
            return 0.0
        dt = self._times[-1] - self._times[0]
        if dt <= 0:
            return 0.0
        return (len(self._times) - 1) / dt

    @property
    def latency_ms(self) -> float:
        if not self._latencies_ms:
            return 0.0
        return float(statistics.fmean(self._latencies_ms))


def draw_overlay(image, stats: CaptureStats, frame_id: int, source_label: str):
    """HUD: FPS, latency, frame id — mutates BGR image."""
    lines = [
        f"HAYLON capture  src={source_label}",
        f"fps {stats.fps:5.1f}   latency {stats.latency_ms:5.1f} ms",
        f"frame {frame_id}",
    ]
    y = 28
    for line in lines:
        cv2.putText(
            image,
            line,
            (12, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 0, 0),
            4,
            cv2.LINE_AA,
        )
        cv2.putText(
            image,
            line,
            (12, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (210, 255, 80),
            2,
            cv2.LINE_AA,
        )
        y += 28
    return image


def run_capture(
    source: FrameSource,
    *,
    source_label: str,
    duration_s: float,
    headless: bool,
    out_path: Optional[str],
    min_fps: float,
) -> int:
    stats = CaptureStats()
    writer = None
    fps_samples: list[float] = []
    t_start = time.perf_counter()
    last_report = t_start

    with source:
        while True:
            elapsed = time.perf_counter() - t_start
            if duration_s > 0 and elapsed >= duration_s:
                break

            frame = source.read()
            if frame is None:
                print("Capture ended (no more frames).", file=sys.stderr)
                break

            stats.observe(frame.timestamp_ms)
            image = frame.data.copy()
            draw_overlay(image, stats, frame.frame_id, source_label)

            if out_path and writer is None:
                # Prefer H.264 when available — mp4v often fails in browsers.
                fourcc = cv2.VideoWriter_fourcc(*"avc1")
                writer = cv2.VideoWriter(out_path, fourcc, 30.0, (frame.width, frame.height))
                if not writer.isOpened():
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    writer = cv2.VideoWriter(out_path, fourcc, 30.0, (frame.width, frame.height))
                if not writer.isOpened():
                    raise RuntimeError(f"Could not open VideoWriter: {out_path}")

            if writer is not None:
                writer.write(image)

            if not headless:
                cv2.imshow("haylon-capture", image)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            now = time.perf_counter()
            # Collect FPS after warmup (1s)
            if elapsed > 1.0:
                fps_samples.append(stats.fps)
            if now - last_report >= 1.0:
                print(
                    f"t={elapsed:5.1f}s  frames={stats.frames:5d}  "
                    f"fps={stats.fps:5.1f}  latency_ms={stats.latency_ms:5.1f}",
                    flush=True,
                )
                last_report = now

    if writer is not None:
        writer.release()
    if not headless:
        cv2.destroyAllWindows()

    # Interactive mode (--duration 0): success if we showed any frames.
    if duration_s <= 0:
        if stats.frames > 0:
            print(f"Stopped. frames={stats.frames}  last_fps={stats.fps:.1f}")
            return 0
        print("FAIL: camera produced no frames.", file=sys.stderr)
        return 1

    if not fps_samples:
        print("FAIL: no FPS samples (duration too short?)", file=sys.stderr)
        return 1

    # Use median of post-warmup rolling FPS as pass metric
    median_fps = float(statistics.median(fps_samples))
    print(f"\nResult: median_fps={median_fps:.1f}  frames={stats.frames}  min_required={min_fps}")
    if median_fps < min_fps:
        print("FAIL: below min FPS", file=sys.stderr)
        return 1
    print("PASS")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Haylon host Capture (M2.1)")
    p.add_argument(
        "--source",
        default="synthetic",
        help="synthetic | webcam index (0) | path/to/video.mp4",
    )
    p.add_argument("--duration", type=float, default=60.0, help="Seconds to run (0 = until quit)")
    p.add_argument("--headless", action="store_true", help="No GUI window (CI / cloud)")
    p.add_argument("--out", default=None, help="Optional annotated mp4 path")
    p.add_argument("--min-fps", type=float, default=15.0, help="Pass/fail FPS floor")
    p.add_argument("--no-loop", action="store_true", help="Do not loop video files")
    args = p.parse_args(argv)

    source = make_source(args.source, loop_file=not args.no_loop)
    return run_capture(
        source,
        source_label=args.source,
        duration_s=args.duration,
        headless=args.headless,
        out_path=args.out,
        min_fps=args.min_fps,
    )


if __name__ == "__main__":
    raise SystemExit(main())
