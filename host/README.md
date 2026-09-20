# Host control stack

Laptop-side software for the real interceptor pipeline (not the browser sim).

```
Xbox (first) ──► StickMap → ChannelFrame → ELRS TX packets → FC
Camera (later) → Capture → Detect → Track → Guide ──┘
```

## Setup

```bash
cd ~/haylon-intercept-sim
git pull origin main
cd host

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt

# Mac camera window:
python -m pip uninstall -y opencv-python-headless
python -m pip install "opencv-python>=4.8,<5"
```

If `import cv2` fails after a bad mediapipe install:

```bash
python -m pip uninstall -y mediapipe opencv-contrib-python opencv-python opencv-python-headless
python -m pip install --force-reinstall "opencv-python==4.10.0.84"
python -c "import cv2; print(cv2.__version__)"
```

## Accurate finger track (recommended)

Uses **OpenCV Zoo** palm + hand-pose ONNX models (from
[opencv/opencv_zoo](https://github.com/opencv/opencv_zoo)) — real index-fingertip
landmarks, **no** broken `pip install mediapipe`.

```bash
cd ~/haylon-intercept-sim/host
source .venv/bin/activate
git fetch origin && git checkout cursor/yolo-hand-track-822c && git pull

# Default: accurate index tip (downloads ONNX models on first run)
python run_finger_track.py --source 0 --mode hand --duration 0

# YOLOv8 hand detect (Ultralytics; downloads weights on first run)
python run_finger_track.py --source 0 --mode yolo --duration 0
```

Hold your hand toward the camera. Expect `backend: OpenCV Zoo hand landmarks`
and a **steady** green tip on your index finger with live `frame dx/dy`.

| Field | Meaning |
|---|---|
| `origin` | Image center (crosshair) |
| `image x,y` | Pixels from top-left |
| `frame dx,dy` | Offset from origin (+X right, +Y up) |
| `norm nx,ny` | ≈±1 at frame edge |

`r` = reset, `q` = quit.

## Capture only (no tracking)

```bash
python run_capture.py --source 0 --duration 0
```
