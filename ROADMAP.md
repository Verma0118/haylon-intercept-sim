# Haylon Interceptor — Architecture Roadmap

> Derived from the 9/4 meeting with Namin + the existing intercept sim (`BLUEPRINT.md`).
> Goal: make the **real** software/control architecture work — slowly, one proven step at a time.
> Rule: do not start step N+1 until step N has a clear pass/fail demo.

---

## What the 9/4 meeting actually decided

| Decision | Implication for software |
|---|---|
| Focus on **software + control**, not designing a drone from scratch | Architecture must sit *above* the flight controller, not replace it |
| Haylon provides an **OTS small quad** (FC + ESC + ELRS already onboard) | We talk to the FC via radio (ELRS/CRSF), not custom motor mixing first |
| **Image processing runs on a laptop/host**, not onboard | Vision + guidance live on the host; the drone is an actuator + camera platform |
| Control should be **transferable across platforms** | Define a thin, platform-agnostic command interface (rates / sticks), not Betaflight-specific hacks baked into guidance |
| Separate **target drone** also provided | Testing path is real flying target, not only sim scenarios |
| Battery integration is **out of scope** | Ignore energy systems; use stock batteries |
| Frame / nose-cone exploration is optional side work | Do **not** block the software pipeline on mechanical redesign |
| Soft field-test window: late Oct → early Nov | Bench closed-loop must exist well before that; field is validation, not first contact |

### Real system shape (from the meeting)

```
[Interceptor camera] ──video──► [Host laptop]
                                      │
                         detect → track → guide
                                      │
                              control commands
                                      │
                                      ▼
                               [ELRS TX module]
                                      │
                                      ▼
                         [Interceptor FC / ELRS RX]
                                      │
                                      ▼
                                   motors
```

That is the architecture that must “truly work.” The browser sim is a **pitch / teaching aid** for the control loop idea — not the production stack.

---

## What the current repo already proves

The Vite + Three.js sim (`BLUEPRINT.md`) demonstrates the **logical pipeline**:

```
Launch Detect → Stabilize → Track → Guidance → Hit/Miss
```

Useful for explaining Haylon’s product story and tuning guidance intuition (lead pursuit, target weave/erratic).

Explicit sim non-goals (still correct for v1 of the **demo**):

- No real throw-detection classifier
- No camera / CV
- No ELRS / radio link
- No sensor noise or latency
- Idealized perfect state

**Do not confuse “sim looks good” with “architecture works.”** Closing the gap below is the real project.

---

## Gap: sim story vs deployable architecture

| Module (sim / pitch) | What “works” means in hardware | Biggest missing piece today |
|---|---|---|
| **Launch Detect** | Reliable “mission start” signal (throw IMU, arm+RC, or operator trigger — TBD with Haylon) | Real trigger policy not chosen; sim fakes it |
| **Stabilize** | Attitude hold / recovery via FC (or host-assisted) after launch | We rely on stock FC; no host attitude loop yet |
| **Track** | Continuous target estimate from camera (bbox → bearing / range proxy) | No vision stack; sim uses god-mode positions |
| **Guidance** | Turn estimate into **safe, rate-limited stick/CRSF commands** | Lead-pursuit math exists in sim only; no command bus |
| **Actuation** | Host → ELRS → FC closed loop at usable latency | No radio bridge |
| **Platform portability** | Same guidance code, different FC profiles / stick maps | No abstraction layer |

---

## Definition of done (architecture truly works)

The architecture is “real” when **all** of these are true on the bench (field is later):

1. Host receives a live camera stream from the interceptor (or a stand-in cam on the bench).
2. Host detects + tracks a known target class (even a colored blob / ArUco is fine for early steps).
3. Host publishes guidance outputs at a fixed rate (e.g. 20–50 Hz) as **normalized stick commands**.
4. Those commands reach the FC over ELRS and move the vehicle predictably (at least yaw/roll toward target).
5. Fail-safes exist: link loss, lost target, operator override, max throttle/rate caps.
6. The same host pipeline can point at a second FC profile with only a config change (portability proof).

Field intercept against the target drone is the **validation milestone**, not the first milestone.

---

## Build philosophy

- **One step = one demoable artifact** with a binary pass/fail.
- Prefer ugly-but-real over beautiful-but-fake.
- Keep the existing browser sim as documentation / narrative; evolve it only when a step needs a better teaching aid.
- Hardware-dependent steps wait on Haylon shipping platforms — software steps in front of them should use webcam + mock TX first.
- No parallel “big bang” vision+ELRS+guidance rewrite.

---

## Step sequence (build only the current step)

Status legend: `DONE` · `NEXT` · `QUEUED` · `BLOCKED` (needs hardware / decision)

### Track A — Decisions & docs (cheap, unblocks everything)

| Step | Deliverable | Pass/fail | Status |
|---|---|---|---|
| **A0** | This roadmap + gap analysis checked into the repo | Team agrees this is the build order | `DONE` |
| **A1** | One-page architecture overview for NOBE onboarding (meeting action item; Haylon-owned, we can draft) | New teammates can explain host-vision → ELRS → FC in <2 min | `QUEUED` |
| **A2** | Freeze v0 interfaces: `CameraFrame`, `TrackEstimate`, `GuidanceCommand`, `StickMap`, failsafe enum | Written schema (Markdown or JSON) reviewed once | `NEXT` |
| **A3** | Decide Launch Detect policy for NOBE scope (operator arm, RC switch, or IMU throw) with Haylon | Written decision; sim legend updated to match | `QUEUED` |

### Track B — Host software skeleton (no drone required)

| Step | Deliverable | Pass/fail | Status |
|---|---|---|---|
| **B1** | Host process boots, grabs webcam frames, shows FPS + latency overlay | Stable ≥15 FPS for 60s on a laptop | `QUEUED` |
| **B2** | Target detect v0: colored blob **or** ArUco marker → bbox | Marker held in frame produces stable bbox | `QUEUED` |
| **B3** | Tracker v0: bbox ID + lost-target timeout | Occlude 1s → `LOST`; reappear → reacquire | `QUEUED` |
| **B4** | Guidance v0: bbox center → desired yaw/pitch rates (or stick N/E) with rate limits | Moving marker left/right flips command sign correctly; saturates at cap | `QUEUED` |
| **B5** | Mock actuator sink: log/plot commands at fixed Hz; inject failsafe on `LOST` | Commands go to 0 (or hold) within 1 frame of loss | `QUEUED` |
| **B6** | Portability shim: `StickMap` profiles (`betaflight_default`, `alternate`) | Same guidance, two maps, unit-checked | `QUEUED` |

### Track C — Radio / ELRS bridge (needs TX hardware; mock first)

| Step | Deliverable | Pass/fail | Status |
|---|---|---|---|
| **C0** | Research note: how this exact ELRS TX will be driven from the host (USB joystick emu, CRSF serial, EdgeTX script, etc.) | One chosen path with link to docs | `QUEUED` / may be `BLOCKED` on platform info |
| **C1** | Mock TX: host writes CRSF/SBUS-like channel packet to a file or virtual serial | Packet format validated against a decoder | `QUEUED` |
| **C2** | Live TX: host commands move **disarmed** FC channel monitors / servo tester | Channels twitch as expected; kill switch works | `BLOCKED` on hardware |
| **C3** | Armed bench: props off or restrained — attitude responds to host yaw/roll commands | Safe, repeatable, operator override always wins | `BLOCKED` on hardware |

### Track D — Closed loop & intercept (after C3)

| Step | Deliverable | Pass/fail | Status |
|---|---|---|---|
| **D1** | Indoor follow: drone yaws to keep marker centered (no chase yet) | Marker stays in central third for N seconds | `QUEUED` |
| **D2** | Translate in place toward static target (range proxy / area growth) | Range proxy decreases without oscillation blow-up | `QUEUED` |
| **D3** | Chase moving person-held marker / second soft target | Sustained track > T seconds | `QUEUED` |
| **D4** | Field: interceptor vs Haylon target drone (straight pass) | Documented hit/near-miss criteria met or learnings captured | `QUEUED` |
| **D5** | Stress: weaving / erratic target (reuse sim behaviors as test plan) | Same as D4 under harder motion | `QUEUED` |

### Track E — Sim alignment (only when it helps a real step)

| Step | Deliverable | Pass/fail | Status |
|---|---|---|---|
| **E1** | Update HUD legend / copy so modules match the **host-vision + ELRS** story (not only throw-detect) | Demo narration matches 9/4 architecture | `QUEUED` |
| **E2** | Optional: add “sensor latency” / “lost track” toggles in sim once B3–B5 exist | Sim failure modes mirror host failsafes | `QUEUED` |
| **E3** | Optional: replace lead-pursuit with PN later if field data demands it | Better intercept stats, not prettier math | `QUEUED` |

### Out of scope (do not schedule as blockers)

- Haylon battery integration
- Recreating FC / ESC hardware
- Full custom airframe as a prerequisite (nose-cone is exploratory only)
- Onboard neural net inference (host-first per meeting; revisit only after closed loop works)

---

## Recommended next action (only this)

**A0 is done. Next: A2 (freeze v0 interfaces).**

Why A2 before writing vision code: without frozen message types (`TrackEstimate`, `GuidanceCommand`, `StickMap`), B1–B5 tend to glue webcam demos directly to sticks and become unportable — which violates the meeting’s “works across platforms” requirement.

After A2, **B1** is the first line of code that proves the host exists.

Hardware steps (C2+) stay blocked until Haylon’s platform link + shipped radios arrive; that must not stall Track A/B.

---

## How to use this doc while building

1. Pick the single lowest-number non-`DONE` step that is not `BLOCKED`.
2. Open a PR that only that step (or a tiny sub-step) lands.
3. Record the pass/fail evidence in the PR (screenshot, log snippet, or short clip).
4. Mark the step `DONE` here in the same PR.
5. Stop. Do not “just start” the next step in the same PR unless it is a trivial doc fix.

Slow is the point. Working is the point.
