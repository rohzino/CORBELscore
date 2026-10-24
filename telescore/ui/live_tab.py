"""
The Live data tab: connect a Sportzcast bot (or a LiveXML file) and bind its
keys to fields. A bound field shows the bot's value; rules, overrides and
conditions still apply, and the operator can override it at any time.
"""

from __future__ import annotations

import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
                             QHeaderView, QLineEdit, QMessageBox, QScrollArea, QSpinBox, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from ..core.fields import ChoiceField, CounterField, TextField
from ..core.sportzcast import CLOUD_HOST, suggest
from .live_ctl import LiveController
from .session import Session
from .widgets import SectionTitle, StateChip, StatusDot, button, caps, label, panel

KINDS = [
    ("", "Off"),
    ("mqtt-cloud", "Sportzcast cloud (MQTT, recommended)"),
    ("mqtt-local", "ScoreConnect III / Scorelink+ on this network (MQTT)"),
    ("tcp", "Sportzcast socket (legacy, port 1402)"),
    ("livexml", "LiveXML file or XML URL"),
    ("json", "JSON file or URL"),
]


class LiveTab(QWidget):
    def __init__(self, session: Session, live: LiveController, parent=None):
        super().__init__(parent)
        self.session, self.live = session, live
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(16, 14, 16, 16)
        root.setSpacing(12)

        root.addWidget(SectionTitle("Connection"))
        box, bl = panel()
        s = session.project.source
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.kind = QComboBox()
        for k, name in KINDS:
            self.kind.addItem(name, k)
        cur = "mqtt-cloud" if (s.kind == "mqtt" and s.cloud) else "mqtt-local" if s.kind == "mqtt" else s.kind
        self.kind.setCurrentIndex(max(0, self.kind.findData(cur)))
        self.kind.activated.connect(self._kind_changed)
        form.addRow(caps("Source"), self.kind)
        self.email = QLineEdit(s.username)
        self.email.setPlaceholderText("The e-mail your bot is assigned to")
        self.token = QLineEdit(live.token())
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText("Access token (sportzcast.net → Account → User info)")
        self.token.setToolTip("Kept in this computer's settings, never in the project file.")
        self.bot = QSpinBox()
        self.bot.setRange(0, 999999)
        self.bot.setValue(s.bot)
        self.host = QLineEdit(s.host)
        self.host.setPlaceholderText("Device address, e.g. 192.168.1.40")
        self.port = QSpinBox()
        self.port.setRange(0, 65535)
        self.port.setSpecialValueText("standard")
        self.port.setValue(s.port)
        self.dtype = QComboBox()
        self.dtype.addItem("JSON", "json")
        self.dtype.addItem("XML", "xml")
        self.dtype.setCurrentIndex(max(0, self.dtype.findData(s.data_type)))
        pr = QHBoxLayout()
        self.path = QLineEdit(s.path)
        self.path.setPlaceholderText("C:\\LiveXML\\scoreboard.xml or http://…")
        pr.addWidget(self.path, 1)
        pr.addWidget(button("Browse…", "", self._browse))
        self.poll = QSpinBox()
        self.poll.setRange(50, 10_000)
        self.poll.setSuffix(" ms")
        self.poll.setValue(s.poll_ms)
        self.stale = QSpinBox()
        self.stale.setRange(1, 3600)
        self.stale.setSuffix(" s")
        self.stale.setValue(s.stale_s)
        self.rows = {}
        for key, cap, w in (("email", "E-mail", self.email), ("token", "Token", self.token), ("bot", "Bot number", self.bot),
                            ("host", "Address", self.host), ("port", "Port", self.port), ("dtype", "Data", self.dtype),
                            ("path", "File or URL", pr), ("poll", "Check every", self.poll),
                            ("stale", "Warn after silence", self.stale)):
            lab = caps(cap)
            form.addRow(lab, w)
            self.rows[key] = (lab, w)
        bl.addLayout(form)
        r = QHBoxLayout()
        r.addWidget(button("Connect", "accent", self.apply))
        r.addWidget(button("Disconnect", "", self.disconnect))
        r.addStretch(1)
        bl.addLayout(r)
        st = QHBoxLayout()
        self.dot = StatusDot()
        self.chip = StateChip("OFF", "muted")
        self.detail = label("", "small", muted=True, wrap=True)
        st.addWidget(self.dot)
        st.addWidget(self.chip)
        st.addWidget(self.detail, 1)
        bl.addLayout(st)
        self.help = label("", "small", muted=True, wrap=True)
        bl.addWidget(self.help)
        root.addWidget(box)

        root.addWidget(SectionTitle("Keys and bindings"))
        box, bl = panel()
        top = QHBoxLayout()
        top.addWidget(label("Every key the source sends. Bind one to a field and the field follows it.", "small",
                            muted=True))
        top.addStretch(1)
        self.show_bound = QCheckBox("Only bound keys")
        self.show_bound.toggled.connect(self.refresh_keys)
        top.addWidget(self.show_bound)
        top.addWidget(button("Suggest bindings", "accent", self.automap,
                             tip="Bind HomeScore, GuestScore, Clock, Period … to this project's fields"))
        bl.addLayout(top)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Key", "Value now", "Bound to", ""])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumHeight(320)
        bl.addWidget(self.table)
        root.addWidget(box)
        root.addStretch(1)

        self._row_keys = []
        live.status.connect(self._status)
        session.structure.connect(self.refresh_keys)
        self._kind_changed()
        self._status()

    # ----- settings ---------------------------------------------------------------
    def _kind_changed(self, *_):
        k = self.kind.currentData() or ""
        visible = {
            "": set(),
            "mqtt-cloud": {"email", "token", "bot", "stale"},
            "mqtt-local": {"bot", "host", "port", "stale"},
            "tcp": {"email", "token", "bot", "dtype", "stale"},
            "livexml": {"path", "poll", "stale"},
            "json": {"path", "poll", "stale"},
        }[k]
        for key, (lab, w) in self.rows.items():
            on = key in visible
            lab.setVisible(on)
            if hasattr(w, "setVisible"):
                w.setVisible(on)
            else:
                for i in range(w.count()):
                    item = w.itemAt(i).widget()
                    if item:
                        item.setVisible(on)
        self.help.setText({
            "": "No live data. Fields keep their own values.",
            "mqtt-cloud": f"Connects to {CLOUD_HOST}:8883 over TLS and reads bot/<bot>/json. Needs an active "
                          "Sportzcast account, licence and the bot assigned to you.",
            "mqtt-local": "Reads a ScoreConnect III or Scorelink+ on this network (MQTT port 1883, no login). "
                          "Turn on the device's local MQTT server first.",
            "tcp": "The older socket interface. Sportzcast recommends MQTT for new setups.",
            "livexml": "Watches the XML file written by Sportzcast LiveXML (or any XML file or web address) and "
                       "reads it when it changes. A file caught half-written is skipped.",
            "json": "Watches a JSON file or web address and reads it when it changes.",
        }[k])

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Live data file", "", "XML or JSON (*.xml *.json);;All files (*)")
        if path:
            self.path.setText(path)

    def apply(self):
        k = self.kind.currentData() or ""
        s = self.session.project.source
        s.kind = {"mqtt-cloud": "mqtt", "mqtt-local": "mqtt"}.get(k, k)
        s.cloud = k in ("mqtt-cloud", "tcp")
        s.username = self.email.text().strip()
        s.bot = self.bot.value()
        s.host = self.host.text().strip() if k in ("mqtt-local",) else ""
        s.port = self.port.value() if k == "mqtt-local" else 0
        s.data_type = self.dtype.currentData() if k == "tcp" else "json"
        s.path = self.path.text().strip()
        s.poll_ms = self.poll.value()
        s.stale_s = self.stale.value()
        self.live.set_token(self.token.text().strip())
        self.session.source_changed()

    def disconnect(self):
        self.kind.setCurrentIndex(0)
        self._kind_changed()
        self.apply()

    # ----- status and keys ------------------------------------------------------------
    def _status(self):
        st = self.live.source.status
        self.dot.setState({"live": "live", "connecting": "busy", "stale": "busy", "error": "error"}.get(st.state, "off"))
        word, kind = {"live": ("LIVE", "accent"), "connecting": ("CONNECTING", "user"), "stale": ("SILENT", "user"),
                      "error": ("FAILING", "alert")}.get(st.state, ("OFF", "muted"))
        self.chip.set(word, kind)
        extra = ""
        if st.last_packet:
            age = time.time() - st.last_packet
            extra = f" · {st.packets} updates · last {age:.0f} s ago" if age >= 2 else f" · {st.packets} updates · now"
        self.detail.setText((st.detail or "") + extra)
        if self.isVisible():
            self.refresh_keys()

    def refresh_keys(self, *_):
        keys = self.live.keys()
        bound = {f.source: f.key for f in self.session.engine.fields.values() if f.source}
        for sk in bound:
            keys.setdefault(sk, "")
        names = sorted(keys, key=str.lower)
        if self.show_bound.isChecked():
            names = [n for n in names if n in bound]
        if names != self._row_keys:
            self._row_keys = names
            self.table.setRowCount(len(names))
            for r, sk in enumerate(names):
                it = QTableWidgetItem(sk)
                it.setToolTip(sk)
                self.table.setItem(r, 0, it)
                self.table.setItem(r, 1, QTableWidgetItem(""))
                combo = QComboBox()
                combo.addItem("—", "")
                for fk in self.session.engine.fields:
                    combo.addItem(fk, fk)
                combo.activated.connect(lambda _i, sk=sk, combo=combo: self._bind(sk, combo.currentData()))
                self.table.setCellWidget(r, 2, combo)
                self.table.setCellWidget(r, 3, button("Make a field", "", lambda sk=sk: self._make_field(sk)))
        for r, sk in enumerate(names):
            v = self.table.item(r, 1)
            if v is not None and v.text() != keys.get(sk, ""):
                v.setText(keys.get(sk, ""))
            combo = self.table.cellWidget(r, 2)
            if isinstance(combo, QComboBox):
                want = combo.findData(bound.get(sk, ""))
                if combo.currentIndex() != want and not combo.view().isVisible():
                    combo.setCurrentIndex(max(0, want))

    def _bind(self, source_key: str, field_key: str):
        for f in self.session.engine.fields.values():
            if f.source == source_key and f.key != field_key:
                f.source = ""
        if field_key:
            self.session.engine.field(field_key).source = source_key
        self.session.fields_changed()

    def _make_field(self, sk: str):
        from ..core.fields import normalise_key
        key = normalise_key("live." + sk)
        e = self.session.engine
        if key in e.fields:
            self._bind(sk, key)
            return
        val = self.live.keys().get(sk, "")
        cls = CounterField if val.strip().lstrip("-").isdigit() else TextField
        f = cls(key, sk, source=sk, **({"minimum": None} if cls is CounterField else {}))
        try:
            e.add_field(f)
        except ValueError as err:
            self.session.message.emit(str(err), True)
            return
        self.session.fields_changed()

    def automap(self):
        keys = self.live.keys()
        if not keys:
            self.session.message.emit("No keys yet. Connect and wait for the first update, then try again.", True)
            return
        e = self.session.engine
        free = [k for k, f in e.fields.items() if not f.source]
        plan = suggest(keys, free)
        if not plan:
            self.session.message.emit("No matching names found. Bind keys by hand in the table.", False)
            return
        lines = "\n".join(f"{fk}  ←  {sk}" for fk, sk in plan.items())
        if QMessageBox.question(self, "Suggest bindings", f"Bind these?\n\n{lines}") != QMessageBox.StandardButton.Yes:
            return
        for fk, sk in plan.items():
            f = e.field(fk)
            f.source = sk
            # Bots send period numbers; a choice field shows its own words for them.
            if isinstance(f, ChoiceField) and not f.rules and keys.get(sk, "").strip().isdigit():
                f.rules = "|".join(f"{i + 1}={o}" for i, o in enumerate(f.options))
        self.session.fields_changed()
        self.session.message.emit(f"Bound {len(plan)} field{'s' if len(plan) != 1 else ''}. "
                                  "Period numbers are turned into your period names with a rule.", False)

    def showEvent(self, ev):
        super().showEvent(ev)
        self.refresh_keys()
