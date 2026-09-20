"""M4.3 fixture — same GuidanceCommand, two StickMap layouts (AETR vs TAER).

Run:  python check_stickmap_profiles.py
Exit 0 on pass.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from guidance_cmd import GuidanceCommand, GuidanceFlags, stick_profile

# Distinct rates so channel permutation is obvious in the fixture.
FIXTURE_CMD = GuidanceCommand(
    timestamp_ms=1_710_000_000_140.0,
    mode="TRACK_CENTER",
    yaw_rate=-0.35,
    pitch_rate=0.10,
    roll_rate=0.25,
    throttle=0.45,
    flags=GuidanceFlags(lost_target=False, link_ok=True),
)

# Expected µs (deadband 0.05, mid 1500, span 500, thr 1000..2000).
# roll 0.25 → after db: (0.25-0.05)/0.95 ≈ 0.2105 → 1605.3
# pitch 0.10 → (0.10-0.05)/0.95 ≈ 0.0526 → 1526.3
# yaw -0.35 → -0.3158 → 1342.1
# throttle 0.45 → 1450.0
EXPECTED = {
    "betaflight_default": {
        "order": ["roll", "pitch", "throttle", "yaw"],
        "channels_us": [1605.3, 1526.3, 1450.0, 1342.1],
    },
    "taer": {
        "order": ["throttle", "roll", "pitch", "yaw"],
        "channels_us": [1450.0, 1605.3, 1526.3, 1342.1],
    },
}


def _round1(xs: list[float]) -> list[float]:
    return [round(x, 1) for x in xs]


def main() -> int:
    rows = {}
    for name in ("betaflight_default", "taer"):
        sm = stick_profile(name)
        frame = sm.to_channels(FIXTURE_CMD)
        got = _round1(frame.channels[:4])
        want = EXPECTED[name]["channels_us"]
        if got != want:
            print(f"FAIL {name}: got {got} want {want}", file=sys.stderr)
            return 1
        if list(sm.channel_order) != EXPECTED[name]["order"]:
            print(f"FAIL {name} order: {sm.channel_order}", file=sys.stderr)
            return 1
        rows[name] = {
            "order": list(sm.channel_order),
            "channels_us": got,
        }

    # Same cmd must permute: AETR ch0 != TAER ch0 (roll vs throttle)
    if rows["betaflight_default"]["channels_us"] == rows["taer"]["channels_us"]:
        print("FAIL: profiles produced identical channel vectors", file=sys.stderr)
        return 1
    if rows["betaflight_default"]["channels_us"][0] == rows["taer"]["channels_us"][0]:
        print("FAIL: ch0 should differ (roll vs throttle)", file=sys.stderr)
        return 1

    out = Path(__file__).resolve().parent / "fixtures" / "stickmap_profiles.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "command": {
            "timestamp_ms": FIXTURE_CMD.timestamp_ms,
            "mode": FIXTURE_CMD.mode,
            "yaw_rate": FIXTURE_CMD.yaw_rate,
            "pitch_rate": FIXTURE_CMD.pitch_rate,
            "roll_rate": FIXTURE_CMD.roll_rate,
            "throttle": FIXTURE_CMD.throttle,
        },
        "profiles": rows,
    }
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"PASS  AETR={rows['betaflight_default']['channels_us']}")
    print(f"PASS  TAER={rows['taer']['channels_us']}")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
