"""Thermal warm-up state tracking for GaggiMate status frames.

The tracker is deliberately local to MATEbot.  GaggiMate exposes current
(`ct`) and target (`tt`) temperature in `evt:status`, but it does not expose a
single documented "thermally ready" flag.  We therefore require an observed
overshoot followed by a stable return to the target band.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any


OVERSHOOT_DELTA_C = 3.0
READY_BAND_C = 0.7
READY_STABLE_S = 20.0
SETTLING_DROP_C = 0.3
TARGET_MIN_C = 60.0
TARGET_CHANGE_C = 0.5


class WarmupPhase(str, Enum):
    IDLE = "IDLE"
    OBSERVING = "OBSERVING"
    HEATING = "HEATING"
    OVERSHOOT = "OVERSHOOT"
    SETTLING = "SETTLING"
    READY = "READY"


@dataclass(frozen=True, slots=True)
class WarmupSnapshot:
    phase: WarmupPhase
    current_c: float | None
    target_c: float | None
    peak_c: float | None
    overshoot_seen: bool
    stable_for_s: float
    ready: bool
    tracked: bool
    settle_duration_s: float | None

    @property
    def overshoot_c(self) -> float | None:
        if self.peak_c is None or self.target_c is None:
            return None
        return self.peak_c - self.target_c

    @property
    def in_ready_band(self) -> bool:
        if self.current_c is None or self.target_c is None:
            return False
        return abs(self.current_c - self.target_c) <= READY_BAND_C


class WarmupTracker:
    """Observe `evt:status` frames and classify thermal warm-up state."""

    def __init__(self) -> None:
        self._phase = WarmupPhase.IDLE
        self._current_c: float | None = None
        self._target_c: float | None = None
        self._peak_c: float | None = None
        self._peak_at: float | None = None
        self._overshoot_seen = False
        self._stable_since: float | None = None
        self._settle_duration: float | None = None
        self._tracked = False
        self._previous_mode: int | None = None

    def reset(self) -> None:
        self._phase = WarmupPhase.IDLE
        self._current_c = None
        self._target_c = None
        self._peak_c = None
        self._peak_at = None
        self._overshoot_seen = False
        self._stable_since = None
        self._settle_duration = None
        self._tracked = False

    def _start_cycle(self) -> None:
        self._phase = WarmupPhase.OBSERVING
        self._current_c = None
        self._target_c = None
        self._peak_c = None
        self._peak_at = None
        self._overshoot_seen = False
        self._stable_since = None
        self._settle_duration = None
        self._tracked = True

    @staticmethod
    def _number(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        return None

    def observe(self, frame: dict[str, Any], *, now: float | None = None) -> WarmupSnapshot:
        if frame.get("tp") != "evt:status":
            return self.snapshot(now=now)

        now = time.monotonic() if now is None else now
        mode = frame.get("m")

        # A transition into brew starts a new thermal cycle.  Leaving brew
        # clears the previous ready state so steam/standby cannot leak into a
        # later brew session.
        if mode != 1:
            if self._previous_mode == 1 or self._phase != WarmupPhase.IDLE:
                self.reset()
            self._previous_mode = mode if isinstance(mode, int) else None
            return self.snapshot(now=now)

        if self._previous_mode != 1 and not self._tracked:
            self._start_cycle()
        self._previous_mode = 1

        current = self._number(frame.get("ct"))
        target = self._number(frame.get("tt"))
        self._current_c = current

        if current is not None:
            if self._peak_c is None or current > self._peak_c:
                self._peak_c = current
                self._peak_at = now

        if target is None or target < TARGET_MIN_C:
            self._phase = WarmupPhase.OBSERVING
            self._stable_since = None
            return self.snapshot(now=now)

        old_target = self._target_c
        target_changed = (
            old_target is not None and abs(target - old_target) > TARGET_CHANGE_C
        )
        self._target_c = target

        if target_changed:
            # A new selected profile/target must settle again.  We preserve the
            # fact that the machine already completed its startup overshoot.
            self._stable_since = None
            if self._phase == WarmupPhase.READY:
                self._phase = (
                    WarmupPhase.SETTLING
                    if self._overshoot_seen
                    else WarmupPhase.OBSERVING
                )

        if current is None:
            self._phase = WarmupPhase.OBSERVING
            self._stable_since = None
            return self.snapshot(now=now)

        # Use the observed peak as well as the current sample.  This makes the
        # detector robust if `tt` becomes valid just after the actual peak.
        if self._peak_c is not None and self._peak_c >= target + OVERSHOOT_DELTA_C:
            self._overshoot_seen = True

        if self._overshoot_seen:
            if (
                self._peak_c is not None
                and current >= target + OVERSHOOT_DELTA_C
                and current >= self._peak_c - SETTLING_DROP_C
            ):
                self._phase = WarmupPhase.OVERSHOOT
                self._stable_since = None
                return self.snapshot(now=now)

            in_band = abs(current - target) <= READY_BAND_C
            if in_band:
                if self._stable_since is None:
                    self._stable_since = now
                stable_for = now - self._stable_since
                if stable_for >= READY_STABLE_S:
                    self._phase = WarmupPhase.READY
                    if self._settle_duration is None and self._peak_at is not None:
                        self._settle_duration = (
                            self._stable_since + READY_STABLE_S
                        ) - self._peak_at
                else:
                    self._phase = WarmupPhase.SETTLING
            else:
                self._stable_since = None
                self._phase = WarmupPhase.SETTLING
        else:
            self._stable_since = None
            if current < target - READY_BAND_C:
                self._phase = WarmupPhase.HEATING
            else:
                # Crossing the target on the way up is deliberately NOT ready.
                self._phase = WarmupPhase.OBSERVING

        return self.snapshot(now=now)

    def snapshot(self, *, now: float | None = None) -> WarmupSnapshot:
        now = time.monotonic() if now is None else now
        stable_for = 0.0
        if self._stable_since is not None:
            stable_for = max(0.0, now - self._stable_since)
        return WarmupSnapshot(
            phase=self._phase,
            current_c=self._current_c,
            target_c=self._target_c,
            peak_c=self._peak_c,
            overshoot_seen=self._overshoot_seen,
            stable_for_s=stable_for,
            ready=self._phase == WarmupPhase.READY,
            tracked=self._tracked,
            settle_duration_s=self._settle_duration,
        )
