"""
Setup → Outputs: where scores go.

Files for OBS text sources and graphics systems, a local web server for
browser sources and remote control, and PNG pictures of boards. Every output
has a status light and a word.
"""

from __future__ import annotations

import os
import secrets
import time

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QApplication, QCheckBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout,
                             QLineEdit, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from ..outputs.formats import XML_PROFILES
from ..outputs.manager import default_output_folder
from .outputs_ctl import OutputController
from .session import Session
from .widgets import SectionTitle, StateChip, StatusDot, button, caps, clear_layout, label, panel

XML_HELP = {
    "nested": "Ross XPression DataLinq, Chyron: address values by path, e.g. /telescore/home/score",
    "flat": "vMix data source: one row, XPath //row; columns are home_score, clock_game …",
    "fields": "Any system that looks values up by key: //field[@key='home.score']",
}


class StatusRow(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.dot = StatusDot()
        self.chip = StateChip("OFF", "muted")
        self.detail = label("", "small", muted=True)
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.dot)
        lay.addWidget(label(title, "title"))
        lay.addWidget(self.chip)
        lay.addWidget(self.detail, 1)

    def set(self, state: str, detail: str = "") -> None:
        self.dot.setState({"ok": "live", "error": "error", "busy": "busy"}.get(state, "off"))
        word, kind = {"ok": ("LIVE", "accent"), "error": ("FAILING", "alert"), "busy": ("STARTING", "user")}.get(
            state, ("OFF", "muted"))
        self.chip.set(word, kind)
        self.detail.setText(detail)
        self.detail.setProperty("alerttext", state == "error")
        self.detail.setProperty("muted", state != "error")
        from . import theme
        theme.repolish(self.detail)


class OutputsTab(QWidget):
    def __init__(self, session: Session, ctl: OutputController, parent=None):
        super().__init__(parent)
        self.session, self.ctl = session, ctl
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(16, 14, 16, 16)
        root.setSpacing(14)
        o = session.project.outputs

        # Files -------------------------------------------------------------------
        root.addWidget(SectionTitle("Files"))
        box, bl = panel()
        row = QHBoxLayout()
        row.addWidget(caps("Folder"))
        self.folder = QLineEdit(o.folder)
        self.folder.setPlaceholderText(default_output_folder(session.project.name))
        self.folder.editingFinished.connect(self._folder_typed)
        row.addWidget(self.folder, 1)
        row.addWidget(button("Choose…", "", self._choose_folder))
        row.addWidget(button("Open folder", "", self._open_folder))
        bl.addLayout(row)
        self.text_on = QCheckBox("Text files: one per value, for OBS Text sources (text/home.score.txt)")
        self.xml_on = QCheckBox("XML")
        self.json_on = QCheckBox("JSON (state.json)")
        for cb, attr in ((self.text_on, "text_enabled"), (self.xml_on, "xml_enabled"), (self.json_on, "json_enabled")):
            cb.setChecked(getattr(o, attr))
            cb.toggled.connect(lambda v, attr=attr: self._set(attr, v))
        bl.addWidget(self.text_on)
        self.st_text = StatusRow("Text")
        bl.addWidget(self.st_text)
        bl.addWidget(self.xml_on)
        grid = QGridLayout()
        grid.setContentsMargins(24, 0, 0, 0)
        self.xml_boxes = {}
        for r, (prof, (fname, _)) in enumerate(XML_PROFILES.items()):
            cb = QCheckBox(fname)
            cb.setChecked(prof in o.xml_profiles)
            cb.toggled.connect(self._xml_profiles)
            self.xml_boxes[prof] = cb
            grid.addWidget(cb, r, 0)
            grid.addWidget(label(XML_HELP[prof], "small", muted=True, wrap=True), r, 1)
        grid.setColumnStretch(1, 1)
        bl.addLayout(grid)
        self.st_xml = StatusRow("XML")
        bl.addWidget(self.st_xml)
        bl.addWidget(self.json_on)
        self.st_json = StatusRow("JSON")
        bl.addWidget(self.st_json)
        bl.addWidget(label("Files are replaced in one step, so a graphics system never reads half a file. "
                           "XML and JSON are rewritten at most 20 times a second; text files only when their "
                           "value changes. The schema for fields.xml is docs/schema/fields.xsd.",
                           "small", muted=True, wrap=True))
        root.addWidget(box)

        # Web ---------------------------------------------------------------------
        root.addWidget(SectionTitle("Browser sources and remote control"))
        box, bl = panel()
        self.http_on = QCheckBox("Run the web server")
        self.http_on.setChecked(o.http_enabled)
        self.http_on.toggled.connect(lambda v: self._set("http_enabled", v))
        bl.addWidget(self.http_on)
        form = QFormLayout()
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(o.http_port)
        self.port.setKeyboardTracking(False)
        self.port.valueChanged.connect(lambda v: self._set("http_port", v))
        form.addRow(caps("Port"), self.port)
        self.lan = QCheckBox("Allow other computers and phones on this network")
        self.lan.setChecked(o.http_lan)
        self.lan.toggled.connect(lambda v: self._set("http_lan", v))
        form.addRow("", self.lan)
        tok = QHBoxLayout()
        self.token = QLineEdit(o.http_token)
        self.token.setPlaceholderText("No token: anyone who can reach the server can press buttons")
        self.token.editingFinished.connect(lambda: self._set("http_token", self.token.text().strip()))
        tok.addWidget(self.token, 1)
        tok.addWidget(button("Make one", "", self._make_token))
        form.addRow(caps("Control token"), tok)
        bl.addLayout(form)
        self.st_http = StatusRow("Web server")
        bl.addWidget(self.st_http)
        self.lan_warn = label("", "small", wrap=True)
        bl.addWidget(self.lan_warn)
        self.links = QVBoxLayout()
        self.links.setSpacing(4)
        bl.addLayout(self.links)
        root.addWidget(box)

        # Pictures ----------------------------------------------------------------
        root.addWidget(SectionTitle("Pictures"))
        box, self.png_lay = panel()
        root.addWidget(box)
        root.addStretch(1)

        ctl.status.connect(self.refresh_status)
        session.boards.connect(self.rebuild_links)
        session.outputs.connect(self.rebuild_links)
        self.rebuild_links()
        self.refresh_status()

    # ----- edits ---------------------------------------------------------------
    def _set(self, attr: str, value) -> None:
        o = self.session.project.outputs
        if getattr(o, attr) != value:
            setattr(o, attr, value)
            self.session.outputs_changed()

    def _folder_typed(self):
        self._set("folder", self.folder.text().strip())

    def _choose_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Output folder", self.ctl.folder)
        if d:
            self.folder.setText(d)
            self._set("folder", d)

    def _open_folder(self):
        os.makedirs(self.ctl.folder, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.ctl.folder))

    def _xml_profiles(self, *_):
        self._set("xml_profiles", [p for p, cb in self.xml_boxes.items() if cb.isChecked()])

    def _make_token(self):
        t = secrets.token_urlsafe(9)
        self.token.setText(t)
        self._set("http_token", t)

    # ----- display -------------------------------------------------------------
    def _copy_row(self, title: str, url: str, note: str = "") -> QWidget:
        w = QWidget()
        r = QHBoxLayout(w)
        r.setContentsMargins(0, 0, 0, 0)
        r.addWidget(label(title, "cell"), 0)
        e = QLineEdit(url)
        e.setReadOnly(True)
        r.addWidget(e, 1)
        if note:
            r.addWidget(label(note, "small", muted=True))
        r.addWidget(button("Copy", "", lambda: QApplication.clipboard().setText(url)))
        r.addWidget(button("Open", "", lambda: QDesktopServices.openUrl(QUrl(url))))
        return w

    def rebuild_links(self) -> None:
        clear_layout(self.links)
        p = self.session.project
        self.links.addWidget(caps("Boards · add as a Browser source at the board's size"))
        for b in p.boards:
            self.links.addWidget(self._copy_row(b.name, self.ctl.url(f"/board/{b.id}"), f"{b.width} × {b.height}"))
        self.links.addWidget(caps("Feeds"))
        self.links.addWidget(self._copy_row("JSON", self.ctl.url("/state.json")))
        for prof, (fname, _) in XML_PROFILES.items():
            self.links.addWidget(self._copy_row(fname, self.ctl.url("/" + fname)))
        self.links.addWidget(caps("Remote control · Stream Deck, Companion, any HTTP request"))
        tok = f"&token={p.outputs.http_token}" if p.outputs.http_token else ""
        self.links.addWidget(self._copy_row("Example", self.ctl.url(f"/api/action?do=toggle&field=clock.game{tok}")))
        self.links.addWidget(self._copy_row("All pages", self.ctl.url("/")))
        # Pictures
        clear_layout(self.png_lay)
        self.png_lay.addWidget(label("Write a transparent PNG of a board whenever its values change "
                                     "(images/<board>.png), for systems that load pictures.", "small", muted=True,
                                     wrap=True))
        self.png_rows = {}
        for b in p.boards:
            row = QHBoxLayout()
            cb = QCheckBox(f"{b.name}  ({b.width} × {b.height})")
            cb.setChecked(b.id in p.outputs.image_boards)
            cb.toggled.connect(lambda v, bid=b.id: self._png(bid, v))
            row.addWidget(cb, 1)
            st = label("", "small", muted=True)
            row.addWidget(st)
            self.png_rows[b.id] = st
            self.png_lay.addLayout(row)
        self.refresh_status()

    def _png(self, bid: str, on: bool):
        lst = list(self.session.project.outputs.image_boards)
        if on and bid not in lst:
            lst.append(bid)
        if not on and bid in lst:
            lst.remove(bid)
        self._set("image_boards", lst)

    def refresh_status(self) -> None:
        st = self.ctl.file_status()
        for row, key in ((self.st_text, "text"), (self.st_xml, "xml"), (self.st_json, "json")):
            s = st.get(key)
            if s is None:
                continue
            ago = ""
            if s.state == "ok" and s.last_write:
                secs = int(time.time() - s.last_write)
                ago = "written just now" if secs < 2 else f"last written {secs} s ago"
            row.set(s.state, s.detail if s.state == "error" else (f"{s.detail} · {ago}" if ago else s.detail))
        srv = self.ctl.server
        o = self.session.project.outputs
        if srv.running:
            n = srv.hub.clients
            where = "this computer and the network" if srv.host == "0.0.0.0" else "this computer only"
            self.st_http.set("ok", f"{where} · port {srv.port} · {n} browser source{'s' if n != 1 else ''} connected")
        elif o.http_enabled:
            self.st_http.set("error", srv.error or "Not running.")
        else:
            self.st_http.set("off", "")
        if o.http_lan and not o.http_token:
            self.lan_warn.setText("Anyone on this network can change the score. Make a control token, or turn "
                                  "network access off.")
            self.lan_warn.setProperty("alerttext", True)
        elif o.http_lan:
            self.lan_warn.setText("From other devices use: " + ", ".join(self.ctl.lan_urls("/")[:3]))
            self.lan_warn.setProperty("alerttext", False)
        else:
            self.lan_warn.setText("")
        from . import theme
        theme.repolish(self.lan_warn)
        for bid, lab in getattr(self, "png_rows", {}).items():
            state = self.ctl.png_state.get(bid, "")
            on = bid in o.image_boards
            lab.setText("" if not on else ("written" if state == "ok" else state or "waiting for a change"))
