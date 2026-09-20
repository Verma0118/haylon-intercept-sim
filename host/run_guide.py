"""M4.1 — camera track → Guide → StickMap → mock TX (no Xbox required).

Hold your hand in front of the camera. When the tip is left of center, yaw
command goes left (negative); right → positive. LOST/SEARCHING → zero rates.

Same StickMap path the Xbox gamepad uses — swap MockTx for live ELRS later.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

import cv2

from finger_tracker import make_tracker
from guide import CenterGuide
from guidance_cmd import stick_profile
from mock_tx import MockTx
from run_capture import CaptureStats
from run_finger_track import _offset_words, _draw_crosshair
from source import make_source


def draw_guide_hud(image, stats: CaptureStats, track, cmd, frame) -> None:
    h, w = image.shape[:2]
    _draw_crosshair(image, (w * 0.5, h * 0.5))

    status = track.status
    color = {
        "TRACKING": (80, 255, 120),
        "SEARCHING": (0, 200, 255),
        "LOST": (60, 60, 255),
    }.get(status, (200, 200, 200))

    if track.bbox is not None:
        x, y, bw, bh = map(int, (track.bbox.x, track.bbox.y, track.bbox.w, track.bbox.h))
        cv2.rectangle(image, (x, y), (x + bw, y + bh), color, 2)
    if track.target_xy is not None and track.origin_xy is not None:
        tx, ty = map(int, track.target_xy)
        ox, oy = map(int, track.origin_xy)
        cv2.circle(image, (tx, ty), 8, color, 2)
        cv2.line(image, (ox, oy), (tx, ty), color, 1)
        where = _offset_words(*(track.offset_px or (0.0, 0.0)))
    else:
        where = "looking…"

    # Compact: status, where, steer command, fps
    yaw = cmd.yaw_rate
    pitch = cmd.pitch_rate
    if abs(yaw) < 0.05 and abs(pitch) < 0.05:
        steer = "steer  hold"
    else:
        yaw_s = f"{'R' if yaw > 0 else 'L'}{abs(yaw):.2f}"
        pitch_s = f"{'U' if pitch > 0 else 'D'}{abs(pitch):.2f}"
        steer = f"steer  {yaw_s}  {pitch_s}"

    a, e, t, r = (frame.channels[i] for i in range(4))
    ch = f"AETR  {a:.0f} {e:.0f} {t:.0f} {r:.0f}"

    lines = [status, where, steer, ch, f"{stats.fps:.0f} fps"]
    pad_x, pad_y = 12, 10
    line_h = 28
    panel_w = min(w - 16, 320)
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
    p = argparse.ArgumentParser(description="Haylon guide: track → sticks → mock TX")
    p.add_argument("--source", default="0")
    p.add_argument("--mode", default="hand", help="Tracker mode (default hand)")
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
    args = p.parse_args(argv)

    try:
        stick = stick_profile(args.profile)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    print(
        f"guide  track={args.mode}  profile={stick.name}  mock_tx={args.out_tx}\n"
        "  Move hand left/right of center → yaw command flips sign.\n"
        "  Cover hand → HOLD / zeros.  q=quit  r=reset",
        flush=True,
    )

    source = make_source(args.source, loop_file=True)
    tracker = make_tracker(args.mode)
    guide = CenterGuide(kp_yaw=args.kp, kp_pitch=args.kp, rate_limit=args.rate_limit)
    tx = MockTx(args.out_tx)
    stats = CaptureStats()
    t0 = time.perf_counter()
    last_report = t0
    guided = 0

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
                draw_guide_hud(image, stats, track, cmd, ch)

                if not args.headless:
                    cv2.imshow("haylon-guide", image)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        break
                    if key == ord("r"):
                        tracker.reset()

                now = time.perf_counter()
                if now - last_report >= 1.0:
                    print(
                        f"t={elapsed:5.1f}s  {track.status:9s}  mode={cmd.mode:12s}  "
                        f"yaw={cmd.yaw_rate:+.2f}  pitch={cmd.pitch_rate:+.2f}  "
                        f"A={ch.channels[0]:.0f} R={ch.channels[3]:.0f}  "
                        f"fps={stats.fps:5.1f}",
                        flush=True,
                    )
                    last_report = now
    finally:
        tracker.close()
        tx.close()
        if not args.headless:
            cv2.destroyAllWindows()

    print(f"\nDone. frames={stats.frames}  guided={guided}  mock_tx={args.out_tx} ({tx.frames} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
