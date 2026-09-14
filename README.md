# Haylon Intercept Simulation

Pre-hardware demo sim for the Haylon interceptor drone project. Proves out the control *idea* (launch detect → stabilize → track → guide) visually, before any CAD or real electronics exist.

| Doc | What it’s for |
|---|---|
| `ARCHITECTURE.md` | Design source of truth — current sim map **and** real host→ELRS→FC stack |
| `ROADMAP.md` | Milestone build order (one proven step at a time) |
| `BLUEPRINT.md` | Spec for **this browser sim** only (state machine, physics, guidance math) |

Do not confuse a good-looking sim with a working interceptor architecture.

## Run

```bash
npm install
npm run dev
```

Open the local URL Vite prints (default `http://localhost:5173`).

- **Throw** / `Space` — start a toss (randomized tumble + inbound target)
- **Reset** / `R` — return to IDLE (also stops auto demo)
- **Preset** — Nominal / Weave stress / Erratic dodge / Forced miss
- Target dropdown — `straight` / `weaving` / `erratic` (live mid-flight)
- **Follow cam** — cinematic framing during flight (drag to orbit temporarily overrides)
- **Auto demo** / `A` — loops throws after HIT/MISS
- Drag to orbit, scroll to zoom
- Tunables panel — adjust flight envelope / target aggression live
