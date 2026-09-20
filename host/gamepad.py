"""Xbox / generic gamepad → GuidanceCommand (M2.1)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from guidance_cmd import GuidanceCommand, GuidanceFlags


@dataclass
class GamepadReading:
    roll: float = 0.0  # left stick X, -1..1
    pitch: float = 0.0  # left stick Y, -1..1 (+ = stick forward / nose up desire)
    yaw: float = 0.0  # right stick X
    throttle: float = 0.0  # right stick Y mapped 0..1 (up = more)
    kill: bool = False  # B / circle
    connected: bool = False
    name: str = ""


class Gamepad:
    """
    Read an Xbox (or similar) controller via pygame.

    Layout (Xbox, typical):
      Left stick  → roll (X), pitch (Y)
      Right stick → yaw (X), throttle (Y, up = higher)
      B button    → kill / override flag
    """

    def __init__(self) -> None:
        try:
            import pygame
        except ImportError as exc:  # noqa: BLE001
            raise RuntimeError(
                "pygame is required for gamepad input.\n"
                "  python -m pip install pygame\n"
                f"Import error: {exc!r}"
            ) from exc

        self._pygame = pygame
        pygame.init()
        pygame.joystick.init()
        self._joy = None
        if pygame.joystick.get_count() > 0:
            self._joy = pygame.joystick.Joystick(0)
            self._joy.init()

    @property
    def connected(self) -> bool:
        return self._joy is not None

    def name(self) -> str:
        if self._joy is None:
            return ""
        return self._joy.get_name()

    def close(self) -> None:
        self._pygame.joystick.quit()
        self._pygame.quit()

    def read(self) -> GamepadReading:
        pygame = self._pygame
        pygame.event.pump()
        if self._joy is None:
            # Hot-plug: try again
            if pygame.joystick.get_count() > 0:
                self._joy = pygame.joystick.Joystick(0)
                self._joy.init()
            else:
                return GamepadReading(connected=False)

        joy = self._joy
        # Invert Y so stick forward / up is positive pitch / throttle
        roll = float(joy.get_axis(0)) if joy.get_numaxes() > 0 else 0.0
        pitch = float(-joy.get_axis(1)) if joy.get_numaxes() > 1 else 0.0
        yaw = float(joy.get_axis(2)) if joy.get_numaxes() > 2 else 0.0
        # Axis 3 is often right-stick Y on Xbox via pygame
        ry = float(-joy.get_axis(3)) if joy.get_numaxes() > 3 else 0.0
        # Map right-stick Y from -1..1 → throttle 0..1 (center = 0.5 hover-ish)
        throttle = max(0.0, min(1.0, 0.5 + 0.5 * ry))
        kill = bool(joy.get_button(1)) if joy.get_numbuttons() > 1 else False  # B
        return GamepadReading(
            roll=max(-1.0, min(1.0, roll)),
            pitch=max(-1.0, min(1.0, pitch)),
            yaw=max(-1.0, min(1.0, yaw)),
            throttle=throttle,
            kill=kill,
            connected=True,
            name=joy.get_name(),
        )

    def to_guidance(self, reading: Optional[GamepadReading] = None) -> GuidanceCommand:
        r = reading if reading is not None else self.read()
        now_ms = time.time() * 1000.0
        if not r.connected:
            return GuidanceCommand(
                timestamp_ms=now_ms,
                mode="IDLE",
                flags=GuidanceFlags(link_ok=False),
            )
        mode = "ABORT" if r.kill else "HOLD"
        return GuidanceCommand(
            timestamp_ms=now_ms,
            mode=mode,
            yaw_rate=r.yaw,
            pitch_rate=r.pitch,
            roll_rate=r.roll,
            throttle=r.throttle,
            flags=GuidanceFlags(operator_override=True, link_ok=True),
        )
