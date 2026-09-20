# Host control stack

Laptop-side software for the real interceptor pipeline (not the browser sim).

## Setup (Mac)

```bash
cd ~/haylon-intercept-sim
git fetch origin && git checkout cursor/yolo-hand-track-822c && git pull
cd host

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip

# Core only (hand landmarks). Do NOT install opencv-python-headless.
python -m pip uninstall -y opencv-python opencv-python-headless opencv-contrib-python mediapipe
python -m pip install --force-reinstall "opencv-python==4.10.0.84" "numpy>=1.24"
python -m pip install -r requirements.txt

# Must print: 4.10.0 True True
python -c "import cv2; print(cv2.__version__, hasattr(cv2,'dnn'), hasattr(cv2,'imshow'))"
```

If you see `False` for `dnn` or `imshow`, OpenCV is still broken — repeat the uninstall/reinstall lines.

### Optional YOLOv8 (large: pulls torch)

```bash
python -m pip install -r requirements-yolo.txt
```

## Accurate hand track (recommended)

```bash
source .venv/bin/activate
python run_finger_track.py --source 0 --mode hand --duration 0
```

First run downloads OpenCV Zoo ONNX models (~8MB). Hold your hand toward the
camera. Expect `backend: OpenCV Zoo hand landmarks` and a steady green tip.

```bash
# Optional YOLO (after requirements-yolo.txt)
python run_finger_track.py --source 0 --mode yolo --duration 0
```

`r` = reset, `q` = quit.

| Field | Meaning |
|---|---|
| `origin` | Image center (crosshair) |
| `frame dx,dy` | Offset from origin (+X right, +Y up) |

## Capture only

```bash
python run_capture.py --source 0 --duration 0
```
