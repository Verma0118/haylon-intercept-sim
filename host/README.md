# Host control stack

Laptop-side software for the real interceptor pipeline (not the browser sim).

```
Xbox (first) ──► StickMap → ChannelFrame → ELRS TX packets → FC
Camera (later) → Capture → Detect → Track → Guide ──┘
```

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

## Accurate hand track

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python run_finger_track.py --source 0 --mode hand --duration 0
```

HUD shows only **status**, **where** (e.g. `right 80  up 40`), and **fps**.

## Xbox gamepad → mock TX (M2.1)

Next building block after vision: prove sticks become channel packets (logged).

```bash
python -m pip install pygame
python run_gamepad.py --hz 50
# optional CSV: python run_gamepad.py --out channels.csv
```

Plug in an Xbox controller (USB or Bluetooth). Move sticks — terminal prints
A/E/T/R in µs. **B** = kill. See [`ELRS_TX_PATH.md`](./ELRS_TX_PATH.md) for the
radio path (M2.0).

## Capture only (no tracking)

```bash
python run_capture.py --source 0 --duration 0
```
