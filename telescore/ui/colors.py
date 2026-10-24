"""
Colour schemes and the Keystone derivation recipe. No Qt imports, so the
contrast rules are unit-tested without a display.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

# ----- schemes -----------------------------------------------------------------

SCHEMES: Dict[str, Dict[str, str]] = {
    "Keystone Dark": dict(bg="#0f1513", panel="#18211e", head="#0a0f0d", ink="#e8f1ec", accent="#3ddc84",
                          hi="#5ad1e6", user="#ffb454", alert="#ff6b6b", mark="#3ddc84"),
    "Keystone Light": dict(bg="#eef1ee", panel="#ffffff", head="#12201a", ink="#14201b", accent="#0b7a3b",
                           hi="#0e7490", user="#f5a524", alert="#c62828", mark="#0b7a3b"),
    "Rally": dict(bg="#0b111c", panel="#121a28", head="#070b12", ink="#f2f7fa", accent="#4fd1c5",
                  hi="#3d8bfd", user="#ffb547", alert="#ff5a7a", mark="#4fd1c5"),
}
DEFAULT_SCHEME = "Keystone Dark"


def _rgb(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(c) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v))) for v in c)


def mix(a: str, b: str, t: float) -> str:
    """``t`` of colour ``a`` into colour ``b`` (Keystone's recipe notation)."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(x * t + y * (1 - t) for x, y in zip(ra, rb)))


def luminance(h: str) -> float:
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(h)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def ink_on(fill: str) -> str:
    """#010101 or #ffffff, whichever reads better on ``fill``."""
    return "#010101" if contrast("#010101", fill) >= contrast("#ffffff", fill) else "#ffffff"


def mix_until(a: str, b: str, start: float, against, target: float) -> str:
    """Mix ``a`` into ``b`` starting at ``start`` and add more of ``a`` until the
    result reaches ``target`` contrast on every colour in ``against``."""
    t = start
    while t <= 1.0:
        c = mix(a, b, t)
        if all(contrast(c, g) >= target for g in against):
            return c
        t += 0.01
    return a


@dataclass
class Palette:
    name: str
    c: Dict[str, str]

    def __getitem__(self, k: str) -> str:
        return self.c[k]

    @property
    def dark(self) -> bool:
        return luminance(self.c["bg"]) < 0.2


def derive(name: str) -> Palette:
    """Expand a nine-colour scheme with the Keystone recipe."""
    s = dict(SCHEMES.get(name) or SCHEMES[DEFAULT_SCHEME])
    c = dict(s)
    c["accent-ink"] = ink_on(s["accent"])
    c["hi-ink"] = ink_on(s["hi"])
    c["user-ink"] = ink_on(s["user"])
    c["alert-ink"] = ink_on(s["alert"])
    c["head-ink"] = s["ink"] if contrast(s["ink"], s["head"]) >= 4.5 else ink_on(s["head"])
    c["muted"] = mix(s["ink"], s["panel"], 0.72)
    c["rule"] = mix(s["ink"], s["panel"], 0.17)
    c["field"] = mix(s["panel"], s["bg"], 0.72)
    # Control borders (inputs, buttons) reach 3:1 on panel and field; the plain
    # ``rule`` hairline stays exact and is never the only cue for a control.
    c["rule-strong"] = mix_until(s["ink"], s["panel"], 0.32, (s["panel"], c["field"]), 3.0)
    c["field"] = mix(s["panel"], s["bg"], 0.72)
    c["accent-soft"] = mix(s["accent"], s["panel"], 0.14)
    c["sel"] = mix(s["accent"], s["panel"], 0.18)
    c["accent-text"] = mix(s["accent"], s["ink"], 0.78)
    c["alert-soft"] = mix(s["alert"], s["panel"], 0.12)
    c["alert-text"] = mix(s["alert"], s["ink"], 0.82)
    c["warn-soft"] = mix(s["hi"], s["panel"], 0.30)
    c["user-text"] = mix_until(s["ink"], s["user"], 0.15, (s["panel"], s["bg"]), 4.5)
    c["row-alt"] = mix(s["bg"], s["panel"], 0.45)
    c["hover"] = mix(s["ink"], s["panel"], 0.06)
    c["menu-fill"] = mix(c["head-ink"], s["head"], 0.12)
    c["menu-border"] = mix(c["head-ink"], s["head"], 0.38)
    return Palette(name, c)


