"""
Data fields: the single source of truth for everything TeleScore shows.

In 1.x every value lived inside a Qt widget, so there was nothing to export
except one text file per widget. In 2.0 a scoreboard is a set of named fields
(``home.score``, ``clock.game``, ``period``) and every output, every board and
every button reads or writes those names.

A field key is lower-case dotted words: ``[a-z0-9_]+(\\.[a-z0-9_]+)*``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

from .clock import Clock
from .timefmt import format_ms, ordinal, parse_time

__all__ = [
    "Field", "CounterField", "TextField", "ToggleField", "ChoiceField",
    "ClockField", "PenaltyField", "ImageField", "FIELD_TYPES",
    "field_from_dict", "valid_key", "normalise_key",
]

KEY_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")


def valid_key(key: str) -> bool:
    return bool(KEY_RE.match(key or ""))


def normalise_key(text: str) -> str:
    """Turn a label like 'Home Score' into 'home_score'."""
    s = re.sub(r"[^a-z0-9_.]+", "_", (text or "").strip().lower())
    s = re.sub(r"_+", "_", s)
    s = re.sub(r"\.+", ".", s).strip("._")
    return s or "field"


class Field:
    """Base class. Subclasses set ``type`` and implement value handling."""

    type = "field"

    def __init__(self, key: str, label: str = "", **_: Any) -> None:
        if not valid_key(key):
            raise ValueError(f"{key!r} is not a valid field key. Use lower-case words joined by dots, "
                             "for example home.score.")
        self.key = key
        self.label = label or key

    # Subclasses override -------------------------------------------------
    def display(self, t: Optional[float] = None) -> str:
        raise NotImplementedError

    def raw(self, t: Optional[float] = None) -> Any:
        """The machine value (int, str, bool, ...) for JSON and XML."""
        raise NotImplementedError

    def extra(self, t: Optional[float] = None) -> Dict[str, str]:
        """Additional sub-keys published with this field (key suffix -> text)."""
        return {}

    def state(self, t: Optional[float] = None) -> Any:
        """Opaque value snapshot for undo."""
        return self.raw(t)

    def restore(self, state: Any, t: Optional[float] = None) -> None:
        raise NotImplementedError

    def reset(self, t: Optional[float] = None) -> None:
        raise NotImplementedError

    def to_dict(self, t: Optional[float] = None) -> dict:
        return {"key": self.key, "type": self.type, "label": self.label}

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} {self.key}={self.display()!r}>"


class CounterField(Field):
    """A whole number: a score, a period, fouls, shots, outs."""

    type = "counter"

    def __init__(self, key: str, label: str = "", value: int = 0, default: int = 0,
                 minimum: Optional[int] = 0, maximum: Optional[int] = None,
                 steps: Iterable[int] = (1,), ordinal: bool = False,
                 blank_zero: bool = False, pad: int = 0, **kw: Any) -> None:
        super().__init__(key, label, **kw)
        self.default = int(default)
        self.minimum = None if minimum is None else int(minimum)
        self.maximum = None if maximum is None else int(maximum)
        self.steps = [int(s) for s in steps] or [1]
        self.ordinal = bool(ordinal)
        self.blank_zero = bool(blank_zero)
        self.pad = max(0, int(pad))
        self.value = self._clamp(int(value))

    def _clamp(self, v: int) -> int:
        if self.minimum is not None:
            v = max(self.minimum, v)
        if self.maximum is not None:
            v = min(self.maximum, v)
        return v

    def set(self, v: Any) -> None:
        try:
            self.value = self._clamp(int(str(v).strip()))
        except ValueError:
            raise ValueError(f"{v!r} is not a whole number.") from None

    def add(self, amount: int = 1) -> None:
        self.value = self._clamp(self.value + int(amount))

    def display(self, t=None) -> str:
        if self.blank_zero and self.value == 0:
            return ""
        if self.ordinal:
            return ordinal(self.value)
        return f"{self.value:0{self.pad}d}" if self.pad else str(self.value)

    def raw(self, t=None) -> int:
        return self.value

    def restore(self, state, t=None) -> None:
        self.value = int(state)

    def reset(self, t=None) -> None:
        self.value = self._clamp(self.default)

    def to_dict(self, t=None) -> dict:
        d = super().to_dict()
        d.update(value=self.value, default=self.default, minimum=self.minimum,
                 maximum=self.maximum, steps=self.steps, ordinal=self.ordinal,
                 blank_zero=self.blank_zero, pad=self.pad)
        return d


class TextField(Field):
    """Free text: a team name, a sponsor line, a down and distance."""

    type = "text"

    def __init__(self, key: str, label: str = "", value: str = "", default: Optional[str] = None,
                 uppercase: bool = False, **kw: Any) -> None:
        super().__init__(key, label, **kw)
        self.value = str(value)
        self.default = self.value if default is None else str(default)
        self.uppercase = bool(uppercase)

    def set(self, v: Any) -> None:
        self.value = "" if v is None else str(v)

    def display(self, t=None) -> str:
        return self.value.upper() if self.uppercase else self.value

    def raw(self, t=None) -> str:
        return self.value

    def restore(self, state, t=None) -> None:
        self.value = str(state)

    def reset(self, t=None) -> None:
        self.value = self.default

    def to_dict(self, t=None) -> dict:
        d = super().to_dict()
        d.update(value=self.value, default=self.default, uppercase=self.uppercase)
        return d


class ToggleField(Field):
    """On or off: possession, bonus, power play, a graphic shown or hidden."""

    type = "toggle"

    def __init__(self, key: str, label: str = "", value: bool = False, default: bool = False,
                 on_text: str = "1", off_text: str = "", **kw: Any) -> None:
        super().__init__(key, label, **kw)
        self.value = bool(value)
        self.default = bool(default)
        self.on_text = str(on_text)
        self.off_text = str(off_text)

    def set(self, v: Any) -> None:
        if isinstance(v, str):
            v = v.strip().lower() in ("1", "true", "on", "yes", "y", "show")
        self.value = bool(v)

    def toggle(self) -> None:
        self.value = not self.value

    def display(self, t=None) -> str:
        return self.on_text if self.value else self.off_text

    def raw(self, t=None) -> bool:
        return self.value

    def restore(self, state, t=None) -> None:
        self.value = bool(state)

    def reset(self, t=None) -> None:
        self.value = self.default

    def to_dict(self, t=None) -> dict:
        d = super().to_dict()
        d.update(value=self.value, default=self.default, on_text=self.on_text, off_text=self.off_text)
        return d


class ChoiceField(Field):
    """One of a list: period names (1st, 2nd, OT), downs, halves."""

    type = "choice"

    def __init__(self, key: str, label: str = "", options: Iterable[str] = ("",),
                 index: int = 0, default: int = 0, wrap: bool = False, **kw: Any) -> None:
        super().__init__(key, label, **kw)
        self.options = [str(o) for o in options] or [""]
        self.default = self._clamp(int(default))
        self.wrap = bool(wrap)
        self.index = self._clamp(int(index))

    def _clamp(self, i: int) -> int:
        return max(0, min(len(self.options) - 1, i))

    def set(self, v: Any) -> None:
        """Accept an option's text or its 0-based index."""
        if isinstance(v, int) and not isinstance(v, bool):
            self.index = self._clamp(v)
            return
        s = str(v).strip()
        for i, o in enumerate(self.options):
            if o.lower() == s.lower():
                self.index = i
                return
        if s.lstrip("-").isdigit():
            self.index = self._clamp(int(s))
            return
        raise ValueError(f"{v!r} is not one of {', '.join(self.options)}.")

    def step(self, delta: int) -> None:
        n = len(self.options)
        i = self.index + int(delta)
        self.index = i % n if self.wrap else self._clamp(i)

    def display(self, t=None) -> str:
        return self.options[self.index]

    def raw(self, t=None) -> str:
        return self.options[self.index]

    def state(self, t=None) -> int:
        return self.index

    def restore(self, state, t=None) -> None:
        self.index = self._clamp(int(state))

    def reset(self, t=None) -> None:
        self.index = self.default

    def extra(self, t=None) -> Dict[str, str]:
        return {"index": str(self.index + 1)}

    def to_dict(self, t=None) -> dict:
        d = super().to_dict()
        d.update(options=self.options, index=self.index, default=self.default, wrap=self.wrap)
        return d


class ClockField(Field):
    """A game clock, shot clock, play clock or stopwatch."""

    type = "clock"

    def __init__(self, key: str, label: str = "", clock: Optional[Clock] = None, **kw: Any) -> None:
        clock_kw = {k: kw.pop(k) for k in list(kw) if k in Clock.__dataclass_fields__ and not k.startswith("_")}
        value_ms = kw.pop("value_ms", None)
        kw.pop("running", None)
        super().__init__(key, label, **kw)
        if clock is None:
            cfg = dict(clock_kw)
            if value_ms is not None:
                cfg["value_ms"] = value_ms
            clock = Clock.from_dict(cfg)
        self.clock = clock

    def display(self, t=None) -> str:
        return self.clock.display(t)

    def raw(self, t=None) -> int:
        return self.clock.value(t)

    def extra(self, t=None) -> Dict[str, str]:
        return {"running": "1" if self.clock.running else "0"}

    def state(self, t=None):
        return self.clock.state(t)

    def restore(self, state, t=None) -> None:
        self.clock.restore(state[0], state[1], t)

    def reset(self, t=None) -> None:
        self.clock.reset(t)

    def to_dict(self, t=None) -> dict:
        d = super().to_dict()
        d.update(self.clock.to_dict(t))
        d["running"] = False
        return d


class PenaltyField(Field):
    """Timed penalties (hockey, lacrosse) that run only while a master clock runs.

    1.x gave every penalty its own free-running timer started by a button, so
    penalties drifted from the game clock and kept running through stoppages.
    Here the engine advances penalties by exactly the time the master clock ran.

    Published sub-keys, for slots 1..``slots``: ``<key>.<n>.player`` and
    ``<key>.<n>.time``, plus ``<key>.count``.
    """

    type = "penalties"

    def __init__(self, key: str, label: str = "", master: str = "clock.game", slots: int = 2,
                 fmt: str = "m:ss", entries: Optional[List[dict]] = None, **kw: Any) -> None:
        super().__init__(key, label, **kw)
        self.master = master
        self.slots = max(1, int(slots))
        self.fmt = fmt
        self.entries: List[dict] = []
        for e in entries or []:
            self.entries.append({"player": str(e.get("player", "")), "ms": int(e.get("ms", 0))})

    def add(self, player: str, time_text: str) -> None:
        ms = parse_time(time_text) if isinstance(time_text, str) else int(time_text)
        if ms <= 0:
            raise ValueError("A penalty needs a time above zero.")
        self.entries.append({"player": str(player), "ms": ms})

    def remove(self, index: int) -> None:
        if not 0 <= index < len(self.entries):
            raise ValueError(f"There is no penalty {index + 1}.")
        self.entries.pop(index)

    def clear(self) -> None:
        self.entries.clear()

    def advance(self, elapsed_ms: int) -> List[dict]:
        """Run the first ``slots`` penalties (the ones on the board) by
        ``elapsed_ms``. Returns the penalties that expired."""
        if elapsed_ms <= 0:
            return []
        expired = []
        for e in self.entries[: self.slots]:
            e["ms"] -= elapsed_ms
        keep = []
        for e in self.entries:
            (expired if e["ms"] <= 0 else keep).append(e)
        self.entries = keep
        return expired

    def display(self, t=None) -> str:
        return str(len(self.entries))

    def raw(self, t=None) -> int:
        return len(self.entries)

    def extra(self, t=None) -> Dict[str, str]:
        out = {"count": str(len(self.entries))}
        for n in range(1, self.slots + 1):
            e = self.entries[n - 1] if n - 1 < len(self.entries) else None
            out[f"{n}.player"] = e["player"] if e else ""
            out[f"{n}.time"] = format_ms(e["ms"], self.fmt, countdown=True) if e else ""
        return out

    def state(self, t=None):
        return [dict(e) for e in self.entries]

    def restore(self, state, t=None) -> None:
        self.entries = [dict(e) for e in state]

    def reset(self, t=None) -> None:
        self.entries.clear()

    def to_dict(self, t=None) -> dict:
        d = super().to_dict()
        d.update(master=self.master, slots=self.slots, fmt=self.fmt, entries=self.state())
        return d


class ImageField(Field):
    """A picture path: a team logo, a sponsor, a flag."""

    type = "image"

    def __init__(self, key: str, label: str = "", value: str = "", default: Optional[str] = None, **kw: Any) -> None:
        super().__init__(key, label, **kw)
        self.value = str(value)
        self.default = self.value if default is None else str(default)

    def set(self, v: Any) -> None:
        self.value = "" if v is None else str(v)

    def display(self, t=None) -> str:
        return self.value

    def raw(self, t=None) -> str:
        return self.value

    def restore(self, state, t=None) -> None:
        self.value = str(state)

    def reset(self, t=None) -> None:
        self.value = self.default

    def to_dict(self, t=None) -> dict:
        d = super().to_dict()
        d.update(value=self.value, default=self.default)
        return d


FIELD_TYPES = {cls.type: cls for cls in
               (CounterField, TextField, ToggleField, ChoiceField, ClockField, PenaltyField, ImageField)}


def field_from_dict(d: dict) -> Field:
    d = dict(d)
    kind = d.pop("type", None)
    if kind not in FIELD_TYPES:
        raise ValueError(f"Unknown field type {kind!r}.")
    return FIELD_TYPES[kind](**d)
