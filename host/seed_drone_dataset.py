"""Seed datasets/drone from fixture UAV images using YOLO-World auto-labels.

Weak labels — good enough to bootstrap fine-tune; replace with hand labels
from collect_drone_data.py for real accuracy.

  python seed_drone_dataset.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

import cv2

from collect_drone_data import _save_sample
from drone_detector import DroneObjectTracker
from track_estimate import BBox

HOST = Path(__file__).resolve().parent
FIX = HOST / "fixtures"
OUT = HOST / "datasets" / "drone"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for split in ("train", "val"):
        (OUT / "images" / split).mkdir(parents=True, exist_ok=True)
        (OUT / "labels" / split).mkdir(parents=True, exist_ok=True)

    yaml_path = OUT / "data.yaml"
    yaml_path.write_text(
        f"path: {OUT.resolve()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "names:\n"
        "  0: drone\n",
        encoding="utf-8",
    )

    tracker = DroneObjectTracker(conf=0.12, min_lock_conf=0.12, acquire_hits=1, lost_timeout_s=0.05)
    src = FIX / "accept_uav.jpg"
    if not src.is_file():
        print(f"missing {src}")
        return 1

    img = cv2.imread(str(src))
    assert img is not None
    track = None
    for i in range(3):
        track = tracker.update(img, float(i))
    if track is None or track.bbox is None or track.status != "TRACKING":
        print(f"FAIL could not auto-label {src}: {track}")
        return 1

    # Write several augmented crops/scales as weak seed
    n = 0
    h, w = img.shape[:2]
    variants = [img]
    # horizontal flip
    flip = cv2.flip(img, 1)
    variants.append(flip)
    # slight brightness
    bright = cv2.convertScaleAbs(img, alpha=1.15, beta=10)
    variants.append(bright)
    dark = cv2.convertScaleAbs(img, alpha=0.85, beta=-10)
    variants.append(dark)

    for i, variant in enumerate(variants):
        tracker.reset()
        t = None
        for k in range(3):
            t = tracker.update(variant, float(k))
        if t is None or t.bbox is None or t.status != "TRACKING":
            # fall back: reuse original bbox mirrored for flip
            if i == 1:
                b = track.bbox
                mirrored = BBox(w - b.x - b.w, b.y, b.w, b.h)
                _save_sample(variant, mirrored, OUT, f"seed_flip_{n:03d}")
                n += 1
            continue
        stem = f"seed_{n:03d}"
        path = _save_sample(variant, t.bbox, OUT, stem)
        print(f"seed {path}  {t.class_label} {t.confidence:.2f}")
        n += 1

    # Copy one sample to val
    train_imgs = sorted((OUT / "images" / "train").glob("*.jpg"))
    if train_imgs:
        src_img = train_imgs[0]
        src_lbl = OUT / "labels" / "train" / (src_img.stem + ".txt")
        shutil.copy2(src_img, OUT / "images" / "val" / src_img.name)
        if src_lbl.is_file():
            shutil.copy2(src_lbl, OUT / "labels" / "val" / src_lbl.name)
        print(f"val ← {src_img.name}")

    print(f"Done. train samples≈{n}  data={yaml_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
