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
| [`run_capture.py`](./run_capture.py) | Camera only (FPS) — **does not track** |
| [`run_finger_track.py`](./run_finger_track.py) | **Finger lock** — center-origin coords (`dx/dy`, norm, bearing) |
| [`frame_coords.py`](./frame_coords.py) | Image → guidance-frame coordinate helper |
| [`finger_tracker.py`](./finger_tracker.py) | finger / skin / face / phone / … detectors |
| [`../ARCHITECTURE.md`](../ARCHITECTURE.md) | Full design |
| [`../ROADMAP.md`](../ROADMAP.md) | Build order — next: **M2.0** Xbox → ELRS TX path |

## Setup (venv — avoids Mac `No module named 'cv2'`)

```bash
cd ~/haylon-intercept-sim
git pull origin main
cd host

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt

# Mac preview window:
python -m pip uninstall -y opencv-python-headless
python -m pip install opencv-python
```

Allow **Camera** for Terminal (System Settings → Privacy & Security), then reopen Terminal and `source .venv/bin/activate` again.

```bash
python -c "import cv2; print(cv2.__version__)"
```

## 1) Capture only (camera + FPS)

```bash
source .venv/bin/activate
python run_capture.py --source 0 --duration 0          # q = quit
python run_capture.py --source synthetic --duration 5 --headless
```

This does **not** draw a target box. For that, use step 2.

## 2) Finger track — live coordinates (center origin)

**Default = OpenCV skin fingertip** (no MediaPipe). MediaPipe often fails to
install on Mac Python 3.9 — skip it.

```bash
cd ~/haylon-intercept-sim/host
source .venv/bin/activate
git fetch origin && git checkout cursor/finger-origin-coords-822c && git pull

# If a bad mediapipe install left things messy (No module named 'cv2'):
python -m pip uninstall -y mediapipe opencv-contrib-python opencv-python opencv-python-headless
python -m pip install --force-reinstall "opencv-python==4.10.0.84"
python -c "import cv2; print(cv2.__version__)"

# Run fingertip track (no mediapipe)
python run_finger_track.py --source 0 --mode skin --duration 0
```

Hold your **index finger up**, palm toward the camera, a bit away from your face /
bright windows. Expect a **steady** green tip + `TRACKING` + live `dx/dy`.

**Coordinate reference (O / +X / +Y on screen):**

| Name | Meaning |
|---|---|
| `origin` | Image center (crosshair) — guidance zero |
| `image x,y` | OpenCV pixels from top-left |
| `frame dx,dy` | Offset from origin — **+X right, +Y up** |
| `norm nx,ny` | ≈±1 at the frame edge |
| `bearing` | yaw/pitch (rad) from the same offsets |

`r` = reset lock, `q` = quit.

### Optional: MediaPipe (only if skin is not enough)

On many Macs `pip install mediapipe` crashes (bogus `∂` in a test file). Prefer skin.
If you still want it on Python 3.10+:

```bash
python -m pip install "mediapipe==0.10.14" --no-compile
python run_finger_track.py --source 0 --mode finger --duration 0
```
