# Haylon Interceptor — Build Roadmap

Companion to `ARCHITECTURE.md` (design source of truth).

**Rule:** one milestone exit at a time. A PR should advance at most one step unless the change is a tiny doc fix.

Status: `DONE` · `NEXT` · `QUEUED` · `BLOCKED`

---

## Why this roadmap exists

The browser sim already demonstrates a *story*: Detect → Stabilize → Track → Guide.

The real machine is simpler at the radio layer:

> **ELRS transmitter sends packets to the drone.**  
> Sticks (human or software) keep it from drifting.  
> Vision/guidance later becomes just another packet source.

**First live step:** fly the drone from a **laptop + Xbox controller**. Prove the packet path before closing any vision loop.

---

## Principles

1. **Ugly-but-real beats pretty-but-fake.** An Xbox hover on ELRS outranks another HUD polish pass.
2. **Packets before autonomy.** Manual host→TX flight is the foundation; auto guidance reuses that pipe.
3. **Contracts before glue.** Freeze `GuidanceCommand` / `StickMap` / `ChannelFrame` before inventing ad-hoc channel writers.
4. **Hardware must not stall software.** Mock TX + logged channels until the radio is plugged in — but the *goal* of M2 is live packets.
5. **FC owns attitude.** Host/operator only sends stick packets; do not rebuild stabilize PID first.
6. **Sim stays a teaching aid.** Only change it when it clarifies the real stack.
7. **Pass/fail or it didn’t happen.** Every step below has an exit check.

---

## Critical path (dependency order)

```
M0 Architecture docs
        │
        ▼
M1 Freeze contracts
        │
        ▼
M2 Manual fly — Xbox → laptop → ELRS packets → drone     ← FIRST LIVE GOAL
        │
        ▼
M3 Host sense (cam → track)     [desk demos can proceed in parallel once M2.0 research is clear]
        │
        ▼
M4 Guide + failsafe (auto commands on the same StickMap/TX path)
        │
        ▼
M5 Bench closed-loop → field
```

Optional parallel (never blocks critical path): sim legend honesty, onboarding one-pager, nose-cone exploration, Haylon hardware shipping.

---

## Milestone M0 — Shared picture

| Step | Deliverable | Exit check | Status |
|---|---|---|---|
| **M0.1** | `ARCHITECTURE.md` — sim map + host stack + ELRS packet model + Xbox-first goal | Someone new can explain: TX sends packets; Xbox is step one | `DONE` |
| **M0.2** | This roadmap rewritten against milestones | Critical path above is the agreed order | `DONE` |

---

## Milestone M1 — Freeze the seams

**Goal:** agree the messages so later PRs do not invent ad-hoc dicts.

| Step | Deliverable | Exit check | Status |
|---|---|---|---|
| **M1.1** | Formalize v0 schemas into `host/contracts.md` | Schemas reviewed once; no conflicting shapes | `DONE` |
| **M1.2** | Record defaults for open decisions D1–D6 (incl. D3 = Xbox→ELRS) | Each decision has a written default | `DONE` |
| **M1.3** | Repo layout: `host/` in this repo | Folder exists with README pointing at contracts | `DONE` |

---

## Milestone M2 — Host can fly (manual)

**Goal:** laptop + Xbox controller moves the real drone via ELRS packets. No vision required.

This is the **first hardware milestone**. Vision demos do not replace it.

| Step | Deliverable | Exit check | Status |
|---|---|---|---|
| **M2.0** | Research note for D3: exact ELRS TX drive path from a Mac/PC (USB JoyStick emu, CRSF serial to TX module, EdgeTX, etc.) | One chosen approach + links + required dongle/module | `DONE` (`host/ELRS_TX_PATH.md`) |
| **M2.1** | Gamepad input: read Xbox controller axes/buttons on the laptop at ≥20 Hz | Sticks move logged normalized channels predictably | `NEXT` (`host/run_gamepad.py`) |
| **M2.2** | StickMap → `ChannelFrame` → TX bridge (mock file/serial first) | Round-trip decode matches; rate capped | `QUEUED` |
| **M2.3** | Live ELRS, **disarmed**: gamepad moves FC channel monitor / RX output | Channels respond; kill switch works | `BLOCKED` on TX hardware |
| **M2.4** | Armed / restrained bench or open hover: fly and **hold position without uncontrolled drift** using Xbox on the laptop | Operator can take off, hover, land; override always wins | `BLOCKED` on airframe + TX |

Exit milestone at **M2.4**. Do not treat autonomy as “in progress” until this is boring.

---

## Milestone M3 — Host can see

**Goal:** prove the host process can produce a `TrackEstimate`. Can overlap calendar-wise with M2 once M2.0 is chosen, but **does not unblock field autonomy** without M2.

| Step | Deliverable | Exit check | Status |
|---|---|---|---|
| **M3.1** | Capture: open webcam (or video file), emit `CameraFrame`, overlay FPS + latency | ≥15 FPS stable for 60s | `DONE` (built early) |
| **M3.2** | Detect/track v0: phone / fingertip / blob → live `(x,y)` + status | Target in frame → coords that move with it | `DONE` (built early) |
| **M3.3** | Track polish: honest `SEARCHING/TRACKING/LOST` + timeout | Occlude ~1s → `LOST`; reappear → reacquire | `QUEUED` |

Exit milestone when a laptop demo shows live frames + track status for several minutes.

---

## Milestone M4 — Host can decide

**Goal:** turn track into safe `GuidanceCommand`s on the **same** StickMap → TX path proven in M2.

| Step | Deliverable | Exit check | Status |
|---|---|---|---|
| **M4.1** | Guide v0: keep target centered → yaw/pitch rates (+ optional throttle hold), with rate limits | Move marker left → opposite-sign yaw command; saturates at cap | `QUEUED` |
| **M4.2** | Failsafe: on `LOST`, commands go idle/hold within one publish cycle; log every cmd at fixed Hz | Loss → near-zero rates in logs | `QUEUED` |
| **M4.3** | StickMap profiles: at least two layouts for the same `GuidanceCommand` | Same cmd, different channel layouts; fixture-checked | `QUEUED` |
| **M4.4** | Mux: Xbox override always wins over auto `GuidanceCommand` | Flip override → auto rates ignored immediately | `QUEUED` |

Exit milestone when a CSV/plot of commands follows a waved marker, drops safe on occlusion, and yields to Xbox.

---

## Milestone M5 — Closed loop, then field

**Goal:** behavior in the real world. Only after M2.4 (manual fly) and M4 (safe auto commands).

| Step | Deliverable | Exit check | Status |
|---|---|---|---|
| **M5.1** | Indoor yaw-to-center (no chase) | Marker stays in central third for N seconds | `QUEUED` |
| **M5.2** | Translate toward static target using range proxy | Range proxy trends down without violent oscillation | `QUEUED` |
| **M5.3** | Chase moving cooperative target (hand-held marker / soft target) | Sustained track duration met | `QUEUED` |
| **M5.4** | Field: interceptor vs Haylon target drone, straight pass | Written hit/near-miss criteria + log package | `QUEUED` |
| **M5.5** | Stress: weave / erratic (reuse sim target behaviors as the **test plan**) | Same criteria under harder motion | `QUEUED` |

Soft calendar reminder: aim to *enter* field work late Oct / early Nov — which means **M2.4 must already be true**.

---

## Side track S — Sim & onboarding (never blocks M1–M5)

| Step | Deliverable | Exit check | Status |
|---|---|---|---|
| **S1** | One-page overview: “TX sends packets; Xbox first; vision later” | New teammate explains host→ELRS→FC in &lt;2 min | `QUEUED` |
| **S2** | Update sim HUD copy/legend so it does not imply the browser *is* the host stack | Narration matches `ARCHITECTURE.md` | `QUEUED` |
| **S3** | Optional: sim toggles for latency / lost-track once M3–M4 exist | Failure modes mirror host failsafes | `QUEUED` |
| **S4** | Optional: upgrade lead-pursuit → PN only if field data demands it | Better intercept stats, not prettier math | `QUEUED` |

---

## Out of scope (do not put on the critical path)

- Haylon battery system integration
- Recreating FC / ESC electronics
- Custom airframe as a prerequisite (nose-cone = exploratory only)
- Onboard neural nets before bench closed-loop works
- More Three.js polish as a substitute for M2–M4
- Vision polish as a substitute for Xbox→ELRS flight

---

## Current position

| Milestone | State |
|---|---|
| M0 | **Complete** |
| M1 | **Complete** |
| M2 | **Active** — M2.0 done (`ELRS_TX_PATH.md`); **M2.1** gamepad demo in `run_gamepad.py` (prove sticks → channels, then mark DONE) |
| M3 | Sense **ahead** — hand landmarks working; HUD simplified |
| M4–M5 | Queued / hardware-blocked as marked |
| Side track S | Optional |

### Do this next (only)

**M2.1 exit:** plug in an Xbox controller, run `python run_gamepad.py --hz 50`, confirm A/E/T/R µs move with sticks at ≥20 Hz. Then implement mock→live TX bridge (**M2.2**).

---

## How to advance a step

1. Take the single `NEXT` step (or lowest non-blocked `QUEUED` on the critical path).
2. Ship it in its own PR with pass/fail evidence (screenshot, log snippet, or short clip).
3. Mark the step `DONE` here in that PR; point `NEXT` at the following step.
4. Stop. Do not silently start the next milestone in the same PR.
