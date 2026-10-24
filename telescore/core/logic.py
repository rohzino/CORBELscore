"""
Rules, overrides and conditions: the SportzSuite model, applied to every
output (text files, XML, JSON, boards), not just graphics.

Value pipeline for a field, in order (first match wins):

    1. override      while ``override_on``, the field shows ``override`` text
    2. live source   a bound live-data key (Sportzcast HomeScore, Clock, ...)
                     replaces the field's own value
    3. rule          ``bot value=display value`` pairs joined by ``|``
    4. conditional   a rule that applies only while a condition holds
       rule          (a plain rule beats a conditional rule, as in SportzSuite)
    5. the value itself

Rules: ``0.0=Final|2:00=Two-minute warning``. ``*`` matches any run of
characters (``0:0*=FINAL SECONDS``); ``\\|`` and ``\\=`` are literal; ``NULL``
on the left matches an empty value; ``{value}`` on the right inserts the
original value (``1=1st {value}``).

Conditions: "If <principal> <op> <value> then <target> <action> <arg>".
A condition is checked when its principal's value changes (and once when the
project opens), like SportzSuite evaluating new bot data.

Operators: equals (SportzSuite "has value"), not_equals, greater, less,
changes_by, changes, contains, empty, not_empty. ``NULL`` means empty.
Numbers compare as numbers and times (2:00, 34.5) as seconds.

Target actions on a board element:
    show / hide <ms or *>     show_once <ms or *>     color <colour>   fill <colour>
    font <family>             image <file>             rule <rules>     animate <name>
Target actions on a field (these reach .txt and .xml):
    rule <rules>   while the condition holds, apply these rules to the field
    set <value>    set the field (not an undo step)
    pulse <ms>     switch a toggle on for ms, then off
    action         run any action, e.g. the "Next period" button's action
Every action can have a finish: after ``finish_ms``, run ``finish`` (e.g. hide,
or an out animation), as SportzSuite's finish animations do.
"""

from __future__ import annotations

import fnmatch
import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .timefmt import TimeParseError, parse_time

__all__ = ["parse_rules", "apply_rules", "Condition", "Logic", "OPS", "ELEMENT_ACTIONS", "FIELD_ACTIONS",
           "compare_value"]

OPS = {
    "equals": "has value",
    "not_equals": "does not have value",
    "greater": "is greater than",
    "less": "is less than",
    "changes_by": "changes by",
    "changes": "changes",
    "contains": "contains",
    "empty": "is empty",
    "not_empty": "is not empty",
}
ELEMENT_ACTIONS = {
    "show": "Show", "show_once": "Show once", "hide": "Hide", "color": "Change colour",
    "fill": "Change fill", "font": "Change font", "image": "Alternate picture", "rule": "Conditional rule",
    "animate": "Animate",
}
FIELD_ACTIONS = {"rule": "Conditional rule", "set": "Set value", "pulse": "Pulse on", "action": "Run action"}


# ----- rules ---------------------------------------------------------------------

def _split(text: str, sep: str, keep: bool = False) -> List[str]:
    """Split on ``sep`` unless escaped with a backslash. ``keep`` leaves the
    escapes in the pieces (for a later split on another separator)."""
    out, cur, esc = [], [], False
    for ch in text:
        if esc:
            if keep:
                cur.append("\\" + ch)
            else:
                cur.append(ch if ch in "|=\\" else "\\" + ch)
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == sep:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if esc:
        cur.append("\\")
    out.append("".join(cur))
    return out


def parse_rules(text: str) -> List[Tuple[str, str]]:
    """``"a=b|c=d"`` -> [("a", "b"), ("c", "d")]. Pieces without ``=`` are ignored."""
    pairs = []
    if not text:
        return pairs
    for piece in _split(text, "|", keep=True):
        if not piece.strip():
            continue
        parts = _split(piece, "=")
        if len(parts) < 2:
            continue
        left = parts[0].strip()
        right = "=".join(parts[1:]).strip()
        pairs.append((left, right))
    return pairs


_RULE_CACHE: Dict[str, List[Tuple[str, str]]] = {}


def apply_rules(rules: str, value: str) -> Optional[str]:
    """The replacement for ``value``, or None when no rule matches."""
    if not rules:
        return None
    pairs = _RULE_CACHE.get(rules)
    if pairs is None:
        pairs = parse_rules(rules)
        if len(_RULE_CACHE) > 500:
            _RULE_CACHE.clear()
        _RULE_CACHE[rules] = pairs
    v = (value or "").strip()
    for left, right in pairs:
        if left == "NULL":
            hit = v == ""
        elif "*" in left or "?" in left:
            hit = fnmatch.fnmatchcase(v, left.replace("[", "[[]"))
        else:
            hit = v == left
        if hit:
            return right.replace("{value}", value or "")
    return None


# ----- comparisons ----------------------------------------------------------------

_NUM = re.compile(r"^[+-]?\d+(\.\d+)?$")


def _number(text: str) -> Optional[float]:
    s = (text or "").strip()
    if _NUM.match(s):
        return float(s)
    if ":" in s or "." in s:
        try:
            return parse_time(s) / 1000.0
        except TimeParseError:
            return None
    return None


def compare_value(op: str, current: str, target: str, previous: Optional[str]) -> bool:
    cur = (current or "").strip()
    tgt = "" if (target or "").strip() == "NULL" else (target or "").strip()
    if op == "equals":
        return cur == tgt
    if op == "not_equals":
        return cur != tgt
    if op == "empty":
        return cur == ""
    if op == "not_empty":
        return cur != ""
    if op == "contains":
        return tgt.lower() in cur.lower() if tgt else False
    if op == "changes":
        return previous is not None and previous != current
    if op in ("greater", "less"):
        a, b = _number(cur), _number(tgt)
        if a is None or b is None:
            return False
        return a > b if op == "greater" else a < b
    if op == "changes_by":
        if previous is None:
            return False
        a, b, d = _number(cur), _number(previous), _number(tgt)
        if a is None or b is None or d is None:
            return False
        return abs((a - b) - d) < 1e-6
    raise ValueError(f"Unknown condition {op!r}.")


# ----- conditions ------------------------------------------------------------------

@dataclass
class Condition:
    principal: str = ""                  # field key (sub-keys allowed: home.penalties.1.time)
    op: str = "equals"
    value: str = ""
    target_kind: str = "element"         # element | field
    target: str = ""                     # element id, or field key
    action: str = "show"
    arg: str = "*"                       # ms or *, colour, font, rules, value, animation name
    run: Dict[str, Any] = field(default_factory=dict)   # for action == "action"
    finish_ms: int = 0                   # 0 = no finish
    finish: str = ""                     # finish action (element: hide, show, animate:<name>; field: set:<value>)
    enabled: bool = True
    note: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v not in ("", {}, 0) or k in ("principal", "op", "target", "action", "id")}

    @classmethod
    def from_dict(cls, d: Mapping) -> "Condition":
        names = set(cls.__dataclass_fields__)
        c = cls(**{k: v for k, v in d.items() if k in names})
        if c.op not in OPS:
            raise ValueError(f"Unknown condition {c.op!r}.")
        acts = ELEMENT_ACTIONS if c.target_kind == "element" else FIELD_ACTIONS
        if c.action not in acts:
            raise ValueError(f"{c.action!r} is not an action for a {c.target_kind}.")
        return c

    def describe(self, labels: Mapping[str, str] = {}) -> str:
        v = "" if self.op in ("empty", "not_empty", "changes") else f" {self.value or 'NULL'}"
        tgt = labels.get(self.target, self.target)
        arg = "" if self.action in ("action",) else f" {self.arg}"
        fin = f", then after {self.finish_ms} ms {self.finish}" if self.finish_ms and self.finish else ""
        return f"If {self.principal} {OPS.get(self.op, self.op)}{v} then {tgt} {ELEMENT_ACTIONS.get(self.action) or FIELD_ACTIONS.get(self.action, self.action)}{arg}{fin}"


def _ms(arg: str) -> Optional[int]:
    """'*' or '' -> None (indefinitely); '5000' -> 5000."""
    s = (arg or "").strip()
    if s in ("", "*"):
        return None
    try:
        return max(0, int(float(s)))
    except ValueError:
        return None


class Logic:
    """Evaluates conditions and keeps their effects.

    The engine calls :meth:`evaluate` with the published values each time it
    builds a snapshot. Effects come back two ways:
      * ``fx``: per board element: visible, color, fill, font, src, rule,
        anim {name, id}; read by every board renderer;
      * ``field_rules``: conditional rules per field, applied by the engine
        before it publishes values;
      * ``pending``: actions (set, pulse, run) the engine performs next tick.
    """

    def __init__(self, conditions: Optional[List[Condition]] = None):
        self.conditions: List[Condition] = list(conditions or [])
        self.reset()

    def reset(self) -> None:
        self.prev: Dict[str, str] = {}                 # principal -> last value seen
        self.truth: Dict[str, bool] = {}               # condition id -> last result
        self.fx: Dict[str, Dict[str, Any]] = {}        # element id -> effects
        self.field_rules: Dict[str, Dict[str, str]] = {}   # field key -> {condition id: rules}
        self.timers: List[Tuple[float, str, Any]] = []  # (due, kind, payload)
        self.pending: List[dict] = []
        self._anim_id = 0
        self.started = False

    def set_conditions(self, conds: List[Condition]) -> None:
        self.conditions = list(conds)
        self.reset()

    def principals(self) -> set:
        return {c.principal for c in self.conditions if c.enabled}

    # ----- effects -------------------------------------------------------
    def _fx(self, eid: str) -> Dict[str, Any]:
        return self.fx.setdefault(eid, {})

    def _element_action(self, eid: str, action: str, arg: str, t: float) -> None:
        fx = self._fx(eid)
        if action in ("show", "show_once", "hide"):
            vis = action != "hide"
            fx["visible"] = vis
            ms = _ms(arg)
            self.timers = [x for x in self.timers if not (x[1] == "vis" and x[2][0] == eid)]
            if ms is not None:
                self.timers.append((t + ms / 1000.0, "vis", (eid, not vis)))
        elif action in ("color", "fill", "font", "image", "rule"):
            key = {"image": "src"}.get(action, action)
            if arg.strip() in ("", "*", "NULL"):
                fx.pop(key, None)
            else:
                fx[key] = arg.strip()
        elif action == "animate":
            self._anim_id += 1
            fx["anim"] = {"name": arg.strip(), "id": self._anim_id}

    def _finish(self, c: Condition, t: float) -> None:
        if not c.finish_ms or not c.finish:
            return
        self.timers.append((t + c.finish_ms / 1000.0, "finish", (c.target_kind, c.target, c.finish)))

    def _run_finish(self, kind: str, target: str, finish: str, t: float) -> None:
        verb, _, arg = finish.partition(":")
        if kind == "element":
            if verb in ELEMENT_ACTIONS:
                self._element_action(target, verb, arg or "*", t)
        else:
            if verb == "set":
                self.pending.append({"do": "set", "field": target, "value": arg})

    def _fire(self, c: Condition, t: float) -> None:
        if c.target_kind == "element":
            self._element_action(c.target, c.action, c.arg, t)
        else:
            if c.action == "set":
                self.pending.append({"do": "set", "field": c.target, "value": c.arg})
            elif c.action == "pulse":
                self.pending.append({"do": "set", "field": c.target, "value": True})
                ms = _ms(c.arg) or 1000
                self.timers.append((t + ms / 1000.0, "pending", {"do": "set", "field": c.target, "value": False}))
            elif c.action == "action" and c.run:
                self.pending.append(dict(c.run))
        self._finish(c, t)

    # ----- evaluation -------------------------------------------------------
    def evaluate(self, values: Mapping[str, str], t: float) -> bool:
        """Check conditions whose principal changed; run due timers. Returns
        True when ``field_rules`` changed (the engine then re-applies them)."""
        rules_before = {k: dict(v) for k, v in self.field_rules.items()}
        # timers first, so a finish scheduled earlier lands before new events
        if self.timers:
            due = [x for x in self.timers if x[0] <= t]
            if due:
                self.timers = [x for x in self.timers if x[0] > t]
                for _, kind, payload in sorted(due, key=lambda x: x[0]):
                    if kind == "vis":
                        eid, vis = payload
                        self._fx(eid)["visible"] = vis
                    elif kind == "finish":
                        self._run_finish(payload[0], payload[1], payload[2], t)
                    elif kind == "pending":
                        self.pending.append(payload)
        changed = {k for k in self.principals()
                   if (not self.started) or values.get(k, "") != self.prev.get(k, "")}
        for c in self.conditions:
            if not c.enabled or c.principal not in changed:
                continue
            cur = values.get(c.principal, "")
            prev = self.prev.get(c.principal) if self.started else None
            try:
                ok = compare_value(c.op, cur, c.value, prev)
            except ValueError:
                ok = False
            was = self.truth.get(c.id, False)
            self.truth[c.id] = ok
            if c.action == "rule":
                # Conditional rules hold while their condition holds.
                if c.target_kind == "field":
                    slot = self.field_rules.setdefault(c.target, {})
                    if ok:
                        slot[c.id] = c.arg
                    else:
                        slot.pop(c.id, None)
                elif ok:
                    self._fx(c.target)["rule"] = c.arg
                elif self._fx(c.target).get("rule") == c.arg:
                    self._fx(c.target).pop("rule", None)
                continue
            if not ok:
                continue
            if c.action == "show_once" and was:
                continue
            self._fire(c, t)
        for k in changed:
            self.prev[k] = values.get(k, "")
        self.started = True
        self.field_rules = {k: v for k, v in self.field_rules.items() if v}
        return self.field_rules != rules_before

    def take_pending(self) -> List[dict]:
        out, self.pending = self.pending, []
        return out

    def conditional_rules(self, key: str) -> List[str]:
        return list(self.field_rules.get(key, {}).values())

    def next_due(self) -> Optional[float]:
        return min((x[0] for x in self.timers), default=None)

    def fx_snapshot(self) -> Dict[str, Dict[str, Any]]:
        return {k: dict(v) for k, v in self.fx.items() if v}
