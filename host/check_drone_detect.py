"""M3.4 fixture — accept drone-family, reject person scene.

Run:  python check_drone_detect.py
Needs ultralytics + yolov8s-worldv2.pt (see requirements-yolo.txt).
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import cv2

from drone_detector import DroneObjectTracker

FIX = Path(__file__).resolve().parent / "fixtures"
FIX.mkdir(parents=True, exist_ok=True)


def _download(url: str, dest: Path) -> Path:
    if dest.is_file() and dest.stat().st_size > 1000:
        return dest
    print(f"Downloading {dest.name} …", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        dest.write_bytes(r.read())
    return dest


def main() -> int:
    # Person-heavy scene (must NOT lock as drone)
    bus = _download(
        "https://ultralytics.com/images/bus.jpg",
        FIX / "reject_bus.jpg",
    )
    # UAV-ish photo (YOLO-World often labels as aircraft — in accept set)
    drone = _download(
        "https://images.unsplash.com/photo-1473968512647-3e447244af8f?w=640",
        FIX / "accept_uav.jpg",
    )

    tracker = DroneObjectTracker(conf=0.15, lost_timeout_s=0.1)
    tracker.reset()

    bus_img = cv2.imread(str(bus))
    assert bus_img is not None
    # Warm-up + acquire hits
    for i in range(4):
        est = tracker.update(bus_img, float(i))
    bus_dets = list(tracker.last_detections)
    bus_accepted = [d for d in bus_dets if d.accepted]
    if est.status == "TRACKING" and est.class_label:
        print(
            f"FAIL bus scene locked as {est.class_label!r} (should reject)",
            file=sys.stderr,
        )
        return 1
    if any(d.label.lower() in {"person", "hand"} for d in bus_dets) is False:
        print("WARN: no person/hand on bus — detector may have changed", file=sys.stderr)
    if bus_accepted:
        print(f"FAIL bus produced accepted dets: {bus_accepted}", file=sys.stderr)
        return 1

    tracker.reset()
    drone_img = cv2.imread(str(drone))
    assert drone_img is not None
    est = None
    for i in range(4):
        est = tracker.update(drone_img, 100.0 + i)
    ok_dets = [d for d in tracker.last_detections if d.accepted]
    if not ok_dets and est is not None and est.status != "TRACKING":
        # Soft fail with diagnostic — image CDN may change
        print(
            f"FAIL UAV image: no accepted detection. dets={[(d.label, round(d.confidence,2), d.accepted) for d in tracker.last_detections]}",
            file=sys.stderr,
        )
        return 1
    if est is None or est.status != "TRACKING" or not est.class_label:
        print(
            f"FAIL UAV image: expected TRACKING with class_label, got {est}",
            file=sys.stderr,
        )
        return 1

    report = {
        "bus": {
            "status": "pending",
            "class_label": None,
            "detections": [
                {"label": d.label, "conf": round(d.confidence, 3), "accepted": d.accepted}
                for d in bus_dets[:8]
            ],
        },
        "uav": {
            "status": est.status,
            "class_label": est.class_label,
            "detections": [
                {"label": d.label, "conf": round(d.confidence, 3), "accepted": d.accepted}
                for d in tracker.last_detections[:8]
            ],
        },
    }
    tracker.reset()
    bus_est = None
    for i in range(4):
        bus_est = tracker.update(bus_img, float(i))
    assert bus_est is not None
    report["bus"]["status"] = bus_est.status
    report["bus"]["class_label"] = bus_est.class_label

    out = FIX / "drone_detect_report.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"PASS  bus={report['bus']['status']} (no drone lock)  "
        f"uav={report['uav']['status']} class={report['uav']['class_label']}"
    )
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
