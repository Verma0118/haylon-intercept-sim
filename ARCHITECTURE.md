# Haylon Interceptor — Architecture

This document is the design source of truth. It covers:

1. **What exists today** (browser sim in this repo)
2. **What must exist for the product to work** (host control stack)
3. **How those two relate** (so we stop mixing pitch demo with engineering)
4. **Contracts & open decisions** that control every later build step

`ROADMAP.md` is the build order. This file is the *what* and *why*.

---

## 1. Two systems (do not conflate them)

| | **Sim (this repo today)** | **Host stack (what must work)** |
|---|---|---|
| Purpose | Pitch / teach the control *idea* | Fly a real interceptor toward a real target |
| Runtime | Browser, Vite + Three.js, no backend | Laptop/host process + radio + FC |
| Sensing | God-mode world positions | Camera → detect → track |
| Actuation | Directly writes drone velocity/position | **Packets over an ELRS transmitter** → FC → motors |
| “Stabilize” | Fake tumble damping in JS | Stock flight-controller attitude hold + **pilot sticks to stop drift** |
| Success metric | Pretty HIT/MISS in a 3D scene | Closed-loop behavior on the bench, then field |

The sim is valuable. It is **not** the architecture that has to “truly work.”

---

## 2. Current architecture (sim — as implemented)

### 2.1 Pipeline the HUD narrates

```
IDLE → THROWN → STABILIZING → TRACKING → INTERCEPT → HIT
                                              ↘ MISS
```

Mapped to pitch modules via `PHASE_TO_MODULE` in `src/params.js`:

| Phase | Pitch module | What the code actually does |
|---|---|---|
| `THROWN` | Launch Detect | Button/Space starts a randomized toss; short hold so HUD can be read |
| `STABILIZING` | Stabilize | Gravity + exponential damping of angular velocity |
| `TRACKING` | Track | Still ballistic; dwell timer; compute lead point but **do not steer** |
| `INTERCEPT` | Guidance | Lead pursuit + turn-rate limit + accel; write `drone.vel` / `drone.pos` |
| `HIT` / `MISS` | Outcome | Distance &lt; `hitRadius`, or negative closing / time cap |

### 2.2 Runtime shape

```
┌─────────────────────────────────────────────────────────────┐
│ index.html  (#scene canvas + #hud root)                     │
└───────────────────────────────┬─────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│ src/main.js  — composition root                             │
│  • Three.js scene / meshes / lights                         │
│  • owns sm, drone, target, leadPoint                        │
│  • fixed timestep 60 Hz (FIXED_DT = 1/60)                   │
│  • wires HUD callbacks + keyboard                           │
└───────┬──────────┬──────────┬──────────┬──────────┬─────────┘
        │          │          │          │          │
        ▼          ▼          ▼          ▼          ▼
 stateMachine.js physics.js guidance.js target.js  hud.js
  (phases)     (toss/damp) (lead +     (behaviors) (DOM only)
                            steer)
        │          │          │          │
        └──────────┴──────────┴──────────┘
                         │
                         ▼
                   params.js  (shared mutable tunables)
```

Peer modules do **not** import each other. `main.js` is the only orchestrator. Everything reads/writes the shared `params` object.

### 2.3 Per-tick ownership

| Concern | Owner | Mutates |
|---|---|---|
| Phase transitions | `stateMachine.js` → `updateStateMachine` | `sm.*` |
| Toss / tumble / ballistic flight | `physics.js` → `updateThrowStabilize` | `drone.pos/vel/orientation/angularVel` |
| Lead pursuit + steering | `guidance.js` → `updateIntercept` | `drone.heading/speed/vel/pos/orientation` |
| Target motion | `target.js` → `updateTarget` | `target.pos/vel/...` |
| Telemetry (range, closing) | `main.js` telemetry helper | local numbers for HUD + SM |
| Presentation | mesh sync, `cameraFollow.js` → `updateFollowCamera`, `hud.update` | meshes / DOM |

### 2.4 What is deliberately fake (and fine for a pitch)

- No throw-detection classifier — mission starts on button
- No camera, bbox, or lost-track
- No latency / noise
- No radio, sticks, or FC
- Target state is perfect world-frame truth
- Guidance integrates kinematics directly (acts like a physics god, not a pilot)

Reusable ideas worth keeping later: phase vocabulary, turn-rate limiting, lead-pursuit kernel (`computeLeadPoint` in `guidance.js`), fixed-rate loop, target behavior scenarios as **test plans**.

---

## 3. Target architecture (host stack)

### 3.1 Plain English (read this first)

1. The interceptor already has a flight controller and an **ELRS receiver**. Attitude hold is mostly the FC’s job.
2. Quads still **drift**. A human (or later, software) must keep correcting with stick inputs so it doesn’t wander.
3. Those stick inputs leave the ground as **packets from an ELRS transmitter** to the drone. That is the only actuation path we own on the host.
4. **First live goal:** fly the drone around from a **laptop + Xbox controller**, with the laptop turning gamepad axes into TX packets. No vision required for that step.
5. Later, vision/guidance on the same laptop *replaces* (or shares) those stick packets — same TX path, different packet source.

### 3.2 Meeting constraints that define the design

- Software/control is the project; do **not** rebuild the drone from scratch
- Haylon supplies OTS interceptor (FC + ESC + **ELRS RX** already onboard) + a separate target drone
- **Vision runs on a host laptop**, not onboard the interceptor
- Host sends **control packets** via an ELRS TX (not motor PWM from the laptop)
- Control approach should be **portable across quad platforms**
- Battery integration out of scope; frame/nose-cone is optional side work
- Soft field window: late Oct → early Nov → means **manual host→TX flight first**, then vision closed-loop

### 3.3 System diagram

```
                    ┌──────────────────────────────────────────────┐
                    │                 HOST LAPTOP                  │
                    │                                              │
  Xbox controller ─►│  Gamepad → StickMap → ChannelFrame           │
  (first step)      │           │                                  │
                    │           │  (later also:)                   │
  Camera ──────────►│  Capture → Detect → Track → Guide ───────────┤
  (later)           │                         │                    │
                    │                    StickMap                  │
                    │                         │                    │
                    │              ELRS TX bridge (packets out)    │
                    └─────────────────────────┬────────────────────┘
                                              │  ELRS radio packets
                                              ▼
                                   ┌─────────────────────┐
                                   │ Interceptor FC + RX │
                                   │ (attitude, mixers)  │
                                   └──────────┬──────────┘
                                              ▼
                                           motors
```

**Mental model:** the transmitter is a packet pipe. Manual Xbox flight and autonomous guidance are two different *producers* of the same `ChannelFrame` stream.

### 3.4 Logical modules (production)

| Module | Runs on | Job | Does *not* do |
|---|---|---|---|
| **Gamepad / Operator** | Host | Read Xbox (or other) sticks; keep the craft from drifting by hand | Vision |
| **Capture** | Host | Frames in, timestamps, FPS/latency metrics | Detection |
| **Detect** | Host | “Is there a **drone** (vs clutter)?” → class + bbox | Long-term identity / fine-tuned net (later) |
| **Track** | Host | Temporal estimate + IoU continuity + `LOST` / reacquire | Steering |

**Detect quality ladder (do not skip):** open-vocab class gate (done) → stable lock + operator telemetry (done) → more real drone footage / optional fine-tune → `run_guide --mode drone` closed on StickMap → field.
| **Guide** | Host | Estimate → desired motion (rates / body cmds), rate-limited | Motor mixing |
| **StickMap / TX** | Host | Map commands → channel values; **send ELRS packets** | Vision |
| **Flight controller** | Drone | Attitude stabilize, arming, failsafe, mixers | Target recognition |
| **Operator override** | Human | Kill / take over sticks at any time | — |

### 3.5 Mapping pitch story → real ownership

The pitch still says Detect → Stabilize → Track → Guide. In hardware those words mean different owners:

| Pitch word | Who owns it for real | Notes |
|---|---|---|
| Launch Detect | **TBD** (operator / RC switch / IMU) — see open decisions | Sim’s `THROWN` is a stand-in |
| Stabilize | **Flight controller** (stock) + **stick corrections** so it does not drift | Host must not reinvent rate PID first; Xbox flight proves stick→packet→FC |
| Track | **Host vision** | Continuous estimate, not a HUD dwell |
| Guide | **Host guidance → same StickMap/TX path** | Replaces Xbox as packet source once vision works |
| Hit/Miss | Field criteria + logging | Not Euclidean god-mode distance |

---

## 4. Contracts (v0 — freeze before writing glue)

These are the seams that make the stack portable. **Normative detail** (units, ranges, examples) lives in [`host/contracts.md`](host/contracts.md). Summary below; change both files together.

### 4.1 `CameraFrame`

```
timestamp_ms: number
width: number
height: number
format: "rgb" | "bgr" | "gray" | "encoded"
data: bytes | handle        # implementation-defined buffer
frame_id: number
```

### 4.2 `TrackEstimate`

```
TrackEstimate:
  timestamp_ms: number
  status: "SEARCHING" | "TRACKING" | "LOST"
  track_id: number | null
  bbox: { x, y, w, h } | null     # pixels, image frame
  confidence: number              # 0..1
  class_label: string | null      # e.g. "drone" when class-aware detect locks
  # Optional later:
  bearing_rad: { yaw, pitch } | null
  range_proxy: number | null      # e.g. bbox area / marker size
```

### 4.3 `GuidanceCommand`

Platform-agnostic. **Not** Betaflight channel numbers.

```
GuidanceCommand:
  timestamp_ms: number
  mode: "IDLE" | "HOLD" | "TRACK_CENTER" | "INTERCEPT" | "ABORT"
  # Normalized body desires, each in [-1, 1] unless noted
  yaw_rate: number
  pitch_rate: number      # or tilt; document chosen convention
  roll_rate: number
  throttle: number        # 0..1
  flags: {
    operator_override: boolean
    lost_target: boolean
    link_ok: boolean
  }
```

Xbox sticks map into this same shape (or straight into `ChannelFrame` via StickMap) so auto guidance later is a drop-in producer.

### 4.4 `StickMap` → `ChannelFrame` → ELRS packets

```
StickMap:
  name: string                    # e.g. "betaflight_default"
  channel_order: [A, E, T, R, ...]
  scale: per-axis gains + limits
  deadbands: ...
  toChannels(cmd: GuidanceCommand) -> ChannelFrame  # µs (1000..2000) or CRSF units

ChannelFrame → TX bridge → ELRS packets on the air
```

### 4.5 Failsafe rules (must be explicit)

| Condition | Required behavior |
|---|---|
| `TrackEstimate.status == LOST` past timeout | `GuidanceCommand.mode = ABORT` or `HOLD`; rates → 0 |
| TX/link unhealthy | Operator/FC failsafe; host stops sending aggressive cmds |
| Operator override (Xbox / kill) | Host auto commands ignored or blended out immediately |
| Rate/throttle caps | Always applied in Guide or StickMap (never bypassed) |

---

## 5. Open decisions (answer these before overbuilding)

These change the roadmap if answered differently. Until decided, prefer the **default**.

| ID | Question | Default for NOBE (until Haylon says otherwise) | Blocks |
|---|---|---|---|
| **D1** | Mission start: throw-IMU vs RC switch vs operator button on host? | Operator / RC switch for bench; IMU throw later if Haylon requires product story | Launch Detect work, sim legend honesty |
| **D2** | Camera path: onboard FPV → ground receiver → host, or USB webcam stand-in? | Webcam stand-in until hardware arrives; design Capture behind an interface | Capture impl |
| **D3** | How does host drive ELRS TX? | **Laptop reads Xbox controller → StickMap → ELRS TX module/packets** (exact USB/CRSF bridge TBD in M2 research note) | Live radio / first flight |
| **D4** | Detect v0 target: ArUco / colored blob / phone / trained detector? | Phone / bright blob for desk demos; ArUco when available | Detect step |
| **D5** | Guidance output convention: body rates vs angle vs “stick percentages”? | Normalized rates + throttle (`GuidanceCommand` above) | StickMap |
| **D6** | Where does this host code live? Same repo vs `haylon-host/` package? | New `host/` directory in this repo until it outgrows it | Repo layout |

Do not spend weeks on neural detectors, onboard inference, or custom frames before **Xbox → ELRS packets → fly** works.

---

## 6. Non-goals (current phase)

- Replacing the flight controller or writing motor mixers
- Haylon battery integration
- Onboard neural inference as a prerequisite
- Perfecting the Three.js pitch demo instead of host→TX flight
- True proportional navigation before a dumb center-the-bbox controller works on the bench
- Treating vision demos as “done” while the craft still cannot be flown from the laptop

---

## 7. Definition: architecture “truly works”

**First proof (manual):**

1. Laptop reads an Xbox controller
2. Host publishes `ChannelFrame`s at a fixed rate and the ELRS TX sends packets
3. Operator can arm (per FC rules) and **fly / hover without uncontrolled drift** using the gamepad
4. Kill / override is boringly reliable

**Bench-complete (before treating field intercepts as validation):**

1. Host also ingests live frames through `CameraFrame`
2. Host produces `TrackEstimate` for a cooperative target (marker/blob/phone OK)
3. Host publishes `GuidanceCommand` at a fixed rate (target **20–50 Hz**) on the **same** StickMap → TX path
4. Failsafes in §4.5 are demonstrated
5. Swapping `StickMap` profile is enough to target a second FC setup (portability smoke test)

Field intercept vs Haylon’s target drone is **validation**, not the first proof.

---

## 8. How to change this document

- Architecture changes (seams, ownership, contracts) → update **this file** in the same PR as the code/doc that depends on them
- Sequencing / status of build steps → update **`ROADMAP.md`**
- Sim implementation details → **`BLUEPRINT.md`**
