"""Collect drone frames + YOLO labels for fine-tuning.

While TRACKING an accepted drone-family box, press **s** to save
image + YOLO txt label under datasets/drone/.

Also supports auto-save every N locked frames: --auto-every 15

Usage:
  python collect_drone_data.py --source 0
  python collect_drone_data.py --source 0 --auto-every 20 --weights runs/drone/weights/best.pt
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Optional

import cv2

from drone_detector import DroneObjectTracker
from run_capture import CaptureStats
from run_detect import draw_detect_hud
from source import make_source
from track_estimate import BBox

ROOT = Path(__file__).resolve().parent / "datasets" / "drone"


def _yolo_line(bbox: BBox, img_w: int, img_h: int, class_id: int = 0) -> str:
    cx = (bbox.x + bbox.w * 0.5) / img_w
    cy = (bbox.y + bbox.h * 0.5) / img_h
    nw = bbox.w / img_w
    nh = bbox.h / img_h
    return f"{class_id} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}\n"


def _save_sample(image, bbox: BBox, out_dir: Path, stem: str) -> Path:
    img_dir = out_dir / "images" / "train"
    lbl_dir = out_dir / "labels" / "train"
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    img_path = img_dir / f"{stem}.jpg"
    lbl_path = lbl_dir / f"{stem}.txt"
    h, w = image.shape[:2]
    cv2.imwrite(str(img_path), image)
    lbl_path.write_text(_yolo_line(bbox, w, h), encoding="utf-8")
    return img_path


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Collect drone training samples")
    p.add_argument("--source", default="0")
    p.add_argument("--out", default=str(ROOT))
    p.add_argument("--auto-every", type=int, default=0, help="Auto-save every N locked frames (0=manual s only)")
    p.add_argument("--weights", default="")
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--headless", action="store_true")
    args = p.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "images" / "train").mkdir(parents=True, exist_ok=True)
    (out / "labels" / "train").mkdir(parents=True, exist_ok=True)

    # Ensure data.yaml exists
    yaml_path = out / "data.yaml"
    if not yaml_path.is_file():
        yaml_path.write_text(
            "path: .\n"
            "train: images/train\n"
            "val: images/val\n"
            "names:\n"
            "  0: drone\n",
            encoding="utf-8",
        )

    print(
        f"collect → {out}\n"
        "  TRACKING + press s = save sample.  q=quit  r=reset\n"
        f"  auto-every={args.auto_every or 'off'}",
        flush=True,
    )

    source = make_source(args.source, loop_file=True)
    tracker = DroneObjectTracker(
        conf=args.conf,
        weights=args.weights.strip() or None,
        acquire_hits=2,
    )
    stats = CaptureStats()
    saved = 0
    locked_i = 0
    t0 = time.perf_counter()

    try:
        with source:
            while True:
                frame = source.read()
                if frame is None:
                    break
                stats.observe(frame.timestamp_ms)
                track = tracker.update(frame.data, frame.timestamp_ms)
                image = frame.data.copy()
                draw_detect_hud(image, stats, track, tracker)
                cv2.putText(
                    image,
                    f"saved {saved}   press s",
                    (12, image.shape[0] - 16),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (220, 220, 220),
                    1,
                    cv2.LINE_AA,
                )

                do_save = False
                if track.status == "TRACKING" and track.bbox is not None:
                    locked_i += 1
                    if args.auto_every > 0 and locked_i % args.auto_every == 0:
                        do_save = True

                if not args.headless:
                    cv2.imshow("haylon-collect", image)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        break
                    if key == ord("r"):
                        tracker.reset()
                    if key == ord("s") and track.status == "TRACKING" and track.bbox is not None:
                        do_save = True

                if do_save and track.bbox is not None:
                    stem = f"cap_{int(time.time() * 1000)}_{saved:04d}"
                    path = _save_sample(frame.data, track.bbox, out, stem)
                    saved += 1
                    print(f"saved {path}  class={track.class_label}", flush=True)
    finally:
        tracker.close()
        if not args.headless:
            cv2.destroyAllWindows()

    print(f"\nDone. saved={saved}  under {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
