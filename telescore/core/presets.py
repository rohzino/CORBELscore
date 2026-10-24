"""
Starting templates for the New Project screen.

Each preset gives a sport's fields, a broadcast scorebug, a full-screen
scoreboard for a projector or LED wall, and an operator panel with that
sport's common moves and keyboard shortcuts. Everything is editable after.

The scorebug follows the Keystone on-air look: a flat near-black panel at 95%,
a 6px accent edge, team IDs in heavy capitals, tabular figures, small corners.
Team colour strips read ``{home.color}`` and ``{away.color}``.
"""

from __future__ import annotations

from typing import Callable, Dict, List

from .board import Board, Element
from .clock import Clock
from .engine import Engine
from .fields import (ChoiceField, ClockField, CounterField, ImageField, PenaltyField, TextField,
                     ToggleField)
from .project import Button, Panel, Project

__all__ = ["PRESETS", "make_project", "preset_names"]

# On-air palette (Keystone Dark brand; always used on air whatever the UI scheme)
ONAIR = {
    "ink": "#e8f1ec", "panel": "#18211e", "head": "#0a0f0d", "head95": "#0a0f0df2",
    "accent": "#3ddc84", "hi": "#5ad1e6", "user": "#ffb454", "alert": "#ff6b6b",
    "muted": "#a8b5ae", "rule": "#34423c",
}


def _teams(home="Home", away="Away", hs="HOM", as_="AWY") -> List:
    out = []
    for side, name, short, color in (("away", away, as_, "#5ad1e6"), ("home", home, hs, "#ffb454")):
        out += [
            TextField(f"{side}.name", f"{side.title()} name", value=name),
            TextField(f"{side}.short", f"{side.title()} abbreviation", value=short, uppercase=True),
            CounterField(f"{side}.score", f"{side.title()} score", steps=[1]),
            TextField(f"{side}.color", f"{side.title()} colour", value=color),
            ImageField(f"{side}.logo", f"{side.title()} logo"),
        ]
    return out


def _clock(key="clock.game", label="Game clock", minutes=12, tenths=True, countdown=True, fmt="m:ss"):
    c = Clock(countdown=countdown, initial_ms=minutes * 60_000 if countdown else 0, fmt=fmt,
              tenths_under_ms=60_000 if (tenths and countdown) else 0, tenths_fmt="s.t")
    return ClockField(key, label, clock=c)


def _t(**kw) -> Element:
    base = dict(kind="text", font="Archivo", weight=900, color=ONAIR["ink"], tabular=True, fit=True)
    base.update(kw)
    return Element(**base)


def _box(**kw) -> Element:
    base = dict(kind="box")
    base.update(kw)
    return Element(**base)


def _scorebug(extra_right: Callable[[float, float], List[Element]] = None, chip="{period}",
              clock="{clock.game}") -> Board:
    """A one-line scorebug, bottom left, 1920 x 1080 transparent."""
    x, y, h = 60, 950, 76
    els = [
        _box(name="Panel", x=x, y=y, w=100, h=h, fill=ONAIR["head95"], stroke=ONAIR["rule"],
             stroke_width=1, radius=3),
        _box(name="Accent edge", x=x, y=y, w=6, h=h, fill=ONAIR["accent"]),
    ]
    cx = x + 6
    for side in ("away", "home"):
        els += [
            _box(name=f"{side.title()} colour", x=cx + 14, y=y + 14, w=6, h=h - 28, fill="{%s.color}" % side),
            _t(name=f"{side.title()} ID", text="{%s.short}" % side, x=cx + 28, y=y, w=118, h=h,
               size=34, align="left", uppercase=True, tracking=0.02),
            _box(name=f"{side.title()} score box", x=cx + 150, y=y + 8, w=86, h=h - 16, fill=ONAIR["panel"], radius=3),
            _t(name=f"{side.title()} score", text="{%s.score}" % side, x=cx + 150, y=y + 8, w=86, h=h - 16, size=46),
        ]
        cx += 246
    els += [
        _box(name="Period chip", x=cx + 12, y=y + 16, w=84, h=h - 32, fill=ONAIR["accent"], radius=3),
        _t(name="Period", text=chip, x=cx + 12, y=y + 16, w=84, h=h - 32, size=26, color=ONAIR["head"],
           uppercase=True),
        _t(name="Clock", text=clock, x=cx + 104, y=y, w=150, h=h, size=44, weight=800),
    ]
    if not clock:
        els.pop()                      # no clock (baseball): the extras move left
        cx -= 154
    if extra_right:
        els += extra_right(cx + 260, y)
    # The panel hugs its permanent contents with a 14px end margin. Situational
    # tags (power play, added time) sit just outside it, so the panel never
    # carries an empty gap while they are hidden.
    right = max(e.x + e.w for e in els[2:] if not e.show_when)
    els[0].w = right + 14 - x
    tags = [e for e in els[2:] if e.show_when]
    if tags:
        shift = (right + 14 + 6) - min(e.x for e in tags)
        for e in tags:
            e.x += shift
    return Board(name="Scorebug", width=1920, height=1080, background="", elements=els)


def _projector(title_line: str = "{period}", clock="{clock.game}", extras: List[Element] = ()) -> Board:
    """A full-screen scoreboard for a projector, TV or LED wall."""
    els = [
        _box(name="Away colour", x=80, y=120, w=760, h=14, fill="{away.color}", radius=3),
        _box(name="Home colour", x=1080, y=120, w=760, h=14, fill="{home.color}", radius=3),
        _t(name="Away name", text="{away.name}", x=80, y=150, w=760, h=110, size=84, uppercase=True),
        _t(name="Home name", text="{home.name}", x=1080, y=150, w=760, h=110, size=84, uppercase=True),
        _t(name="Away score", text="{away.score}", x=80, y=270, w=760, h=420, size=380),
        _t(name="Home score", text="{home.score}", x=1080, y=270, w=760, h=420, size=380),
        _t(name="Clock", text=clock, x=560, y=720, w=800, h=220, size=200, weight=800, color=ONAIR["user"]),
        _t(name="Period", text=title_line, x=760, y=330, w=400, h=120, size=90, color=ONAIR["accent"],
           uppercase=True),
    ]
    return Board(name="Full screen", width=1920, height=1080, background="#000000",
                 elements=els + list(extras))


def _common_buttons(game="clock.game") -> List[Button]:
    return [
        Button("Start / stop clock", {"do": "toggle", "field": game}, role="accent", hotkey="Space"),
        Button("Undo", {"do": "undo"}, hotkey="Ctrl+Z"),
        Button("Redo", {"do": "redo"}, hotkey="Ctrl+Y"),
    ]


def _score_buttons(points=(1,)) -> List[Button]:
    out = []
    keys = {"away": ["Q", "W", "E"], "home": ["O", "P", "["]}
    for side in ("away", "home"):
        for i, p in enumerate(points):
            out.append(Button(f"{side.title()} +{p}", {"do": "add", "field": f"{side}.score", "amount": p},
                              hotkey=keys[side][i] if i < 3 else ""))
        out.append(Button(f"{side.title()} -1", {"do": "add", "field": f"{side}.score", "amount": -1},
                          role="alert"))
    return out


# ----- sports -----------------------------------------------------------------

def basketball() -> Project:
    shot = Clock(countdown=True, initial_ms=24_000, fmt="s", tenths_under_ms=5_000, tenths_fmt="s.t",
                 blank_at_zero=False)
    fields = _teams() + [
        _clock(minutes=10),
        ClockField("clock.shot", "Shot clock", clock=shot),
        ChoiceField("period", "Quarter", options=["1st", "2nd", "3rd", "4th", "OT"]),
        CounterField("away.fouls", "Away fouls", maximum=99), CounterField("home.fouls", "Home fouls", maximum=99),
        CounterField("away.timeouts", "Away time-outs", value=5, default=5, maximum=9),
        CounterField("home.timeouts", "Home time-outs", value=5, default=5, maximum=9),
        ToggleField("away.bonus", "Away bonus", on_text="BONUS"),
        ToggleField("home.bonus", "Home bonus", on_text="BONUS"),
        ToggleField("possession.home", "Home possession", on_text="◀"),
    ]

    def right(x, y):
        return [
            _box(name="Shot clock box", x=x, y=y + 8, w=70, h=60, fill=ONAIR["panel"], radius=3),
            _t(name="Shot clock", text="{clock.shot}", x=x, y=y + 8, w=70, h=60, size=36, color=ONAIR["user"]),
        ]
    bug = _scorebug(right)
    buttons = _common_buttons() + [
        Button("Start / stop both", {"do": "batch", "actions": [
            {"do": "toggle", "field": "clock.game"}, {"do": "toggle", "field": "clock.shot"}]},
            role="accent", hotkey="Ctrl+Space"),
        Button("Shot clock 24", {"do": "batch", "actions": [
            {"do": "reset", "field": "clock.shot"}]}, role="hi", hotkey="R"),
        Button("Shot clock 14", {"do": "set", "field": "clock.shot", "value": "14"}, role="hi", hotkey="T"),
        Button("Next quarter", {"do": "batch", "actions": [
            {"do": "next", "field": "period"}, {"do": "reset", "field": "clock.game"},
            {"do": "reset", "field": "clock.shot"}]}, role="user"),
    ] + _score_buttons((1, 2, 3))
    return Project(name="Basketball", sport="basketball", engine=Engine(fields),
                   boards=[bug, _projector()], panels=[Panel("Game", 4, buttons)])


def hockey() -> Project:
    fields = _teams() + [
        _clock(minutes=20),
        ChoiceField("period", "Period", options=["1st", "2nd", "3rd", "OT", "SO"]),
        CounterField("away.shots", "Away shots", maximum=999), CounterField("home.shots", "Home shots", maximum=999),
        PenaltyField("away.penalties", "Away penalties", master="clock.game", slots=2),
        PenaltyField("home.penalties", "Home penalties", master="clock.game", slots=2),
        ToggleField("away.pp", "Away power play", on_text="PP"),
        ToggleField("home.pp", "Home power play", on_text="PP"),
    ]

    def right(x, y):
        return [
            _box(name="Power play", x=x, y=y + 16, w=80, h=44, fill=ONAIR["user"], radius=3,
                 show_when="home.pp"),
            _t(name="Power play text", text="PP {home.penalties.1.time}", x=x, y=y + 16, w=80, h=44, size=20,
               color=ONAIR["head"], show_when="home.pp"),
        ]
    bug = _scorebug(right)
    buttons = _common_buttons() + [
        Button("Next period", {"do": "batch", "actions": [
            {"do": "next", "field": "period"}, {"do": "reset", "field": "clock.game"}]}, role="user"),
        Button("Away shot +1", {"do": "add", "field": "away.shots", "amount": 1}),
        Button("Home shot +1", {"do": "add", "field": "home.shots", "amount": 1}),
        Button("Away minor", {"do": "penalty.add", "field": "away.penalties", "player": "", "time": "2:00"},
               role="alert"),
        Button("Home minor", {"do": "penalty.add", "field": "home.penalties", "player": "", "time": "2:00"},
               role="alert"),
    ] + _score_buttons((1,))
    return Project(name="Hockey", sport="hockey", engine=Engine(fields),
                   boards=[bug, _projector()], panels=[Panel("Game", 4, buttons)])


def soccer() -> Project:
    clock = Clock(countdown=False, initial_ms=0, fmt="mm:ss")
    fields = _teams() + [
        ClockField("clock.game", "Match clock", clock=clock),
        TextField("clock.added", "Added time", value=""),
        ChoiceField("period", "Half", options=["1H", "2H", "ET1", "ET2", "PENS"]),
    ]

    def right(x, y):
        return [
            _box(name="Added time box", x=x, y=y + 16, w=64, h=44, fill=ONAIR["user"], radius=3,
                 show_when="clock.added"),
            _t(name="Added time", text="{clock.added}", x=x, y=y + 16, w=64, h=44, size=24, color=ONAIR["head"],
               show_when="clock.added"),
        ]
    bug = _scorebug(right)
    buttons = _common_buttons() + [
        Button("Second half (45:00)", {"do": "batch", "actions": [
            {"do": "set", "field": "period", "value": "2H"}, {"do": "set", "field": "clock.game", "value": "45:00"},
            {"do": "set", "field": "clock.added", "value": ""}]}, role="user"),
        Button("+1 added", {"do": "set", "field": "clock.added", "value": "+1"}),
        Button("+3 added", {"do": "set", "field": "clock.added", "value": "+3"}),
        Button("Clear added", {"do": "set", "field": "clock.added", "value": ""}),
    ] + _score_buttons((1,))
    return Project(name="Soccer", sport="soccer", engine=Engine(fields),
                   boards=[bug, _projector()], panels=[Panel("Match", 4, buttons)])


def football() -> Project:
    play = Clock(countdown=True, initial_ms=40_000, fmt="s")
    fields = _teams() + [
        _clock(minutes=15, tenths=False),
        ClockField("clock.play", "Play clock", clock=play),
        ChoiceField("period", "Quarter", options=["1st", "2nd", "3rd", "4th", "OT"]),
        ChoiceField("down", "Down", options=["1st", "2nd", "3rd", "4th"]),
        TextField("distance", "Distance", value="10"),
        CounterField("away.timeouts", "Away time-outs", value=3, default=3, maximum=3),
        CounterField("home.timeouts", "Home time-outs", value=3, default=3, maximum=3),
        ToggleField("possession.home", "Home ball", on_text="●"),
        ToggleField("possession.away", "Away ball", on_text="●"),
    ]

    def right(x, y):
        return [
            _t(name="Down and distance", text="{down} & {distance}", x=x, y=y, w=150, h=76, size=30,
               color=ONAIR["user"], uppercase=True),
            _t(name="Play clock", text=":{clock.play}", x=x + 150, y=y, w=70, h=76, size=30, color=ONAIR["muted"]),
        ]
    bug = _scorebug(right)
    buttons = _common_buttons() + [
        Button("Play clock 40", {"do": "batch", "actions": [
            {"do": "reset", "field": "clock.play"}, {"do": "start", "field": "clock.play"}]}, role="hi", hotkey="R"),
        Button("Play clock 25", {"do": "batch", "actions": [
            {"do": "set", "field": "clock.play", "value": "25"}]}, role="hi", hotkey="T"),
        Button("Next down", {"do": "next", "field": "down"}, hotkey="D"),
        Button("1st & 10", {"do": "batch", "actions": [
            {"do": "set", "field": "down", "value": "1st"}, {"do": "set", "field": "distance", "value": "10"}]},
            hotkey="F"),
        Button("Change possession", {"do": "batch", "actions": [
            {"do": "toggle", "field": "possession.home"}, {"do": "toggle", "field": "possession.away"}]}),
    ] + _score_buttons((1, 3, 6))
    return Project(name="Football", sport="football", engine=Engine(fields),
                   boards=[bug, _projector()], panels=[Panel("Game", 4, buttons)])


def volleyball() -> Project:
    fields = _teams() + [
        CounterField("away.sets", "Away sets", maximum=5), CounterField("home.sets", "Home sets", maximum=5),
        CounterField("set", "Set", value=1, default=1, minimum=1, maximum=5, ordinal=True),
        ToggleField("serve.home", "Home serving", on_text="●"),
        _clock(minutes=0, countdown=False, fmt="h:mm:ss", tenths=False),
    ]
    bug = _scorebug(chip="SET {set}", clock="{away.sets}-{home.sets}")
    buttons = [
        Button("Undo", {"do": "undo"}, hotkey="Ctrl+Z"),
        Button("Next set", {"do": "batch", "actions": [
            {"do": "next", "field": "set"}, {"do": "reset", "field": "away.score"},
            {"do": "reset", "field": "home.score"}]}, role="user"),
        Button("Away wins set", {"do": "add", "field": "away.sets", "amount": 1}),
        Button("Home wins set", {"do": "add", "field": "home.sets", "amount": 1}),
        Button("Switch serve", {"do": "toggle", "field": "serve.home"}, hotkey="S"),
    ] + _score_buttons((1,))
    return Project(name="Volleyball", sport="volleyball", engine=Engine(fields),
                   boards=[bug, _projector(title_line="SET {set}", clock="{away.sets} – {home.sets}")],
                   panels=[Panel("Match", 4, buttons)])


def baseball() -> Project:
    fields = _teams() + [
        CounterField("inning", "Inning", value=1, default=1, minimum=1, maximum=99, ordinal=True),
        ChoiceField("half", "Half", options=["▲", "▼"], wrap=True),
        CounterField("balls", "Balls", maximum=3), CounterField("strikes", "Strikes", maximum=2),
        CounterField("outs", "Outs", maximum=2),
        ToggleField("base.first", "Runner on first"), ToggleField("base.second", "Runner on second"),
        ToggleField("base.third", "Runner on third"),
    ]

    def right(x, y):
        return [
            _t(name="Count", text="{balls}-{strikes}", x=x, y=y, w=90, h=76, size=34),
            _t(name="Outs", text="{outs} OUT", x=x + 90, y=y, w=110, h=76, size=26, color=ONAIR["user"]),
        ]
    bug = _scorebug(right, chip="{half}{inning}", clock="")
    buttons = [
        Button("Undo", {"do": "undo"}, hotkey="Ctrl+Z"),
        Button("Ball", {"do": "add", "field": "balls", "amount": 1}, hotkey="B"),
        Button("Strike", {"do": "add", "field": "strikes", "amount": 1}, hotkey="K"),
        Button("Out", {"do": "batch", "actions": [
            {"do": "add", "field": "outs", "amount": 1}, {"do": "reset", "field": "balls"},
            {"do": "reset", "field": "strikes"}]}, role="alert", hotkey="X"),
        Button("New batter", {"do": "batch", "actions": [
            {"do": "reset", "field": "balls"}, {"do": "reset", "field": "strikes"}]}, hotkey="N"),
        Button("Next half inning", {"do": "batch", "actions": [
            {"do": "next", "field": "half"}, {"do": "reset", "field": "outs"},
            {"do": "reset", "field": "balls"}, {"do": "reset", "field": "strikes"},
            {"do": "set", "field": "base.first", "value": False},
            {"do": "set", "field": "base.second", "value": False},
            {"do": "set", "field": "base.third", "value": False}]}, role="user"),
        Button("Next inning", {"do": "next", "field": "inning"}),
    ] + _score_buttons((1,))
    return Project(name="Baseball", sport="baseball", engine=Engine(fields),
                   boards=[bug, _projector(title_line="{half} {inning}", clock="{balls}-{strikes}  {outs} OUT")],
                   panels=[Panel("Game", 4, buttons)])


def generic() -> Project:
    fields = _teams() + [
        _clock(minutes=10, tenths=False),
        CounterField("period", "Period", value=1, default=1, minimum=1, maximum=9, ordinal=True),
    ]
    buttons = _common_buttons() + [
        Button("Next period", {"do": "batch", "actions": [
            {"do": "next", "field": "period"}, {"do": "reset", "field": "clock.game"}]}, role="user"),
    ] + _score_buttons((1,))
    return Project(name="Scoreboard", sport="generic", engine=Engine(fields),
                   boards=[_scorebug(), _projector()], panels=[Panel("Game", 4, buttons)])


def blank() -> Project:
    return Project(name="Untitled", sport="blank", engine=Engine([]),
                   boards=[Board(name="Board 1")], panels=[Panel("Controls", 4, [])])


PRESETS: Dict[str, Callable[[], Project]] = {
    "Blank project": blank,
    "General scoreboard": generic,
    "Basketball": basketball,
    "Hockey": hockey,
    "Soccer": soccer,
    "Football": football,
    "Volleyball": volleyball,
    "Baseball": baseball,
}


def preset_names() -> List[str]:
    return list(PRESETS)


def make_project(name: str) -> Project:
    try:
        return PRESETS[name]()
    except KeyError:
        raise ValueError(f"No template called {name!r}.") from None
