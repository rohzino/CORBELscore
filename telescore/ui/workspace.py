"""
The three top tabs and the sections inside them.

    Operate   the scorekeeper's screen
    Design    Boards · Logic · Animations      (section switches across the top,
                                                so the canvas keeps its width)
    Setup     Fields · Live data · Buttons · Outputs   (section list down the left)

Pages are built once and kept; switching sections never rebuilds an editor.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton,
                             QStackedWidget, QVBoxLayout, QWidget)

from . import theme


class Sections(QWidget):
    """A stack of named pages with a switcher, either across the top
    (``side="top"``) or as a list down the left (``side="left"``)."""

    changed = pyqtSignal(str)                 # key of the section now shown

    def __init__(self, pages: List[Tuple[str, str, QWidget]], side: str = "top", parent=None):
        super().__init__(parent)
        self.keys: List[str] = [k for k, _t, _w in pages]
        self.pages: Dict[str, QWidget] = {k: w for k, _t, w in pages}
        self.stack = QStackedWidget()
        for _k, _t, w in pages:
            self.stack.addWidget(w)
        self._buttons: Dict[str, QPushButton] = {}
        self._list: Optional[QListWidget] = None

        if side == "left":
            root = QHBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)
            nav = QListWidget()
            nav.setProperty("sectionlist", True)
            nav.setFixedWidth(176)
            nav.setFont(theme.tfont("cell"))
            for _k, title, _w in pages:
                nav.addItem(QListWidgetItem(title))
            nav.currentRowChanged.connect(self._row)
            self._list = nav
            root.addWidget(nav)
            rule = QFrame()
            rule.setFixedWidth(1)
            rule.setProperty("vrule", True)
            root.addWidget(rule)
            root.addWidget(self.stack, 1)
        else:
            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)
            bar = QFrame()
            bar.setProperty("sectionbar", True)
            bl = QHBoxLayout(bar)
            bl.setContentsMargins(12, 4, 12, 0)
            bl.setSpacing(4)
            group = QButtonGroup(self)
            group.setExclusive(True)
            for key, title, _w in pages:
                b = QPushButton(title)
                b.setProperty("nav", True)
                b.setCheckable(True)
                b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
                b.clicked.connect(lambda _=False, k=key: self.show_section(k))
                group.addButton(b)
                bl.addWidget(b)
                self._buttons[key] = b
            bl.addStretch(1)
            root.addWidget(bar)
            root.addWidget(self.stack, 1)
        self.show_section(self.keys[0])

    def current(self) -> str:
        w = self.stack.currentWidget()
        return next((k for k, p in self.pages.items() if p is w), self.keys[0])

    def show_section(self, key: str) -> None:
        if key not in self.pages:
            return
        self.stack.setCurrentWidget(self.pages[key])
        if key in self._buttons:
            self._buttons[key].setChecked(True)
        if self._list is not None:
            row = self.keys.index(key)
            if self._list.currentRow() != row:
                self._list.blockSignals(True)
                self._list.setCurrentRow(row)
                self._list.blockSignals(False)
        self.changed.emit(key)

    def _row(self, row: int) -> None:
        if 0 <= row < len(self.keys):
            self.show_section(self.keys[row])
