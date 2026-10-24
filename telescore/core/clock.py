"""
A drift-free game clock.

TeleScore 1.x counted whole seconds with ``int(time())`` and an unaligned
QTimer, so displays could skip or repeat a second and a pause threw away the
fraction already run. This clock keeps the value in milliseconds and derives
it from a monotonic time source whenever it is read: the UI timer only decides
how often the display is refreshed, never how fast time passes.

The clock has no Qt dependency. ``now`` is always a float in seconds from a
monotonic source and is passed in, which keeps every behaviour testable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from .timefmt import format_ms

__all__ = ["Clock", "now"]


def now() -> float:
    """The monotonic time source used throughout the engine."""
    return time.monotonic()


@dataclass
class Clock:
    """A countdown timer or a stopwatch.

    Attributes:
        countdown:   True counts down to zero; False counts up.
        initial_ms:  Value restored by :meth:`reset` (the period length).
        limit_ms:    Stopwatch only: stop when this is reached (0 = no limit).
        fmt:         Display format, see :mod:`telescore.core.timefmt`.
        tenths_under_ms: Countdown only. Below this value the display switches
                     to ``tenths_fmt`` (basketball and hockey style). 0 = never.
        tenths_fmt:  Format used under the threshold.
        blank_at_zero: Display an empty string once a countdown expires.
    """

    countdown: bool = True
    initial_ms: int = 12 * 60_000
    limit_ms: int = 0
    fmt: str = "m:ss"
    tenths_under_ms: int = 0
    tenths_fmt: str = "s.t"
    blank_at_zero: bool = False
    _base_ms: int = field(default=-1, repr=False)
    _started: Optional[float] = field(default=None, repr=False)

    MAX_MS = 100 * 3_600_000  # 100 hours; anything above is a typo

    def __post_init__(self) -> None:
        if self._base_ms < 0:
            self._base_ms = self.initial_ms if self.countdown else 0

    # ----- reading ---------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._started is not None

    def value(self, t: Optional[float] = None) -> int:
        """Current value in ms, clamped to the clock's range."""
        if self._started is None:
            return self._base_ms
        t = now() if t is None else t
        elapsed = int(round((t - self._started) * 1000))
        if self.countdown:
            return max(0, self._base_ms - elapsed)
        v = self._base_ms + elapsed
        if self.limit_ms and v > self.limit_ms:
            return self.limit_ms
        return min(v, self.MAX_MS)

    def display(self, t: Optional[float] = None) -> str:
        v = self.value(t)
        if self.countdown and self.blank_at_zero and v <= 0:
            return ""
        if self.countdown and self.tenths_under_ms and 0 < v < self.tenths_under_ms:
            return format_ms(v, self.tenths_fmt, countdown=True)
        return format_ms(v, self.fmt, countdown=self.countdown)

    # ----- control ---------------------------------------------------------
    def start(self, t: Optional[float] = None) -> bool:
        """Start the clock. Returns False if it is already running or a
        countdown is at zero (there is nothing to run)."""
        if self.running:
            return False
        if self.countdown and self._base_ms <= 0:
            return False
        if not self.countdown and self.limit_ms and self._base_ms >= self.limit_ms:
            return False
        self._started = now() if t is None else t
        return True

    def stop(self, t: Optional[float] = None) -> bool:
        """Stop the clock, keeping the exact milliseconds already run."""
        if not self.running:
            return False
        self._base_ms = self.value(t)
        self._started = None
        return True

    def toggle(self, t: Optional[float] = None) -> bool:
        """Start a stopped clock or stop a running one. Returns running."""
        if self.running:
            self.stop(t)
        else:
            self.start(t)
        return self.running

    def set(self, ms: int, t: Optional[float] = None) -> None:
        """Set the value; a running clock keeps running from the new value."""
        ms = int(max(0, min(int(ms), self.MAX_MS)))
        if self.limit_ms and not self.countdown:
            ms = min(ms, self.limit_ms)
        was_running = self.running
        self._base_ms = ms
        self._started = (now() if t is None else t) if was_running else None
        if was_running and self.countdown and ms == 0:
            self._started = None

    def adjust(self, delta_ms: int, t: Optional[float] = None) -> None:
        """Add (or with a negative delta, remove) time without stopping."""
        self.set(self.value(t) + int(delta_ms), t)

    def reset(self, t: Optional[float] = None) -> None:
        """Stop and restore the period length (countdown) or zero (stopwatch)."""
        self._started = None
        self._base_ms = self.initial_ms if self.countdown else 0

    def tick(self, t: Optional[float] = None) -> bool:
        """Settle the clock at ``t``. Returns True exactly once when a
        countdown reaches zero or a stopwatch reaches its limit, and stops it."""
        if not self.running:
            return False
        v = self.value(t)
        if (self.countdown and v <= 0) or (not self.countdown and self.limit_ms and v >= self.limit_ms):
            self._base_ms = v
            self._started = None
            return True
        return False

    # ----- persistence -----------------------------------------------------
    def config(self) -> dict:
        return {
            "countdown": self.countdown,
            "initial_ms": self.initial_ms,
            "limit_ms": self.limit_ms,
            "fmt": self.fmt,
            "tenths_under_ms": self.tenths_under_ms,
            "tenths_fmt": self.tenths_fmt,
            "blank_at_zero": self.blank_at_zero,
        }

    def to_dict(self, t: Optional[float] = None) -> dict:
        d = self.config()
        d["value_ms"] = self.value(t)
        d["running"] = self.running
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Clock":
        c = cls(
            countdown=bool(d.get("countdown", True)),
            initial_ms=int(d.get("initial_ms", 12 * 60_000)),
            limit_ms=int(d.get("limit_ms", 0)),
            fmt=str(d.get("fmt", "m:ss")),
            tenths_under_ms=int(d.get("tenths_under_ms", 0)),
            tenths_fmt=str(d.get("tenths_fmt", "s.t")),
            blank_at_zero=bool(d.get("blank_at_zero", False)),
        )
        if "value_ms" in d:
            c._base_ms = int(max(0, d["value_ms"]))
        # A saved project always opens with its clocks stopped.
        return c

    def state(self, t: Optional[float] = None) -> tuple:
        """(value_ms, running) for undo records."""
        return (self.value(t), self.running)

    def restore(self, value_ms: int, running: bool, t: Optional[float] = None) -> None:
        self._base_ms = int(max(0, value_ms))
        self._started = (now() if t is None else t) if running else None
