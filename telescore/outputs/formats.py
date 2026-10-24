"""
Serialisers that turn an engine :class:`Snapshot` into feed documents.

XML profiles (all UTF-8, all regenerated whole on each change):

``nested`` -> telescore.xml
    Field keys become a tree: ``home.score`` is ``<home><score>3</score></home>``.
    A field's sub-keys are attributes on its element
    (``<game running="1">4:07</game>``, penalty slots as ``p1_player``,
    ``p1_time``), so ``string()`` of an element is always just its value.
    Good for Ross XPression DataLinq and Chyron, which address data by XPath.

``flat`` -> vmix.xml
    One ``<row>`` holding every value as a child named after its key with
    dots turned into underscores: ``<home_score>3</home_score>``. Point a vMix
    XML data source at it with the XPath ``//row``.

``fields`` -> fields.xml
    One ``<field key=".." type=".." label="..">value</field>`` per value,
    validated by ``docs/schema/fields.xsd``. Stable for any system that can
    look values up by attribute: ``//field[@key='home.score']``.

Plus ``state.json`` and plain ``.txt`` files, one per key.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from typing import Dict, Iterable, List, Optional, Tuple
from xml.sax.saxutils import escape, quoteattr

from ..core.engine import Snapshot

__all__ = ["xml_nested", "xml_flat", "xml_fields", "state_json", "xml_name", "XML_PROFILES",
           "text_filename"]

_NAME_BAD = re.compile(r"[^A-Za-z0-9_\-]")
# XML 1.0 forbids most control characters even when escaped.
_XML_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def _clean(text: str) -> str:
    return _XML_ILLEGAL.sub("", str(text))


def xml_name(part: str) -> str:
    """Make ``part`` a valid XML element name (keys may start with digits)."""
    n = _NAME_BAD.sub("_", part) or "_"
    if not (n[0].isalpha() or n[0] == "_") or n.lower().startswith("xml"):
        n = "_" + n
    return n


def _stamp(snap: Snapshot) -> str:
    return _dt.datetime.fromtimestamp(snap.wall).isoformat(timespec="milliseconds")


def _split(snap: Snapshot) -> Tuple[List[str], Dict[str, Dict[str, str]]]:
    """Top-level field keys, and each field's sub-keys {field: {sub: text}}."""
    fields = list(snap.types)
    subs: Dict[str, Dict[str, str]] = {k: {} for k in fields}
    fset = set(fields)
    for key, text in snap.values.items():
        if key in fset:
            continue
        # The longest field key that prefixes this value key owns it.
        owner = None
        parts = key.split(".")
        for i in range(len(parts) - 1, 0, -1):
            cand = ".".join(parts[:i])
            if cand in fset:
                owner = cand
                break
        if owner is not None:
            subs[owner][key[len(owner) + 1:]] = text
    return fields, subs


def _attr_name(sub: str) -> str:
    # "1.player" -> "p1_player", "running" -> "running"
    parts = sub.split(".")
    if parts[0].isdigit():
        parts[0] = "p" + parts[0]
    return xml_name("_".join(parts))


def xml_nested(snap: Snapshot, root: str = "telescore") -> str:
    fields, subs = _split(snap)
    tree: dict = {}
    for k in fields:
        node = tree
        for part in k.split("."):
            node = node.setdefault(part, {})
        node["\0value"] = k

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<{root} version="2" seq="{snap.seq}" updated="{_stamp(snap)}">']

    def walk(node: dict, depth: int) -> None:
        pad = "  " * depth
        for name, child in node.items():
            if name == "\0value":
                continue
            tag = xml_name(name)
            key = child.get("\0value")
            attrs = ""
            if key is not None:
                attrs = f" type={quoteattr(snap.types[key])}"
                for sub, text in subs.get(key, {}).items():
                    attrs += f" {_attr_name(sub)}={quoteattr(_clean(text))}"
            kids = [n for n in child if n != "\0value"]
            if kids:
                if key is not None:
                    attrs += f" value={quoteattr(_clean(snap.values.get(key, '')))}"
                out.append(f"{pad}<{tag}{attrs}>")
                walk(child, depth + 1)
                out.append(f"{pad}</{tag}>")
            else:
                text = escape(_clean(snap.values.get(key, ""))) if key is not None else ""
                out.append(f"{pad}<{tag}{attrs}>{text}</{tag}>")

    walk(tree, 1)
    out.append(f"</{root}>")
    return "\n".join(out) + "\n"


def xml_flat(snap: Snapshot) -> str:
    out = ['<?xml version="1.0" encoding="UTF-8"?>', f'<data seq="{snap.seq}" updated="{_stamp(snap)}">', "  <row>"]
    seen = set()
    for key, text in snap.values.items():
        tag = xml_name(key.replace(".", "_"))
        while tag in seen:          # e.g. home.score_x vs home_score.x
            tag += "_"
        seen.add(tag)
        out.append(f"    <{tag}>{escape(_clean(text))}</{tag}>")
    out += ["  </row>", "</data>"]
    return "\n".join(out) + "\n"


def xml_fields(snap: Snapshot) -> str:
    fields, subs = _split(snap)
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<fields version="2" seq="{snap.seq}" updated="{_stamp(snap)}">']
    for k in fields:
        raw = snap.raw.get(k)
        raw_attr = ""
        if isinstance(raw, bool):
            raw_attr = f' raw="{"1" if raw else "0"}"'
        elif isinstance(raw, int) and str(raw) != snap.values.get(k):
            raw_attr = f' raw="{raw}"'
        out.append(f"  <field key={quoteattr(k)} type={quoteattr(snap.types[k])} "
                   f"label={quoteattr(_clean(snap.labels.get(k, k)))}{raw_attr}>"
                   f"{escape(_clean(snap.values.get(k, '')))}</field>")
        for sub, text in subs.get(k, {}).items():
            out.append(f"  <field key={quoteattr(k + '.' + sub)} type=\"sub\" "
                       f"label={quoteattr(_clean(snap.labels.get(k, k)) + ' ' + sub)}>{escape(_clean(text))}</field>")
    out.append("</fields>")
    return "\n".join(out) + "\n"


def state_json(snap: Snapshot, indent: Optional[int] = None) -> str:
    raw = {}
    for k, v in snap.raw.items():
        raw[k] = v if isinstance(v, (int, float, str, bool)) or v is None else str(v)
    return json.dumps({"version": 2, "seq": snap.seq, "updated": _stamp(snap), "values": snap.values,
                       "raw": raw, "types": snap.types, "labels": snap.labels},
                      ensure_ascii=False, indent=indent)


XML_PROFILES = {
    "nested": ("telescore.xml", xml_nested),
    "flat": ("vmix.xml", xml_flat),
    "fields": ("fields.xml", xml_fields),
}


_FILE_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def text_filename(key: str) -> str:
    """``home.score`` -> ``home.score.txt`` (safe on Windows)."""
    name = _FILE_BAD.sub("_", key).strip(". ") or "field"
    if name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                                      *(f"LPT{i}" for i in range(1, 10))}:
        name = "_" + name
    return name + ".txt"
