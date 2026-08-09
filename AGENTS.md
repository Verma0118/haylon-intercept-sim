# Haylon Intercept Simulation

Browser-based 3D demo (Three.js + Vite, vanilla JS ES modules) of an interceptor drone's
flight-software pipeline: launch detect → stabilize → track → guide. Entirely client-side;
there is no backend, database, or external service.

See `README.md` for the run/controls reference and `BLUEPRINT.md` for the design spec.

## Cursor Cloud specific instructions

- Single service only: the Vite dev server (`npm run dev`). Standard commands live in `package.json` (`dev`, `build`, `preview`); there is no lint config and no automated test suite.
- The dev server port is pinned to `5173` and binds all interfaces (`host: true` in `vite.config.js`), so it is reachable and hot-reload works after `npm install`.
- The app runs fully offline. The only external references are Google Fonts in `index.html`, which are cosmetic and fall back gracefully with no network access.
- Verify end-to-end by opening `http://localhost:5173/` and clicking **Throw** (or pressing `Space`): the HUD state machine should progress `IDLE → THROWN → STABILIZING → TRACKING → INTERCEPT` and resolve to `HIT`/`MISS`. Just loading the page is not sufficient to prove it works.
