"""Design → Animations: start from a built-in, change the move, preview it."""

from __future__ import annotations

import copy
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLineEdit, QListWidget,
                             QListWidgetItem, QSpinBox, QVBoxLayout, QWidget)

from ..core.animation import EASINGS, Animation, library
from ..core.board import Board, Element
from .session import Session
from .widgets import BoardView, ConfirmButton, button, caps, label, panel

KINDS = [("in", "In: the element appears"), ("out", "Out: the element disappears"),
         ("emphasis", "Emphasis: plays, then returns")]
WIPES = [("", "None"), ("left", "From/to the left"), ("right", "From/to the right"), ("up", "Upward"),
         ("down", "Downward")]


class AnimationsPage(QWidget):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        self._cur: Optional[Animation] = None
        self._loading = False
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(14)

        left = QVBoxLayout()
        left.addWidget(caps("Animations"))
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._picked)
        left.addWidget(self.list, 1)
        r = QHBoxLayout()
        r.addWidget(button("New", "accent", self.new))
        r.addWidget(button("Copy", "", self.copy_current, tip="Make an editable copy, e.g. of a built-in"))
        self.b_del = ConfirmButton("Delete")
        self.b_del.confirmed.connect(self.delete)
        r.addWidget(self.b_del)
        left.addLayout(r)
        root.addLayout(left, 2)

        right = QVBoxLayout()
        box, bl = panel()
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.name = QLineEdit()
        self.name.editingFinished.connect(self._rename)
        self.kind = QComboBox()
        for k, t in KINDS:
            self.kind.addItem(t, k)
        self.duration = QSpinBox()
        self.duration.setRange(1, 20_000)
        self.duration.setSuffix(" ms")
        self.delay = QSpinBox()
        self.delay.setRange(0, 20_000)
        self.delay.setSuffix(" ms")
        self.easing = QComboBox()
        for e in EASINGS:
            self.easing.addItem(e, e)
        self.opacity = QSpinBox()
        self.opacity.setRange(0, 100)
        self.opacity.setSuffix(" %")
        self.sp_x = QDoubleSpinBox()
        self.sp_y = QDoubleSpinBox()
        for sp in (self.sp_x, self.sp_y):
            sp.setRange(-4000, 4000)
            sp.setSuffix(" px")
            sp.setDecimals(0)
        self.scale = QSpinBox()
        self.scale.setRange(1, 1000)
        self.scale.setSuffix(" %")
        self.wipe = QComboBox()
        for k, t in WIPES:
            self.wipe.addItem(t, k)
        self.repeat = QSpinBox()
        self.repeat.setRange(1, 50)
        self.repeat.setSuffix(" times")
        form.addRow(caps("Name"), self.name)
        form.addRow(caps("Type"), self.kind)
        form.addRow(caps("Duration"), self.duration)
        form.addRow(caps("Delay"), self.delay)
        form.addRow(caps("Easing"), self.easing)
        form.addRow(caps("Opacity"), self.opacity)
        xy = QHBoxLayout()
        xy.addWidget(self.sp_x)
        xy.addWidget(self.sp_y)
        form.addRow(caps("Offset X  Y"), xy)
        form.addRow(caps("Scale"), self.scale)
        form.addRow(caps("Wipe"), self.wipe)
        form.addRow(caps("Repeat"), self.repeat)
        bl.addLayout(form)
        self.explain = label("", "small", muted=True, wrap=True)
        bl.addWidget(self.explain)
        for w in (self.duration, self.delay, self.opacity, self.scale, self.repeat):
            w.valueChanged.connect(self._edited)
        for w in (self.sp_x, self.sp_y):
            w.valueChanged.connect(self._edited)
        for w in (self.kind, self.easing, self.wipe):
            w.activated.connect(self._edited)
        right.addWidget(box)

        pv, pl = panel(pad=10)
        top = QHBoxLayout()
        top.addWidget(caps("Preview"))
        top.addStretch(1)
        top.addWidget(button("Play", "accent", self.play))
        pl.addLayout(top)
        self.sample = Element(id="sample", kind="text", text="HOME 3", x=180, y=95, w=280, h=90, fill="#0a0f0df2",
                              color="#e8f1ec", size=46, weight=900, radius=3)
        self.board = Board(name="Preview", width=640, height=280, background="#18211e", elements=[self.sample])
        self.view = BoardView(checker=False)
        self.view.setMinimumHeight(200)
        pl.addWidget(self.view, 1)
        right.addWidget(pv, 1)
        root.addLayout(right, 3)
        self._fill()

    # ----- list ---------------------------------------------------------------
    @property
    def custom(self):
        return self.session.project.animations

    def _fill(self, select: Optional[str] = None):
        lib = library(self.custom)
        self.list.blockSignals(True)
        self.list.clear()
        for name, a in lib.items():
            it = QListWidgetItem(f"{name}" + ("" if not a.builtin else "   · built in"))
            it.setData(Qt.ItemDataRole.UserRole, name)
            self.list.addItem(it)
        self.list.blockSignals(False)
        row = 0
        if select:
            for i in range(self.list.count()):
                if self.list.item(i).data(Qt.ItemDataRole.UserRole) == select:
                    row = i
        self.list.setCurrentRow(row)
        self._picked(row)

    def _picked(self, row: int):
        it = self.list.item(row)
        name = it.data(Qt.ItemDataRole.UserRole) if it else None
        self._cur = library(self.custom).get(name) if name else None
        self._load()

    def _load(self):
        a = self._cur
        self._loading = True
        editable = a is not None and not a.builtin
        for w in (self.name, self.kind, self.duration, self.delay, self.easing, self.opacity, self.sp_x, self.sp_y,
                  self.scale, self.wipe, self.repeat):
            w.setEnabled(editable)
        self.b_del.setEnabled(editable)
        if a is not None:
            self.name.setText(a.name)
            self.kind.setCurrentIndex(max(0, self.kind.findData(a.kind)))
            self.duration.setValue(a.duration)
            self.delay.setValue(a.delay)
            self.easing.setCurrentIndex(max(0, self.easing.findData(a.easing)))
            self.opacity.setValue(round(a.opacity * 100))
            self.sp_x.setValue(a.x)
            self.sp_y.setValue(a.y)
            self.scale.setValue(round(a.scale * 100))
            self.wipe.setCurrentIndex(max(0, self.wipe.findData(a.wipe)))
            self.repeat.setValue(a.repeat)
            self.repeat.setEnabled(editable and a.kind == "emphasis")
            self.explain.setText(self._explain(a) + ("" if editable else "  Built in: copy it to change it."))
        self._loading = False
        self.play()

    @staticmethod
    def _explain(a: Animation) -> str:
        parts = []
        if a.opacity != 1:
            parts.append(f"opacity {round(a.opacity * 100)}%")
        if a.x or a.y:
            parts.append(f"offset {a.x:+.0f}, {a.y:+.0f} px")
        if a.scale != 1:
            parts.append(f"scale {round(a.scale * 100)}%")
        if a.wipe:
            parts.append(f"wipe {a.wipe}")
        look = ", ".join(parts) or "no change"
        if a.kind == "in":
            return f"Starts at {look} and moves to normal in {a.duration} ms."
        if a.kind == "out":
            return f"Moves from normal to {look} in {a.duration} ms, then hides."
        return f"Goes to {look} and back, {a.repeat} time(s), {a.duration} ms each."

    # ----- edits ----------------------------------------------------------------
    def _edited(self, *_):
        a = self._cur
        if self._loading or a is None or a.builtin:
            return
        a.kind = self.kind.currentData()
        a.duration = self.duration.value()
        a.delay = self.delay.value()
        a.easing = self.easing.currentData()
        a.opacity = self.opacity.value() / 100
        a.x, a.y = self.sp_x.value(), self.sp_y.value()
        a.scale = self.scale.value() / 100
        a.wipe = self.wipe.currentData()
        a.repeat = self.repeat.value()
        self.repeat.setEnabled(a.kind == "emphasis")
        self.explain.setText(self._explain(a))
        self.session.animations_changed()
        self.play()

    def _unique(self, base: str) -> str:
        names = set(library(self.custom))
        name, n = base, 2
        while name in names:
            name = f"{base} {n}"
            n += 1
        return name

    def _rename(self):
        a = self._cur
        if a is None or a.builtin:
            return
        new = self.name.text().strip()
        if not new or new == a.name:
            self.name.setText(a.name)
            return
        if new in library(self.custom):
            self.session.message.emit(f"An animation called {new!r} already exists.", True)
            self.name.setText(a.name)
            return
        old = a.name
        a.name = new
        # Elements and conditions that used the old name follow the new one.
        for b in self.session.project.boards:
            for e in b.elements:
                for prop in ("anim_in", "anim_out", "anim_change"):
                    if getattr(e, prop) == old:
                        setattr(e, prop, new)
        for c in self.session.engine.logic.conditions:
            if c.action == "animate" and c.arg == old:
                c.arg = new
            if c.finish == f"animate:{old}":
                c.finish = f"animate:{new}"
        self.session.animations_changed()
        self.session.boards_changed()
        self._fill(new)

    def new(self):
        a = Animation(name=self._unique("My animation"), kind="in", duration=400, x=-120, opacity=0.0)
        self.custom.append(a)
        self.session.animations_changed()
        self._fill(a.name)

    def copy_current(self):
        if self._cur is None:
            return
        a = copy.deepcopy(self._cur)
        a.builtin = False
        a.name = self._unique(self._cur.name + " copy")
        self.custom.append(a)
        self.session.animations_changed()
        self._fill(a.name)

    def delete(self):
        a = self._cur
        if a is None or a.builtin:
            return
        self.custom.remove(a)
        self.session.animations_changed()
        self._fill()

    def play(self):
        if self._cur is None:
            return
        self.view.setBoard(self.board, self.custom)
        self.view.setValues({}, None, {})
        QTimer.singleShot(0, lambda: self.view.play("sample", self._cur.name) if self._cur else None)


    def show_animation(self, name: str) -> None:
        """Select one animation by name (used when the builder asks for it)."""
        self._fill(name)
