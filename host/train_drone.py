"""Fine-tune YOLOv8 on datasets/drone (single class: drone).

Bootstrap:
  python seed_drone_dataset.py
  python collect_drone_data.py --source 0    # add real frames (press s)

Train:
  python train_drone.py --epochs 30 --model yolov8n.pt

Use weights:
  python run_detect.py --source 0 --weights runs/drone/weights/best.pt
  python run_guide.py --mode drone --weights runs/drone/weights/best.pt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Fine-tune YOLOv8 drone detector")
    p.add_argument("--data", default="datasets/drone/data.yaml")
    p.add_argument("--model", default="yolov8n.pt", help="Base checkpoint")
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--device", default="", help="cuda|cpu|mps — empty = auto")
    p.add_argument("--name", default="drone")
    args = p.parse_args(argv)

    data = Path(args.data)
    if not data.is_file():
        print(
            f"Missing {data}. Run: python seed_drone_dataset.py "
            "and/or python collect_drone_data.py",
            file=sys.stderr,
        )
        return 1

    try:
        from ultralytics import YOLO
    except ImportError:
        print("pip install -r requirements-yolo.txt", file=sys.stderr)
        return 1

    model = YOLO(args.model)
    kwargs = dict(
        data=str(data.resolve()),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project=str(Path(__file__).resolve().parent / "runs"),
        name=args.name,
        exist_ok=True,
    )
    if args.device:
        kwargs["device"] = args.device

    print(f"train  data={data}  base={args.model}  epochs={args.epochs}", flush=True)
    results = model.train(**kwargs)
    best = Path(results.save_dir) / "weights" / "best.pt"
    print(f"\nDone. best weights → {best}")
    print(f"  python run_guide.py --mode drone --weights {best}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
