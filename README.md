# Haylon Intercept Simulation

Pre-hardware demo sim for the Haylon interceptor drone project. Proves out the software architecture (launch detect → stabilize → track → guide) visually, before any CAD or real electronics exist.

See BLUEPRINT.md for the full build spec (state machine, physics, guidance math, tunables).

For the **real** host-vision → ELRS → FC build path (from the 9/4 Namin meeting), see ROADMAP.md — one proven step at a time; do not confuse this sim with a working architecture.

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
