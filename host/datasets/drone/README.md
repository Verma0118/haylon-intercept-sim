# Drone fine-tune dataset

Single class `drone` in YOLO format.

## Bootstrap weak labels

```bash
python seed_drone_dataset.py
```

## Collect real frames (best)

```bash
python collect_drone_data.py --source 0
# TRACKING + press `s` to save image+label
```

## Train

```bash
python train_drone.py --epochs 30 --model yolov8n.pt
```

## Use

```bash
python run_detect.py --source 0 --weights runs/drone/weights/best.pt
python run_guide.py --mode drone --weights runs/drone/weights/best.pt
```

`images/` and `labels/` are gitignored — only this README + `data.yaml` are tracked.
Add real Haylon target footage here; weak seed labels are not field-ready.
