"""GuidanceCommand / ChannelFrame / StickMap — matches host/contracts.md."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Sequence

GuidanceMode = Literal["IDLE", "HOLD", "TRACK_CENTER", "INTERCEPT", "ABORT"]

# Axis tags for StickMap.channel_order (first four = primary sticks).
AxisTag = Literal["roll", "pitch", "throttle", "yaw"]


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


# Named channel orders (contracts.md): AETR vs TAER.
CHANNEL_ORDERS: dict[str, tuple[AxisTag, AxisTag, AxisTag, AxisTag]] = {
    "AETR": ("roll", "pitch", "throttle", "yaw"),
    "TAER": ("throttle", "roll", "pitch", "yaw"),
}


@dataclass
class StickMap:
    """Map GuidanceCommand → ChannelFrame for one FC/radio profile."""

    name: str = "betaflight_default"
    # Indices 0..3 get these axes (AETR Betaflight-style default).
    channel_order: tuple[AxisTag, AxisTag, AxisTag, AxisTag] = (
        "roll",
        "pitch",
        "throttle",
        "yaw",
    )
    deadband: float = 0.05
    mid_us: float = 1500.0
    span_us: float = 500.0
    throttle_min_us: float = 1000.0
    throttle_max_us: float = 2000.0

    def to_channels(self, cmd: GuidanceCommand) -> ChannelFrame:
        c = cmd.clamped()
        axis_us: dict[AxisTag, float] = {
            "roll": _norm_to_us(
                _deadband(c.roll_rate, self.deadband), self.mid_us, self.span_us
            ),
            "pitch": _norm_to_us(
                _deadband(c.pitch_rate, self.deadband), self.mid_us, self.span_us
            ),
            "yaw": _norm_to_us(
                _deadband(c.yaw_rate, self.deadband), self.mid_us, self.span_us
            ),
            "throttle": self.throttle_min_us
            + float(max(0.0, min(1.0, c.throttle)))
            * (self.throttle_max_us - self.throttle_min_us),
        }

        channels = [1500.0] * 16
        for i, tag in enumerate(self.channel_order):
            channels[i] = axis_us[tag]
        return ChannelFrame(timestamp_ms=c.timestamp_ms, channels=channels)


def stick_profile(name: str) -> StickMap:
    """
    Built-in StickMap profiles (M4.3).

    - betaflight_default / aetr — AETR (roll, pitch, throttle, yaw)
    - taer — TAER (throttle, roll, pitch, yaw) — common radio order
    """
    key = name.strip().lower()
    if key in ("betaflight_default", "aetr", "betaflight"):
        return StickMap(
            name="betaflight_default",
            channel_order=CHANNEL_ORDERS["AETR"],
        )
    if key == "taer":
        return StickMap(
            name="taer",
            channel_order=CHANNEL_ORDERS["TAER"],
        )
    known = "betaflight_default, aetr, taer"
    raise ValueError(f"Unknown StickMap profile {name!r}. Known: {known}")


def list_stick_profiles() -> list[str]:
    return ["betaflight_default", "taer"]
