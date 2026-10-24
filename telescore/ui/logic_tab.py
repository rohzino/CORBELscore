"""
Design → Logic: conditions, the SportzSuite way.

"If <field> <has value / changes by / ...> <value> then <element or field>
<show / hide / animate / conditional rule / set / ...>". Element actions
change graphics; field actions reach the text and XML outputs.
"""

from __future__ import annotations

import copy
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFontComboBox, QFormLayout, QHBoxLayout,
                             QLineEdit, QListWidget, QListWidgetItem, QScrollArea, QSpinBox, QSplitter,
                             QVBoxLayout, QWidget)

from ..core.animation import library
from ..core.logic import ELEMENT_ACTIONS, FIELD_ACTIONS, OPS, Condition
from .session import Session
from .widgets import ColorEdit, ConfirmButton, SectionTitle, StateChip, button, caps, clear_layout, label, panel

NO_VALUE_OPS = ("empty", "not_empty", "changes")
HELP = {
    "show": "Show the element. For a time, or until another condition hides it.",
    "show_once": "Show it only when the condition first becomes true, not again while it stays true.",
    "hide": "Hide the element. For a time, or until another condition shows it.",
    "color": "Text colour for text, fill for a box.",
    "fill": "Background fill.",
    "font": "Font family for text.",
    "image": "Swap the picture (an alternate picture).",
    "rule": "Rules that apply only while the condition holds, e.g. 1=Joe|2=John. A plain rule still wins.",
    "animate": "Play an animation. An 'out' animation hides the element at its end.",
    "set": "Set the field. This is not an undo step.",
    "pulse": "Switch an on/off field on for a while, then off. Good for 'flash this graphic' flags in XML.",
    "action": "Run what a button does, e.g. 'Next period' when the clock reaches 0:00.",
}


class LogicTab(QWidget):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        self._cur: Optional[Condition] = None
        self._loading = False
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 8, 0)
        ll.addWidget(SectionTitle("Conditions"))
        ll.addWidget(label("Checked whenever the field's value changes, like SportzSuite checking new bot data. "
                           "Use a converse pair (has value F → show; does not have value F → hide) for both states.",
                           "small", muted=True, wrap=True))
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._picked)
        self.list.itemChanged.connect(self._toggled)
        ll.addWidget(self.list, 1)
        r = QHBoxLayout()
        r.addWidget(button("Add condition", "accent", self.add))
        r.addWidget(button("Duplicate", "", self.duplicate))
        r.addWidget(button("Up", "", lambda: self.move(-1)))
        r.addWidget(button("Down", "", lambda: self.move(1)))
        self.b_del = ConfirmButton("Delete")
        self.b_del.confirmed.connect(self.delete)
        r.addWidget(self.b_del)
        ll.addLayout(r)
        split.addWidget(left)

        self.editor_host = QWidget()
        self.editor = QVBoxLayout(self.editor_host)
        self.editor.setContentsMargins(8, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.editor_host)
        split.addWidget(scroll)
        split.setSizes([460, 620])

        session.logic.connect(self.refresh)
        session.structure.connect(self._rebuild_editor)
        session.boards.connect(self._rebuild_editor)
        session.snapshot.connect(self._truth)
        self.refresh()

    # ----- list ---------------------------------------------------------------
    @property
    def conds(self) -> List[Condition]:
        return self.session.engine.logic.conditions

    def _labels(self):
        out = {}
        for b in self.session.project.boards:
            for e in b.elements:
                out[e.id] = f"{b.name} › {e.name or e.kind}"
        return out

    def refresh(self) -> None:
        if getattr(self, "_own", False):
            return
        keep = self.list.currentRow()
        labels = self._labels()
        self.list.blockSignals(True)
        self.list.clear()
        for c in self.conds:
            it = QListWidgetItem(c.describe(labels))
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if c.enabled else Qt.CheckState.Unchecked)
            it.setToolTip(c.note or c.describe(labels))
            self.list.addItem(it)
        self.list.blockSignals(False)
        if self.conds:
            self.list.setCurrentRow(min(max(0, keep), len(self.conds) - 1))
        self._picked(self.list.currentRow())

    def _picked(self, row: int):
        self._cur = self.conds[row] if 0 <= row < len(self.conds) else None
        self.b_del.setEnabled(self._cur is not None)
        self._rebuild_editor()

    def _toggled(self, it: QListWidgetItem):
        row = self.list.row(it)
        if 0 <= row < len(self.conds):
            self.conds[row].enabled = it.checkState() == Qt.CheckState.Checked
            self._commit(rebuild_list=False)

    def _commit(self, rebuild_list: bool = True) -> None:
        """Push edits to the engine without rebuilding the editor under the cursor."""
        self._own = True
        try:
            self.session.conditions_changed()
        finally:
            self._own = False
        if rebuild_list:
            row = self.list.currentRow()
            it = self.list.item(row)
            if it is not None and self._cur is not None:
                it.setText(self._cur.describe(self._labels()))

    def add(self):
        keys = list(self.session.engine.fields)
        c = Condition(principal=keys[0] if keys else "", op="equals", value="", target_kind="element",
                      target="", action="show", arg="*")
        self.conds.append(c)
        self.session.conditions_changed()
        self.list.setCurrentRow(len(self.conds) - 1)

    def duplicate(self):
        if self._cur is None:
            return
        c = copy.deepcopy(self._cur)
        import uuid
        c.id = uuid.uuid4().hex[:10]
        i = self.conds.index(self._cur)
        self.conds.insert(i + 1, c)
        self.session.conditions_changed()
        self.list.setCurrentRow(i + 1)

    def move(self, d: int):
        if self._cur is None:
            return
        i = self.conds.index(self._cur)
        j = max(0, min(len(self.conds) - 1, i + d))
        if i != j:
            self.conds.insert(j, self.conds.pop(i))
            self.session.conditions_changed()
            self.list.setCurrentRow(j)

    def delete(self):
        if self._cur is not None:
            self.conds.remove(self._cur)
            self.session.conditions_changed()

    def _truth(self, snap, changed):
        c = self._cur
        if c is None or not hasattr(self, "state"):
            return
        t = self.session.engine.logic.truth.get(c.id)
        if t is None:
            self.state.set("NOT CHECKED YET", "muted")
        else:
            self.state.set("TRUE" if t else "FALSE", "accent" if t else "muted")

    # ----- editor -------------------------------------------------------------
    def _rebuild_editor(self):
        clear_layout(self.editor)
        c = self._cur
        if c is None:
            self.editor.addWidget(label("Add a condition to make graphics and outputs react to the score: "
                                        "flash a goal graphic, show FINAL at 0:00, swap a sponsor each inning.",
                                        "body", muted=True, wrap=True))
            self.editor.addStretch(1)
            return
        self._loading = True
        head = QHBoxLayout()
        head.addWidget(label("Condition", "dialog-title"))
        head.addStretch(1)
        self.state = StateChip("", "muted")
        head.addWidget(self.state)
        self.editor.addLayout(head)
        self._truth(None, set())

        # IF ----------------------------------------------------------------------
        box, bl = panel()
        bl.addWidget(caps("If"))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        principal = QComboBox()
        principal.setEditable(True)
        for k in self.session.values():
            principal.addItem(k)
        principal.setCurrentText(c.principal)
        principal.setToolTip("Any published value, sub-keys included (clock.game.running, home.penalties.1.time)")
        principal.lineEdit().editingFinished.connect(lambda: self._set("principal", principal.currentText().strip()))
        principal.activated.connect(lambda _: self._set("principal", principal.currentText().strip()))
        form.addRow(caps("Field"), principal)
        op = QComboBox()
        for k, name in OPS.items():
            op.addItem(name, k)
        op.setCurrentIndex(max(0, op.findData(c.op)))
        form.addRow(caps("Test"), op)
        value = QLineEdit(c.value)
        value.setPlaceholderText("value · NULL means empty · times like 2:00 compare as time")
        value.editingFinished.connect(lambda: self._set("value", value.text()))
        value.setVisible(c.op not in NO_VALUE_OPS)
        form.addRow(caps("Value"), value)

        def op_changed(_):
            self._set("op", op.currentData())
            value.setVisible(op.currentData() not in NO_VALUE_OPS)
        op.activated.connect(op_changed)
        bl.addLayout(form)
        self.editor.addWidget(box)

        # THEN --------------------------------------------------------------------
        box, bl = panel()
        bl.addWidget(caps("Then"))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        kind = QComboBox()
        kind.addItem("An element on a board", "element")
        kind.addItem("A field (reaches .txt and .xml)", "field")
        kind.setCurrentIndex(0 if c.target_kind == "element" else 1)

        def kind_changed(_):
            new = kind.currentData()
            if new != c.target_kind:
                c.target_kind = new
                c.target = ""
                c.action = "show" if new == "element" else "rule"
                c.arg = "*" if new == "element" else ""
                self._commit()
                self._rebuild_editor()
        kind.activated.connect(kind_changed)
        form.addRow(caps("Target"), kind)
        target = QComboBox()
        if c.target_kind == "element":
            for b in self.session.project.boards:
                for e in reversed(b.elements):
                    target.addItem(f"{b.name} › {e.name or e.kind}", e.id)
        else:
            for k in self.session.engine.fields:
                target.addItem(k, k)
        i = target.findData(c.target)
        if i < 0 and c.target:
            target.addItem(f"{c.target} (missing)", c.target)
            i = target.count() - 1
        if i < 0 and target.count() and c.action != "action":
            i = 0
            c.target = target.itemData(0)
        target.setCurrentIndex(max(0, i))
        target.activated.connect(lambda _: self._set("target", target.currentData()))
        form.addRow(caps(""), target)
        target.setVisible(not (c.target_kind == "field" and c.action == "action"))
        action = QComboBox()
        acts = ELEMENT_ACTIONS if c.target_kind == "element" else FIELD_ACTIONS
        for k, name in acts.items():
            action.addItem(name, k)
        action.setCurrentIndex(max(0, action.findData(c.action)))

        def action_changed(_):
            c.action = action.currentData()
            c.arg = {"show": "*", "hide": "*", "show_once": "3000", "pulse": "2000", "animate": "Fade in"}.get(
                c.action, "")
            self._commit()
            self._rebuild_editor()
        action.activated.connect(action_changed)
        form.addRow(caps("Do"), action)
        form.addRow(caps(""), self._arg_widget(c))
        bl.addLayout(form)
        bl.addWidget(label(HELP.get(c.action, ""), "small", muted=True, wrap=True))
        self.editor.addWidget(box)

        # FINISH ------------------------------------------------------------------
        box, bl = panel()
        on = QCheckBox("Afterwards, do something else")
        on.setChecked(bool(c.finish_ms and c.finish))
        bl.addWidget(on)
        row = QHBoxLayout()
        ms = QSpinBox()
        ms.setRange(0, 3_600_000)
        ms.setSingleStep(500)
        ms.setSuffix(" ms later")
        ms.setValue(c.finish_ms or 4000)
        fin = QComboBox()
        fin.setEditable(True)
        if c.target_kind == "element":
            fin.addItems(["hide", "show"] + [f"animate:{n}" for n in library(self.session.project.animations)])
        else:
            fin.addItems(["set:", "set:0", "set:1"])
        fin.setCurrentText(c.finish or ("hide" if c.target_kind == "element" else "set:"))
        row.addWidget(ms)
        row.addWidget(fin, 1)
        bl.addLayout(row)
        bl.addWidget(label("Like SportzSuite's finish animations: e.g. tween out, then 4000 ms later tween back in.",
                           "small", muted=True, wrap=True))

        def fin_changed(*_):
            if on.isChecked():
                c.finish_ms, c.finish = ms.value(), fin.currentText().strip()
            else:
                c.finish_ms, c.finish = 0, ""
            ms.setEnabled(on.isChecked())
            fin.setEnabled(on.isChecked())
            self._commit()
        on.toggled.connect(fin_changed)
        ms.valueChanged.connect(fin_changed)
        fin.activated.connect(fin_changed)
        fin.lineEdit().editingFinished.connect(fin_changed)
        ms.setEnabled(on.isChecked())
        fin.setEnabled(on.isChecked())
        self.editor.addWidget(box)

        note = QLineEdit(c.note)
        note.setPlaceholderText("Note (optional), e.g. 'goal flash'")
        note.editingFinished.connect(lambda: self._set("note", note.text()))
        self.editor.addWidget(note)
        self.editor.addStretch(1)
        self._loading = False

    def _arg_widget(self, c: Condition) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        a = c.action
        if a in ("show", "hide", "show_once", "pulse"):
            sp = QSpinBox()
            sp.setRange(0, 3_600_000)
            sp.setSingleStep(500)
            sp.setSuffix(" ms")
            forever = QCheckBox("Until changed (*)")
            is_star = c.arg.strip() in ("", "*")
            forever.setChecked(is_star and a != "pulse")
            forever.setVisible(a != "pulse")
            try:
                sp.setValue(int(float(c.arg)))
            except ValueError:
                sp.setValue(5000)
            sp.setEnabled(not forever.isChecked())

            def upd(*_):
                sp.setEnabled(not forever.isChecked())
                self._set("arg", "*" if forever.isChecked() else str(sp.value()))
            sp.valueChanged.connect(upd)
            forever.toggled.connect(upd)
            lay.addWidget(sp)
            lay.addWidget(forever)
        elif a in ("color", "fill"):
            ce = ColorEdit()
            ce.setValues(self.session.values())
            ce.setValue(c.arg)
            ce.changed.connect(lambda v: self._set("arg", v))
            lay.addWidget(ce)
        elif a == "font":
            fc = QFontComboBox()
            fc.setCurrentFont(QFont(c.arg or "Archivo"))
            fc.currentFontChanged.connect(lambda f: self._set("arg", f.family()))
            lay.addWidget(fc)
        elif a == "image":
            e = QLineEdit(c.arg)
            e.setPlaceholderText("Picture file, or a field like {home.logo}")
            e.editingFinished.connect(lambda: self._set("arg", e.text().strip()))

            def browse():
                path, _ = QFileDialog.getOpenFileName(self, "Alternate picture", "",
                                                      "Pictures (*.png *.jpg *.jpeg *.gif *.webp *.svg *.bmp)")
                if path:
                    e.setText(path)
                    self._set("arg", path)
            lay.addWidget(e, 1)
            lay.addWidget(button("Browse…", "", browse))
        elif a == "animate":
            cb = QComboBox()
            for name, an in library(self.session.project.animations).items():
                cb.addItem(f"{name}  ({an.kind})", name)
            cb.setCurrentIndex(max(0, cb.findData(c.arg)))
            cb.activated.connect(lambda _: self._set("arg", cb.currentData()))
            lay.addWidget(cb, 1)
        elif a == "action":
            cb = QComboBox()
            cb.addItem("Choose a button…", None)
            for p in self.session.project.panels:
                for b in p.buttons:
                    cb.addItem(f"{p.name} › {b.label}", b.action)
            for i in range(1, cb.count()):
                if cb.itemData(i) == c.run:
                    cb.setCurrentIndex(i)
            cb.activated.connect(lambda _: cb.currentData() and self._set("run", copy.deepcopy(cb.currentData())))
            lay.addWidget(cb, 1)
        else:   # rule, set
            e = QLineEdit(c.arg)
            e.setPlaceholderText("1=Joe|2=John|3=Bob" if a == "rule" else "value")
            e.editingFinished.connect(lambda: self._set("arg", e.text()))
            lay.addWidget(e, 1)
        return w

    def _set(self, attr: str, value) -> None:
        if self._loading or self._cur is None:
            return
        if getattr(self._cur, attr) == value:
            return
        setattr(self._cur, attr, value)
        self._commit()
