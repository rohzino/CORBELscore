"""
The Data tab: the fields that make up a scoreboard.

Add, rename, reorder and configure fields. Renaming a field updates every
board, button and penalty that refers to it, and the tab lists where a field
is used before you delete it.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
                             QHeaderView, QInputDialog, QLineEdit, QMenu, QPlainTextEdit, QScrollArea, QSpinBox,
                             QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..core.fields import (FIELD_TYPES, ChoiceField, ClockField, CounterField, Field, ImageField, PenaltyField,
                           TextField, ToggleField, normalise_key, valid_key)
from ..core.timefmt import LEGACY_FORMATS, TimeParseError, format_ms, parse_time
from . import theme
from .session import Session
from .widgets import ConfirmButton, button, caps, clear_layout, label, panel

TYPE_NAMES = {"counter": "Counter", "text": "Text", "toggle": "On / off", "choice": "Choice", "clock": "Clock",
              "penalties": "Penalties", "image": "Picture"}
TYPE_HELP = {
    "counter": "A whole number: score, period, fouls, shots.",
    "text": "Free text: names, sponsor lines, down and distance.",
    "toggle": "On or off: possession, bonus, power play, show or hide a graphic.",
    "choice": "One of a list: 1st, 2nd, 3rd, OT.",
    "clock": "Counts down or up: game clock, shot clock, stopwatch.",
    "penalties": "Timed penalties that run only while their game clock runs.",
    "image": "A picture: team logo, sponsor, flag.",
}
CLOCK_FORMATS = ["m:ss", "mm:ss", "h:mm:ss", "s", "ss", "m:ss.t", "s.t", "ss.t"] + \
                [f for f in LEGACY_FORMATS if f not in ("m:ss", "mm:ss")]


class DataTab(QWidget):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        self._key: Optional[str] = None
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        bar = QHBoxLayout()
        add = QMenu(self)
        for t, name in TYPE_NAMES.items():
            act = add.addAction(name, lambda _=False, t=t: self.add_field(t))
            act.setToolTip(TYPE_HELP[t])
        add.setToolTipsVisible(True)
        b_add = button("Add field", "accent")
        b_add.setMenu(add)
        bar.addWidget(b_add)
        bar.addWidget(button("Rename key", "", self.rename, tip="Change the key; every board and button follows"))
        bar.addWidget(button("Duplicate", "", self.duplicate))
        bar.addWidget(button("Move up", "", lambda: self.move(-1)))
        bar.addWidget(button("Move down", "", lambda: self.move(1)))
        self.b_delete = ConfirmButton("Delete", "Press again to delete")
        self.b_delete.confirmed.connect(self.delete)
        bar.addWidget(self.b_delete)
        bar.addStretch(1)
        bar.addWidget(label("The Operate tab builds its controls from this list.", "small", muted=True))
        root.addLayout(bar)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Key", "Type", "Label", "Now"])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._selected)
        split.addWidget(self.table)

        self.editor_holder = QWidget()
        self.editor = QVBoxLayout(self.editor_holder)
        self.editor.setContentsMargins(12, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.editor_holder)
        scroll.setMinimumWidth(380)
        split.addWidget(scroll)
        split.setSizes([620, 420])
        root.addWidget(split, 1)

        session.structure.connect(self.refresh)
        session.snapshot.connect(self._values)
        self.refresh()

    # ----- table -----------------------------------------------------------
    def refresh(self) -> None:
        keep = self._key
        fields = list(self.session.engine.fields.values())
        self.table.blockSignals(True)
        self.table.setRowCount(len(fields))
        values = self.session.values()
        for r, f in enumerate(fields):
            for c, text in enumerate((f.key, TYPE_NAMES.get(f.type, f.type), f.label, values.get(f.key, ""))):
                it = QTableWidgetItem(text)
                it.setData(Qt.ItemDataRole.UserRole, f.key)
                if c == 0:
                    it.setFont(theme.font(13, 600, family="Consolas"))
                if c == 1 or c == 3:
                    it.setForeground(theme_color("muted"))
                self.table.setItem(r, c, it)
        self.table.blockSignals(False)
        row = next((r for r, f in enumerate(fields) if f.key == keep), 0 if fields else -1)
        if row >= 0:
            self.table.selectRow(row)
        self._selected()

    def _values(self, snap, changed):
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it and it.text() in changed:
                self.table.item(r, 3).setText(snap.values.get(it.text(), ""))

    def _current(self) -> Optional[Field]:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        key = self.table.item(rows[0].row(), 0).text()
        return self.session.engine.fields.get(key)

    def _selected(self):
        f = self._current()
        self._key = f.key if f else None
        self.b_delete.setEnabled(f is not None)
        # Settings edits refresh the table but keep the editor (and its focus).
        if f is None or f is not getattr(self, "_built", None):
            self._built = f
            self.build_editor(f)

    # ----- commands --------------------------------------------------------
    def _free_key(self, base: str) -> str:
        key, n = base, 2
        keys = set(self.session.engine.fields)
        while key in keys or any(k.startswith(key + ".") or key.startswith(k + ".") for k in keys):
            key = f"{base}_{n}"
            n += 1
        return key

    def add_field(self, ftype: str) -> None:
        text, ok = QInputDialog.getText(self, "Add field",
                                        f"{TYPE_HELP[ftype]}\n\nKey (lower-case words joined by dots, "
                                        "for example home.fouls):")
        if not ok or not text.strip():
            return
        key = normalise_key(text)
        if not valid_key(key):
            self.session.message.emit(f"{text!r} cannot be a key. Use letters, digits and dots.", True)
            return
        key = self._free_key(key)
        label_text = key.replace(".", " ").replace("_", " ").title()
        cls = FIELD_TYPES[ftype]
        kwargs = {}
        if ftype == "choice":
            kwargs["options"] = ["1st", "2nd", "3rd", "4th"]
        if ftype == "penalties":
            clocks = [k for k, f in self.session.engine.fields.items() if isinstance(f, ClockField)]
            kwargs["master"] = clocks[0] if clocks else ""
        try:
            f = cls(key, label_text, **kwargs)
            self.session.engine.add_field(f)
        except ValueError as e:
            self.session.message.emit(str(e), True)
            return
        self._key = key
        self.session.fields_changed()

    def rename(self) -> None:
        f = self._current()
        if f is None:
            return
        text, ok = QInputDialog.getText(self, "Rename key", "New key:", text=f.key)
        if not ok:
            return
        new = normalise_key(text)
        if new == f.key:
            return
        if not valid_key(new) or new in self.session.engine.fields:
            self.session.message.emit(f"{new!r} is taken or not a valid key.", True)
            return
        try:
            n = self.session.rename_key_everywhere(f.key, new)
        except ValueError as e:
            self.session.message.emit(str(e), True)
            return
        self._key = new
        self._built = None
        self.refresh()
        self.session.message.emit(f"Renamed to {new}. {n} reference{'s' if n != 1 else ''} updated.", False)

    def duplicate(self) -> None:
        f = self._current()
        if f is None:
            return
        from ..core.fields import field_from_dict
        d = f.to_dict()
        d["key"] = self._free_key(f.key + "_copy")
        d["label"] = f.label + " copy"
        try:
            self.session.engine.add_field(field_from_dict(d), index=list(self.session.engine.fields).index(f.key) + 1)
        except ValueError as e:
            self.session.message.emit(str(e), True)
            return
        self._key = d["key"]
        self.session.fields_changed()

    def move(self, delta: int) -> None:
        f = self._current()
        if f is None:
            return
        keys = list(self.session.engine.fields)
        i = keys.index(f.key)
        j = max(0, min(len(keys) - 1, i + delta))
        if i == j:
            return
        eng = self.session.engine
        items = list(eng.fields.items())
        items.insert(j, items.pop(i))
        from collections import OrderedDict
        eng._fields = OrderedDict(items)
        self.session.fields_changed()

    def delete(self) -> None:
        f = self._current()
        if f is None:
            return
        # Live data, rules and override: the value pipeline (core.logic) --------------
        pipe, pl = panel()
        pl.addWidget(caps("What this field outputs"))
        pform = QFormLayout()
        pform.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        src = QComboBox()
        src.setEditable(True)
        src.addItem("")
        for k in sorted(self.session.engine.sources, key=str.lower):
            src.addItem(k)
        src.setCurrentText(f.source)
        src.lineEdit().setPlaceholderText("not bound to live data")
        src.setToolTip("A key from the Live data tab, e.g. HomeScore. The field then shows the bot's value.")

        def set_src(*_):
            f.source = src.currentText().strip()
            self.changed()
        src.activated.connect(set_src)
        src.lineEdit().editingFinished.connect(set_src)
        pform.addRow(caps("Live key"), src)
        rules = QLineEdit(f.rules)
        rules.setPlaceholderText("0:00=FINAL|2:00=Two-minute warning")
        rules.setToolTip("value=replacement pairs joined by |. * matches anything, NULL matches empty, "
                         "{value} inserts the value. \\| and \\= are literal.")
        rules.editingFinished.connect(lambda: (setattr(f, "rules", rules.text().strip()), self.changed()))
        pform.addRow(caps("Rules"), rules)
        orow = QHBoxLayout()
        ov = QLineEdit(f.override)
        ov.setPlaceholderText("fixed text to show instead")
        tog = button("Override on" if f.override_on else "Override off", "accent" if f.override_on else "alert",
                     checkable=True)
        tog.setChecked(f.override_on)

        def set_ov(*_):
            f.override = ov.text()
            f.override_on = tog.isChecked()
            tog.setText("Override on" if f.override_on else "Override off")
            tog.setProperty("role", "accent" if f.override_on else "alert")
            theme.repolish(tog)
            self.changed()
        ov.editingFinished.connect(set_ov)
        tog.toggled.connect(set_ov)
        orow.addWidget(ov, 1)
        orow.addWidget(tog)
        pform.addRow(caps("Override"), orow)
        pl.addLayout(pform)
        pl.addWidget(label("Order: override, then live key, then rules, then conditional rules from Logic. The text "
                           "files, XML, JSON and every board get the result.", "small", muted=True, wrap=True))
        self.editor.addWidget(pipe)

        refs = self.session.references(f.key)
        self.session.engine.remove_field(f.key)
        self._key = None
        self.session.fields_changed()
        if refs:
            self.session.message.emit(f"Deleted {f.key}. Still referenced by: {', '.join(refs[:6])}"
                                      f"{' …' if len(refs) > 6 else ''}. Those now show nothing.", True)

    # ----- editor ----------------------------------------------------------
    def changed(self) -> None:
        """A setting changed: republish and refresh the Operate cards."""
        self.session.fields_changed()

    def build_editor(self, f: Optional[Field]) -> None:
        clear_layout(self.editor)
        if f is None:
            self.editor.addWidget(label("Pick a field to change its settings, or add one.", "body", muted=True,
                                        wrap=True))
            self.editor.addStretch(1)
            return
        title = label(f.key, "dialog-title")
        self.editor.addWidget(title)
        self.editor.addWidget(label(TYPE_HELP.get(f.type, ""), "small", muted=True, wrap=True))
        box, bl = panel()
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        bl.addLayout(form)
        self.editor.addWidget(box)

        lab = QLineEdit(f.label)
        lab.editingFinished.connect(lambda: (setattr(f, "label", lab.text().strip() or f.key), self.changed()))
        form.addRow(caps("Label"), lab)

        def spin(value, lo, hi, apply, suffix=""):
            s = QSpinBox()
            s.setRange(lo, hi)
            s.setValue(int(value))
            s.setKeyboardTracking(False)
            if suffix:
                s.setSuffix(suffix)
            s.valueChanged.connect(lambda v: (apply(v), self.changed()))
            return s

        def check(text, value, apply):
            c = QCheckBox(text)
            c.setChecked(bool(value))
            c.toggled.connect(lambda v: (apply(v), self.changed()))
            return c

        if isinstance(f, CounterField):
            form.addRow(caps("Starts at"), spin(f.default, -99999, 99999, lambda v: setattr(f, "default", v)))
            lo = QLineEdit("" if f.minimum is None else str(f.minimum))
            hi = QLineEdit("" if f.maximum is None else str(f.maximum))
            lo.setPlaceholderText("no minimum")
            hi.setPlaceholderText("no maximum")

            def limits():
                try:
                    f.minimum = int(lo.text()) if lo.text().strip() else None
                    f.maximum = int(hi.text()) if hi.text().strip() else None
                    f.value = f._clamp(f.value)
                    self.changed()
                except ValueError:
                    self.session.message.emit("Limits must be whole numbers.", True)
            lo.editingFinished.connect(limits)
            hi.editingFinished.connect(limits)
            r = QHBoxLayout()
            r.addWidget(lo)
            r.addWidget(hi)
            form.addRow(caps("Min  max"), r)
            steps = QLineEdit(", ".join(str(s) for s in f.steps))
            steps.setToolTip("The + buttons on the Operate card, for example 1, 2, 3")

            def set_steps():
                try:
                    vals = [int(x) for x in steps.text().replace(" ", "").split(",") if x]
                    f.steps = [v for v in vals if v != 0][:6] or [1]
                    self.changed()
                except ValueError:
                    self.session.message.emit("Steps are whole numbers separated by commas, like 1, 2, 3.", True)
            steps.editingFinished.connect(set_steps)
            form.addRow(caps("Buttons"), steps)
            form.addRow(caps("Digits"), spin(f.pad, 0, 6, lambda v: setattr(f, "pad", v)))
            form.addRow("", check("Show as 1st, 2nd, 3rd", f.ordinal, lambda v: setattr(f, "ordinal", v)))
            form.addRow("", check("Blank when zero", f.blank_zero, lambda v: setattr(f, "blank_zero", v)))

        elif isinstance(f, TextField):
            d = QLineEdit(f.default)
            d.editingFinished.connect(lambda: (setattr(f, "default", d.text()), self.changed()))
            form.addRow(caps("Reset to"), d)
            form.addRow("", check("Capitals", f.uppercase, lambda v: setattr(f, "uppercase", v)))

        elif isinstance(f, ToggleField):
            on, off = QLineEdit(f.on_text), QLineEdit(f.off_text)
            on.setToolTip("What outputs show when on, e.g. PP, BONUS, ●")
            off.setPlaceholderText("nothing")
            on.editingFinished.connect(lambda: (setattr(f, "on_text", on.text()), self.changed()))
            off.editingFinished.connect(lambda: (setattr(f, "off_text", off.text()), self.changed()))
            form.addRow(caps("When on"), on)
            form.addRow(caps("When off"), off)
            form.addRow("", check("Starts on", f.default, lambda v: setattr(f, "default", v)))

        elif isinstance(f, ChoiceField):
            opts = QPlainTextEdit("\n".join(f.options))
            opts.setFixedHeight(120)
            opts.setToolTip("One option per line")

            def set_opts():
                lines = [x.strip() for x in opts.toPlainText().splitlines()]
                lines = [x for x in lines if x] or [""]
                f.options = lines
                f.index = f._clamp(f.index)
                f.default = f._clamp(f.default)
                self.changed()
            b = button("Apply options", "", set_opts)
            form.addRow(caps("Options"), opts)
            form.addRow("", b)
            form.addRow("", check("Next wraps to the first", f.wrap, lambda v: setattr(f, "wrap", v)))

        elif isinstance(f, ClockField):
            c = f.clock
            mode = QComboBox()
            mode.addItem("Counts down", True)
            mode.addItem("Counts up (stopwatch)", False)
            mode.setCurrentIndex(0 if c.countdown else 1)

            def set_mode(_):
                c.stop()
                c.countdown = bool(mode.currentData())
                c.reset()
                self.changed()
            mode.activated.connect(set_mode)
            form.addRow(caps("Mode"), mode)
            length = QLineEdit(format_ms(c.initial_ms, "h:mm:ss" if c.initial_ms >= 3_600_000 else "m:ss"))
            length.setToolTip("Period length for a countdown; where Reset goes")

            def set_len():
                try:
                    c.initial_ms = parse_time(length.text())
                    length.setProperty("error", False)
                    theme.repolish(length)
                    self.changed()
                except TimeParseError as e:
                    length.setProperty("error", True)
                    theme.repolish(length)
                    self.session.message.emit(str(e), True)
            length.editingFinished.connect(set_len)
            form.addRow(caps("Period length"), length)
            fmt = QComboBox()
            fmt.setEditable(True)
            fmt.addItems(CLOCK_FORMATS)
            fmt.setCurrentText(c.fmt)
            fmt.setToolTip("m minutes, s seconds, h hours, t tenths. Example 12:00 is m:ss.")

            def set_fmt(*_):
                c.fmt = fmt.currentText().strip() or "m:ss"
                self.changed()
            fmt.activated.connect(set_fmt)
            fmt.lineEdit().editingFinished.connect(set_fmt)
            form.addRow(caps("Format"), fmt)
            tenths = QSpinBox()
            tenths.setRange(0, 600)
            tenths.setSuffix(" s")
            tenths.setSpecialValueText("never")
            tenths.setValue(c.tenths_under_ms // 1000)
            tenths.setToolTip("Below this, a countdown shows tenths (59.9). 60 is usual for basketball and hockey.")
            tenths.valueChanged.connect(lambda v: (setattr(c, "tenths_under_ms", v * 1000), self.changed()))
            form.addRow(caps("Tenths under"), tenths)
            limit = QLineEdit(format_ms(c.limit_ms, "m:ss", False) if c.limit_ms else "")
            limit.setPlaceholderText("no limit")
            limit.setToolTip("Stopwatch only: stop when this is reached, e.g. 45:00")

            def set_limit():
                try:
                    c.limit_ms = parse_time(limit.text()) if limit.text().strip() else 0
                    self.changed()
                except TimeParseError as e:
                    self.session.message.emit(str(e), True)
            limit.editingFinished.connect(set_limit)
            form.addRow(caps("Stop at"), limit)
            form.addRow("", check("Blank at zero", c.blank_at_zero, lambda v: setattr(c, "blank_at_zero", v)))
            buzz = QLineEdit(f.buzzer)
            buzz.setPlaceholderText("No buzzer")
            buzz.setReadOnly(True)

            def pick_buzz():
                path, _ = QFileDialog.getOpenFileName(self, "Buzzer sound", "", "Sounds (*.wav *.mp3 *.ogg *.m4a)")
                if path:
                    f.buzzer = path
                    buzz.setText(path)
                    self.changed()

            def clear_buzz():
                f.buzzer = ""
                buzz.clear()
                self.changed()
            br = QHBoxLayout()
            br.addWidget(buzz, 1)
            br.addWidget(button("Choose…", "", pick_buzz))
            br.addWidget(button("None", "", clear_buzz))
            form.addRow(caps("Buzzer"), br)
            bl.addWidget(label("Time is kept in milliseconds from the system clock, so the display never drifts, "
                               "and a pause keeps the fraction already run.", "small", muted=True, wrap=True))

        elif isinstance(f, PenaltyField):
            master = QComboBox()
            master.addItem("(none)", "")
            for k, g in self.session.engine.fields.items():
                if isinstance(g, ClockField):
                    master.addItem(f"{g.label}  ({k})", k)
            master.setCurrentIndex(max(0, master.findData(f.master)))
            master.activated.connect(lambda _: (setattr(f, "master", master.currentData() or ""), self.changed()))
            form.addRow(caps("Runs with"), master)
            form.addRow(caps("On the board"), spin(f.slots, 1, 6, lambda v: setattr(f, "slots", v)))
            fmt = QComboBox()
            fmt.setEditable(True)
            fmt.addItems(["m:ss", "mm:ss", "ss"])
            fmt.setCurrentText(f.fmt)

            def set_pfmt(*_):
                f.fmt = fmt.currentText().strip() or "m:ss"
                self.changed()
            fmt.activated.connect(set_pfmt)
            fmt.lineEdit().editingFinished.connect(set_pfmt)
            form.addRow(caps("Format"), fmt)
            bl.addWidget(label(f"Boards read {f.key}.1.player and {f.key}.1.time (and .2, .3 …). Penalties beyond "
                               "the board's slots wait their turn.", "small", muted=True, wrap=True))

        elif isinstance(f, ImageField):
            d = QLineEdit(f.default)
            d.setPlaceholderText("No picture")

            def pick():
                path, _ = QFileDialog.getOpenFileName(self, "Default picture", "",
                                                      "Pictures (*.png *.jpg *.jpeg *.gif *.webp *.svg *.bmp)")
                if path:
                    f.default = path
                    d.setText(path)
                    self.changed()
            r = QHBoxLayout()
            r.addWidget(d, 1)
            r.addWidget(button("Choose…", "", pick))
            d.editingFinished.connect(lambda: (setattr(f, "default", d.text().strip()), self.changed()))
            form.addRow(caps("Reset to"), r)

        refs = self.session.references(f.key)
        used, ul = panel(pad=10, spacing=4)
        ul.addWidget(caps("Used by"))
        if refs:
            for r in refs[:20]:
                ul.addWidget(label(r, "small"))
            if len(refs) > 20:
                ul.addWidget(label(f"… and {len(refs) - 20} more", "small", muted=True))
        else:
            ul.addWidget(label("Nothing yet. Drag it onto a board in Build, or use it in a button.", "small",
                               muted=True, wrap=True))
        self.editor.addWidget(used)
        keys = [f.key] + [k for k in self.session.values() if k.startswith(f.key + ".")]
        ul2 = label("Outputs as " + ", ".join(keys[:8]) + (" …" if len(keys) > 8 else ""), "small", muted=True,
                    wrap=True)
        self.editor.addWidget(ul2)
        self.editor.addStretch(1)


def theme_color(key: str):
    from PyQt6.QtGui import QColor
    return QColor(theme.CURRENT[key])
