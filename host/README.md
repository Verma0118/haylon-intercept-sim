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
| [`run_finger_track.py`](./run_finger_track.py) | **OpenCV lock** — green box + live `(x,y)` |
| [`finger_tracker.py`](./finger_tracker.py) | face / motion / phone / color / … detectors |
| [`../ARCHITECTURE.md`](../ARCHITECTURE.md) | Full design |
| [`../ROADMAP.md`](../ROADMAP.md) | Build order — next: **M2.0** Xbox → ELRS TX path |

## Setup (venv — avoids Mac `No module named 'cv2'`)

Use a **venv** so `pip` and `python` stay the same (Mac often has several Pythons; plain `pip3` / `python3` can disagree and you get `No module named 'cv2'`).

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

## 2) Track something (green box + coordinates)

**Default = OpenCV face lock.** Sit in front of the laptop camera.

```bash
cd ~/haylon-intercept-sim/host
source .venv/bin/activate
git pull origin cursor/opencv-face-track-822c   # or main once merged

python run_finger_track.py --source 0 --mode face --duration 0
```

Success looks like:
- HUD status **`TRACKING`**
- Green rectangle on your face + line from crosshair
- Terminal prints `xy=(…,…)` each second
- `r` = reset lock, `q` = quit

Other modes:

```bash
python run_finger_track.py --source 0 --mode motion --duration 0   # wave your hand
python run_finger_track.py --source 0 --mode phone --duration 0    # black phone upright
python run_finger_track.py --source 0 --mode color --hue 90 --duration 0
```
