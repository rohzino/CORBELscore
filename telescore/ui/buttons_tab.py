"""
The Buttons tab: operator panels.

A button runs one action or several in a row (one undo step), and can have a
keyboard shortcut. This replaces 1.x's connection wiring: instead of linking
a "Start" widget to a clock widget, a button says "start clock.game", and a
"Next quarter" button can advance the period, reset the clock and reset the
shot clock at once.
"""

from __future__ import annotations

import copy
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QInputDialog,
                             QKeySequenceEdit, QLineEdit, QListWidget, QListWidgetItem, QScrollArea, QSpinBox,
                             QSplitter, QVBoxLayout, QWidget)

from ..core.fields import ChoiceField, ClockField, CounterField, ImageField, PenaltyField, TextField, ToggleField
from ..core.project import Button, Panel
from .hotkeys import is_global_safe, normalise
from .session import Session
from .widgets import ConfirmButton, button, caps, clear_layout, label, panel

ROLES = [("neutral", "Plain"), ("accent", "Main action (green)"), ("hi", "Highlight"), ("user", "Warning (amber)"),
         ("alert", "Danger (red)")]

# do -> (label, field types it applies to; None = no field)
STEPS = {
    "add": ("Add", (CounterField, ClockField, ChoiceField)),
    "set": ("Set to", (CounterField, TextField, ToggleField, ChoiceField, ClockField, ImageField)),
    "reset": ("Reset", (CounterField, TextField, ToggleField, ChoiceField, ClockField, ImageField, PenaltyField)),
    "toggle": ("Start/stop or flip", (ClockField, ToggleField)),
    "start": ("Start", (ClockField,)),
    "stop": ("Stop", (ClockField,)),
    "adjust": ("Add time", (ClockField,)),
    "next": ("Next", (ChoiceField, CounterField)),
    "prev": ("Previous", (ChoiceField, CounterField)),
    "penalty.add": ("Add penalty", (PenaltyField,)),
    "penalty.remove": ("Remove penalty", (PenaltyField,)),
    "penalty.clear": ("Clear penalties", (PenaltyField,)),
    "stop_all": ("Stop every clock", None),
    "undo": ("Undo", None),
    "redo": ("Redo", None),
}


def describe(a: dict) -> str:
    do = a.get("do", "")
    name = STEPS.get(do, (do,))[0]
    f = a.get("field", "")
    if do == "add":
        return f"{f} {int(a.get('amount', 1)):+d}"
    if do == "set":
        return f"{f} = {a.get('value', '')}"
    if do == "adjust":
        return f"{f} {int(a.get('ms', 0)) / 1000:+g} s"
    if do == "penalty.add":
        return f"{f}: add {a.get('player', '') or 'penalty'} {a.get('time', '2:00')}"
    if do == "batch":
        return " · ".join(describe(s) for s in a.get("actions", []))
    return f"{name} {f}".strip()


class StepRow(QWidget):
    """One action: what to do, to which field, with what."""

    def __init__(self, tab: "ButtonsTab", step: dict, parent=None):
        super().__init__(parent)
        self.tab, self.step = tab, step
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.do = QComboBox()
        for k, (name, _) in STEPS.items():
            self.do.addItem(name, k)
        self.do.setCurrentIndex(max(0, self.do.findData(step.get("do", "add"))))
        self.do.activated.connect(self._do_changed)
        self.field = QComboBox()
        self.field.activated.connect(self._changed)
        self.param = QWidget()
        self.param_lay = QHBoxLayout(self.param)
        self.param_lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.do)
        lay.addWidget(self.field, 1)
        lay.addWidget(self.param, 1)
        self.remove = button("Remove", "alert", lambda: tab.remove_step(self))
        lay.addWidget(self.remove)
        self._fill_fields()
        self._fill_param()

    def _fill_fields(self):
        do = self.do.currentData()
        types = STEPS[do][1]
        self.field.clear()
        self.field.setVisible(types is not None)
        if types is None:
            return
        for k, f in self.tab.session.engine.fields.items():
            if isinstance(f, types):
                self.field.addItem(f"{k}", k)
        want = self.step.get("field")
        i = self.field.findData(want)
        if i < 0 and want:
            self.field.addItem(f"{want} (missing)", want)
            i = self.field.count() - 1
        self.field.setCurrentIndex(max(0, i))

    def _fill_param(self):
        clear_layout(self.param_lay)
        do = self.do.currentData()
        s = self.step
        if do == "add":
            sp = QSpinBox()
            sp.setRange(-999, 999)
            sp.setValue(int(s.get("amount", 1)))
            sp.valueChanged.connect(self._changed)
            self.param_lay.addWidget(sp)
            self._get = lambda: {"amount": sp.value()}
        elif do == "set":
            e = QLineEdit(str(s.get("value", "")))
            e.setPlaceholderText("value, e.g. 0, 2:00, Hawks, on")
            e.editingFinished.connect(self._changed)
            self.param_lay.addWidget(e)
            self._get = lambda: {"value": self._typed_value(e.text())}
        elif do == "adjust":
            sp = QDoubleSpinBox()
            sp.setRange(-3600, 3600)
            sp.setDecimals(1)
            sp.setSuffix(" s")
            sp.setValue(int(s.get("ms", 1000)) / 1000)
            sp.valueChanged.connect(self._changed)
            self.param_lay.addWidget(sp)
            self._get = lambda: {"ms": int(round(sp.value() * 1000))}
        elif do == "penalty.add":
            pl, tm = QLineEdit(str(s.get("player", ""))), QLineEdit(str(s.get("time", "2:00")))
            pl.setPlaceholderText("player (optional)")
            tm.setFixedWidth(64)
            pl.editingFinished.connect(self._changed)
            tm.editingFinished.connect(self._changed)
            self.param_lay.addWidget(pl)
            self.param_lay.addWidget(tm)
            self._get = lambda: {"player": pl.text().strip(), "time": tm.text().strip() or "2:00"}
        elif do == "penalty.remove":
            sp = QSpinBox()
            sp.setRange(1, 20)
            sp.setPrefix("#")
            sp.setValue(int(s.get("index", 1)))
            sp.valueChanged.connect(self._changed)
            self.param_lay.addWidget(sp)
            self._get = lambda: {"index": sp.value()}
        else:
            self._get = lambda: {}

    def _typed_value(self, text: str):
        f = self.tab.session.engine.fields.get(self.field.currentData())
        if isinstance(f, ToggleField):
            return text.strip().lower() in ("1", "true", "on", "yes", "show")
        if isinstance(f, CounterField):
            try:
                return int(text)
            except ValueError:
                return text
        return text

    def _do_changed(self, _):
        self._fill_fields()
        self._fill_param()
        self._changed()

    def _changed(self, *_):
        self.tab.steps_changed()

    def value(self) -> dict:
        d = {"do": self.do.currentData()}
        if STEPS[d["do"]][1] is not None:
            d["field"] = self.field.currentData() or ""
        d.update(self._get())
        return d


class ButtonsTab(QWidget):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        self._panel: Optional[Panel] = None
        self._button: Optional[Button] = None
        self.rows: List[StepRow] = []
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split)

        # Panels
        pw = QWidget()
        pl = QVBoxLayout(pw)
        pl.setContentsMargins(0, 0, 8, 0)
        pl.addWidget(caps("Panels"))
        self.panels = QListWidget()
        self.panels.currentRowChanged.connect(self._panel_picked)
        pl.addWidget(self.panels, 1)
        r = QHBoxLayout()
        r.addWidget(button("Add", "", self.add_panel))
        r.addWidget(button("Rename", "", self.rename_panel))
        self.del_panel = ConfirmButton("Delete")
        self.del_panel.confirmed.connect(self.delete_panel)
        r.addWidget(self.del_panel)
        pl.addLayout(r)
        cr = QHBoxLayout()
        cr.addWidget(caps("Columns"))
        self.columns = QSpinBox()
        self.columns.setRange(1, 8)
        self.columns.valueChanged.connect(self._columns)
        cr.addWidget(self.columns)
        cr.addStretch(1)
        pl.addLayout(cr)
        split.addWidget(pw)

        # Buttons
        bw = QWidget()
        bl = QVBoxLayout(bw)
        bl.setContentsMargins(8, 0, 8, 0)
        bl.addWidget(caps("Buttons on this panel"))
        self.buttons = QListWidget()
        self.buttons.currentRowChanged.connect(self._button_picked)
        bl.addWidget(self.buttons, 1)
        r = QHBoxLayout()
        r.addWidget(button("Add button", "accent", self.add_button))
        r.addWidget(button("Duplicate", "", self.duplicate_button))
        r.addWidget(button("Up", "", lambda: self.move_button(-1)))
        r.addWidget(button("Down", "", lambda: self.move_button(1)))
        self.del_button = ConfirmButton("Delete")
        self.del_button.confirmed.connect(self.delete_button)
        r.addWidget(self.del_button)
        bl.addLayout(r)
        split.addWidget(bw)

        # Editor
        self.editor_w = QWidget()
        el = QVBoxLayout(self.editor_w)
        el.setContentsMargins(8, 0, 0, 0)
        el.setSpacing(10)
        box, boxl = panel()
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.e_label = QLineEdit()
        self.e_label.editingFinished.connect(self._save_meta)
        self.e_role = QComboBox()
        for k, name in ROLES:
            self.e_role.addItem(name, k)
        self.e_role.activated.connect(self._save_meta)
        keyrow = QHBoxLayout()
        self.e_key = QKeySequenceEdit()
        try:
            self.e_key.setMaximumSequenceLength(1)
        except AttributeError:
            pass
        self.e_key.editingFinished.connect(self._save_meta)
        keyrow.addWidget(self.e_key, 1)
        keyrow.addWidget(button("Clear", "", self._clear_key))
        form.addRow(caps("Label"), self.e_label)
        form.addRow(caps("Colour"), self.e_role)
        form.addRow(caps("Shortcut"), keyrow)
        boxl.addLayout(form)
        self.key_note = label("", "small", muted=True, wrap=True)
        boxl.addWidget(self.key_note)
        el.addWidget(box)
        steps_box, sl = panel()
        sl.addWidget(caps("Steps · run in order, undone together"))
        self.steps_lay = QVBoxLayout()
        self.steps_lay.setSpacing(6)
        sl.addLayout(self.steps_lay)
        r = QHBoxLayout()
        r.addWidget(button("Add step", "", self.add_step))
        r.addStretch(1)
        r.addWidget(button("Try it", "accent", self.try_it, tip="Run the button now"))
        sl.addLayout(r)
        el.addWidget(steps_box)
        el.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.editor_w)
        split.addWidget(scroll)
        split.setSizes([220, 320, 620])

        session.panels.connect(self.refresh)
        session.structure.connect(self._fields_changed)
        self.refresh()

    # ----- panels ----------------------------------------------------------
    def _notify(self) -> None:
        """Tell the rest of the app about an edit made in this editor without
        rebuilding the editor under the cursor."""
        self._own = True
        try:
            self.session.panels_changed()
        finally:
            self._own = False

    def refresh(self) -> None:
        if getattr(self, "_own", False):
            return
        keep = self.panels.currentRow()
        self.panels.blockSignals(True)
        self.panels.clear()
        for p in self.session.project.panels:
            self.panels.addItem(p.name)
        self.panels.blockSignals(False)
        if self.session.project.panels:
            self.panels.setCurrentRow(min(max(0, keep), len(self.session.project.panels) - 1))
        self._panel_picked(self.panels.currentRow())

    def _panel_picked(self, row: int):
        ps = self.session.project.panels
        self._panel = ps[row] if 0 <= row < len(ps) else None
        self.del_panel.setEnabled(len(ps) > 1)
        self.columns.blockSignals(True)
        self.columns.setValue(self._panel.columns if self._panel else 4)
        self.columns.blockSignals(False)
        self._fill_buttons()

    def add_panel(self):
        name, ok = QInputDialog.getText(self, "Add panel", "Panel name:", text="Controls")
        if ok and name.strip():
            self.session.project.panels.append(Panel(name.strip(), 4, []))
            self.session.panels_changed()
            self.panels.setCurrentRow(len(self.session.project.panels) - 1)

    def rename_panel(self):
        if self._panel is None:
            return
        name, ok = QInputDialog.getText(self, "Rename panel", "Panel name:", text=self._panel.name)
        if ok and name.strip():
            self._panel.name = name.strip()
            self.session.panels_changed()

    def delete_panel(self):
        ps = self.session.project.panels
        if self._panel is not None and len(ps) > 1:
            ps.remove(self._panel)
            self.session.panels_changed()

    def _columns(self, v: int):
        if self._panel is not None:
            self._panel.columns = v
            self._notify()

    # ----- buttons ---------------------------------------------------------
    def _fill_buttons(self):
        keep = self.buttons.currentRow()
        self.buttons.blockSignals(True)
        self.buttons.clear()
        for b in (self._panel.buttons if self._panel else []):
            it = QListWidgetItem(f"{b.label}" + (f"    [{b.hotkey}]" if b.hotkey else ""))
            it.setToolTip(describe(b.action))
            self.buttons.addItem(it)
        self.buttons.blockSignals(False)
        n = self.buttons.count()
        if n:
            self.buttons.setCurrentRow(min(max(0, keep), n - 1))
        self._button_picked(self.buttons.currentRow())

    def _button_picked(self, row: int):
        bs = self._panel.buttons if self._panel else []
        self._button = bs[row] if 0 <= row < len(bs) else None
        self.editor_w.setEnabled(self._button is not None)
        self.del_button.setEnabled(self._button is not None)
        self._load_editor()

    def add_button(self):
        if self._panel is None:
            return
        self._panel.buttons.append(Button("New button", {"do": "add", "field": self._first_field(), "amount": 1}))
        self.session.panels_changed()
        self.buttons.setCurrentRow(len(self._panel.buttons) - 1)

    def _first_field(self) -> str:
        for k, f in self.session.engine.fields.items():
            if isinstance(f, CounterField):
                return k
        return next(iter(self.session.engine.fields), "")

    def duplicate_button(self):
        if self._button is None:
            return
        b = Button(self._button.label + " copy", copy.deepcopy(self._button.action), self._button.role, "")
        i = self._panel.buttons.index(self._button)
        self._panel.buttons.insert(i + 1, b)
        self.session.panels_changed()
        self.buttons.setCurrentRow(i + 1)

    def move_button(self, d: int):
        if self._button is None:
            return
        bs = self._panel.buttons
        i = bs.index(self._button)
        j = max(0, min(len(bs) - 1, i + d))
        if i != j:
            bs.insert(j, bs.pop(i))
            self.session.panels_changed()
            self.buttons.setCurrentRow(j)

    def delete_button(self):
        if self._button is not None:
            self._panel.buttons.remove(self._button)
            self.session.panels_changed()

    # ----- editor ----------------------------------------------------------
    def _load_editor(self):
        clear_layout(self.steps_lay)
        self.rows = []
        b = self._button
        self.e_label.setText(b.label if b else "")
        self.e_role.setCurrentIndex(max(0, self.e_role.findData(b.role if b else "neutral")))
        self.e_key.setKeySequence(QKeySequence(b.hotkey) if b and b.hotkey else QKeySequence())
        self._key_note()
        if b is None:
            return
        steps = b.action.get("actions", []) if b.action.get("do") == "batch" else [b.action]
        for st in steps:
            self._add_row(st)

    def _add_row(self, step: dict):
        row = StepRow(self, dict(step))
        self.rows.append(row)
        self.steps_lay.addWidget(row)

    def add_step(self):
        if self._button is None:
            return
        self._add_row({"do": "add", "field": self._first_field(), "amount": 1})
        self.steps_changed()

    def remove_step(self, row: StepRow):
        if len(self.rows) <= 1:
            self.session.message.emit("A button needs at least one step. Delete the button instead.", True)
            return
        self.rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self.steps_changed()

    def steps_changed(self):
        if self._button is None:
            return
        steps = [r.value() for r in self.rows]
        self._button.action = steps[0] if len(steps) == 1 else {"do": "batch", "actions": steps}
        self._refresh_list_item()
        self._notify()

    def _save_meta(self, *_):
        b = self._button
        if b is None:
            return
        b.label = self.e_label.text().strip() or "Button"
        b.role = self.e_role.currentData() or "neutral"
        seq = self.e_key.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        b.hotkey = normalise(seq)
        self._key_note()
        self._refresh_list_item()
        self._notify()

    def _clear_key(self):
        self.e_key.clear()
        self._save_meta()

    def _key_note(self):
        b = self._button
        if not b or not b.hotkey:
            self.key_note.setText("Shortcuts work on the Operate tab and in projector windows. "
                                  "While you type in a box, only Ctrl, Alt and F-key shortcuts fire.")
            return
        clash = [o.label for p in self.session.project.panels for o in p.buttons
                 if o is not b and normalise(o.hotkey) == normalise(b.hotkey)]
        text = f"Clashes with “{clash[0]}”: only the first button with this shortcut runs. " if clash else ""
        text += ("Can also work when TeleScore is in the background (Settings)." if is_global_safe(b.hotkey)
                 else "Works while TeleScore is the active window.")
        self.key_note.setText(text)

    def _refresh_list_item(self):
        row = self.buttons.currentRow()
        it = self.buttons.item(row)
        b = self._button
        if it is not None and b is not None:
            it.setText(f"{b.label}" + (f"    [{b.hotkey}]" if b.hotkey else ""))
            it.setToolTip(describe(b.action))

    def try_it(self):
        if self._button is not None:
            self.session.act(self._button.action)

    def _fields_changed(self):
        # Field lists inside the step rows may be stale.
        if self._button is not None:
            self._load_editor()
