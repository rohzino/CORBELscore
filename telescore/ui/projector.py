"""Projector windows: a board full screen on any display (LED wall, TV, projector)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QGuiApplication
from PyQt6.QtWidgets import QMenu, QVBoxLayout, QWidget

from .session import Session
from .widgets import BoardView


class ProjectorWindow(QWidget):
    def __init__(self, session: Session, board_id: str, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.session, self.board_id = session, board_id
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.view = BoardView(checker=False, letterbox="#000000")
        lay.addWidget(self.view)
        self.setStyleSheet("background:#000000;")
        self.resize(960, 540)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        session.snapshot.connect(self._values)
        session.board_edited.connect(self._edited)
        session.boards.connect(self._boards)
        self._boards()
        self.view.setValues(session.values(), None, session.fx())
        session.animations.connect(self._anims)

    def _boards(self):
        b = self.session.board(self.board_id)
        if b is None:
            self.close()
            return
        self.view.setBoard(b, self.session.project.animations)
        self.setWindowTitle(f"{b.name} · TeleScore projector")

    def _anims(self):
        self.view.setAnimations(self.session.project.animations)

    def _edited(self, bid: str):
        if bid == self.board_id:
            self.view.refresh_keys()

    def _values(self, snap, changed):
        self.view.setValues(snap.values, changed, snap.fx)

    def show_on(self, screen_index: int) -> None:
        screens = QGuiApplication.screens()
        if 0 <= screen_index < len(screens):
            g = screens[screen_index].geometry()
            self.showNormal()
            self.setGeometry(g)
            self.windowHandle() and self.windowHandle().setScreen(screens[screen_index])
            self.showFullScreen()

    def toggle_full(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_F11 or (ev.key() == Qt.Key.Key_Escape and self.isFullScreen()):
            self.toggle_full()
            return
        super().keyPressEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        self.toggle_full()

    def _menu(self, pos):
        m = QMenu(self)
        for i, s in enumerate(QGuiApplication.screens()):
            g = s.geometry()
            m.addAction(f"Full screen on {s.name() or 'display'} {i + 1}  ({g.width()} × {g.height()})",
                        lambda _=False, i=i: self.show_on(i))
        m.addSeparator()
        m.addAction("Windowed" if self.isFullScreen() else "Full screen here  (F11)").triggered.connect(
            lambda _=False: self.toggle_full())
        top = QAction("Always on top", m)
        top.setCheckable(True)
        top.setChecked(bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))

        def set_top(v):
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, v)
            self.show()
        top.toggled.connect(set_top)
        m.addAction(top)
        m.addSeparator()
        m.addAction("Close").triggered.connect(lambda _=False: self.close())
        m.exec(self.mapToGlobal(pos))
