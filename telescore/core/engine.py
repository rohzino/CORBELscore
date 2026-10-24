"""
The engine owns the fields, runs the clocks, carries out actions and publishes
snapshots for outputs.

Threading: the engine is driven from one thread (the Qt GUI thread calls
:meth:`tick` on a timer). Other threads, such as the HTTP control server, never
touch fields; they call :meth:`submit`, and the action runs on the next tick.
:meth:`snapshot` is safe from any thread.
"""

from __future__ import annotations

import queue
import threading
from collections import OrderedDict
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from .clock import now
from .fields import (ChoiceField, ClockField, CounterField, Field, ImageField, PenaltyField,
                     TextField, ToggleField)
from .logic import Condition, Logic, apply_rules
from .timefmt import TimeParseError, parse_time

__all__ = ["Engine", "ActionError", "Snapshot", "ACTIONS", "FX_KEY", "BASE_KEY"]

Listener = Callable[["Snapshot", set], None]


class ActionError(ValueError):
    """An action that cannot be carried out. The message is written for the
    operator: what happened and what to do next."""


class Snapshot:
    """An immutable picture of every field at one moment.

    ``values``  flat ``{key: display text}`` including sub-keys
                (``clock.game.running``, ``home.penalties.1.time``)
    ``raw``     ``{key: machine value}`` for top-level fields
    ``types``   ``{key: field type}`` for top-level fields
    ``labels``  ``{key: label}`` for top-level fields
    """

    __slots__ = ("values", "raw", "types", "labels", "seq", "wall", "fx", "base", "live")

    def __init__(self, values, raw, types, labels, seq, wall, fx=None, base=None, live=None):
        self.values: Dict[str, str] = values
        self.raw: Dict[str, Any] = raw
        self.types: Dict[str, str] = types
        self.labels: Dict[str, str] = labels
        self.seq: int = seq
        self.wall: float = wall
        # Board element effects from conditions: {element id: {visible, color, fill, font, src, rule, anim}}
        self.fx: Dict[str, Dict[str, Any]] = fx or {}
        # Each top-level field's value before override and rules (what the field itself holds)
        self.base: Dict[str, str] = base or {}
        # Keys whose value currently comes from a live source
        self.live: set = live or set()

    def get(self, key: str, default: str = "") -> str:
        return self.values.get(key, default)


# Action vocabulary --------------------------------------------------------
# Every button, hotkey and HTTP call is one of these dictionaries.
ACTIONS = {
    "set":        "Set a field: {do, field, value}",
    "add":        "Add to a counter (negative to subtract): {do, field, amount}",
    "reset":      "Reset a field to its default; a clock to its period length: {do, field}",
    "toggle":     "Flip a toggle, or start/stop a clock: {do, field}",
    "start":      "Start a clock: {do, field}",
    "stop":       "Stop a clock: {do, field}",
    "adjust":     "Add milliseconds to a clock (negative removes): {do, field, ms}",
    "next":       "Next option of a choice, or +1 on a counter: {do, field}",
    "prev":       "Previous option of a choice, or -1 on a counter: {do, field}",
    "penalty.add":    "{do, field, player, time}",
    "penalty.remove": "{do, field, index (1-based)}",
    "penalty.clear":  "{do, field}",
    "stop_all":   "Stop every running clock: {do}",
    "batch":      "Run several actions as one undo step: {do, actions: [...]}",
    "undo":       "Undo the last action: {do}",
    "redo":       "Redo: {do}",
}

_UNDO_LIMIT = 200
FX_KEY = "#fx"        # in a change set: board element effects changed
BASE_KEY = "#live"    # in a change set: which fields follow a live source changed


def _raw_from_text(f: Field, text: str) -> Any:
    """Machine value for a field fed from live text."""
    s = (text or "").strip()
    if isinstance(f, CounterField):
        try:
            return int(s)
        except ValueError:
            return s
    if isinstance(f, ClockField):
        try:
            return parse_time(s)
        except TimeParseError:
            return s
    if isinstance(f, ToggleField):
        return s not in ("", "0", "false", "False", "N", "n")
    return text


class Engine:
    def __init__(self, fields: Iterable[Field] = ()) -> None:
        self._fields: "OrderedDict[str, Field]" = OrderedDict()
        self._undo: List[List[Tuple[str, Any, float]]] = []
        self._redo: List[List[Tuple[str, Any, float]]] = []
        for f in fields:
            self.add_field(f)
        self._listeners: List[Listener] = []
        self._expired_listeners: List[Callable[[str], None]] = []
        self._inbox: "queue.Queue[Tuple[dict, Optional[Callable]]]" = queue.Queue()
        self._lock = threading.Lock()
        self._snapshot: Optional[Snapshot] = None
        self._seq = 0
        # Master clock states at the last settle: key -> (running, value_ms, t)
        self._marks: Dict[str, Tuple[bool, int, float]] = {}
        self.logic = Logic()
        self.sources: Dict[str, str] = {}          # live data: source key -> text
        self._feeds: "queue.Queue[Dict[str, str]]" = queue.Queue()
        self.last_feed: float = 0.0                # monotonic time of the last live packet
        self.logic_errors: List[str] = []
        self.publish(force=True)

    # ----- fields ----------------------------------------------------------
    @property
    def fields(self) -> "OrderedDict[str, Field]":
        return self._fields

    def field(self, key: str) -> Field:
        try:
            return self._fields[key]
        except KeyError:
            raise ActionError(f"There is no field called {key!r}. Check Setup → Fields for its name.") from None

    def add_field(self, f: Field, index: Optional[int] = None) -> None:
        if f.key in self._fields:
            raise ValueError(f"A field called {f.key!r} already exists.")
        for existing in self._fields:
            if existing.startswith(f.key + ".") or f.key.startswith(existing + "."):
                # A sub-key collision would make outputs ambiguous (home.score vs home.score.x).
                if isinstance(self._fields[existing], (ClockField, PenaltyField, ChoiceField)) or \
                        isinstance(f, (ClockField, PenaltyField, ChoiceField)):
                    raise ValueError(f"{f.key!r} collides with the published sub-keys of {existing!r}.")
        if index is None:
            self._fields[f.key] = f
        else:
            items = list(self._fields.items())
            items.insert(index, (f.key, f))
            self._fields = OrderedDict(items)
        self._structure_changed()

    def remove_field(self, key: str) -> None:
        self._fields.pop(key, None)
        self._structure_changed()

    def _structure_changed(self) -> None:
        """Undo history refers to fields by key; after a structural change it
        is cleared, and the snapshot is rebuilt so outputs match at once."""
        self._undo.clear()
        self._redo.clear()
        if getattr(self, "_snapshot", None) is not None:
            self.publish(force=True)

    def rename_field(self, old: str, new: str) -> None:
        f = self.field(old)
        if new in self._fields:
            raise ValueError(f"A field called {new!r} already exists.")
        from .fields import valid_key
        if not valid_key(new):
            raise ValueError(f"{new!r} is not a valid field key.")
        items = [((new if k == old else k), v) for k, v in self._fields.items()]
        f.key = new
        self._fields = OrderedDict(items)
        self._structure_changed()

    # ----- live data and conditions ------------------------------------------
    def feed(self, values: Dict[str, Any]) -> None:
        """Live data from a source thread (Sportzcast, ...). Any thread."""
        self._feeds.put({str(k): ("" if v is None else str(v)) for k, v in values.items()})

    def clear_sources(self) -> None:
        self.sources = {}

    def set_conditions(self, conditions: List[Condition]) -> None:
        self.logic.set_conditions(conditions)
        if getattr(self, "_snapshot", None) is not None:
            self.publish(force=True)

    # ----- listeners -------------------------------------------------------
    def on_change(self, fn: Listener) -> None:
        self._listeners.append(fn)

    def on_expired(self, fn: Callable[[str], None]) -> None:
        """Called with the clock's key when a countdown hits zero (buzzer)."""
        self._expired_listeners.append(fn)

    # ----- actions ---------------------------------------------------------
    def submit(self, action: dict, done: Optional[Callable[[Optional[str]], None]] = None) -> None:
        """Queue an action from any thread. ``done(error_or_None)`` is called on
        the engine thread after it runs."""
        self._inbox.put((action, done))

    def perform(self, action: dict, t: Optional[float] = None) -> None:
        """Run one action now (engine thread only) and publish the result."""
        t = now() if t is None else t
        self._settle(t)
        do = (action or {}).get("do")
        if do == "undo":
            self._step(self._undo, self._redo, t)
        elif do == "redo":
            self._step(self._redo, self._undo, t)
        else:
            record: List[Tuple[str, Any, float]] = []
            try:
                self._run(action, t, record, depth=0)
            except Exception:
                # All or nothing: roll back what a failed batch already changed.
                for key, state, _ in reversed(record):
                    f = self._fields.get(key)
                    if f is not None:
                        f.restore(state, t)
                self._mark(t)
                raise
            if record:
                self._undo.append(record)
                del self._undo[:-_UNDO_LIMIT]
                self._redo.clear()
        self._mark(t)
        self.publish(t)

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def _remember(self, record, key: str, t: float) -> None:
        if any(k == key for k, _, _ in record):
            return
        record.append((key, self._fields[key].state(t), t))

    def _step(self, src, dst, t: float) -> None:
        if not src:
            return
        record = src.pop()
        back = []
        for key, state, t_then in record:
            f = self._fields.get(key)
            if f is None:
                continue
            back.append((key, f.state(t), t))
            if isinstance(f, ClockField):
                value, running = state
                if running and f.clock.running:
                    # The clock kept running since the action; keep that time.
                    run = int(round((t - t_then) * 1000))
                    value = value - run if f.clock.countdown else value + run
                f.restore((value, running), t)
            else:
                f.restore(state, t)
        dst.append(back)

    def _run(self, action: dict, t: float, record, depth: int) -> None:
        if not isinstance(action, dict):
            raise ActionError("An action must be a set of named values, such as {\"do\": \"add\"}.")
        do = action.get("do")
        if do not in ACTIONS:
            raise ActionError(f"Unknown action {do!r}. Known actions: {', '.join(ACTIONS)}.")
        if do == "batch":
            if depth > 4:
                raise ActionError("Batches can be nested at most 4 deep.")
            for sub in action.get("actions", []):
                self._run(sub, t, record, depth + 1)
            return
        if do == "stop_all":
            for k, f in self._fields.items():
                if isinstance(f, ClockField) and f.clock.running:
                    self._remember(record, k, t)
                    f.clock.stop(t)
            return
        if do in ("undo", "redo"):
            raise ActionError("Undo and redo cannot go inside a batch.")

        key = action.get("field")
        f = self.field(key)
        self._remember(record, key, t)
        try:
            self._apply(f, do, action, t)
        except ActionError:
            raise
        except ValueError as e:
            raise ActionError(str(e)) from None

    def _apply(self, f: Field, do: str, a: dict, t: float) -> None:
        if do == "reset":
            f.reset(t)
            return

        if isinstance(f, ClockField):
            c = f.clock
            if do == "start":
                if not c.start(t) and c.countdown and c.value(t) <= 0:
                    raise ActionError(f"{f.label} is at zero. Reset it or set a time first.")
            elif do == "stop":
                c.stop(t)
            elif do == "toggle":
                if not c.running and c.countdown and c.value(t) <= 0:
                    raise ActionError(f"{f.label} is at zero. Reset it or set a time first.")
                c.toggle(t)
            elif do == "set":
                v = a.get("value")
                ms = parse_time(v) if isinstance(v, str) else int(v)
                c.set(ms, t)
            elif do == "adjust":
                c.adjust(int(a.get("ms", 0)), t)
            elif do == "add":  # seconds, for convenience
                c.adjust(int(round(float(a.get("amount", 1)) * 1000)), t)
            else:
                raise ActionError(f"{do!r} does not apply to a clock.")
            return

        if isinstance(f, CounterField):
            if do == "add":
                f.add(int(a.get("amount", 1)))
            elif do == "set":
                f.set(a.get("value"))
            elif do == "next":
                f.add(1)
            elif do == "prev":
                f.add(-1)
            else:
                raise ActionError(f"{do!r} does not apply to a counter.")
            return

        if isinstance(f, ChoiceField):
            if do in ("next", "add"):
                f.step(int(a.get("amount", 1)) if do == "add" else 1)
            elif do == "prev":
                f.step(-1)
            elif do == "set":
                f.set(a.get("value"))
            else:
                raise ActionError(f"{do!r} does not apply to a choice.")
            return

        if isinstance(f, ToggleField):
            if do == "toggle":
                f.toggle()
            elif do == "set":
                f.set(a.get("value"))
            else:
                raise ActionError(f"{do!r} does not apply to a toggle.")
            return

        if isinstance(f, PenaltyField):
            if do == "penalty.add":
                f.add(str(a.get("player", "")), a.get("time", "2:00"))
            elif do == "penalty.remove":
                f.remove(int(a.get("index", 1)) - 1)
            elif do == "penalty.clear":
                f.clear()
            else:
                raise ActionError(f"{do!r} does not apply to penalties.")
            return

        if isinstance(f, (TextField, ImageField)):
            if do == "set":
                f.set(a.get("value", ""))
            else:
                raise ActionError(f"{do!r} does not apply to {f.type} fields.")
            return

        raise ActionError(f"{do!r} does not apply to {f.label}.")

    # ----- time ------------------------------------------------------------
    def _settle(self, t: float) -> None:
        """Advance penalties by exactly what their master clocks ran since the
        last settle, then fire expiries. Every action settles first, so a
        master's running state is constant between two settles."""
        expired: List[str] = []
        for f in self._fields.values():
            if isinstance(f, PenaltyField):
                mark = self._marks.get(f.master)
                master = self._fields.get(f.master)
                if mark and mark[0] and isinstance(master, ClockField):
                    ran = int(round((t - mark[2]) * 1000))
                    if master.clock.countdown:
                        ran = min(ran, mark[1])  # the master stopped at zero
                    f.advance(ran)
        for k, f in self._fields.items():
            if isinstance(f, ClockField) and f.clock.tick(t):
                expired.append(k)
        self._mark(t)
        for k in expired:
            for fn in self._expired_listeners:
                try:
                    fn(k)
                except Exception:  # a listener must never stop the clock
                    pass

    def _mark(self, t: float) -> None:
        self._marks = {k: (f.clock.running, f.clock.value(t), t)
                       for k, f in self._fields.items() if isinstance(f, ClockField)}

    def tick(self, t: Optional[float] = None) -> List[Tuple[dict, Optional[str]]]:
        """Drain queued actions, settle clocks and publish. Call 10-30 times a
        second from the UI thread. Returns (action, error) for queued actions."""
        t = now() if t is None else t
        results = []
        fed = False
        while True:
            try:
                self.sources.update(self._feeds.get_nowait())
                fed = True
            except queue.Empty:
                break
        if fed:
            self.last_feed = t
        for action in self.logic.take_pending():
            # Condition-driven actions change state but are not undo steps.
            try:
                self._run(action, t, [], depth=0)
            except (ActionError, ValueError) as e:
                self.logic_errors.append(f"A condition could not run {action.get('do')}: {e}")
                del self.logic_errors[:-20]
        while True:
            try:
                action, done = self._inbox.get_nowait()
            except queue.Empty:
                break
            err = None
            try:
                self.perform(action, t)
            except ActionError as e:
                err = str(e)
            except Exception as e:  # never let a remote call crash the engine
                err = f"That action failed: {e}"
            results.append((action, err))
            if done:
                try:
                    done(err)
                except Exception:
                    pass
        self._settle(t)
        self.publish(t)
        return results

    # ----- publishing ------------------------------------------------------
    def _source_text(self, f: Field) -> Optional[str]:
        if f.source and f.source in self.sources:
            return self.sources[f.source]
        return None

    def _pipeline(self, f: Field, base: str) -> str:
        """override > rule > conditional rule > value (see core.logic)."""
        if f.override_on:
            return f.override
        r = apply_rules(f.rules, base)
        if r is not None:
            return r
        for cr in self.logic.conditional_rules(f.key):
            r = apply_rules(cr, base)
            if r is not None:
                return r
        return base

    def build_snapshot(self, t: Optional[float] = None) -> Snapshot:
        t = now() if t is None else t
        values: Dict[str, str] = {}
        base: Dict[str, str] = {}
        raw: Dict[str, Any] = {}
        types: Dict[str, str] = {}
        labels: Dict[str, str] = {}
        live = set()
        for k, f in self._fields.items():
            src = self._source_text(f)
            if src is not None:
                live.add(k)
                b = src
                raw[k] = _raw_from_text(f, src)
            else:
                b = f.display(t)
                raw[k] = f.raw(t)
            base[k] = b
            values[k] = self._pipeline(f, b)
            extra = f.extra(t)
            if src is not None and isinstance(f, ClockField):
                status = self.sources.get(getattr(f, "source_status", "") or "ClockStatus")
                if status is not None:
                    extra = dict(extra, running="1" if status.strip().upper() == "R" else "0")
            for sub, text in extra.items():
                values[f"{k}.{sub}"] = text
            types[k] = f.type
            labels[k] = f.label
        # Conditions see the published values; conditional rules they switch on
        # change published values, which conditions may react to in turn.
        for _ in range(3):
            if not self.logic.evaluate(values, t):
                break
            for k, f in self._fields.items():
                values[k] = self._pipeline(f, base[k])
        import time as _time
        return Snapshot(values, raw, types, labels, self._seq, _time.time(), self.logic.fx_snapshot(), base, live)

    def publish(self, t: Optional[float] = None, force: bool = False) -> Optional[set]:
        """Rebuild the snapshot; notify listeners with the changed keys."""
        snap = self.build_snapshot(t)
        prev = self._snapshot
        if prev is None or force:
            changed = set(snap.values) | {FX_KEY, BASE_KEY}
        else:
            changed = {k for k, v in snap.values.items() if prev.values.get(k) != v}
            changed |= set(prev.values) - set(snap.values)
            if snap.fx != prev.fx:
                changed.add(FX_KEY)
            if snap.live != prev.live:
                changed.add(BASE_KEY)
            if snap.labels != prev.labels or snap.types != prev.types:
                changed |= set(snap.labels)
        if not changed and prev is not None:
            return None
        self._seq += 1
        snap.seq = self._seq
        with self._lock:
            self._snapshot = snap
        for fn in list(self._listeners):
            try:
                fn(snap, changed)
            except Exception:
                pass
        return changed

    def snapshot(self) -> Snapshot:
        with self._lock:
            return self._snapshot

    # ----- persistence -----------------------------------------------------
    def fields_to_list(self, t: Optional[float] = None) -> List[dict]:
        return [f.to_dict(t) for f in self._fields.values()]
