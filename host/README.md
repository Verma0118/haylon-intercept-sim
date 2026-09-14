# Host control stack

Laptop-side software for the real interceptor pipeline (not the browser sim).

**Plain English:** a camera (on the drone, or a USB webcam on the desk) sends video to this laptop. The laptop finds the target and decides how to steer. Those steering desires become radio stick commands and go out over ELRS to the flight controller.

```
camera → Capture → Detect → Track → Guide → StickMap → ELRS TX → FC
```

| Doc / code | Purpose |
|---|---|
| [`contracts.md`](./contracts.md) | Frozen v0 message schemas (M1) |
| [`camera_frame.py`](./camera_frame.py) | `CameraFrame` dataclass |
| [`source.py`](./source.py) | Webcam / video file / synthetic sources |
| [`run_capture.py`](./run_capture.py) | **M2.1** Capture runner + FPS/latency overlay |
| [`../ARCHITECTURE.md`](../ARCHITECTURE.md) | Full design |
| [`../ROADMAP.md`](../ROADMAP.md) | Build order — next: **M2.2** detect |

## Setup

```bash
cd host
pip install -r requirements.txt
```

## Capture (M2.1)

```bash
# No camera needed (CI / cloud) — synthetic moving bar
python3 run_capture.py --source synthetic --duration 60 --headless

# Webcam (device 0), with preview window — press q to quit
python3 run_capture.py --source 0 --duration 0

# Video file (loops by default)
python3 run_capture.py --source path/to/clip.mp4 --duration 60 --headless
```

Pass/fail: median rolling FPS ≥ 15 after 1s warmup (roadmap exit for M2.1).

Optional: `--out annotated.mp4` writes frames with the HUD overlay.
