"""Project-wide field renames and usage lookups."""

from __future__ import annotations

from typing import List

from .board import template_keys
from .fields import PenaltyField

__all__ = ["rename_field_everywhere", "field_references"]


def _swap_key(k: str, old: str, new: str) -> str:
    if k == old:
        return new
    if k.startswith(old + "."):
        return new + k[len(old):]
    return k


def rename_field_everywhere(project, old: str, new: str) -> int:
    """Rename field ``old`` to ``new`` and update every template, show-when,
    button action and penalty master that refers to it (sub-keys included,
    so ``{home.penalties.1.time}`` follows ``home.penalties``).
    Returns the number of references changed."""
    project.engine.rename_field(old, new)
    count = 0

    def swap_tpl(t: str) -> str:
        nonlocal count
        if not t or "{" not in t:
            return t
        out = t
        for k in set(template_keys(t)):
            nk = _swap_key(k, old, new)
            if nk != k:
                out = out.replace("{%s}" % k, "{%s}" % nk)
                count += 1
        return out

    for b in project.boards:
        b.background = swap_tpl(b.background)
        for e in b.elements:
            e.text, e.src = swap_tpl(e.text), swap_tpl(e.src)
            e.fill, e.stroke, e.color = swap_tpl(e.fill), swap_tpl(e.stroke), swap_tpl(e.color)
            if e.show_when:
                nk = _swap_key(e.show_when, old, new)
                if nk != e.show_when:
                    e.show_when = nk
                    count += 1

    def fix_action(a: dict) -> None:
        nonlocal count
        f = a.get("field")
        if f:
            nk = _swap_key(f, old, new)
            if nk != f:
                a["field"] = nk
                count += 1
        for sub in a.get("actions", []) or []:
            fix_action(sub)

    for panel in project.panels:
        for btn in panel.buttons:
            fix_action(btn.action)
    for f in project.engine.fields.values():
        if isinstance(f, PenaltyField) and f.master == old:
            f.master = new
            count += 1
    return count


def field_references(project, key: str) -> List[str]:
    """Human-readable places where ``key`` (or one of its sub-keys) is used."""
    def uses(k: str) -> bool:
        return k == key or k.startswith(key + ".")

    out = []
    for b in project.boards:
        for e in b.elements:
            if any(uses(k) for k in e.keys()):
                out.append(f"{b.name} → {e.name or e.kind}")

    def walk(a):
        yield a
        for sub in a.get("actions", []) or []:
            yield from walk(sub)

    for panel in project.panels:
        for btn in panel.buttons:
            if any(uses(a.get("field") or "") for a in walk(btn.action)):
                out.append(f"Button “{btn.label}”")
    for f in project.engine.fields.values():
        if isinstance(f, PenaltyField) and f.master == key:
            out.append(f"{f.label} (runs from this clock)")
    return out
