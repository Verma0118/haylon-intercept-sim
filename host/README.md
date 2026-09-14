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
| [`track_estimate.py`](./track_estimate.py) | `TrackEstimate` / `BBox` |
| [`source.py`](./source.py) | Webcam / video file / synthetic sources |
| [`run_capture.py`](./run_capture.py) | **M2.1** Capture runner + FPS/latency overlay |
| [`finger_tracker.py`](./finger_tracker.py) | Skin / MediaPipe / color detectors |
| [`run_finger_track.py`](./run_finger_track.py) | **M2.2** Live fingertip coords on camera |
| [`../ARCHITECTURE.md`](../ARCHITECTURE.md) | Full design |
| [`../ROADMAP.md`](../ROADMAP.md) | Build order — next: **M2.3** track lock timeout |

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

## Finger track (M2.2) — live target coordinates

Rudimentary “where is the intercept target?” signal: a point `(x, y)` that should follow your fingertip.

```bash
cd ~/haylon-intercept-sim/host

# Improved skin mode (ignores huge face/torso blobs, locks near last tip)
python3 run_finger_track.py --source 0 --mode skin --duration 0

# Most reliable no-ML option: put bright green/cyan tape on a fingertip
python3 run_finger_track.py --source 0 --mode color --hue 90 --duration 0

# Best quality if MediaPipe installs on your Mac
# pip3 install mediapipe
python3 run_finger_track.py --source 0 --mode finger --duration 0
```

**Tips if it looks confused**
- Hold **one finger up**, away from your face
- Plain `skin` mode gets confused by faces/arms — that’s expected; use **`--mode color`** with tape for a clean demo
- Once it locks, keep the tip moving smoothly (it searches in a small radius around the last tip)

HUD shows status, pixel `x/y`, center offset `nx/ny`, and rough bearing. Press **q** to quit.
