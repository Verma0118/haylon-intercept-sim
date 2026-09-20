"""M2.1 — Xbox gamepad → GuidanceCommand → StickMap → mock ChannelFrame log.

No radio required. Proves sticks move normalized channels at ≥20 Hz.
Press B for kill (ABORT / zeros). q or Ctrl-C to quit.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Optional

from gamepad import Gamepad
from guidance_cmd import StickMap


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Haylon gamepad → mock TX channels (M2.1)")
    p.add_argument("--hz", type=float, default=50.0, help="Publish rate (default 50)")
    p.add_argument("--duration", type=float, default=0.0, help="Seconds (0 = until Ctrl-C)")
    p.add_argument("--out", default=None, help="Optional CSV log of ChannelFrames")
    args = p.parse_args(argv)

    try:
        pad = Gamepad()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    stick = StickMap(name="betaflight_default")
    period = 1.0 / max(1.0, args.hz)
    t0 = time.perf_counter()
    last_print = t0
    n = 0
    writer = None
    out_path = Path(args.out) if args.out else None

    if not pad.connected:
        print(
            "No gamepad detected yet — plug in an Xbox controller and wait.\n"
            "On Mac: pair via Bluetooth or USB, then re-run if needed.",
            flush=True,
        )
    else:
        print(f"Gamepad: {pad.name()}", flush=True)

    print(
        "Reading sticks → AETR µs channels (mock TX).\n"
        "  Left stick = roll/pitch   Right stick = yaw/throttle\n"
        "  B = kill (ABORT)   Ctrl-C = quit\n",
        flush=True,
    )

    try:
        if out_path is not None:
            f = out_path.open("w", newline="")
            writer = csv.writer(f)
            writer.writerow(
                ["t_s", "mode", "roll_us", "pitch_us", "throttle_us", "yaw_us", "kill"]
            )

        while True:
            loop_start = time.perf_counter()
            elapsed = loop_start - t0
            if args.duration > 0 and elapsed >= args.duration:
                break

            reading = pad.read()
            cmd = pad.to_guidance(reading)
            if reading.kill:
                cmd.yaw_rate = cmd.pitch_rate = cmd.roll_rate = 0.0
                cmd.throttle = 0.0
                cmd.mode = "ABORT"
            frame = stick.to_channels(cmd)
            n += 1

            if writer is not None:
                writer.writerow(
                    [
                        f"{elapsed:.3f}",
                        cmd.mode,
                        f"{frame.channels[0]:.1f}",
                        f"{frame.channels[1]:.1f}",
                        f"{frame.channels[2]:.1f}",
                        f"{frame.channels[3]:.1f}",
                        int(reading.kill),
                    ]
                )

            now = time.perf_counter()
            if now - last_print >= 0.25:
                conn = "OK" if reading.connected else "NO PAD"
                print(
                    f"t={elapsed:6.1f}s  pad={conn:6s}  mode={cmd.mode:5s}  "
                    f"A={frame.channels[0]:6.0f}  E={frame.channels[1]:6.0f}  "
                    f"T={frame.channels[2]:6.0f}  R={frame.channels[3]:6.0f}  "
                    f"hz~{n / max(elapsed, 1e-3):5.1f}",
                    flush=True,
                )
                last_print = now

            sleep = period - (time.perf_counter() - loop_start)
            if sleep > 0:
                time.sleep(sleep)
    except KeyboardInterrupt:
        print("\nquit", flush=True)
    finally:
        pad.close()
        if out_path is not None and writer is not None:
            f.close()
            print(f"Wrote {out_path}", flush=True)

    print(f"Done. frames={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
