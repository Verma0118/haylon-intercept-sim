# Host control stack

Laptop-side software for the real interceptor pipeline (not the browser sim).

**Plain English:** a camera (on the drone, or a USB webcam on the desk) sends video to this laptop. The laptop finds the target and decides how to steer. Those steering desires become radio stick commands and go out over ELRS to the flight controller.

```
camera → Capture → Detect → Track → Guide → StickMap → ELRS TX → FC
```

| Doc | Purpose |
|---|---|
| [`contracts.md`](./contracts.md) | Frozen v0 message schemas (M1) |
| [`../ARCHITECTURE.md`](../ARCHITECTURE.md) | Full design (sim vs host, ownership, open decisions) |
| [`../ROADMAP.md`](../ROADMAP.md) | Build order — next code step is **M2.1** (webcam capture) |

No runtime code in this folder yet. Contracts first; capture next.
