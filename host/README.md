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

## Class-aware drone detect (M3.4+)

Hand track finds a tip — it does **not** know drone vs person. This mode does:

```bash
python -m pip install -r requirements-yolo.txt   # if needed
# weights: host/yolov8s-worldv2.pt (or auto-download)
python run_detect.py --source 0
python check_drone_detect.py   # fixture: bus=reject, UAV photo=accept
```

HUD shows **status, class/conf, offset (+norm), size/range, top reject, lock age, infer/lat/fps**.

Green boxes = accepted (`drone` / `quadcopter` / `UAV` / `aircraft`). Red = reject
(`person`, `bottle`, …) and never become the track lock. Lock prefers IoU continuity
with the previous box. Also: `python run_finger_track.py --mode drone`.

Tune: `--conf 0.25 --min-lock-conf 0.30 --acquire-hits 3 --imgsz 640`.

### Better drone data / fine-tune

```bash
python seed_drone_dataset.py              # weak labels from fixture UAV
python collect_drone_data.py --source 0   # press s while TRACKING (real data)
python train_drone.py --epochs 30 --model yolov8n.pt
python run_detect.py --source 0 --weights runs/drone/weights/best.pt
```

See [`datasets/drone/README.md`](./datasets/drone/README.md).

## Xbox gamepad → mock TX (M2.1) — when you have a controller

```bash
python -m pip install pygame
python run_gamepad.py --hz 50
# optional CSV / StickMap profile:
python run_gamepad.py --out channels.csv --profile taer
```

Plug in an Xbox controller (USB or Bluetooth). Move sticks — terminal prints
channel µs. **B** = kill. See [`ELRS_TX_PATH.md`](./ELRS_TX_PATH.md) for the
radio path (M2.0).

## Guide without Xbox (M4.1) — class + AETR on one HUD

**Desk demo (water bottle):**

```bash
git fetch origin && git checkout cursor/bottle-demo-822c && git pull
cd host && source .venv/bin/activate
python run_guide.py --source 0 --mode bottle
```

Hold a water bottle in frame → `TRACKING` / `see bottle`. Wave it left/right of
center → AETR yaw moves. No drone needed.

**Drone path** (default `--mode drone`):

```bash
python run_guide.py --source 0 --mode drone --out-tx mock_tx.jsonl
# optional fine-tuned weights:
python run_guide.py --mode drone --weights runs/drone/weights/best.pt
```

HUD shows **see (class/conf) → offset → steer → AETR µs** together. Nothing flies
until live ELRS (M2.3) — this only writes the mock TX file.
### StickMap profiles (M4.3)

Same `GuidanceCommand`, different channel layouts:

| Profile | Order (ch0..ch3) |
|---|---|
| `betaflight_default` / `aetr` | roll, pitch, throttle, yaw |
| `taer` | throttle, roll, pitch, yaw |

```bash
python check_stickmap_profiles.py
```

## Capture only (no tracking)

```bash
python run_capture.py --source 0 --duration 0
```
