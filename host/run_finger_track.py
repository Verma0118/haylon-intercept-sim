"""Finger / hand track demo — simple HUD + center-origin coords."""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

import cv2

from finger_tracker import make_tracker
from frame_coords import optional_frame_coords
from run_capture import CaptureStats
from source import make_source


def _draw_crosshair(image, origin) -> None:
    ox, oy = int(origin[0]), int(origin[1])
    cv2.drawMarker(
        image, (ox, oy), (220, 220, 220), markerType=cv2.MARKER_CROSS, markerSize=16, thickness=1
    )


def _offset_words(dx: float, dy: float, dead: float = 12.0) -> str:
    """Human-readable offset from center (+X right, +Y up)."""
    if abs(dx) < dead and abs(dy) < dead:
        return "centered"
    parts = []
    if abs(dx) >= dead:
        parts.append(f"{'right' if dx > 0 else 'left'} {abs(dx):.0f}")
    if abs(dy) >= dead:
        parts.append(f"{'up' if dy > 0 else 'down'} {abs(dy):.0f}")
    return "  ".join(parts)


def draw_track_hud(image, stats: CaptureStats, track, source_label: str, mode: str) -> None:
    h, w = image.shape[:2]
    origin = (w * 0.5, h * 0.5)
    _draw_crosshair(image, origin)

    status = track.status
    color = {
        "TRACKING": (80, 255, 120),
        "SEARCHING": (0, 200, 255),
        "LOST": (60, 60, 255),
    }.get(status, (200, 200, 200))

    if track.bbox is not None:
        x, y, bw, bh = map(int, (track.bbox.x, track.bbox.y, track.bbox.w, track.bbox.h))
        cv2.rectangle(image, (x, y), (x + bw, y + bh), color, 2)

    tx = ty = dx = dy = None
    if track.target_xy is not None:
        if track.offset_px is not None:
            dx, dy = track.offset_px
            tx, ty = track.target_xy
            ox, oy = track.origin_xy or origin
        else:
            fc = optional_frame_coords(track.target_xy, w, h)
            if fc is not None:
                dx, dy = fc.offset_px
                tx, ty = fc.image_xy
                ox, oy = fc.origin_xy
            else:
                ox, oy = origin
        cv2.circle(image, (int(tx), int(ty)), 8, color, 2)
        cv2.line(image, (int(ox), int(oy)), (int(tx), int(ty)), color, 1)
        where = _offset_words(dx, dy)
    else:
        where = "looking…"

    # Keep the panel short — status + where + fps only
    lines = [
        status,
        where,
        f"{stats.fps:.0f} fps",
    ]

    pad_x, pad_y = 12, 10
    line_h = 32
    panel_w = min(w - 16, 280)
    panel_h = pad_y * 2 + line_h * len(lines)
    overlay = image.copy()
    cv2.rectangle(overlay, (8, 8), (8 + panel_w, 8 + panel_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, image, 0.45, 0, image)

    y = 8 + pad_y + 22
    sizes = (0.7, 0.55, 0.45)
    for i, line in enumerate(lines):
        cv2.putText(
            image,
            line,
            (8 + pad_x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            sizes[i],
            color if i == 0 else (220, 220, 220),
            2 if i == 0 else 1,
            cv2.LINE_AA,
        )
        y += line_h


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Haylon hand / finger track")
    p.add_argument("--source", default="0", help="0=webcam | synthetic | path/to/video")
    p.add_argument("--duration", type=float, default=0.0, help="Seconds (0 = until q)")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--out", default=None, help="Optional annotated mp4")
    p.add_argument(
        "--mode",
        choices=("hand", "yolo", "skin", "finger", "face", "motion", "phone", "two", "color"),
        default="hand",
        help="hand=OpenCV Zoo index tip (default); yolo=YOLOv8 pose",
    )
    p.add_argument("--hue", type=int, default=90, help="HSV hue for --mode color")
    p.add_argument("--lost-timeout", type=float, default=0.75)
    args = p.parse_args(argv)

    print(
        f"mode={args.mode}  cam={args.source}\n"
        "  Hold your hand toward the camera.  q=quit  r=reset",
        flush=True,
    )
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
                draw_track_hud(image, stats, track, args.source, args.mode)

                if args.out and writer is None:
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
                    cv2.imshow("haylon-track", image)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        break
                    if key == ord("r"):
                        tracker.reset()
                        print("reset", flush=True)

                now = time.perf_counter()
                if now - last_report >= 1.0:
                    if track.offset_px:
                        dx, dy = track.offset_px
                        where = _offset_words(dx, dy)
                    else:
                        where = "—"
                    print(
                        f"t={elapsed:5.1f}s  {track.status:9s}  {where:20s}  "
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

    print(f"\nDone. frames={stats.frames}  tracking={tracking_frames}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
