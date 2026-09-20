"""GuidanceCommand / ChannelFrame / StickMap — matches host/contracts.md."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Sequence

GuidanceMode = Literal["IDLE", "HOLD", "TRACK_CENTER", "INTERCEPT", "ABORT"]


@dataclass
class GuidanceFlags:
    operator_override: bool = False
    lost_target: bool = False
    link_ok: bool = True


@dataclass
class GuidanceCommand:
    timestamp_ms: float
    mode: GuidanceMode
    yaw_rate: float = 0.0  # -1..1, + = yaw right
    pitch_rate: float = 0.0  # -1..1, + = nose up
    roll_rate: float = 0.0  # -1..1, + = roll right
    throttle: float = 0.0  # 0..1
    flags: GuidanceFlags = field(default_factory=GuidanceFlags)

    def clamped(self) -> "GuidanceCommand":
        return GuidanceCommand(
            timestamp_ms=self.timestamp_ms,
            mode=self.mode,
            yaw_rate=float(max(-1.0, min(1.0, self.yaw_rate))),
            pitch_rate=float(max(-1.0, min(1.0, self.pitch_rate))),
            roll_rate=float(max(-1.0, min(1.0, self.roll_rate))),
            throttle=float(max(0.0, min(1.0, self.throttle))),
            flags=self.flags,
        )


@dataclass
class ChannelFrame:
    """RC channels in µs (typically 1000..2000) — ready for ELRS TX packets."""

    timestamp_ms: float
    channels: list[float]  # length 16; first N used


def _deadband(x: float, db: float) -> float:
    if abs(x) < db:
        return 0.0
    sign = 1.0 if x > 0 else -1.0
    return sign * (abs(x) - db) / max(1e-6, 1.0 - db)


def _norm_to_us(x: float, mid: float = 1500.0, span: float = 500.0) -> float:
    """Map -1..1 → mid±span, clamp 1000..2000."""
    return float(max(1000.0, min(2000.0, mid + x * span)))


@dataclass
class StickMap:
    """Map GuidanceCommand → ChannelFrame (AETR Betaflight-style default)."""

    name: str = "betaflight_default"
    # channel indices 0..3 = roll, pitch, throttle, yaw (AETR)
    deadband: float = 0.05
    mid_us: float = 1500.0
    span_us: float = 500.0
    throttle_min_us: float = 1000.0
    throttle_max_us: float = 2000.0

    def to_channels(self, cmd: GuidanceCommand) -> ChannelFrame:
        c = cmd.clamped()
        roll = _deadband(c.roll_rate, self.deadband)
        pitch = _deadband(c.pitch_rate, self.deadband)
        yaw = _deadband(c.yaw_rate, self.deadband)
        thr = float(max(0.0, min(1.0, c.throttle)))

        channels = [1500.0] * 16
        channels[0] = _norm_to_us(roll, self.mid_us, self.span_us)  # A roll
        channels[1] = _norm_to_us(pitch, self.mid_us, self.span_us)  # E pitch
        channels[2] = self.throttle_min_us + thr * (
            self.throttle_max_us - self.throttle_min_us
        )  # T
        channels[3] = _norm_to_us(yaw, self.mid_us, self.span_us)  # R yaw
        return ChannelFrame(timestamp_ms=c.timestamp_ms, channels=channels)
