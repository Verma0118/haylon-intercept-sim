# Haylon Interceptor — Build Roadmap

Companion to `ARCHITECTURE.md` (design source of truth).

**Rule:** one milestone exit at a time. A PR should advance at most one step unless the change is a tiny doc fix.

Status: `DONE` · `NEXT` · `QUEUED` · `BLOCKED`

---

## Why this roadmap exists

The browser sim already demonstrates a *story*: Detect → Stabilize → Track → Guide.
The 9/4 meeting defined a *machine*: **host vision → guidance → ELRS → FC**.

Those are different. This roadmap builds the machine slowly, without pretending the sim is done.

---

## Principles

1. **Ugly-but-real beats pretty-but-fake.** A webcam + logged stick commands outranks another HUD polish pass.
2. **Contracts before glue.** Freeze `CameraFrame` / `TrackEstimate` / `GuidanceCommand` / `StickMap` before wiring OpenCV to a radio.
3. **Hardware must not stall software.** Webcam + mock TX until drones/radios arrive.
4. **FC owns attitude.** Host steers with commands; do not rebuild stabilize PID first.
5. **Sim stays a teaching aid.** Only change it when it clarifies the real stack (legend, failure modes, test scenarios).
6. **Pass/fail or it didn’t happen.** Every step below has an exit check.

---

## Critical path (dependency order)

```
M0 Architecture docs ──► M1 Freeze contracts ──► M2 Host sense (cam→track)
                                                    │
                                                    ▼
                                              M3 Guide + failsafe (commands logged)
                                                    │
                                                    ▼
                                              M4 TX bridge (mock → live ELRS)
                                                    │
                                                    ▼
                                              M5 Bench closed-loop → field
```

Optional parallel (never blocks critical path): sim legend honesty, one-pager for onboarding, nose-cone exploration, Haylon hardware shipping.

---

## Milestone M0 — Shared picture

| Step | Deliverable | Exit check | Status |
|---|---|---|---|
| **M0.1** | `ARCHITECTURE.md` — current sim map + target host stack + contracts draft + open decisions | Someone new can explain both systems and where they differ | `DONE` |
| **M0.2** | This roadmap rewritten against milestones (not a grab-bag checklist) | Critical path above is the agreed order | `DONE` |

---

## Milestone M1 — Freeze the seams

**Goal:** agree the messages so later PRs do not invent ad-hoc dicts.

| Step | Deliverable | Exit check | Status |
|---|---|---|---|
| **M1.1** | Formalize v0 schemas from `ARCHITECTURE.md` §4 into `host/contracts.md` (or JSON Schema) — field names, units, ranges | Schemas reviewed once; no code depends on conflicting shapes | `DONE` |
| **M1.2** | Record defaults for open decisions D1–D6 in `ARCHITECTURE.md` §5 (update if Haylon overrides) | Each decision has a written default | `DONE` |
| **M1.3** | Decide repo layout (`host/` in this repo vs separate) — default: `host/` | Folder exists with README stub pointing at contracts | `DONE` |

**Why before webcam code:** without this, detect demos glue pixels straight to “channels” and become unportable — which violates the meeting.

---

## Milestone M2 — Host can see

**Goal:** prove the host process exists and can produce a `TrackEstimate`. No drone required.

| Step | Deliverable | Exit check | Status |
|---|---|---|---|
| **M2.1** | Capture: open webcam (or video file), emit `CameraFrame`, overlay FPS + e2e latency | ≥15 FPS stable for 60s | `DONE` |
| **M2.2** | Detect v0: fingertip / target point → `TrackEstimate` with live `(x,y)` (skin default; MediaPipe/color optional) | Finger/target in frame → coords that move with the target | `DONE` |
| **M2.3** | Track v0: id + `SEARCHING/TRACKING/LOST` + timeout | Occlude ~1s → `LOST`; reappear → reacquire | `NEXT` |

Exit milestone when a laptop demo shows live frames + track status without crashing for several minutes.

---

## Milestone M3 — Host can decide

**Goal:** turn track into safe `GuidanceCommand`s. Still no radio required.

| Step | Deliverable | Exit check | Status |
|---|---|---|---|
| **M3.1** | Guide v0: keep target centered → yaw/pitch rates (+ optional throttle hold), with rate limits | Move marker left → opposite-sign yaw command; saturates at cap | `QUEUED` |
| **M3.2** | Failsafe: on `LOST`, commands go idle/hold within one publish cycle; log every cmd at fixed Hz | Loss → near-zero rates in logs | `QUEUED` |
| **M3.3** | StickMap v0: two profiles (`betaflight_default`, `alternate`) mapping the same `GuidanceCommand` → channels | Same cmd, different channel layouts; checked with a fixture | `QUEUED` |

Exit milestone when a CSV/plot of commands clearly follows a waved marker and drops safe on occlusion.

---

## Milestone M4 — Host can talk to a radio

**Goal:** get commands onto ELRS. Mock first; live when hardware exists.

| Step | Deliverable | Exit check | Status |
|---|---|---|---|
| **M4.0** | Research note for D3: exact TX drive path for Haylon’s platform | One chosen approach + links | `QUEUED` (may be `BLOCKED` on platform info) |
| **M4.1** | Mock TX: write channel frames to virtual serial / file; decode/verify | Round-trip decode matches | `QUEUED` |
| **M4.2** | Live TX, **disarmed**: host moves FC channel monitor / RX output | Channels respond; kill/override works | `BLOCKED` on hardware |
| **M4.3** | Restrained/armed bench: attitude responds to host yaw/roll | Safe, repeatable; operator always wins | `BLOCKED` on hardware |

Exit milestone at **M4.3**. Do not start chasing targets until channels and override are boringly reliable.

---

## Milestone M5 — Closed loop, then field

**Goal:** behavior in the real world. Only after M4.

| Step | Deliverable | Exit check | Status |
|---|---|---|---|
| **M5.1** | Indoor yaw-to-center (no chase) | Marker stays in central third for N seconds | `QUEUED` |
| **M5.2** | Translate toward static target using range proxy | Range proxy trends down without violent oscillation | `QUEUED` |
| **M5.3** | Chase moving cooperative target (hand-held marker / soft target) | Sustained track duration met | `QUEUED` |
| **M5.4** | Field: interceptor vs Haylon target drone, straight pass | Written hit/near-miss criteria + log package | `QUEUED` |
| **M5.5** | Stress: weave / erratic (reuse sim target behaviors as the **test plan**) | Same criteria under harder motion | `QUEUED` |

Soft calendar reminder from 9/4: aim to *enter* field work late Oct / early Nov — which means M4.3 should already be true.

---

## Side track S — Sim & onboarding (never blocks M1–M5)

| Step | Deliverable | Exit check | Status |
|---|---|---|---|
| **S1** | One-page overview for NOBE onboarding (meeting action; can draft here, Haylon may own final) | New teammate explains host→ELRS→FC in &lt;2 min | `QUEUED` |
| **S2** | Update sim HUD copy/legend so it does not imply the browser *is* the host stack | Narration matches `ARCHITECTURE.md` | `QUEUED` |
| **S3** | Optional: sim toggles for latency / lost-track once M2–M3 exist | Failure modes mirror host failsafes | `QUEUED` |
| **S4** | Optional: upgrade lead-pursuit → PN only if field data demands it | Better intercept stats, not prettier math | `QUEUED` |

---

## Out of scope (do not put on the critical path)

- Haylon battery system integration
- Recreating FC / ESC electronics
- Custom airframe as a prerequisite (nose-cone = exploratory only)
- Onboard neural nets before bench closed-loop works
- More Three.js polish as a substitute for M2–M4

---

## Current position

| Milestone | State |
|---|---|
| M0 | **Complete** |
| M1 | **Complete** (`host/contracts.md` + `host/README.md`; D1–D6 defaults already in Architecture §5) |
| M2 | **Active** — **M2.1–M2.2 done** (capture + fingertip coords); next **M2.3** (LOST timeout polish) |
| M3–M5 | Queued / hardware-blocked as marked |
| Side track S | Optional |

### Do this next (only)

**M2.3 — Track lock polish:** keep `SEARCHING/TRACKING/LOST` honest under occlusion (~1s → LOST, then reacquire).

---

## How to advance a step

1. Take the single `NEXT` step (or lowest non-blocked `QUEUED` on the critical path).
2. Ship it in its own PR with pass/fail evidence (screenshot, log snippet, or short clip).
3. Mark the step `DONE` here in that PR; point `NEXT` at the following step.
4. Stop. Do not silently start the next milestone in the same PR.
