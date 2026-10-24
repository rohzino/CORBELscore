"""
Scoreboard layouts ("boards") for the builder, the projector window, the
browser source and image output.

A board is a fixed canvas (1920 x 1080 by default) holding elements in paint
order. Elements show text built from field templates, boxes, and pictures.
Geometry is stored in canvas pixels, so a board renders identically at any
window size: renderers scale the whole canvas, never individual elements.

Templates: ``{home.score}`` is replaced with the field's display text.
``{{`` and ``}}`` give literal braces. An unknown key renders empty, and the
builder flags it.
"""

from __future__ import annotations

import copy
import re
import uuid
from dataclasses import asdict, dataclass, field, fields as dc_fields
from typing import Dict, Iterable, List, Mapping, Optional

__all__ = ["Element", "Board", "render_template", "template_keys", "new_id", "resolve_color",
           "ELEMENT_KINDS"]

ELEMENT_KINDS = ("text", "box", "image")

_TPL = re.compile(r"\{\{|\}\}|\{([a-z0-9_.]+)\}")


def render_template(template: str, values: Mapping[str, str]) -> str:
    def repl(m: re.Match) -> str:
        tok = m.group(0)
        if tok == "{{":
            return "{"
        if tok == "}}":
            return "}"
        return str(values.get(m.group(1), ""))
    return _TPL.sub(repl, template or "")


_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def resolve_color(value: str, values: Mapping[str, str]) -> str:
    """A colour property may be a literal (#rrggbb or #rrggbbaa) or a template
    such as ``{home.color}``. Returns a normalised #rrggbb / #rrggbbaa, or ""
    when there is nothing valid to paint."""
    v = render_template(value or "", values).strip() if "{" in (value or "") else (value or "").strip()
    if not v:
        return ""
    if not v.startswith("#"):
        v = "#" + v
    if not _HEX.match(v):
        return ""
    if len(v) == 4:
        v = "#" + "".join(ch * 2 for ch in v[1:])
    return v.lower()


def template_keys(template: str) -> List[str]:
    return [m.group(1) for m in _TPL.finditer(template or "") if m.group(1)]


def new_id() -> str:
    return uuid.uuid4().hex[:10]


@dataclass
class Element:
    kind: str = "text"                 # text | box | image
    name: str = ""
    id: str = field(default_factory=new_id)
    x: float = 0
    y: float = 0
    w: float = 200
    h: float = 80
    opacity: float = 1.0
    visible: bool = True               # builder visibility (eye toggle)
    locked: bool = False
    show_when: str = ""                # field key; shown only when it reads non-empty and not "0"
    # Box styling (also the background behind text)
    fill: str = ""                     # "" = none, else #rrggbb or #rrggbbaa
    stroke: str = ""
    stroke_width: float = 0
    radius: float = 0
    # Text
    text: str = ""                     # template, e.g. "{home.score}"
    font: str = "Archivo"
    size: float = 48
    weight: int = 700
    italic: bool = False
    color: str = "#ffffff"
    align: str = "center"              # left | center | right
    valign: str = "middle"             # top | middle | bottom
    uppercase: bool = False
    tracking: float = 0                # letter spacing, em
    fit: bool = True                   # shrink to fit the box
    tabular: bool = True               # tabular numerals
    padding: float = 0
    # Image
    src: str = ""                      # file path, or a template like "{home.logo}"
    contain: bool = True               # keep aspect ratio inside the box

    def copy(self, new_ids: bool = True) -> "Element":
        e = copy.deepcopy(self)
        if new_ids:
            e.id = new_id()
        return e

    def to_dict(self) -> dict:
        d = asdict(self)
        defaults = Element(kind=self.kind)
        # Keep files small and diffable: store only what differs from defaults.
        return {k: v for k, v in d.items()
                if k in ("kind", "id", "x", "y", "w", "h") or v != getattr(defaults, k)}

    @classmethod
    def from_dict(cls, d: Mapping) -> "Element":
        names = {f.name for f in dc_fields(cls)}
        e = cls(**{k: v for k, v in d.items() if k in names})
        if e.kind not in ELEMENT_KINDS:
            raise ValueError(f"Unknown element kind {e.kind!r}.")
        return e

    def keys(self) -> List[str]:
        """Field keys this element reads."""
        out = (template_keys(self.text) + template_keys(self.src) + template_keys(self.fill)
               + template_keys(self.stroke) + template_keys(self.color))
        if self.show_when:
            out.append(self.show_when)
        return out

    def shown(self, values: Mapping[str, str]) -> bool:
        if not self.visible:
            return False
        if not self.show_when:
            return True
        v = str(values.get(self.show_when, "")).strip()
        return v not in ("", "0", "false", "False")


@dataclass
class Board:
    name: str = "Scorebug"
    id: str = field(default_factory=new_id)
    width: int = 1920
    height: int = 1080
    background: str = ""               # "" = transparent (for keying over video)
    elements: List[Element] = field(default_factory=list)

    def element(self, eid: str) -> Optional[Element]:
        for e in self.elements:
            if e.id == eid:
                return e
        return None

    def index(self, eid: str) -> int:
        for i, e in enumerate(self.elements):
            if e.id == eid:
                return i
        raise KeyError(eid)

    def keys(self) -> List[str]:
        seen: Dict[str, None] = {}
        for e in self.elements:
            for k in e.keys():
                seen[k] = None
        return list(seen)

    def missing_keys(self, available: Iterable[str]) -> List[str]:
        avail = set(available)
        return [k for k in self.keys() if k not in avail]

    def bounds(self, ids: Iterable[str]):
        els = [e for e in self.elements if e.id in set(ids)]
        if not els:
            return None
        x1 = min(e.x for e in els)
        y1 = min(e.y for e in els)
        x2 = max(e.x + e.w for e in els)
        y2 = max(e.y + e.h for e in els)
        return x1, y1, x2, y2

    # Arrangement used by the builder's toolbar --------------------------------
    def align(self, ids: List[str], how: str) -> None:
        """Align to the selection's bounds, or to the canvas for one element.
        how: left | hcenter | right | top | vcenter | bottom"""
        els = [e for e in self.elements if e.id in set(ids)]
        if not els:
            return
        if len(els) == 1:
            x1, y1, x2, y2 = 0, 0, self.width, self.height
        else:
            x1, y1, x2, y2 = self.bounds(ids)
        for e in els:
            if how == "left":
                e.x = x1
            elif how == "right":
                e.x = x2 - e.w
            elif how == "hcenter":
                e.x = round((x1 + x2) / 2 - e.w / 2, 2)
            elif how == "top":
                e.y = y1
            elif how == "bottom":
                e.y = y2 - e.h
            elif how == "vcenter":
                e.y = round((y1 + y2) / 2 - e.h / 2, 2)
            else:
                raise ValueError(how)

    def distribute(self, ids: List[str], axis: str) -> None:
        """Equal gaps between three or more elements. axis: h | v"""
        els = [e for e in self.elements if e.id in set(ids)]
        if len(els) < 3:
            return
        if axis == "h":
            els.sort(key=lambda e: e.x)
            span = (els[-1].x + els[-1].w) - els[0].x
            gap = (span - sum(e.w for e in els)) / (len(els) - 1)
            pos = els[0].x
            for e in els:
                e.x = round(pos, 2)
                pos += e.w + gap
        else:
            els.sort(key=lambda e: e.y)
            span = (els[-1].y + els[-1].h) - els[0].y
            gap = (span - sum(e.h for e in els)) / (len(els) - 1)
            pos = els[0].y
            for e in els:
                e.y = round(pos, 2)
                pos += e.h + gap

    def reorder(self, eid: str, where: str) -> None:
        """where: front | back | forward | backward"""
        i = self.index(eid)
        e = self.elements.pop(i)
        if where == "front":
            self.elements.append(e)
        elif where == "back":
            self.elements.insert(0, e)
        elif where == "forward":
            self.elements.insert(min(len(self.elements), i + 1), e)
        elif where == "backward":
            self.elements.insert(max(0, i - 1), e)
        else:
            self.elements.insert(i, e)
            raise ValueError(where)

    def to_dict(self) -> dict:
        return {"name": self.name, "id": self.id, "width": self.width, "height": self.height,
                "background": self.background, "elements": [e.to_dict() for e in self.elements]}

    @classmethod
    def from_dict(cls, d: Mapping) -> "Board":
        b = cls(name=str(d.get("name", "Board")), id=str(d.get("id") or new_id()),
                width=int(d.get("width", 1920)), height=int(d.get("height", 1080)),
                background=str(d.get("background", "")))
        if not (16 <= b.width <= 8192 and 16 <= b.height <= 8192):
            raise ValueError(f"Board {b.name!r} is {b.width} x {b.height}; a board can be 16 to 8192 pixels each way.")
        b.elements = [Element.from_dict(e) for e in d.get("elements", [])]
        return b

    def copy(self) -> "Board":
        b = copy.deepcopy(self)
        b.id = new_id()
        return b
