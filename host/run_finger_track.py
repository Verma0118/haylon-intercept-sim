"""Finger / target track demo — live coordinates on camera (M2.2).

Hold up your hand/finger. The HUD prints pixel (x, y), offset from center,
status, and a rough bearing — the rudimentary “where is the target?” signal.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

import cv2

from finger_tracker import make_tracker
from run_capture import CaptureStats
from source import make_source


def draw_track_hud(image, stats: CaptureStats, track, source_label: str) -> None:
    h, w = image.shape[:2]
    cv2.drawMarker(
        image,
        (w // 2, h // 2),
        (80, 80, 80),
        markerType=cv2.MARKER_CROSS,
        markerSize=18,
        thickness=1,
    )

    status = track.status
    color = {
        "TRACKING": (80, 255, 120),
        "SEARCHING": (0, 200, 255),
        "LOST": (60, 60, 255),
    }.get(status, (200, 200, 200))

    if track.bbox is not None:
        x, y, bw, bh = map(int, (track.bbox.x, track.bbox.y, track.bbox.w, track.bbox.h))
        cv2.rectangle(image, (x, y), (x + bw, y + bh), color, 2)

    if track.target_xy is not None:
        tx, ty = int(track.target_xy[0]), int(track.target_xy[1])
        cv2.circle(image, (tx, ty), 8, color, 2)
        cv2.line(image, (w // 2, h // 2), (tx, ty), color, 1)
        xy_line = f"xy      {tx}, {ty}"
        nx = (track.target_xy[0] - w * 0.5) / (w * 0.5)
        ny = (track.target_xy[1] - h * 0.5) / (h * 0.5)
        norm_line = f"offset  {nx:+.2f}, {ny:+.2f}"
    else:
        xy_line = "xy      —"
        norm_line = "offset  —"

    if getattr(track, "tips_xy", None):
        for tip in track.tips_xy:
            cv2.circle(image, (int(tip[0]), int(tip[1])), 6, (0, 255, 255), 2)
        if len(track.tips_xy) >= 2:
            cv2.line(
                image,
                (int(track.tips_xy[0][0]), int(track.tips_xy[0][1])),
                (int(track.tips_xy[1][0]), int(track.tips_xy[1][1])),
                (0, 255, 255),
                2,
            )

    track_id = track.track_id if track.track_id is not None else "—"
    bearing_line = "bearing —"
    if track.bearing_rad is not None:
        yaw, pitch = track.bearing_rad
        bearing_line = f"bearing {yaw:+.2f}, {pitch:+.2f} rad"

    lines = [
        f"HAYLON  phone-track  cam={source_label}",
        f"{status}   conf={track.confidence:.2f}   id={track_id}",
        xy_line,
        norm_line,
        bearing_line,
        f"fps={stats.fps:.1f}   lag={stats.latency_ms:.1f}ms",
    ]

    # Semi-transparent panel + single-stroke text (no thick outline smear)
    pad_x, pad_y = 14, 12
    line_h = 28
    panel_w = min(w - 16, 460)
    panel_h = pad_y * 2 + line_h * len(lines)
    overlay = image.copy()
    cv2.rectangle(overlay, (8, 8), (8 + panel_w, 8 + panel_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.62, image, 0.38, 0, image)

    y = 8 + pad_y + 18
    for line in lines:
        cv2.putText(
            image,
            line,
            (8 + pad_x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            1,
            cv2.LINE_AA,
        )
        y += line_h


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Haylon finger / target track (M2.2)")
    p.add_argument("--source", default="0", help="0=webcam | synthetic | path/to/video")
    p.add_argument("--duration", type=float, default=0.0, help="Seconds (0 = until q)")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--out", default=None, help="Optional annotated mp4")
    p.add_argument(
        "--mode",
        choices=("phone", "two", "skin", "finger", "color"),
        default="phone",
        help="phone=rectangular phone (default); two=peace-sign; skin/finger/color=fallbacks",
    )
    p.add_argument("--hue", type=int, default=90, help="HSV hue for --mode color")
    p.add_argument("--lost-timeout", type=float, default=0.75)
    args = p.parse_args(argv)

    source = make_source(args.source, loop_file=True)
    tracker = make_tracker(args.mode, hue=args.hue, lost_timeout_s=args.lost_timeout)
    stats = CaptureStats()
    writer = None
    t0 = time.perf_counter()
    last_report = t0
    tracking_frames = 0

    try:
        with source:
            while True:
                elapsed = time.perf_counter() - t0
                if args.duration > 0 and elapsed >= args.duration:
                    break

                frame = source.read()
                if frame is None:
                    print("Capture ended.", file=sys.stderr)
                    break

                stats.observe(frame.timestamp_ms)
                track = tracker.update(frame.data, frame.timestamp_ms)
                if track.status == "TRACKING":
                    tracking_frames += 1

                image = frame.data.copy()
                draw_track_hud(image, stats, track, args.source)

                if args.out and writer is None:
                    # mp4v is the portable default; avc1 often fails on headless Linux.
                    for tag in ("mp4v", "avc1"):
                        fourcc = cv2.VideoWriter_fourcc(*tag)
                        writer = cv2.VideoWriter(
                            args.out, fourcc, 30.0, (frame.width, frame.height)
                        )
                        if writer.isOpened():
                            break
                    if writer is None or not writer.isOpened():
                        print(f"Warning: could not open VideoWriter for {args.out}", file=sys.stderr)
                        writer = None

                if writer is not None:
                    writer.write(image)

                if not args.headless:
                    cv2.imshow("haylon-finger-track", image)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        break
                    if key == ord("r"):
                        tracker.reset()
                        print("reset: unlocked — searching again", flush=True)

                now = time.perf_counter()
                if now - last_report >= 1.0:
                    xy = track.target_xy
                    xy_s = f"({xy[0]:.0f},{xy[1]:.0f})" if xy else "—"
                    print(
                        f"t={elapsed:5.1f}s  status={track.status:9s}  xy={xy_s:>12s}  "
                        f"fps={stats.fps:5.1f}",
                        flush=True,
                    )
                    last_report = now
    finally:
        tracker.close()
        if writer is not None:
            writer.release()
        if not args.headless:
            cv2.destroyAllWindows()

    print(f"\nDone. frames={stats.frames}  tracking_frames={tracking_frames}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
