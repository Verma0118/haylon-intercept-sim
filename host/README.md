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

`run_capture.py` only shows the camera. **Tracking is this script.**

**Default = index finger.** Hold one finger up toward the laptop camera.

```bash
cd ~/haylon-intercept-sim/host
source .venv/bin/activate
git fetch origin && git checkout cursor/finger-origin-coords-822c && git pull

# Default: index fingertip (MediaPipe if installed, else OpenCV skin)
python run_finger_track.py --source 0 --mode finger --duration 0

# Force OpenCV skin fingertip (no MediaPipe)
python run_finger_track.py --source 0 --mode skin --duration 0
```

Optional **recommended** fingertip (much more stable):

```bash
python -m pip install mediapipe
python run_finger_track.py --source 0 --mode finger --duration 0
```

Hold your **index finger up**, palm toward the camera, a bit away from your face.
The terminal should print `backend: MediaPipe index fingertip`. If it prints
`OpenCV skin fingertip`, install mediapipe.

Success: steady green tip (not flashing), `TRACKING`, live `dx/dy`. `r` = reset, `q` = quit.
