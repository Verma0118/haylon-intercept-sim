"""M3.4+ — class-aware detect with operator HUD telemetry.

Shows every YOLO-World box. Only drone-family labels become TRACKING;
person / bottle / hand / etc. are drawn as REJECT and never locked.

HUD prioritizes numbers you need to debug the lock: class/conf, offset,
range proxy, infer latency, reject top hit, lock age.
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


def _fmt_offset(track) -> str:
    if track.offset_px is None or track.status != "TRACKING":
        return "off  —"
    words = _offset_words(*track.offset_px)
    if track.offset_norm is not None:
        nx, ny = track.offset_norm
        return f"off  {words}   n=({nx:+.2f},{ny:+.2f})"
    return f"off  {words}"


def draw_detect_hud(image, stats: CaptureStats, track, tracker: DroneObjectTracker) -> None:
    h, w = image.shape[:2]
    _draw_crosshair(image, (w * 0.5, h * 0.5))
    tel = tracker.telemetry

    for det in tracker.last_detections:
        x, y, bw, bh = map(int, (det.bbox.x, det.bbox.y, det.bbox.w, det.bbox.h))
        color = (80, 255, 120) if det.accepted else (80, 80, 255)
        thickness = 3 if (
            det.accepted
            and track.bbox is not None
            and abs(det.bbox.cx - (track.bbox.x + track.bbox.w * 0.5)) < 4
            and track.status == "TRACKING"
        ) else 2
        cv2.rectangle(image, (x, y), (x + bw, y + bh), color, thickness)
        tag = det.label if det.accepted else f"rej:{det.label}"
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
        cv2.line(image, (int(w * 0.5), int(h * 0.5)), (tx, ty), color, 1)

    label = tel.class_label or track.class_label or "—"
    conf = tel.confidence if tel.confidence else track.confidence
    if track.status == "TRACKING" and label != "—":
        class_line = f"tgt  {label}  {conf:.2f}"
    elif tel.n_accepted > 0:
        class_line = f"tgt  confirming…  ({tel.n_accepted} hit)"
    else:
        class_line = "tgt  —"

    if tel.box_wh is not None and tel.range_proxy is not None:
        bw, bh = tel.box_wh
        size_line = f"size {bw:.0f}x{bh:.0f}   rng {tel.range_proxy:.0f}"
    else:
        size_line = "size —"

    if tel.top_reject:
        rej_line = f"rej  {tel.top_reject} {tel.top_reject_conf:.2f}  (n={tel.n_rejected})"
    else:
        rej_line = f"rej  —  (n={tel.n_rejected})"

    lock_line = (
        f"lock {tel.lock_age_s:.1f}s  id={tel.track_id or '—'}  iou={tel.iou_with_prev:.2f}"
        if track.status == "TRACKING"
        else f"lock —  hits need {tracker._state._acquire_hits}"
    )
    timing = (
        f"infer {tel.infer_ms:.0f}ms   lat {stats.latency_ms:.0f}ms   "
        f"{stats.fps:.0f} fps"
    )

    lines = [
        status,
        class_line,
        _fmt_offset(track),
        size_line,
        rej_line,
        lock_line,
        timing,
    ]
    pad_x, pad_y = 12, 10
    line_h = 26
    panel_w = min(w - 16, 420)
    panel_h = pad_y * 2 + line_h * len(lines)
    overlay = image.copy()
    cv2.rectangle(overlay, (8, 8), (8 + panel_w, 8 + panel_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, image, 0.45, 0, image)
    y = 8 + pad_y + 18
    for i, line in enumerate(lines):
        cv2.putText(
            image,
            line,
            (8 + pad_x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62 if i == 0 else 0.48,
            color if i == 0 else (220, 220, 220),
            2 if i == 0 else 1,
            cv2.LINE_AA,
        )
        y += line_h


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Haylon class-aware detect (M3.4+)")
    p.add_argument("--source", default="0", help="Camera index, video path, or image")
    p.add_argument(
        "--mode",
        default="drone",
        help="drone | bottle (desk demo)",
    )
    p.add_argument("--duration", type=float, default=0.0)
    p.add_argument("--headless", action="store_true")
    p.add_argument("--conf", type=float, default=0.25, help="Detector score floor")
    p.add_argument("--min-lock-conf", type=float, default=0.30, help="Min conf to lock")
    p.add_argument("--imgsz", type=int, default=640, help="YOLO inference size")
    p.add_argument("--acquire-hits", type=int, default=3, help="Frames before first lock")
    p.add_argument(
        "--weights",
        default="",
        help="YOLO-World or fine-tuned .pt (default: yolov8s-worldv2.pt)",
    )
    p.add_argument(
        "--accept",
        default="",
        help="Comma accept labels override, e.g. bottle,cup",
    )
    p.add_argument("--out-frame", default="", help="Optional path to save last annotated frame")
    args = p.parse_args(argv)

    targets = None
    if args.accept.strip():
        targets = [s.strip() for s in args.accept.split(",") if s.strip()]
    elif args.mode == "bottle":
        from detect_result import BOTTLE_DEMO_LABELS

        targets = list(BOTTLE_DEMO_LABELS)

    print(
        f"detect  mode={args.mode}  class-aware lock + telemetry HUD\n"
        "  Green = accepted. Red = reject (never locks).\n"
        "  q=quit  r=reset",
        flush=True,
    )

    source = make_source(args.source, loop_file=True)
    if args.mode == "bottle" and not args.accept.strip():
        from finger_tracker import make_tracker

        tracker = make_tracker("bottle", weights=args.weights.strip() or None)
    else:
        distractors = None
        if args.mode == "bottle" or (
            targets and any(t.lower() in {"bottle", "cup", "water bottle"} for t in targets)
        ):
            distractors = ("person", "hand", "phone", "book", "chair", "car")
        tracker = DroneObjectTracker(
            conf=args.conf if args.mode != "bottle" else min(args.conf, 0.20),
            min_lock_conf=(
                args.min_lock_conf if args.mode != "bottle" else min(args.min_lock_conf, 0.22)
            ),
            imgsz=args.imgsz,
            acquire_hits=args.acquire_hits if args.mode != "bottle" else min(args.acquire_hits, 2),
            target_labels=targets,
            distractor_labels=distractors,
            weights=args.weights.strip() or None,
        )
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
                    tel = tracker.telemetry
                    print(
                        f"t={elapsed:5.1f}s  {track.status:9s}  "
                        f"tgt={tel.class_label or '—':10s} conf={tel.confidence:4.2f}  "
                        f"infer={tel.infer_ms:5.1f}ms  "
                        f"rej={tel.top_reject or '—'}  "
                        f"fps={stats.fps:5.1f}",
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
