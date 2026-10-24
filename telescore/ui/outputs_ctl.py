"""
Runs every output for the open project: files (text, XML, JSON), the web
server (browser sources, feeds, remote control) and PNG images of boards.
"""

from __future__ import annotations

import os
import time
from typing import Dict

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from ..core.board import template_keys
from ..core.fields import ImageField
from ..outputs.manager import OutputManager, OutputStatus
from ..outputs.server import ScoreServer, ServerData
from .render import ImageCache, render_png
from .session import Session


class OutputController(QObject):
    status = pyqtSignal()               # something about outputs changed (lights, server, clients)
    _from_writer = pyqtSignal()         # emitted on the writer thread, delivered on the GUI thread

    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        p = session.project
        self._from_writer.connect(self.status.emit)  # auto-connection queues it across threads
        self.files = OutputManager(p.outputs, p.name, on_status=lambda st: self._from_writer.emit())
        self.data = ServerData(lambda: session.engine.snapshot(), session.engine.submit)
        self.server = ScoreServer(self.data)
        self.images = ImageCache()
        self.png_state: Dict[str, str] = {}      # board id -> "ok" | error text
        self._png_due: Dict[str, float] = {}
        self._png_timer = QTimer(self)
        self._png_timer.setInterval(250)         # at most 4 PNG renders a second per board
        self._png_timer.timeout.connect(self._write_pngs)
        self._poll = QTimer(self)                # status lights and client counts
        self._poll.setInterval(1000)
        self._poll.timeout.connect(self.status.emit)
        session.engine.on_change(self.files.submit)
        session.engine.on_change(self.server.publish)
        session.snapshot.connect(self._on_snapshot)
        session.boards.connect(self.sync_boards)
        session.board_edited.connect(lambda _bid: self.sync_boards())
        session.structure.connect(self.sync_assets)
        session.animations.connect(self.sync_boards)
        session.outputs.connect(self.apply)

    def start(self) -> None:
        self.sync_boards()
        self.apply()
        self.files.submit(self.session.engine.snapshot())
        self._png_timer.start()
        self._poll.start()

    def stop(self) -> None:
        self._png_timer.stop()
        self._poll.stop()
        self.server.stop()
        self.files.close()

    # ----- configuration -----------------------------------------------------
    def apply(self) -> None:
        p = self.session.project
        o = p.outputs
        self.files.reconfigure(o, p.name)
        self.files.submit(self.session.engine.snapshot())
        self.data.token = o.http_token or ""
        want = o.http_enabled
        if want and (not self.server.running or self.server.port != o.http_port or
                     (self.server.host == "0.0.0.0") != bool(o.http_lan)):
            if not self.server.start(o.http_port, o.http_lan):
                self.session.message.emit(self.server.error, True)
        elif not want and self.server.running:
            self.server.stop()
        for bid in o.image_boards:
            self._png_due[bid] = 0.0
        self.status.emit()

    def sync_boards(self) -> None:
        self.data.set_boards([b.to_dict() for b in self.session.project.boards])
        self.data.animations = [a.to_dict() for a in self.session.project.animations]
        self.sync_assets()
        for bid in self.session.project.outputs.image_boards:
            self._png_due[bid] = 0.0

    def sync_assets(self) -> None:
        """Only pictures the project uses may be served over HTTP."""
        paths = set()
        values = self.session.values()
        for f in self.session.engine.fields.values():
            if isinstance(f, ImageField):
                paths.update({f.value, f.default})
        for b in self.session.project.boards:
            for e in b.elements:
                if e.kind == "image" and e.src:
                    if "{" in e.src:
                        for k in template_keys(e.src):
                            paths.add(values.get(k, ""))
                    else:
                        paths.add(e.src)
        self.data.set_assets(p for p in paths if p)

    @property
    def folder(self) -> str:
        return self.files.folder

    def file_status(self) -> Dict[str, OutputStatus]:
        return dict(self.files.status)

    def url(self, path: str = "/") -> str:
        port = self.server.port or self.session.project.outputs.http_port
        return f"http://127.0.0.1:{port}{path}"

    def lan_urls(self, path: str = "/"):
        """Addresses other computers can use when LAN access is on."""
        import socket
        out = []
        try:
            host = socket.gethostname()
            for info in socket.getaddrinfo(host, None, socket.AF_INET):
                ip = str(info[4][0])
                if not ip.startswith("127.") and ip not in out:
                    out.append(ip)
        except OSError:
            pass
        port = self.server.port or self.session.project.outputs.http_port
        return [f"http://{ip}:{port}{path}" for ip in out]

    # ----- live ---------------------------------------------------------------
    def _on_snapshot(self, snap, changed):
        # Image fields may point at new files: keep the asset allow-list current.
        if any(snap.types.get(k) == "image" for k in changed):
            self.sync_assets()
        boards = {b.id: b for b in self.session.project.boards}
        for bid in self.session.project.outputs.image_boards:
            b = boards.get(bid)
            if b is not None and (changed & set(b.keys()) or "#fx" in changed or not b.keys()):
                self._png_due.setdefault(bid, time.monotonic())

    def _write_pngs(self):
        if not self._png_due:
            return
        values = self.session.values()
        boards = {b.id: b for b in self.session.project.boards}
        due, self._png_due = self._png_due, {}
        folder = os.path.join(self.folder, "images")
        for bid in due:
            b = boards.get(bid)
            if b is None or bid not in self.session.project.outputs.image_boards:
                continue
            try:
                os.makedirs(folder, exist_ok=True)
                safe = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in b.name).strip() or b.id
                ok = render_png(b, values, os.path.join(folder, safe + ".png"), self.images, self.session.fx())
                self.png_state[bid] = "ok" if ok else "Could not write the picture."
            except OSError as e:
                self.png_state[bid] = f"Cannot write to {folder}: {e.strerror or e}"
        self.status.emit()
