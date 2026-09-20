"""M3.4 — class-aware detect: drone vs distractors.

Shows every YOLO-World box. Only drone-family labels become TRACKING;
person / bottle / hand / etc. are drawn as REJECT and never locked.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

import cv2

from drone_detector import DroneObjectTracker
from run_capture import CaptureStats
from run_finger_track import _draw_crosshair, _offset_words
from source import make_source


def draw_detect_hud(image, stats: CaptureStats, track, tracker: DroneObjectTracker) -> None:
    h, w = image.shape[:2]
    _draw_crosshair(image, (w * 0.5, h * 0.5))

    for det in tracker.last_detections:
        x, y, bw, bh = map(int, (det.bbox.x, det.bbox.y, det.bbox.w, det.bbox.h))
        color = (80, 255, 120) if det.accepted else (80, 80, 255)
        cv2.rectangle(image, (x, y), (x + bw, y + bh), color, 2)
        tag = det.label if det.accepted else f"reject:{det.label}"
        cv2.putText(
            image,
            f"{tag} {det.confidence:.2f}",
            (x, max(18, y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
            cv2.LINE_AA,
        )

    status = track.status
    color = {
        "TRACKING": (80, 255, 120),
        "SEARCHING": (0, 200, 255),
        "LOST": (60, 60, 255),
    }.get(status, (200, 200, 200))

    if track.target_xy is not None and track.status == "TRACKING":
        tx, ty = map(int, track.target_xy)
        cv2.circle(image, (tx, ty), 8, color, 2)
        where = _offset_words(*(track.offset_px or (0.0, 0.0)))
    else:
        where = "no drone"

    label = track.class_label or "—"
    n_rej = sum(1 for d in tracker.last_detections if not d.accepted)
    n_ok = sum(1 for d in tracker.last_detections if d.accepted)
    lines = [
        status,
        f"class  {label}",
        where,
        f"boxes  ok={n_ok}  reject={n_rej}",
        f"{stats.fps:.0f} fps",
    ]
    pad_x, pad_y = 12, 10
    line_h = 28
    panel_w = min(w - 16, 340)
    panel_h = pad_y * 2 + line_h * len(lines)
    overlay = image.copy()
    cv2.rectangle(overlay, (8, 8), (8 + panel_w, 8 + panel_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, image, 0.45, 0, image)
    y = 8 + pad_y + 20
    for i, line in enumerate(lines):
        cv2.putText(
            image,
            line,
            (8 + pad_x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65 if i == 0 else 0.5,
            color if i == 0 else (220, 220, 220),
            2 if i == 0 else 1,
            cv2.LINE_AA,
        )
        y += line_h


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Haylon class-aware drone detect (M3.4)")
    p.add_argument("--source", default="0", help="Camera index, video path, or image")
    p.add_argument("--duration", type=float, default=0.0)
    p.add_argument("--headless", action="store_true")
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument(
        "--accept",
        default="",
        help="Comma list overriding accept labels (default drone,quadcopter,UAV,…)",
    )
    p.add_argument("--out-frame", default="", help="Optional path to save last annotated frame")
    args = p.parse_args(argv)

    targets = None
    if args.accept.strip():
        targets = [s.strip() for s in args.accept.split(",") if s.strip()]

    print(
        "detect  class-aware drone lock\n"
        "  Green box = accepted (drone family). Red = reject (person/etc.).\n"
        "  q=quit  r=reset",
        flush=True,
    )

    source = make_source(args.source, loop_file=True)
    tracker = DroneObjectTracker(conf=args.conf, target_labels=targets)
    stats = CaptureStats()
    t0 = time.perf_counter()
    last_report = t0
    locked = 0
    last_image = None

    try:
        with source:
            while True:
                elapsed = time.perf_counter() - t0
                if args.duration > 0 and elapsed >= args.duration:
                    break

                frame = source.read()
                if frame is None:
                    break

                stats.observe(frame.timestamp_ms)
                track = tracker.update(frame.data, frame.timestamp_ms)
                if track.status == "TRACKING" and track.class_label:
                    locked += 1

                image = frame.data.copy()
                draw_detect_hud(image, stats, track, tracker)
                last_image = image

                if not args.headless:
                    cv2.imshow("haylon-detect", image)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        break
                    if key == ord("r"):
                        tracker.reset()

                now = time.perf_counter()
                if now - last_report >= 1.0:
                    labs = ", ".join(
                        f"{'OK' if d.accepted else 'NO'}:{d.label}"
                        for d in tracker.last_detections[:6]
                    ) or "—"
                    print(
                        f"t={elapsed:5.1f}s  {track.status:9s}  "
                        f"class={track.class_label or '—':12s}  "
                        f"[{labs}]  fps={stats.fps:5.1f}",
                        flush=True,
                    )
                    last_report = now
    finally:
        tracker.close()
        if not args.headless:
            cv2.destroyAllWindows()
        if args.out_frame and last_image is not None:
            cv2.imwrite(args.out_frame, last_image)
            print(f"Wrote {args.out_frame}", flush=True)

    print(f"\nDone. frames={stats.frames}  locked_frames={locked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
