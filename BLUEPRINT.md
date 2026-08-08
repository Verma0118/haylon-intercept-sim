# Intercept Simulation — Build Blueprint

> Purpose: pre-hardware demo for the Namin scoping call. Proves out the software architecture (launch detect → stabilize → track → guide) visually, before any CAD or real electronics exist. Hand this to Cursor as the build spec.

## Stack

- Vite + vanilla JS (or React if Cursor's project default) + **Three.js**
- No physics engine (cannon/rapier). This is a scripted state machine with per-phase kinematics, not general rigid-body sim — hand-rolled math is more controllable and has zero dependency risk.
- `requestAnimationFrame` loop, fixed-timestep physics update (e.g. 60Hz) decoupled from render rate.

## State machine

```
IDLE → THROWN → STABILIZING → TRACKING → INTERCEPT → HIT
                                              ↓
                                            MISS
                → (reset button returns to IDLE from any state)
```

| Transition | Trigger |
|---|---|
| IDLE → THROWN | "Throw" button / demo trigger |
| THROWN → STABILIZING | immediate (THROWN and STABILIZING share physics; STABILIZING is just the tail end where tumble has decayed below threshold) |
| STABILIZING → TRACKING | `angularVelocity magnitude < 5°/s` AND `elapsed > minStabilizeTime (e.g. 0.8s)` |
| TRACKING → INTERCEPT | after fixed dwell (~0.3s, purely so the HUD reads "acquired" before steering starts) |
| INTERCEPT → HIT | `distance(drone, target) < hitRadius` |
| INTERCEPT → MISS | closing speed negative for `> missTimeout` (e.g. 2s sustained), or hard flight-time cap |

Note on scope: this sim does **not** model the throw-detection classifier itself (the real IMU freefall-signature logic). It starts the state machine already inside THROWN with a randomized initial condition. The sim's job is to prove out what happens *after* detection fires correctly — stabilize, track, guide, intercept.

## Per-phase logic

### THROWN / STABILIZING

Real physics (this phase should look like an actual toss, not a scripted animation):

```
// on entering THROWN:
dronePos = handHeight (e.g. y=1.2)
droneVel = tossVelocity        // forward + upward impulse, tunable
angularVel = randomSpin()      // random axis, large magnitude — this is the tumble

// each frame, dt:
droneVel.y -= GRAVITY * dt
dronePos += droneVel * dt
angularVel *= exp(-STABILIZE_DAMPING * dt)   // represents attitude-hold PID converging
orientation = integrate(orientation, angularVel, dt)
```

`STABILIZE_DAMPING` is the one knob that makes this look convincing — tune until tumble visibly settles over ~0.8–1.2s, not instantly and not forever.

### TRACKING

No physics change — target becomes visible/highlighted in the HUD, dwell timer runs, guidance computes its first lead-point solution but doesn't steer yet. This phase exists for legibility, not because anything physically changes (sensor state is perfect/idealized per the "no simulated noise" call — real detection latency would live here in a future iteration).

### INTERCEPT (guidance — lead pursuit)

```
function computeLeadPoint(dronePos, droneSpeed, targetPos, targetVel):
    r = targetPos - dronePos
    tGo = length(r) / droneSpeed
    repeat 2-3 times:                     // converge the intercept estimate
        predicted = targetPos + targetVel * tGo
        tGo = length(predicted - dronePos) / droneSpeed
    return predicted

// each frame:
leadPoint = computeLeadPoint(...)
desiredDir = normalize(leadPoint - dronePos)
angleDelta = angleBetween(currentDir, desiredDir)
maxTurnThisFrame = TURN_RATE_LIMIT * dt
newDir = rotateToward(currentDir, desiredDir, min(angleDelta, maxTurnThisFrame))
speed = approach(speed, MAX_DRONE_SPEED, ACCEL, dt)
droneVel = newDir * speed
dronePos += droneVel * dt
```

Chose lead pursuit over true proportional navigation deliberately: same intercept outcome, far easier to narrate live on the call ("we lead the target like a quarterback leads a receiver"). Mention PN by name as the production-grade upgrade path if asked — don't need to defend the vector math live for a scoping call.

### Target behavior (user-selectable dropdown)

```
straight:
    targetPos += targetVel * dt   // constant velocity, no lateral term

weaving:
    targetPos = basePath(t) + AMPLITUDE * sin(FREQ * t) * lateralAxis

erratic:
    every ERRATIC_INTERVAL seconds: pick new random heading offset within a cone
    blend current heading toward new offset over ~0.3s (avoid instant snap, still reads as "juking")
```

Exposing this as a live dropdown mid-call is the point — if Namin asks "what if it dodges," you flip the dropdown, not the code.

## Tunable parameters (expose in a debug panel or const block)

| Param | Purpose |
|---|---|
| `tossVelocity` | initial throw impulse |
| `spinMagnitude` | how violent the tumble looks |
| `STABILIZE_DAMPING` | how fast tumble settles |
| `minStabilizeTime` | floor on stabilize phase length |
| `TURN_RATE_LIMIT` | drone's max turn rate — the "agility" knob |
| `MAX_DRONE_SPEED`, `ACCEL` | drone flight envelope |
| `targetSpeed`, `AMPLITUDE`, `FREQ` | weaving target shape |
| `ERRATIC_INTERVAL`, cone angle | erratic target aggressiveness |
| `hitRadius` | intercept success threshold |
| `missTimeout` | give-up condition |

## HUD / UI requirements

- Phase label, always visible, updates live (this is the whole pitch — the viewer should be able to read the state machine off the screen without narration)
- Telemetry: elapsed time, distance-to-target, closing speed, drone speed
- Target-behavior dropdown (straight / weaving / erratic)
- Throw / Reset controls
- Legend mapping HUD phases to the 4 real software modules discussed with Namin: Launch Detect → Stabilize → Track → Guidance — this is what ties the toy demo back to the actual architecture pitch
- Camera: orbit controls (drag to rotate, scroll to zoom) so you can reframe live if Namin wants a different angle

## Suggested file structure

```
src/
  main.js           // scene setup, render loop
  stateMachine.js    // phase enum + transition logic
  physics.js         // throw/stabilize kinematics
  guidance.js        // lead-pursuit + turn-rate steering
  target.js          // straight/weaving/erratic behaviors
  hud.js             // DOM overlay, telemetry, dropdown, buttons
  params.js          // all tunables in one place
```

## Explicit non-goals (don't build these into v1)

- No real throw-detection classifier (sim starts post-detection)
- No sensor noise/detection latency (perfect state assumed)
- No physics engine — hand-rolled kinematics only
- No true proportional navigation — lead pursuit only
