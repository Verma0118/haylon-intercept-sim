"""TrackEstimate → GuidanceCommand (M4.1 center-the-target)."""

from __future__ import annotations

from dataclasses import dataclass

from guidance_cmd import GuidanceCommand, GuidanceFlags
from track_estimate import TrackEstimate


@dataclass
class CenterGuide:
    """
    Keep the tracked tip at the image-center crosshair.

    - Target right of center (+offset_norm.x) → positive yaw_rate (yaw right)
    - Target above center (+offset_norm.y) → positive pitch_rate (nose up)
    - SEARCHING / LOST → HOLD or ABORT with zero rates (failsafe)
    """

    kp_yaw: float = 1.2
    kp_pitch: float = 1.2
    rate_limit: float = 0.85
    deadband: float = 0.04  # ignore tiny norm offsets
    hold_throttle: float = 0.45  # safe mid throttle while tracking (no auto-arm)

    def update(self, track: TrackEstimate) -> GuidanceCommand:
        ts = track.timestamp_ms
        if track.status != "TRACKING" or track.offset_norm is None:
            return GuidanceCommand(
                timestamp_ms=ts,
                mode="HOLD" if track.status == "LOST" else "IDLE",
                yaw_rate=0.0,
                pitch_rate=0.0,
                roll_rate=0.0,
                throttle=0.0,
                flags=GuidanceFlags(
                    lost_target=(track.status != "TRACKING"),
                    link_ok=True,
                ),
            )

        nx, ny = track.offset_norm
        if abs(nx) < self.deadband:
            nx = 0.0
        if abs(ny) < self.deadband:
            ny = 0.0

        yaw = max(-self.rate_limit, min(self.rate_limit, self.kp_yaw * nx))
        pitch = max(-self.rate_limit, min(self.rate_limit, self.kp_pitch * ny))

        return GuidanceCommand(
            timestamp_ms=ts,
            mode="TRACK_CENTER",
            yaw_rate=float(yaw),
            pitch_rate=float(pitch),
            roll_rate=0.0,
            throttle=self.hold_throttle,
            flags=GuidanceFlags(lost_target=False, link_ok=True),
        )
