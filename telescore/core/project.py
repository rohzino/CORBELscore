"""
TeleScore project files (``.tsproj``, JSON).

Format 2 keeps fields, boards, operator panels and output settings in one
readable file. Files from TeleScore 1.x are recognised and imported by
:mod:`telescore.core.legacy`.

Saving is atomic: the file is written beside the target and moved into place,
so a crash or a full disk never leaves a half-written project.
"""

from __future__ import annotations

import datetime as _dt
import getpass
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .animation import Animation
from .board import Board, new_id
from .engine import Engine
from .fields import field_from_dict
from .logic import Condition
from .sportzcast import SourceSettings

__all__ = ["Project", "Panel", "Button", "OutputSettings", "ProjectError", "FORMAT", "VERSION",
           "atomic_write_text", "current_user"]

FORMAT = "telescore-project"
VERSION = 2
APP_VERSION = "2.0.0a2"


class ProjectError(ValueError):
    pass


def current_user() -> str:
    """The OS user name. 1.x called ``os.getlogin()``, which raises when there
    is no controlling terminal (services, some desktop launches)."""
    try:
        return getpass.getuser() or "TeleScore"
    except Exception:
        return "TeleScore"


def atomic_write_text(path: str, text: str, encoding: str = "utf-8", retries: int = 5) -> None:
    """Write ``text`` so readers see either the old or the new file, never a
    partial one. On Windows another program reading the target can briefly
    block the replace; retry, then fall back to a direct write."""
    import time
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    tmp = os.path.join(folder, f".{os.path.basename(path)}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding=encoding, newline="") as fh:
        fh.write(text)
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass
    for attempt in range(retries):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.01 * (attempt + 1))
    try:
        with open(path, "w", encoding=encoding, newline="") as fh:
            fh.write(text)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _load(cls, items, what: str) -> list:
    out = []
    for d in items or []:
        try:
            out.append(cls.from_dict(d))
        except (TypeError, ValueError) as e:
            raise ProjectError(f"A {what} could not be read: {e}") from None
    return out


@dataclass
class Button:
    """One operator button: a label, an action and an optional shortcut.
    ``role`` picks its colour: neutral | accent | alert | user | hi."""
    label: str
    action: dict
    role: str = "neutral"
    hotkey: str = ""
    id: str = field(default_factory=new_id)

    def to_dict(self) -> dict:
        d = {"label": self.label, "action": self.action, "id": self.id}
        if self.role != "neutral":
            d["role"] = self.role
        if self.hotkey:
            d["hotkey"] = self.hotkey
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Button":
        return cls(label=str(d.get("label", "")), action=dict(d.get("action", {})),
                   role=str(d.get("role", "neutral")), hotkey=str(d.get("hotkey", "")),
                   id=str(d.get("id") or new_id()))


@dataclass
class Panel:
    name: str = "Controls"
    columns: int = 4
    buttons: List[Button] = field(default_factory=list)
    id: str = field(default_factory=new_id)

    def to_dict(self) -> dict:
        return {"name": self.name, "columns": self.columns, "id": self.id,
                "buttons": [b.to_dict() for b in self.buttons]}

    @classmethod
    def from_dict(cls, d: dict) -> "Panel":
        return cls(name=str(d.get("name", "Controls")), columns=max(1, int(d.get("columns", 4))),
                   buttons=[Button.from_dict(b) for b in d.get("buttons", [])],
                   id=str(d.get("id") or new_id()))


@dataclass
class OutputSettings:
    folder: str = ""                       # "" = <Documents>/TeleScore Output/<project>
    text_enabled: bool = True
    xml_enabled: bool = True
    xml_profiles: List[str] = field(default_factory=lambda: ["nested", "flat", "fields"])
    json_enabled: bool = True
    http_enabled: bool = True
    http_port: int = 8130
    http_lan: bool = False                 # listen beyond this computer
    http_token: str = ""                   # required for control calls when set
    image_boards: List[str] = field(default_factory=list)  # board ids written as PNG

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "OutputSettings":
        o = cls()
        for k, v in (d or {}).items():
            if hasattr(o, k):
                setattr(o, k, v)
        o.http_port = int(o.http_port)
        if not 1024 <= o.http_port <= 65535:
            o.http_port = 8130
        return o


@dataclass
class Project:
    name: str = "Untitled"
    author: str = field(default_factory=current_user)
    engine: Engine = field(default_factory=Engine)
    boards: List[Board] = field(default_factory=list)
    panels: List[Panel] = field(default_factory=list)
    outputs: OutputSettings = field(default_factory=OutputSettings)
    animations: List[Animation] = field(default_factory=list)     # the project's own animation recipes
    source: SourceSettings = field(default_factory=SourceSettings)  # live data (Sportzcast)
    sport: str = "generic"
    created: str = field(default_factory=lambda: _dt.datetime.now().isoformat(timespec="seconds"))
    path: str = ""                         # not saved
    imported_from: str = ""                # not saved; set when a 1.x file was converted
    import_notes: List[str] = field(default_factory=list)  # not saved

    def board(self, bid: str) -> Optional[Board]:
        return next((b for b in self.boards if b.id == bid), None)

    # ----- serialisation -----------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "format": FORMAT,
            "version": VERSION,
            "app": APP_VERSION,
            "name": self.name,
            "author": self.author,
            "sport": self.sport,
            "created": self.created,
            "saved": _dt.datetime.now().isoformat(timespec="seconds"),
            "fields": self.engine.fields_to_list(),
            "boards": [b.to_dict() for b in self.boards],
            "panels": [p.to_dict() for p in self.panels],
            "outputs": self.outputs.to_dict(),
            "conditions": [c.to_dict() for c in self.engine.logic.conditions],
            "animations": [a.to_dict() for a in self.animations],
            "source": self.source.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Project":
        if d.get("format") != FORMAT:
            raise ProjectError("This is not a TeleScore 2 project.")
        if int(d.get("version", 0)) > VERSION:
            raise ProjectError(f"This project was saved by a newer TeleScore (format {d.get('version')}). "
                               "Update TeleScore to open it.")
        fields = []
        for fd in d.get("fields", []):
            try:
                fields.append(field_from_dict(fd))
            except (TypeError, ValueError) as e:
                raise ProjectError(f"Field {fd.get('key', '?')!r} could not be read: {e}") from None
        p = cls(
            name=str(d.get("name", "Untitled")),
            author=str(d.get("author", "")),
            engine=Engine(fields),
            boards=[Board.from_dict(b) for b in d.get("boards", [])],
            panels=[Panel.from_dict(p) for p in d.get("panels", [])],
            outputs=OutputSettings.from_dict(d.get("outputs")),
            animations=_load(Animation, d.get("animations"), "animation"),
            source=SourceSettings.from_dict(d.get("source")),
            sport=str(d.get("sport", "generic")),
            created=str(d.get("created", "")),
        )
        p.engine.set_conditions(_load(Condition, d.get("conditions"), "condition"))
        return p

    # ----- files -------------------------------------------------------------
    def save(self, path: Optional[str] = None) -> str:
        path = path or self.path
        if not path:
            raise ProjectError("Choose where to save the project first.")
        atomic_write_text(path, json.dumps(self.to_dict(), indent=1, ensure_ascii=False))
        self.path = path
        return path

    @classmethod
    def load(cls, path: str) -> "Project":
        try:
            with open(path, "r", encoding="utf-8-sig") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as e:
            raise ProjectError(f"The file is not valid JSON (line {e.lineno}). It may be damaged.") from None
        except UnicodeDecodeError:
            raise ProjectError("The file is not a text project file.") from None
        if isinstance(data, dict) and data.get("format") == FORMAT:
            p = cls.from_dict(data)
        else:
            from .legacy import is_legacy, import_legacy
            if not is_legacy(data):
                raise ProjectError("This file is not a TeleScore project.")
            p = import_legacy(data)
            p.imported_from = path
            p.path = ""  # Save asks for a new .tsproj name; the 1.x file is never overwritten
            return p
        p.path = path
        return p
