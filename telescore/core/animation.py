"""
Animations for board elements.

An animation is a small recipe: what an element looks like at the start of
an "in" (or the end of an "out", or the peak of an "emphasis"), how long the
move takes, and its easing. Built-in presets cover SportzSuite's Fly, Tween
(here "Wipe") and Fade, Keystone's on-air slide, and a few emphasis moves.
Projects can add their own in the builder.

    kind      in | out | emphasis
    opacity   0..1     start opacity (in), end opacity (out), peak (emphasis)
    x, y      px       offset from the element's place
    scale     1 = none
    wipe      "" | left | right | up | down   reveal (in) or conceal (out) direction
    duration  ms;  delay ms;  easing name;  repeat (emphasis only)

Triggers, set per element in the builder:
    anim_in      when the element becomes visible (show-when, or a condition's Show)
    anim_out     when it becomes hidden; it is hidden at the end
    anim_change  when its text or picture changes
and a condition's "Animate" action plays any animation by name.

The browser source (outputs/overlay.py) carries a JavaScript copy of
:func:`sample` and :func:`ease`; tests check that both agree.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .board import Board, Element, render_template
from .logic import apply_rules

__all__ = ["Animation", "BUILTIN", "EASINGS", "ease", "sample", "library", "Tracker", "element_text", "IDENTITY"]

IDENTITY = {"opacity": 1.0, "x": 0.0, "y": 0.0, "scale": 1.0, "clip": (0.0, 0.0, 1.0, 1.0)}

# name -> cubic-bezier control points (x1, y1, x2, y2), or a special
EASINGS: Dict[str, Any] = {
    "linear": (0.0, 0.0, 1.0, 1.0),
    "ease": (0.25, 0.1, 0.25, 1.0),
    "ease-in": (0.42, 0.0, 1.0, 1.0),
    "ease-out": (0.0, 0.0, 0.58, 1.0),
    "ease-in-out": (0.42, 0.0, 0.58, 1.0),
    "broadcast": (0.2, 0.8, 0.2, 1.0),      # Keystone's on-air curve
    "back-out": (0.34, 1.56, 0.64, 1.0),    # overshoots, then settles
    "bounce-out": "bounce",
}


def _bezier(x1: float, y1: float, x2: float, y2: float, x: float) -> float:
    """CSS cubic-bezier: solve for t at x (Newton, then bisection), return y."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0

    def bx(t):
        return 3 * (1 - t) ** 2 * t * x1 + 3 * (1 - t) * t ** 2 * x2 + t ** 3

    def by(t):
        return 3 * (1 - t) ** 2 * t * y1 + 3 * (1 - t) * t ** 2 * y2 + t ** 3

    def dbx(t):
        return 3 * (1 - t) ** 2 * x1 + 6 * (1 - t) * t * (x2 - x1) + 3 * t ** 2 * (1 - x2)

    t = x
    for _ in range(8):
        err = bx(t) - x
        if abs(err) < 1e-7:
            return by(t)
        d = dbx(t)
        if abs(d) < 1e-6:
            break
        t -= err / d
    lo, hi = 0.0, 1.0
    t = x
    for _ in range(40):
        v = bx(t)
        if abs(v - x) < 1e-7:
            break
        if v < x:
            lo = t
        else:
            hi = t
        t = (lo + hi) / 2
    return by(t)


def _bounce(x: float) -> float:
    n, d = 7.5625, 2.75
    if x < 1 / d:
        return n * x * x
    if x < 2 / d:
        x -= 1.5 / d
        return n * x * x + 0.75
    if x < 2.5 / d:
        x -= 2.25 / d
        return n * x * x + 0.9375
    x -= 2.625 / d
    return n * x * x + 0.984375


def ease(name: str, x: float) -> float:
    x = max(0.0, min(1.0, x))
    e = EASINGS.get(name, EASINGS["broadcast"])
    if e == "bounce":
        return _bounce(x)
    return _bezier(*e, x)


@dataclass
class Animation:
    name: str = "Fade in"
    kind: str = "in"
    duration: int = 350
    delay: int = 0
    easing: str = "broadcast"
    opacity: float = 0.0
    x: float = 0.0
    y: float = 0.0
    scale: float = 1.0
    wipe: str = ""
    repeat: int = 1
    builtin: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("builtin", None)
        return d

    @classmethod
    def from_dict(cls, d: Mapping) -> "Animation":
        names = set(cls.__dataclass_fields__) - {"builtin"}
        a = cls(**{k: v for k, v in d.items() if k in names})
        if a.kind not in ("in", "out", "emphasis"):
            raise ValueError(f"Animation {a.name!r}: kind must be in, out or emphasis.")
        if a.wipe not in ("", "left", "right", "up", "down"):
            raise ValueError(f"Animation {a.name!r}: wipe must be left, right, up or down.")
        a.duration = max(1, int(a.duration))
        a.delay = max(0, int(a.delay))
        a.repeat = max(1, int(a.repeat))
        return a

    @property
    def total(self) -> int:
        return self.delay + self.duration * (self.repeat if self.kind == "emphasis" else 1)


def _b(**kw) -> Animation:
    kw.setdefault("builtin", True)
    return Animation(**kw)


BUILTIN: List[Animation] = [
    _b(name="Fade in", kind="in", duration=350, opacity=0.0),
    _b(name="Fade out", kind="out", duration=350, opacity=0.0),
    # SportzSuite "Fly": in from / out to an edge
    _b(name="Fly in from left", kind="in", duration=450, x=-260, opacity=1.0),
    _b(name="Fly in from right", kind="in", duration=450, x=260, opacity=1.0),
    _b(name="Fly in from top", kind="in", duration=450, y=-160, opacity=1.0),
    _b(name="Fly in from bottom", kind="in", duration=450, y=160, opacity=1.0),
    _b(name="Fly out to left", kind="out", duration=450, x=-260, opacity=1.0, easing="ease-in"),
    _b(name="Fly out to right", kind="out", duration=450, x=260, opacity=1.0, easing="ease-in"),
    _b(name="Fly out to top", kind="out", duration=450, y=-160, opacity=1.0, easing="ease-in"),
    _b(name="Fly out to bottom", kind="out", duration=450, y=160, opacity=1.0, easing="ease-in"),
    # SportzSuite "Tween": the element folds in or out
    _b(name="Wipe in from left", kind="in", duration=400, opacity=1.0, wipe="left"),
    _b(name="Wipe in from right", kind="in", duration=400, opacity=1.0, wipe="right"),
    _b(name="Wipe in upward", kind="in", duration=400, opacity=1.0, wipe="up"),
    _b(name="Wipe in downward", kind="in", duration=400, opacity=1.0, wipe="down"),
    _b(name="Wipe out to left", kind="out", duration=400, opacity=1.0, wipe="left"),
    _b(name="Wipe out to right", kind="out", duration=400, opacity=1.0, wipe="right"),
    _b(name="Wipe out upward", kind="out", duration=400, opacity=1.0, wipe="up"),
    _b(name="Wipe out downward", kind="out", duration=400, opacity=1.0, wipe="down"),
    # Keystone on-air slides: 90 px sideways or 60 px vertical with a fade
    _b(name="Slide in from left", kind="in", duration=450, x=-90, opacity=0.0),
    _b(name="Slide in from right", kind="in", duration=450, x=90, opacity=0.0),
    _b(name="Slide in from below", kind="in", duration=450, y=60, opacity=0.0),
    _b(name="Slide out to left", kind="out", duration=450, x=-90, opacity=0.0, easing="ease-in"),
    _b(name="Slide out to right", kind="out", duration=450, x=90, opacity=0.0, easing="ease-in"),
    _b(name="Slide out downward", kind="out", duration=450, y=60, opacity=0.0, easing="ease-in"),
    _b(name="Pop in", kind="in", duration=380, scale=0.6, opacity=0.0, easing="back-out"),
    _b(name="Pop out", kind="out", duration=300, scale=0.6, opacity=0.0, easing="ease-in"),
    _b(name="Drop in", kind="in", duration=700, y=-120, opacity=1.0, easing="bounce-out"),
    # Emphasis: plays and returns to normal
    _b(name="Flash", kind="emphasis", duration=300, opacity=0.15, easing="ease-in-out", repeat=3),
    _b(name="Pulse", kind="emphasis", duration=450, scale=1.18, opacity=1.0, easing="ease-in-out"),
    _b(name="Shake", kind="emphasis", duration=90, x=10, opacity=1.0, easing="linear", repeat=4),
    _b(name="Bump up", kind="emphasis", duration=350, y=-14, opacity=1.0, easing="ease-out"),
]


def library(custom: Iterable[Animation] = ()) -> Dict[str, Animation]:
    """Built-ins, then project animations (a custom one may replace a built-in name)."""
    lib = {a.name: a for a in BUILTIN}
    for a in custom:
        lib[a.name] = a
    return lib


def _lerp(a: float, b: float, p: float) -> float:
    return a + (b - a) * p


def sample(a: Animation, elapsed_ms: float, w: float = 0.0, h: float = 0.0) -> Dict[str, Any]:
    """The element's look ``elapsed_ms`` after ``a`` started.

    Returns opacity, x, y (px offsets), scale (about the element's centre)
    and clip (x0, y0, x1, y1 as fractions of the element box)."""
    t = elapsed_ms - a.delay
    if a.kind == "emphasis":
        if t <= 0 or t >= a.duration * a.repeat:
            return dict(IDENTITY)
        phase = (t % a.duration) / a.duration
        tri = phase * 2 if phase < 0.5 else (1 - phase) * 2     # 0 -> 1 -> 0
        p = ease(a.easing, tri)
        return {"opacity": _lerp(1.0, a.opacity, p), "x": _lerp(0.0, a.x, p), "y": _lerp(0.0, a.y, p),
                "scale": _lerp(1.0, a.scale, p), "clip": (0.0, 0.0, 1.0, 1.0)}
    raw = 0.0 if t <= 0 else min(1.0, t / a.duration)
    p = ease(a.easing, raw)
    # "in": from the recipe to normal. "out": from normal to the recipe.
    k = 1.0 - p if a.kind == "in" else p          # weight of the recipe's values
    shown = p if a.kind == "in" else 1.0 - p      # how much of a wipe is revealed
    shown = max(0.0, min(1.0, shown))
    clip = (0.0, 0.0, 1.0, 1.0)
    if a.wipe == "left":
        clip = (0.0, 0.0, shown, 1.0)
    elif a.wipe == "right":
        clip = (1.0 - shown, 0.0, 1.0, 1.0)
    elif a.wipe == "up":
        clip = (0.0, 1.0 - shown, 1.0, 1.0)
    elif a.wipe == "down":
        clip = (0.0, 0.0, 1.0, shown)
    return {"opacity": max(0.0, min(1.0, _lerp(1.0, a.opacity, k))), "x": a.x * k, "y": a.y * k,
            "scale": _lerp(1.0, a.scale, k), "clip": clip}


def element_text(e: Element, values: Mapping[str, str], fx: Optional[Mapping[str, Any]] = None) -> str:
    """An element's displayed text: its template, then its own rules, then a
    conditional rule from a condition (a plain rule wins, as in SportzSuite)."""
    text = render_template(e.text, values)
    r = apply_rules(e.rules, text)
    if r is not None:
        return r
    rule = (fx or {}).get("rule")
    if rule:
        r = apply_rules(rule, text)
        if r is not None:
            return r
    return text


class _ElState:
    __slots__ = ("visible", "content", "anim", "start", "hide_after")

    def __init__(self):
        self.visible: Optional[bool] = None
        self.content: Optional[str] = None
        self.anim: Optional[Animation] = None
        self.start = 0.0
        self.hide_after = False


class Tracker:
    """Turns visibility and content changes into running animations.

    Call :meth:`update` with new values and effects; ask :meth:`look` for
    each element while painting. Times are seconds (monotonic)."""

    def __init__(self, board: Optional[Board] = None, custom: Iterable[Animation] = ()):
        self.board = board
        self.lib = library(custom)
        self.state: Dict[str, _ElState] = {}
        self._fx_ids: Dict[str, int] = {}

    def set_board(self, board: Optional[Board], custom: Iterable[Animation] = ()) -> None:
        if board is not self.board:
            self.state = {}
        self.board = board
        self.lib = library(custom)

    @staticmethod
    def target_visible(e: Element, values: Mapping[str, str], fx: Mapping[str, Any]) -> bool:
        if not e.visible:
            return False
        if "visible" in fx:
            return bool(fx["visible"])
        return e.shown(values)

    @staticmethod
    def content(e: Element, values: Mapping[str, str], fx: Mapping[str, Any]) -> str:
        if e.kind == "text":
            return element_text(e, values, fx)
        if e.kind == "image":
            return fx.get("src") or render_template(e.src, values)
        return ""

    def _start(self, st: _ElState, name: str, t: float, hide_after: bool = False) -> bool:
        a = self.lib.get(name)
        if a is None:
            return False
        st.anim, st.start, st.hide_after = a, t, hide_after or a.kind == "out"
        return True

    def update(self, values: Mapping[str, str], fx_all: Mapping[str, Mapping[str, Any]], t: float,
               animate: bool = True) -> None:
        if self.board is None:
            return
        for e in self.board.elements:
            fx = fx_all.get(e.id, {})
            st = self.state.setdefault(e.id, _ElState())
            vis = self.target_visible(e, values, fx)
            cont = self.content(e, values, fx)
            first = st.visible is None
            if not first and animate:
                if vis and not st.visible:
                    if not (e.anim_in and self._start(st, e.anim_in, t)):
                        st.anim = None
                elif not vis and st.visible:
                    if e.anim_out and self._start(st, e.anim_out, t, hide_after=True):
                        pass
                    else:
                        st.anim = None
                elif vis and cont != st.content and e.anim_change:
                    self._start(st, e.anim_change, t)
            anim = fx.get("anim")
            if anim and animate and self._fx_ids.get(e.id) != anim.get("id"):
                self._fx_ids[e.id] = anim.get("id")
                if not first:
                    a = self.lib.get(anim.get("name", ""))
                    if a is not None:
                        self._start(st, a.name, t, hide_after=a.kind == "out")
                        if a.kind == "in":
                            vis = True
            elif anim:
                self._fx_ids[e.id] = anim.get("id")
            st.visible, st.content = vis, cont

    def look(self, e: Element, t: float) -> Optional[Dict[str, Any]]:
        """None = do not draw. Otherwise the transform to draw with."""
        st = self.state.get(e.id)
        if st is None:
            return dict(IDENTITY) if e.visible else None
        if st.anim is not None:
            elapsed = (t - st.start) * 1000.0
            if elapsed >= st.anim.total:
                hide = st.hide_after
                st.anim = None
                if hide:
                    return None
            else:
                if elapsed < st.anim.delay and st.anim.kind == "in":
                    return None if not st.visible else sample(st.anim, elapsed, e.w, e.h)
                return sample(st.anim, elapsed, e.w, e.h)
        return dict(IDENTITY) if st.visible else None

    def active(self, t: float) -> bool:
        return any(s.anim is not None and (t - s.start) * 1000.0 < s.anim.total + 20 for s in self.state.values())

    def play(self, eid: str, name: str, t: float) -> bool:
        """Preview an animation now (the builder's Try button)."""
        st = self.state.setdefault(eid, _ElState())
        if st.visible is None:
            st.visible = True
        a = self.lib.get(name)
        if a is None:
            return False
        st.anim, st.start, st.hide_after = a, t, False
        return True
