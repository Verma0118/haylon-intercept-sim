"""M4.1 — camera track → Guide → StickMap → mock TX (no Xbox required).

Desk default was hand tip. For the real path use --mode drone so the HUD
shows class + AETR together: what we see → what sticks we would send.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any, Optional

import cv2

from finger_tracker import make_tracker
from guide import CenterGuide
from guidance_cmd import stick_profile
from mock_tx import MockTx
from run_capture import CaptureStats
from run_finger_track import _offset_words, _draw_crosshair
from source import make_source


def _fmt_offset(track) -> str:
    if track.offset_px is None or track.status != "TRACKING":
        return "off  —"
    words = _offset_words(*track.offset_px)
    if track.offset_norm is not None:
        nx, ny = track.offset_norm
        return f"off  {words}  n=({nx:+.2f},{ny:+.2f})"
    return f"off  {words}"


def draw_guide_hud(
    image,
    stats: CaptureStats,
    track,
    cmd,
    frame,
    stick_name: str,
    channel_order: tuple[str, ...],
    tracker: Any = None,
) -> None:
    """Class (what we see) + steer + AETR µs (what we would send) on one panel."""
    h, w = image.shape[:2]
    _draw_crosshair(image, (w * 0.5, h * 0.5))

    status = track.status
    color = {
        "TRACKING": (80, 255, 120),
        "SEARCHING": (0, 200, 255),
        "LOST": (60, 60, 255),
    }.get(status, (200, 200, 200))

    # Draw reject/accept boxes when class-aware tracker is present
    last_dets = getattr(tracker, "last_detections", None)
    if last_dets:
        for det in last_dets:
            x, y, bw, bh = map(int, (det.bbox.x, det.bbox.y, det.bbox.w, det.bbox.h))
            c = (80, 255, 120) if det.accepted else (80, 80, 255)
            cv2.rectangle(image, (x, y), (x + bw, y + bh), c, 2)
            tag = det.label if det.accepted else f"rej:{det.label}"
            cv2.putText(
                image,
                f"{tag} {det.confidence:.2f}",
                (x, max(18, y - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                c,
                1,
                cv2.LINE_AA,
            )
    elif track.bbox is not None:
        x, y, bw, bh = map(int, (track.bbox.x, track.bbox.y, track.bbox.w, track.bbox.h))
        cv2.rectangle(image, (x, y), (x + bw, y + bh), color, 2)

    if track.target_xy is not None and track.origin_xy is not None and status == "TRACKING":
        tx, ty = map(int, track.target_xy)
        ox, oy = map(int, track.origin_xy)
        cv2.circle(image, (tx, ty), 8, color, 2)
        cv2.line(image, (ox, oy), (tx, ty), color, 1)

    # --- class / see ---
    label = track.class_label
    tel = getattr(tracker, "telemetry", None)
    if tel is not None and tel.class_label:
        label = tel.class_label
    conf = track.confidence if status == "TRACKING" else (tel.confidence if tel else 0.0)
    if status == "TRACKING" and label:
        see = f"see  {label}  {conf:.2f}"
    elif label:
        see = f"see  {label}  (not locked)"
    else:
        see = "see  —"

    # --- guide ---
    yaw, pitch = cmd.yaw_rate, cmd.pitch_rate
    if abs(yaw) < 0.05 and abs(pitch) < 0.05:
        steer = f"steer hold   mode={cmd.mode}"
    else:
        yaw_s = f"{'R' if yaw > 0 else 'L'}{abs(yaw):.2f}"
        pitch_s = f"{'U' if pitch > 0 else 'D'}{abs(pitch):.2f}"
        steer = f"steer {yaw_s} {pitch_s}   mode={cmd.mode}"

    # --- AETR / profile channels ---
    order = channel_order[:4]
    us = [frame.channels[i] for i in range(4)]
    # Always print both labeled µs and classic AETR shorthand when order is AETR
    ch_labeled = "  ".join(f"{tag[0].upper()}={us[i]:.0f}" for i, tag in enumerate(order))
    aetr_line = f"TX   {ch_labeled}"
    if order == ("roll", "pitch", "throttle", "yaw"):
        aetr_line = f"AETR {us[0]:.0f} {us[1]:.0f} {us[2]:.0f} {us[3]:.0f}"

    infer = ""
    if tel is not None and tel.infer_ms > 0:
        infer = f"  infer {tel.infer_ms:.0f}ms"
    timing = f"{stats.fps:.0f} fps  lat {stats.latency_ms:.0f}ms{infer}"

    rej = "rej  —"
    if tel is not None and tel.top_reject:
        rej = f"rej  {tel.top_reject} {tel.top_reject_conf:.2f}"

    lines = [
        status,
        see,
        _fmt_offset(track),
        steer,
        aetr_line,
        rej,
        f"map  {stick_name}",
        timing,
    ]
    pad_x, pad_y = 12, 10
    line_h = 26
    panel_w = min(w - 16, 440)
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
    p = argparse.ArgumentParser(description="Haylon guide: track → sticks → mock TX")
    p.add_argument("--source", default="0")
    p.add_argument(
        "--mode",
        default="drone",
        help="Tracker mode (default drone). Use hand for fingertip desk demo.",
    )
    p.add_argument("--duration", type=float, default=0.0)
    p.add_argument("--headless", action="store_true")
    p.add_argument("--out-tx", default="mock_tx.jsonl", help="Mock TX JSONL path")
    p.add_argument("--kp", type=float, default=1.2, help="Guide P gain")
    p.add_argument("--rate-limit", type=float, default=0.85)
    p.add_argument(
        "--profile",
        default="betaflight_default",
        help="StickMap profile: betaflight_default (AETR) or taer",
    )
    p.add_argument(
        "--weights",
        default="",
        help="Optional detector weights (YOLO-World or fine-tuned drone .pt)",
    )
    p.add_argument("--out-frame", default="", help="Save last annotated frame")
    args = p.parse_args(argv)

    try:
        stick = stick_profile(args.profile)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    weights = args.weights.strip() or None
    print(
        f"guide  track={args.mode}  profile={stick.name}  mock_tx={args.out_tx}\n"
        "  HUD: see(class) → steer → AETR µs (mock TX, not live radio).\n"
        "  TRACKING + off-center → yaw/pitch leave mid. LOST → zeros.\n"
        "  q=quit  r=reset",
        flush=True,
    )

    source = make_source(args.source, loop_file=True)
    tracker = make_tracker(args.mode, weights=weights)
    guide = CenterGuide(kp_yaw=args.kp, kp_pitch=args.kp, rate_limit=args.rate_limit)
    tx = MockTx(args.out_tx)
    stats = CaptureStats()
    t0 = time.perf_counter()
    last_report = t0
    guided = 0
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
                cmd = guide.update(track)
                ch = stick.to_channels(cmd)
                tx.send(ch)
                if cmd.mode == "TRACK_CENTER":
                    guided += 1

                image = frame.data.copy()
                draw_guide_hud(
                    image,
                    stats,
                    track,
                    cmd,
                    ch,
                    stick_name=stick.name,
                    channel_order=stick.channel_order,
                    tracker=tracker,
                )
                last_image = image

                if not args.headless:
                    cv2.imshow("haylon-guide", image)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        break
                    if key == ord("r"):
                        tracker.reset()

                now = time.perf_counter()
                if now - last_report >= 1.0:
                    cls = track.class_label or "—"
                    print(
                        f"t={elapsed:5.1f}s  {track.status:9s}  see={cls:10s}  "
                        f"mode={cmd.mode:12s}  yaw={cmd.yaw_rate:+.2f}  "
                        f"A={ch.channels[0]:.0f} E={ch.channels[1]:.0f} "
                        f"T={ch.channels[2]:.0f} R={ch.channels[3]:.0f}  "
                        f"fps={stats.fps:5.1f}",
                        flush=True,
                    )
                    last_report = now
    finally:
        tracker.close()
        tx.close()
        if not args.headless:
            cv2.destroyAllWindows()
        if args.out_frame and last_image is not None:
            cv2.imwrite(args.out_frame, last_image)
            print(f"Wrote {args.out_frame}", flush=True)

    print(
        f"\nDone. frames={stats.frames}  guided={guided}  "
        f"mock_tx={args.out_tx} ({tx.frames} rows)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
