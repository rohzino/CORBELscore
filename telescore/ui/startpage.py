"""The first screen: templates, open, and recent projects."""

from __future__ import annotations

import datetime as _dt
import os
from typing import List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from ..core.presets import PRESETS
from .widgets import SectionTitle, button, caps, label, panel

BLURBS = {
    "Blank project": "Nothing yet. Build your own fields and board.",
    "General scoreboard": "Two teams, a clock and a period.",
    "Basketball": "Game and shot clocks, quarters, fouls, time-outs, bonus.",
    "Hockey": "20-minute periods, shots, penalties that follow the clock.",
    "Soccer": "Running match clock, halves, added time.",
    "Football": "Game and play clocks, down and distance, time-outs.",
    "Volleyball": "Points, sets and serve.",
    "Baseball": "Inning, count, outs and runners.",
}


class StartPage(QWidget):
    new_project = pyqtSignal(str)       # preset name
    open_file = pyqtSignal(str)         # path ("" = ask)

    def __init__(self, recent: List[str], parent=None):
        super().__init__(parent)
        root = QHBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(28)

        left = QVBoxLayout()
        left.addWidget(SectionTitle("New project"))
        left.addWidget(label("Start from a sport. Every field, board and button can be changed afterwards.",
                             "body", muted=True, wrap=True))
        grid = QGridLayout()
        grid.setSpacing(10)
        for i, name in enumerate(PRESETS):
            card, cl = panel(pad=14, spacing=4)
            card.setMinimumWidth(220)
            t = label(name, "title")
            cl.addWidget(t)
            cl.addWidget(label(BLURBS.get(name, ""), "small", muted=True, wrap=True))
            b = button("Start", "accent" if name == "General scoreboard" else "", lambda n=name: self.new_project.emit(n))
            cl.addWidget(b, 0, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(card, i // 3, i % 3)
        left.addLayout(grid)
        left.addStretch(1)
        root.addLayout(left, 3)

        right = QVBoxLayout()
        right.addWidget(SectionTitle("Open"))
        right.addWidget(button("Open a project…", "", lambda: self.open_file.emit(""),
                               tip="TeleScore 2 projects (.tsproj) and 1.x projects (.json)"))
        right.addWidget(label("TeleScore 1.x projects open too: they are converted, and the original file is "
                              "left as it is.", "small", muted=True, wrap=True))
        right.addSpacing(12)
        right.addWidget(caps("Recent"))
        self.recent = QListWidget()
        for path in recent:
            if not os.path.isfile(path):
                continue
            when = _dt.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d %b %Y, %H:%M")
            it = QListWidgetItem(f"{os.path.splitext(os.path.basename(path))[0]}\n{when} · {os.path.dirname(path)}")
            it.setData(Qt.ItemDataRole.UserRole, path)
            it.setToolTip(path)
            self.recent.addItem(it)
        if self.recent.count() == 0:
            it = QListWidgetItem("Projects you open appear here.")
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recent.addItem(it)
        self.recent.itemActivated.connect(lambda it: it.data(Qt.ItemDataRole.UserRole) and
                                          self.open_file.emit(it.data(Qt.ItemDataRole.UserRole)))
        right.addWidget(self.recent, 1)
        root.addLayout(right, 2)
