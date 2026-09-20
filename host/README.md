# Host control stack

Laptop-side software for the real interceptor pipeline (not the browser sim).

**Plain English:** the ELRS transmitter sends **packets** to the drone. A human (Xbox on this laptop) or later software fills those packets so the craft does not drift. Vision is the later packet source — not the first step.

```
Xbox (first) ──► StickMap → ChannelFrame → ELRS TX packets → FC
Camera (later) → Capture → Detect → Track → Guide ──┘
```

| Doc / code | Purpose |
|---|---|
| [`contracts.md`](./contracts.md) | Frozen v0 message schemas (M1) |
| [`camera_frame.py`](./camera_frame.py) | `CameraFrame` dataclass |
| [`track_estimate.py`](./track_estimate.py) | `TrackEstimate` / `BBox` |
| [`source.py`](./source.py) | Webcam / video file / synthetic sources |
| [`run_capture.py`](./run_capture.py) | **M2.1** Capture runner + FPS/latency overlay |
| [`finger_tracker.py`](./finger_tracker.py) | Skin / MediaPipe / color detectors |
| [`run_finger_track.py`](./run_finger_track.py) | **M2.2** Live fingertip coords on camera |
| [`../ARCHITECTURE.md`](../ARCHITECTURE.md) | Full design |
| [`../ROADMAP.md`](../ROADMAP.md) | Build order — next: **M2.0** Xbox → ELRS TX path |

## Setup

```bash
cd ~/haylon-intercept-sim/host
pip3 install -r requirements.txt
```

### Mac webcam (your laptop camera)

`requirements.txt` installs **headless** OpenCV (fine for CI / synthetic). For a real Mac camera + preview window, also install the full build:

```bash
pip3 uninstall -y opencv-python-headless
pip3 install opencv-python
```

Then allow camera access:

1. **System Settings → Privacy & Security → Camera**
2. Turn **on** for **Terminal** (or iTerm / Cursor)
3. **Quit Terminal completely** (Cmd+Q) and reopen

## Capture (M2.1)

```bash
cd ~/haylon-intercept-sim/host

# No camera needed — synthetic moving bar (cloud demos)
python3 run_capture.py --source synthetic --duration 60 --headless

# Mac camera, with preview window — press q to quit
python3 run_capture.py --source 0 --duration 0

# Video file (loops by default)
python3 run_capture.py --source clip.mp4 --duration 60 --headless
```

Pass/fail: median rolling FPS ≥ 15 after 1s warmup (roadmap exit for M2.1).

Optional: `--out annotated.mp4` writes frames with the HUD overlay.

## Target track (M2.2) — live coordinates

Rudimentary “where is the intercept target?” signal.

**Default is phone lock** — finds a very dark phone-shaped rectangle (black phone /
black screen). Hold the phone upright toward the camera.

```bash
cd ~/haylon-intercept-sim/host
git pull origin cursor/phone-hud-fix-822c   # or main once merged

# Default: track a phone
python3 run_finger_track.py --source 0 --mode phone --duration 0

# Fallbacks if needed
python3 run_finger_track.py --source 0 --mode color --hue 90 --duration 0   # bright tape
python3 run_finger_track.py --source 0 --mode two --duration 0              # peace-sign
```

Tips:
- Use a **black phone / black screen** (not a bright white wallpaper)
- Hold it **upright and flat** toward the camera, filling ~5–15% of the frame
- Keep it a bit away from dark hair/hoodies if lock jumps
- Press **`r`** to reset lock, **`q`** to quit
- HUD is a dark panel top-left (no smeared outline text)
