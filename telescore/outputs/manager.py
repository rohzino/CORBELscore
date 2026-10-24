"""
Writes snapshots to disk on a background thread.

The engine publishes on the UI thread; slow disks, antivirus scans or a file
held open by another program must never stall the clock. The manager keeps
only the newest snapshot and writes it as soon as the writer is free, so a
burst of changes costs one write, and the files always end on the latest state.

Text files: one per value key, rewritten only when that value changes.
XML and JSON: rewritten whole, at most ``max_rate`` times a second.
Every write is atomic (temp file + replace).
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from ..core.engine import Snapshot
from ..core.project import OutputSettings, atomic_write_text
from .formats import XML_PROFILES, state_json, text_filename

__all__ = ["OutputManager", "OutputStatus", "default_output_folder"]


def default_output_folder(project_name: str) -> str:
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    if not os.path.isdir(docs):
        docs = os.path.expanduser("~")
    safe = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in project_name).strip() or "Untitled"
    return os.path.join(docs, "TeleScore Output", safe)


@dataclass
class OutputStatus:
    """Per-output state for the status lights: ok | busy | error | off."""
    name: str
    state: str = "off"
    detail: str = ""
    last_write: float = 0.0
    writes: int = 0


class OutputManager:
    def __init__(self, settings: OutputSettings, project_name: str = "Untitled",
                 max_rate: float = 20.0, on_status: Optional[Callable[[Dict[str, OutputStatus]], None]] = None):
        self.settings = settings
        self.project_name = project_name
        self.min_interval = 1.0 / max_rate
        self.on_status = on_status
        self._pending: Optional[Snapshot] = None
        self._cond = threading.Condition()
        self._stop = False
        self._written: Dict[str, str] = {}   # text key -> last text written
        self._last_doc = 0.0
        self.status: Dict[str, OutputStatus] = {n: OutputStatus(n) for n in ("text", "xml", "json")}
        self._thread = threading.Thread(target=self._run, name="TeleScore output writer", daemon=True)
        self._thread.start()

    # ----- configuration ---------------------------------------------------
    @property
    def folder(self) -> str:
        return self.settings.folder or default_output_folder(self.project_name)

    def reconfigure(self, settings: OutputSettings, project_name: Optional[str] = None) -> None:
        with self._cond:
            self.settings = settings
            if project_name is not None:
                self.project_name = project_name
            self._written.clear()      # write everything again to the (maybe new) folder
            self._cond.notify()

    # ----- input -----------------------------------------------------------
    def submit(self, snap: Snapshot, changed: Optional[set] = None) -> None:
        """Engine listener. Keeps only the newest snapshot."""
        with self._cond:
            self._pending = snap
            self._cond.notify()

    def flush(self, timeout: float = 5.0) -> bool:
        """Wait until the newest snapshot has been written (for tests and exit)."""
        end = time.monotonic() + timeout
        with self._cond:
            while self._pending is not None and time.monotonic() < end:
                self._cond.wait(0.05)
            return self._pending is None

    def close(self) -> None:
        self.flush(2.0)
        with self._cond:
            self._stop = True
            self._cond.notify()
        self._thread.join(3.0)

    # ----- writer thread ---------------------------------------------------
    def _run(self) -> None:
        while True:
            with self._cond:
                while self._pending is None and not self._stop:
                    self._cond.wait()
                if self._stop:
                    return
                snap = self._pending
                settings = self.settings
            try:
                self._write(snap, settings)
            finally:
                with self._cond:
                    if self._pending is snap:
                        self._pending = None
                    self._cond.notify_all()
            # Rate limit the whole-document outputs; text files are cheap.
            time.sleep(0.005)

    def _set(self, name: str, state: str, detail: str = "", wrote: bool = False) -> None:
        st = self.status[name]
        changed = (st.state, st.detail) != (state, detail)
        st.state, st.detail = state, detail
        if wrote:
            st.last_write = time.time()
            st.writes += 1
        if changed and self.on_status:
            try:
                self.on_status(dict(self.status))
            except Exception:
                pass

    def _write(self, snap: Snapshot, s: OutputSettings) -> None:
        folder = self.folder
        # Text ------------------------------------------------------------
        if s.text_enabled:
            tdir = os.path.join(folder, "text")
            try:
                os.makedirs(tdir, exist_ok=True)
                n = 0
                for key, text in snap.values.items():
                    if self._written.get(key) == text:
                        continue
                    atomic_write_text(os.path.join(tdir, text_filename(key)), text)
                    self._written[key] = text
                    n += 1
                self._set("text", "ok", tdir, wrote=n > 0)
            except OSError as e:
                self._set("text", "error", f"Cannot write to {tdir}: {e.strerror or e}. "
                                           "Pick another folder in Outputs.")
        else:
            self._set("text", "off")

        # Whole documents, rate limited -----------------------------------
        now = time.monotonic()
        wait = self.min_interval - (now - self._last_doc)
        if wait > 0:
            time.sleep(wait)
        self._last_doc = time.monotonic()
        if s.xml_enabled:
            try:
                os.makedirs(folder, exist_ok=True)
                for prof in s.xml_profiles:
                    if prof in XML_PROFILES:
                        fname, fn = XML_PROFILES[prof]
                        atomic_write_text(os.path.join(folder, fname), fn(snap))
                self._set("xml", "ok", folder, wrote=True)
            except OSError as e:
                self._set("xml", "error", f"Cannot write XML to {folder}: {e.strerror or e}.")
        else:
            self._set("xml", "off")
        if s.json_enabled:
            try:
                os.makedirs(folder, exist_ok=True)
                atomic_write_text(os.path.join(folder, "state.json"), state_json(snap, indent=1))
                self._set("json", "ok", folder, wrote=True)
            except OSError as e:
                self._set("json", "error", f"Cannot write JSON to {folder}: {e.strerror or e}.")
        else:
            self._set("json", "off")
