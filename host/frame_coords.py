"""Camera frame coordinates — reference origin at image center.

Two related frames are used:

1. **Image pixels** (OpenCV native)
   - Origin: top-left corner of the frame
   - +X right, +Y down
   - Used for drawing boxes and reading detector outputs

2. **Guidance / crosshair frame** (what we steer with)
   - Origin: image center `(width/2, height/2)` — the crosshair
   - +X right, +Y **up** (same sense as aircraft pitch/yaw desire)
   - `offset_px` and `offset_norm` are in this frame
   - `bearing_rad` (yaw, pitch) is derived from the same offsets

Normalized offsets map the half-width / half-height of the image to ±1:
  offset_norm.x = offset_px.x / (width/2)
  offset_norm.y = offset_px.y / (height/2)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class FrameCoords:
    """Fingertip (or target) expressed against the camera crosshair origin."""

    # Image pixels — origin top-left, +y down
    image_xy: tuple[float, float]
    # Crosshair origin in image pixels
    origin_xy: tuple[float, float]
    # Offset from origin — +x right, +y up (pixels)
    offset_px: tuple[float, float]
    # Offset from origin — roughly ±1 at the frame edge
    offset_norm: tuple[float, float]
    # Approximate bearing from pinhole with fx≈0.8w, fy≈0.8h
    bearing_rad: tuple[float, float]  # (yaw, pitch); +yaw right, +pitch up
    width: int
    height: int

    @property
    def x_img(self) -> float:
        return self.image_xy[0]

    @property
    def y_img(self) -> float:
        return self.image_xy[1]

    @property
    def dx(self) -> float:
        return self.offset_px[0]

    @property
    def dy(self) -> float:
        return self.offset_px[1]


def frame_coords_from_image_xy(
    x_img: float,
    y_img: float,
    width: int,
    height: int,
) -> FrameCoords:
    """Convert OpenCV image pixels → center-origin guidance coordinates."""
    ox = width * 0.5
    oy = height * 0.5
    dx = float(x_img - ox)  # +right
    dy = float(oy - y_img)  # +up (flip image y)
    nx = dx / max(ox, 1.0)
    ny = dy / max(oy, 1.0)
    fx = max(width * 0.8, 1.0)
    fy = max(height * 0.8, 1.0)
    yaw = float(np.arctan2(dx, fx))
    pitch = float(np.arctan2(dy, fy))
    return FrameCoords(
        image_xy=(float(x_img), float(y_img)),
        origin_xy=(ox, oy),
        offset_px=(dx, dy),
        offset_norm=(float(nx), float(ny)),
        bearing_rad=(yaw, pitch),
        width=int(width),
        height=int(height),
    )


def optional_frame_coords(
    image_xy: Optional[tuple[float, float]],
    width: int,
    height: int,
) -> Optional[FrameCoords]:
    if image_xy is None:
        return None
    return frame_coords_from_image_xy(image_xy[0], image_xy[1], width, height)
