# Haylon Intercept Simulation

Pre-hardware demo sim for the Haylon interceptor drone project. Proves out the software architecture (launch detect → stabilize → track → guide) visually, before any CAD or real electronics exist.

See BLUEPRINT.md for the full build spec (state machine, physics, guidance math, tunables).

## Run

```bash
npm install
npm run dev
```

Open the local URL Vite prints (default `http://localhost:5173`).

- **Throw** / `Space` — start a toss (randomized tumble + inbound target)
- **Reset** / `R` — return to IDLE
- Target dropdown — `straight` / `weaving` / `erratic` (live mid-flight)
- Drag to orbit, scroll to zoom
- Tunables panel — adjust flight envelope / target aggression live
