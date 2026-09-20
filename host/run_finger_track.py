"""Finger track demo — live coordinates from a camera crosshair origin.

Hold up your index finger. The HUD shows:
  - image pixels (top-left origin)
  - offset from image-center origin (+X right, +Y up)
  - normalized offset and bearing
"""

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


def _draw_origin_axes(image, origin, axis_len: int = 70) -> None:
    """Draw the guidance frame at the image-center origin."""
    ox, oy = int(origin[0]), int(origin[1])
    # +X right (green-ish)
    cv2.arrowedLine(image, (ox, oy), (ox + axis_len, oy), (80, 220, 80), 2, tipLength=0.25)
    cv2.putText(image, "+X", (ox + axis_len + 4, oy + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (80, 220, 80), 1, cv2.LINE_AA)
    # +Y up (cyan) — image y decreases upward
    cv2.arrowedLine(image, (ox, oy), (ox, oy - axis_len), (220, 200, 40), 2, tipLength=0.25)
    cv2.putText(image, "+Y", (ox + 6, oy - axis_len - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 200, 40), 1, cv2.LINE_AA)
    cv2.drawMarker(image, (ox, oy), (255, 255, 255), markerType=cv2.MARKER_CROSS, markerSize=14, thickness=2)
    cv2.putText(image, "O", (ox + 8, oy + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1, cv2.LINE_AA)


def draw_track_hud(image, stats: CaptureStats, track, source_label: str, mode: str) -> None:
    h, w = image.shape[:2]
    origin = (w * 0.5, h * 0.5)
    _draw_origin_axes(image, origin)

    status = track.status
    color = {
        "TRACKING": (80, 255, 120),
        "SEARCHING": (0, 200, 255),
        "LOST": (60, 60, 255),
    }.get(status, (200, 200, 200))

    if track.bbox is not None:
        x, y, bw, bh = map(int, (track.bbox.x, track.bbox.y, track.bbox.w, track.bbox.h))
        cv2.rectangle(image, (x, y), (x + bw, y + bh), color, 2)

    fc = optional_frame_coords(track.target_xy, w, h)
    if track.offset_px is not None and track.origin_xy is not None and track.target_xy is not None:
        # Prefer contract fields already on the estimate
        ox, oy = track.origin_xy
        dx, dy = track.offset_px
        nx, ny = track.offset_norm if track.offset_norm else (0.0, 0.0)
        tx, ty = track.target_xy
    elif fc is not None:
        ox, oy = fc.origin_xy
        dx, dy = fc.offset_px
        nx, ny = fc.offset_norm
        tx, ty = fc.image_xy
    else:
        ox = oy = dx = dy = nx = ny = tx = ty = None

    if tx is not None:
        cv2.circle(image, (int(tx), int(ty)), 8, color, 2)
        cv2.line(image, (int(ox), int(oy)), (int(tx), int(ty)), color, 1)
        image_line = f"image   x={tx:.0f}  y={ty:.0f}   (O=top-left)"
        origin_line = f"origin  x={ox:.0f}  y={oy:.0f}   (crosshair)"
        offset_line = f"frame   dx={dx:+.0f}  dy={dy:+.0f} px  (+X right +Y up)"
        norm_line = f"norm    nx={nx:+.2f}  ny={ny:+.2f}"
    else:
        image_line = "image   —"
        origin_line = f"origin  x={w*0.5:.0f}  y={h*0.5:.0f}   (crosshair)"
        offset_line = "frame   —"
        norm_line = "norm    —"

    if getattr(track, "tips_xy", None):
        for tip in track.tips_xy:
            cv2.circle(image, (int(tip[0]), int(tip[1])), 6, (0, 255, 255), 2)

    track_id = track.track_id if track.track_id is not None else "—"
    bearing_line = "bearing —"
    if track.bearing_rad is not None:
        yaw, pitch = track.bearing_rad
        bearing_line = f"bearing yaw={yaw:+.3f}  pitch={pitch:+.3f} rad"

    lines = [
        f"HAYLON  finger-track  mode={mode}  cam={source_label}",
        f"{status}   conf={track.confidence:.2f}   id={track_id}",
        origin_line,
        image_line,
        offset_line,
        norm_line,
        bearing_line,
        f"fps={stats.fps:.1f}   lag={stats.latency_ms:.1f}ms",
    ]

    pad_x, pad_y = 14, 12
    line_h = 26
    panel_w = min(w - 16, 560)
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
            0.52,
            color,
            1,
            cv2.LINE_AA,
        )
        y += line_h


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Haylon finger track — index tip with center-origin coordinates"
    )
    p.add_argument("--source", default="0", help="0=webcam | synthetic | path/to/video")
    p.add_argument("--duration", type=float, default=0.0, help="Seconds (0 = until q)")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--out", default=None, help="Optional annotated mp4")
    p.add_argument(
        "--mode",
        choices=("finger", "skin", "face", "motion", "phone", "two", "color"),
        default="finger",
        help="finger=MediaPipe index (default, skin fallback); skin/face/motion/…",
    )
    p.add_argument("--hue", type=int, default=90, help="HSV hue for --mode color")
    p.add_argument("--lost-timeout", type=float, default=0.75)
    args = p.parse_args(argv)

    print(
        f"Tracking mode={args.mode!r}  source={args.source!r}\n"
        "  Hold up your INDEX FINGER toward the camera.\n"
        "  Origin O = image center (crosshair). +X right, +Y up.\n"
        "  Look for TRACKING + frame dx/dy.  q=quit  r=reset",
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
                    cv2.imshow("haylon-finger-track", image)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        break
                    if key == ord("r"):
                        tracker.reset()
                        print("reset: unlocked — searching again", flush=True)

                now = time.perf_counter()
                if now - last_report >= 1.0:
                    if track.target_xy and track.offset_px:
                        tx, ty = track.target_xy
                        dx, dy = track.offset_px
                        nx, ny = track.offset_norm or (0.0, 0.0)
                        xy_s = (
                            f"img=({tx:.0f},{ty:.0f})  "
                            f"frame=({dx:+.0f},{dy:+.0f})px  "
                            f"norm=({nx:+.2f},{ny:+.2f})"
                        )
                    else:
                        xy_s = "—"
                    print(
                        f"t={elapsed:5.1f}s  status={track.status:9s}  {xy_s}  "
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
