"""
Import TeleScore 1.x project files.

1.x saved a JSON object keyed by numbers (``"0"`` header, ``"1"`` layouts;
in each layout ``"9"`` properties and ``"2"`` components; in each component
``"0"`` type, ``"9"`` properties and ``"11"`` connections). Display widgets
become fields plus board elements; buttons become operator-panel buttons whose
actions reproduce the old connections.

The importer is forgiving: anything it cannot convert is listed in
``Project.import_notes`` rather than stopping the import.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .board import Board, Element
from .clock import Clock
from .engine import Engine
from .fields import (ClockField, CounterField, ImageField, PenaltyField, TextField, ToggleField,
                     normalise_key)
from .project import Button, OutputSettings, Panel, Project
from .timefmt import LEGACY_FORMATS, TimeParseError, parse_time

__all__ = ["is_legacy", "import_legacy"]

H, LAYOUTS, COMPS, PROPS, CONN, TYPE = "0", "1", "2", "9", "11", "0"
WEIGHTS = [300, 400, 500, 600, 700, 800, 900]
ALIGN = ["left", "center", "right"]

DISPLAY_TYPES = {"Time Display", "Points Display", "Text Display", "Image Display",
                 "Team Attribute", "Penalty"}
INPUT_TYPES = {"Type Time Amount", "Type Points Amount", "Type Text", "Image Set"}

CLOCK_SIGNALS = {
    "Start": {"do": "start"}, "Stop": {"do": "stop"}, "Reset": {"do": "reset"},
    "ADDS": {"do": "adjust", "ms": 1000}, "SUBS": {"do": "adjust", "ms": -1000},
    "ADDM": {"do": "adjust", "ms": 60_000}, "SUBM": {"do": "adjust", "ms": -60_000},
}
BUTTON_ROLES = {"Start Time": "accent", "Stop Time": "alert", "Reset": "hi", "Sub Points": "alert",
                "Add Points": "accent"}


def is_legacy(data) -> bool:
    return isinstance(data, dict) and H in data and LAYOUTS in data and isinstance(data[LAYOUTS], list)


def _unique(key: str, used: set) -> str:
    base, n = key, 2
    while key in used or any(u.startswith(key + ".") or key.startswith(u + ".") for u in used):
        key = f"{base}_{n}"
        n += 1
    used.add(key)
    return key


def _style(el: Element, p: dict) -> None:
    """Copy 1.x appearance properties onto an element."""
    if p.get("Font Color"):
        el.color = str(p["Font Color"])
    if p.get("Display Font"):
        el.font = str(p["Display Font"])
    try:
        el.size = max(6.0, float(p.get("Font Size", 10)) * 96 / 72)  # points at 96 dpi
    except (TypeError, ValueError):
        pass
    w = p.get("Font Weight")
    if isinstance(w, int) and 0 <= w < len(WEIGHTS):
        el.weight = WEIGHTS[w]
    a = p.get("Text Alignment")
    if isinstance(a, int) and 0 <= a < len(ALIGN):
        el.align = ALIGN[a]
    el.fit = True
    el.tabular = True


def _geom(p: dict) -> Tuple[float, float, float, float]:
    def num(k, d):
        try:
            return float(p.get(k, d))
        except (TypeError, ValueError):
            return float(d)
    return num("X", 0), num("Y", 0), max(8.0, num("Width", 100)), max(8.0, num("Height", 40))


def import_legacy(data: dict) -> Project:
    header = data.get(H) or {}
    notes: List[str] = []
    used: set = set()
    fields = []
    boards: List[Board] = []
    buttons: List[Button] = []
    # component name -> (kind, field key)
    comp_field: Dict[str, Tuple[str, str]] = {}
    pending_buttons: List[Tuple[str, dict, dict]] = []  # (type, props, connections)
    elements_by_comp: Dict[str, List[Element]] = {}
    first_clock: Optional[str] = None
    penalties: List[PenaltyField] = []

    for layout in data.get(LAYOUTS) or []:
        lp = layout.get(PROPS) or {}
        board = Board(name=str(lp.get("Component Name") or f"Layout {len(boards) + 1}"))
        try:
            board.width = int(lp.get("Width", 800)) or 800
            board.height = int(lp.get("Height", 600)) or 600
        except (TypeError, ValueError):
            pass
        board.background = str(lp.get("Background Color") or "#000000")
        if lp.get("Background Image"):
            board.elements.append(Element(kind="image", name="Background image", x=0, y=0,
                                          w=board.width, h=board.height, src=str(lp["Background Image"]),
                                          locked=True))
        for comp in layout.get(COMPS) or []:
            ctype = str(comp.get(TYPE, ""))
            p = comp.get(PROPS) or {}
            cname = str(p.get("Component Name") or ctype)
            conns = comp.get(CONN) or {}
            x, y, w, h = _geom(p)
            fill = "" if p.get("Transparent Background") else str(p.get("Background Color") or "")

            if ctype == "Time Display":
                key = _unique(normalise_key("clock." + cname if not cname.lower().startswith("clock") else cname), used)
                fi = p.get("Format", 0)
                fmt = LEGACY_FORMATS[fi] if isinstance(fi, int) and 0 <= fi < len(LEGACY_FORMATS) else "mm:ss"
                stopwatch = bool(p.get("Stopwatch"))
                try:
                    initial = parse_time(str(p.get("Default Time") or "00:00"))
                except TimeParseError:
                    initial = 0
                    notes.append(f"{cname}: the default time {p.get('Default Time')!r} could not be read; set to 0:00.")
                c = Clock(countdown=not stopwatch, initial_ms=initial, fmt=fmt,
                          blank_at_zero=bool(p.get("Clr when time = 0")),
                          tenths_under_ms=60_000 if (p.get("Tenth of a second") and not stopwatch) else 0,
                          tenths_fmt="ss.t")
                if not stopwatch:
                    c._base_ms = initial
                fields.append(ClockField(key, cname, clock=c))
                first_clock = first_clock or key
                el = Element(kind="text", name=cname, x=x, y=y, w=w, h=h, text="{%s}" % key, fill=fill)
                _style(el, p)
                if p.get("Buzzer Sound"):
                    notes.append(f"{cname}: the buzzer file {p['Buzzer Sound']!r} was kept out; set it again "
                                 "in Data → the clock's buzzer.")
            elif ctype == "Points Display":
                key = _unique(normalise_key(cname), used)
                fields.append(CounterField(key, cname, minimum=None, ordinal=p.get("Suffix (st, nd, rd, th)") in (2, True),
                                           blank_zero=bool(p.get("Clr when points = 0"))))
                el = Element(kind="text", name=cname, x=x, y=y, w=w, h=h, text="{%s}" % key, fill=fill)
                _style(el, p)
            elif ctype == "Text Display":
                key = _unique(normalise_key(cname), used)
                fields.append(TextField(key, cname, value=str(p.get("Display Text") or "")))
                el = Element(kind="text", name=cname, x=x, y=y, w=w, h=h, text="{%s}" % key, fill=fill)
                _style(el, p)
            elif ctype == "Image Display":
                key = _unique(normalise_key(cname), used)
                fields.append(ImageField(key, cname, value=str(p.get("Default Image") or "")))
                el = Element(kind="image", name=cname, x=x, y=y, w=w, h=h, src="{%s}" % key)
            elif ctype == "Team Attribute":
                key = _unique(normalise_key(cname), used)
                used.update({f"{key}.name", f"{key}.attr", f"{key}.logo"})
                fields += [TextField(f"{key}.name", f"{cname} name"), TextField(f"{key}.attr", f"{cname} detail"),
                           ImageField(f"{key}.logo", f"{cname} logo")]
                el = Element(kind="text", name=cname, x=x, y=y, w=w, h=h, text="{%s.name}" % key, fill=fill)
                _style(el, p)
            elif ctype == "Penalty":
                key = _unique(normalise_key(cname), used)
                pf = PenaltyField(key, cname, master="", slots=2)
                penalties.append(pf)
                fields.append(pf)
                el = Element(kind="text", name=cname, x=x, y=y, w=w, h=h,
                             text="{%s.1.player} {%s.1.time}" % (key, key), fill=fill)
                _style(el, p)
            elif ctype in INPUT_TYPES:
                notes.append(f"{cname} ({ctype}): direct entry is built into every field in the Operate tab now, "
                             "so this box was not carried over.")
                continue
            else:
                pending_buttons.append((ctype, p, conns))
                continue

            comp_field[cname] = (ctype, key)
            board.elements.append(el)
            elements_by_comp.setdefault(cname, []).append(el)
        boards.append(board)

    for pf in penalties:
        if first_clock:
            pf.master = first_clock
        else:
            notes.append(f"{pf.label}: there is no game clock to run penalties from; add one and pick it in Data.")

    # Buttons ----------------------------------------------------------------
    vis_keys: Dict[str, str] = {}
    for ctype, p, conns in pending_buttons:
        label = str(p.get("Display Text") or p.get("Component Name") or ctype).replace("\n", " ").strip()
        actions = []
        for signal, receivers in (conns or {}).items():
            for rname in receivers or []:
                target = comp_field.get(rname)
                if not target:
                    continue
                kind, key = target
                if signal in CLOCK_SIGNALS and kind == "Time Display":
                    actions.append(dict(CLOCK_SIGNALS[signal], field=key))
                elif signal in ("Add Points", "Sub Points", "Set Points") and kind == "Points Display":
                    try:
                        amount = int(p.get("Set Amount", 1))
                    except (TypeError, ValueError):
                        amount = 1
                    if signal == "Set Points":
                        actions.append({"do": "set", "field": key, "value": amount})
                    else:
                        actions.append({"do": "add", "field": key,
                                        "amount": amount if signal == "Add Points" else -amount})
                elif signal in ("Set Visible", "Set Invisible"):
                    vis = vis_keys.get(rname)
                    if vis is None:
                        vis = vis_keys[rname] = _unique(normalise_key(f"show.{rname}"), used)
                        fields.append(ToggleField(vis, f"Show {rname}", value=True, default=True))
                        for el in elements_by_comp.get(rname, []):
                            el.show_when = vis
                    actions.append({"do": "set", "field": vis, "value": signal == "Set Visible"})
                elif kind == "Penalty":
                    pass  # penalties now follow their master clock
                else:
                    notes.append(f"Button {label!r}: its {signal!r} connection to {rname!r} has no 2.0 equivalent.")
        if not actions:
            notes.append(f"Button {label!r} ({ctype}) was not connected to anything and was left out.")
            continue
        action = actions[0] if len(actions) == 1 else {"do": "batch", "actions": actions}
        buttons.append(Button(label=label, action=action, role=BUTTON_ROLES.get(ctype, "neutral"),
                              hotkey=str(p.get("Hotkey") or "")))

    outputs = OutputSettings()
    gd = str(header.get("Global Directory") or "")
    if gd and gd not in ("./Output", "./Output/{}"):
        outputs.folder = gd.replace("/{}", "")
    project = Project(
        name=str(header.get("Name") or "Imported project"),
        author=str(header.get("Author") or ""),
        engine=Engine(fields),
        boards=boards or [Board(name="Board 1")],
        panels=[Panel("Imported buttons", 4, buttons)],
        outputs=outputs,
        sport="imported",
    )
    notes.append("Text files are now named after field keys (for example home.score.txt in the text folder); "
                 "update the file paths in OBS or vMix once.")
    project.import_notes = notes
    return project
