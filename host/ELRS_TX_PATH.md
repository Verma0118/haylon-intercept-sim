# ELRS TX path from a laptop (D3 research note) — M2.0

**Decision default:** laptop reads an Xbox controller → `GuidanceCommand` →
`StickMap` → `ChannelFrame` → **ELRS TX module** that sends radio packets to
the interceptor’s ELRS RX / FC.

## Candidate bridges (pick one when hardware arrives)

| Approach | How | Pros | Cons |
|---|---|---|---|
| **A. USB CRSF / ExpressLRS TX module** (e.g. Happymodel ES24TX, Radiomaster Ranger Micro as USB JOY/CRSF) | Host writes CRSF frames or uses a serial bridge to the module | Clean “packets out”; matches flight stack | Need a compatible TX module + driver notes per OS |
| **B. Joystick HID emulation** | Host appears as a USB gamepad to EdgeTX / OpenTX companion or a TX that ingests USB gamepad | Easy to test with existing radios | Extra hop; latency; mapping quirks |
| **C. EdgeTX Lua / trainer port** | External radio remains master; laptop injects trainer overrides | Strong failsafe story (radio always in loop) | More hardware; slower to automate |

## Recommended for NOBE bench (until Haylon specifies otherwise)

1. **Software now (no radio):** `run_gamepad.py` — Xbox → StickMap → mock channel log (**M2.1**, this PR).
2. **Hardware next:** Approach **A** — USB ELRS TX module that accepts CRSF or channels from the host, so the laptop is the packet source.
3. Keep a physical kill on the TX / FC arm switch; host never auto-arms.

## Exit for M2.0

Written choice above + shopping list (TX module SKU, cable, FC target). Update this
file when the module is picked; then implement the live bridge in M2.2–M2.3.
