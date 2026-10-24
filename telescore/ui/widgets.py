"""Small house-style widgets shared by every tab."""

from __future__ import annotations

import time

from typing import Callable, List, Mapping, Optional

from PyQt6.QtCore import QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (QColorDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QSizePolicy, QVBoxLayout, QWidget)

from ..core.board import Board, resolve_color
from . import theme
from .render import ImageCache, paint_board, qcolor


def panel(parent: Optional[QWidget] = None, pad: int = 12, spacing: int = 8, vertical: bool = True):
    """A flat panel (``panel`` fill, 1px ``rule`` border, 6px corners).
    Returns (frame, layout)."""
    f = QFrame(parent)
    f.setProperty("panel", True)
    lay = QVBoxLayout(f) if vertical else QHBoxLayout(f)
    lay.setContentsMargins(pad, pad, pad, pad)
    lay.setSpacing(spacing)
    return f, lay


def label(text: str = "", style: str = "body", muted: bool = False, parent=None, wrap: bool = False) -> QLabel:
    lb = QLabel(text, parent)
    lb.setFont(theme.tfont(style))
    if muted:
        lb.setProperty("muted", True)
    lb.setWordWrap(wrap)
    return lb


class SectionTitle(QLabel):
    """900-weight capitals with the 4px ``hi`` underline (Keystone dialog title)."""

    def __init__(self, text: str, style: str = "dialog-title", underline: bool = True, parent=None):
        super().__init__(text, parent)
        self.setFont(theme.tfont(style))
        self._underline = underline
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setContentsMargins(0, 0, 0, 6 if underline else 0)

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if self._underline:
            p = QPainter(self)
            p.fillRect(0, self.height() - 4, self.width(), 4, QColor(theme.CURRENT["hi"]))
            p.end()


def caps(text: str, parent=None) -> QLabel:
    """The small ``label`` caption in ``muted``: field captions, column heads."""
    return label(text, "label", muted=True, parent=parent)


class StatusDot(QWidget):
    """An 8-10px status light: live (hi), busy (user, blinks), error (alert), off (rule)."""

    def __init__(self, state: str = "off", size: int = 10, parent=None):
        super().__init__(parent)
        self._state = state
        self._on = True
        self.setFixedSize(size, size)
        self._blink = QTimer(self)
        self._blink.setInterval(500)
        self._blink.timeout.connect(self._toggle)

    def setState(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        self._on = True
        if state == "busy":
            self._blink.start()
        else:
            self._blink.stop()
        self.update()

    def _toggle(self):
        self._on = not self._on
        self.update()

    def paintEvent(self, ev):
        c = theme.CURRENT
        col = {"ok": c["hi"], "live": c["hi"], "busy": c["user"], "error": c["alert"]}.get(self._state, c["rule-strong"])
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        color = QColor(col)
        if not self._on:
            color.setAlpha(70)
        p.setBrush(color)
        p.drawEllipse(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1))
        p.end()


class StateChip(QLabel):
    """A status is a colour *and* a word (Rally): RUNNING, STOPPED, LIVE, OFF."""

    STYLES = {
        "accent": ("accent", "accent-ink"), "alert": ("alert", "alert-ink"), "user": ("user", "user-ink"),
        "hi": ("hi", "hi-ink"), "muted": ("field", "muted"),
    }

    def __init__(self, text: str = "", kind: str = "muted", parent=None):
        super().__init__(text, parent)
        self.setFont(theme.tfont("label"))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setContentsMargins(8, 2, 8, 2)
        self.set(text, kind)

    def set(self, text: str, kind: str) -> None:
        self.setText(text)
        bg, fg = self.STYLES.get(kind, self.STYLES["muted"])
        c = theme.CURRENT
        border = c["rule-strong"] if kind == "muted" else c[bg]
        self.setStyleSheet(f"background:{c[bg]}; color:{c[fg]}; border:1px solid {border}; border-radius:3px;")


class ConfirmButton(QPushButton):
    """Destructive actions ask twice by changing their own label (Keystone):
    the first press reads "Press again to delete", the second acts."""

    confirmed = pyqtSignal()

    def __init__(self, text: str, confirm_text: str = "Press again to delete", parent=None):
        super().__init__(text, parent)
        self._text, self._confirm = text, confirm_text
        self._armed = False
        self.setProperty("role", "alert")
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self._disarm)
        self.clicked.connect(self._click)

    def _click(self):
        if self._armed:
            self._disarm()
            self.confirmed.emit()
        else:
            self._armed = True
            self.setText(self._confirm)
            self.setProperty("role", "danger")
            theme.repolish(self)
            self._timer.start()

    def _disarm(self):
        self._armed = False
        self._timer.stop()
        self.setText(self._text)
        self.setProperty("role", "alert")
        theme.repolish(self)


def button(text: str, role: str = "", slot: Optional[Callable] = None, tip: str = "", big: bool = False,
           checkable: bool = False, parent=None) -> QPushButton:
    b = QPushButton(text, parent)
    if role:
        b.setProperty("role", role)
    if big:
        b.setProperty("big", True)
    if tip:
        b.setToolTip(tip)
    b.setCheckable(checkable)
    if slot is not None:
        b.clicked.connect(lambda _=False: slot())
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


class Swatch(QPushButton):
    """A colour well; clicking opens the picker."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(QSize(30, 26))
        self._color = ""
        self.setToolTip("Pick a colour")

    def setColor(self, hexstr: str) -> None:
        self._color = hexstr
        self.update()

    def paintEvent(self, ev):
        super().paintEvent(ev)
        p = QPainter(self)
        r = QRectF(6, 5, self.width() - 12, self.height() - 10)
        col = qcolor(self._color)
        if col is None:
            p.setPen(QPen(QColor(theme.CURRENT["muted"]), 1))
            p.drawRect(r)
            p.drawLine(r.bottomLeft(), r.topRight())
        else:
            p.fillRect(r, col)
            p.setPen(QPen(QColor(theme.CURRENT["rule-strong"]), 1))
            p.drawRect(r)
        p.end()


class ColorEdit(QWidget):
    """A colour property: a swatch plus text that takes #rrggbb, #rrggbbaa,
    a field template such as {home.color}, or nothing (no paint)."""

    changed = pyqtSignal(str)

    def __init__(self, allow_empty: bool = True, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.swatch = Swatch()
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("none" if allow_empty else "#rrggbb")
        self.edit.setToolTip("#rrggbb, #rrggbbaa (with transparency), or a field such as {home.color}")
        lay.addWidget(self.swatch)
        lay.addWidget(self.edit, 1)
        self.swatch.clicked.connect(self._pick)
        self.edit.editingFinished.connect(self._typed)
        self._values: Mapping[str, str] = {}

    def setValues(self, values: Mapping[str, str]) -> None:
        self._values = values
        self.swatch.setColor(resolve_color(self.edit.text(), values))

    def value(self) -> str:
        return self.edit.text().strip()

    def setValue(self, v: str) -> None:
        self.edit.setText(v or "")
        self.swatch.setColor(resolve_color(v or "", self._values))

    def _typed(self):
        v = self.value()
        ok = (not v) or "{" in v or bool(resolve_color(v, {}))
        self.edit.setProperty("error", not ok)
        theme.repolish(self.edit)
        if ok:
            self.swatch.setColor(resolve_color(v, self._values))
            self.changed.emit(v)

    def _pick(self):
        start = qcolor(resolve_color(self.value(), self._values)) or QColor("#ffffff")
        col = QColorDialog.getColor(start, self, "Pick a colour", QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if col.isValid():
            v = "#%02x%02x%02x" % (col.red(), col.green(), col.blue())
            if col.alpha() < 255:
                v += "%02x" % col.alpha()
            self.setValue(v)
            self.changed.emit(v)


class Kbd(QLabel):
    """A keyboard shortcut set as it is printed on the key."""

    def __init__(self, keys: str, parent=None):
        super().__init__(keys, parent)
        self.setFont(theme.font(11, 700))
        c = theme.CURRENT
        self.setStyleSheet(f"background:{c['field']}; color:{c['muted']}; border:1px solid {c['rule-strong']};"
                           f"border-radius:3px; padding:0 4px;")


class BoardView(QWidget):
    """Paints a board scaled to fit, with live values, condition effects and
    animations (the same rules as the browser source)."""

    def __init__(self, parent=None, checker: bool = True, letterbox: Optional[str] = None):
        super().__init__(parent)
        from ..core.animation import Tracker
        self.board: Optional[Board] = None
        self.values: Mapping[str, str] = {}
        self.fx: Mapping[str, Mapping] = {}
        self.images = ImageCache()
        self.checker = checker
        self.letterbox = letterbox
        self.tracker = Tracker()
        self.animations: list = []
        self.setMinimumSize(160, 90)
        self._keys: set = set()
        self._frame = QTimer(self)
        self._frame.setInterval(16)
        self._frame.timeout.connect(self._tick)

    def setBoard(self, board: Optional[Board], animations: Optional[list] = None) -> None:
        if animations is not None:
            self.animations = animations
        self.board = board
        self.tracker.set_board(board, self.animations)
        self._keys = set(board.keys()) if board else set()
        self.tracker.update(self.values, self.fx, time.monotonic(), animate=False)
        self.update()

    def setAnimations(self, animations: list) -> None:
        self.animations = animations
        self.tracker.set_board(self.board, animations)

    def setValues(self, values: Mapping[str, str], changed: Optional[set] = None,
                  fx: Optional[Mapping[str, Mapping]] = None) -> None:
        self.values = values
        if fx is not None:
            self.fx = fx
        self.tracker.update(self.values, self.fx, time.monotonic())
        if self.tracker.active(time.monotonic()) and not self._frame.isActive():
            self._frame.start()
        if changed is None or self.board is None or changed & self._keys or "#fx" in changed or not self._keys:
            self.update()

    def play(self, eid: str, name: str) -> None:
        """Preview an animation on one element (the builder's Try button)."""
        if self.tracker.play(eid, name, time.monotonic()):
            self._frame.start()

    def _tick(self):
        self.update()
        if not self.tracker.active(time.monotonic()):
            self._frame.stop()
            self.update()

    def refresh_keys(self) -> None:
        self._keys = set(self.board.keys()) if self.board else set()
        self.tracker.set_board(self.board, self.animations)
        self.tracker.update(self.values, self.fx, time.monotonic(), animate=False)
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        if self.letterbox:
            p.fillRect(self.rect(), QColor(self.letterbox))
        if self.board is not None:
            paint_board(p, self.board, self.values, QRectF(self.rect()), self.images, checker=self.checker,
                        fx=self.fx, tracker=self.tracker, now=time.monotonic())
        else:
            p.setPen(QColor(theme.CURRENT["muted"]))
            p.setFont(theme.tfont("small"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No board")
        p.end()


class Notice(QFrame):
    """A banner that says what happened and what to do next."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("notice", True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 6, 6)
        self.text = label("", "body", wrap=True)
        lay.addWidget(self.text, 1)
        close = button("Dismiss", "ghost", self.hide)
        lay.addWidget(close)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, alert: bool = False, timeout_ms: int = 0) -> None:
        self.setProperty("notice", "alert" if alert else True)
        theme.repolish(self)
        self.text.setText(text)
        self.show()
        if timeout_ms:
            self._timer.start(timeout_ms)
        else:
            self._timer.stop()


def hline() -> QFrame:
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f"background:{theme.CURRENT['rule']}; border:0;")
    return f


def clear_layout(lay) -> None:
    while lay.count():
        item = lay.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


class FlowRow(QWidget):
    """A wrapping row of buttons (used for segmented choices)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from .flow import FlowLayout
        self.flow = FlowLayout(self, spacing=6)

    def add(self, w: QWidget) -> QWidget:
        self.flow.addWidget(w)
        return w

    def clear(self) -> None:
        clear_layout(self.flow)

    def widgets(self) -> List[QWidget]:
        return [self.flow.itemAt(i).widget() for i in range(self.flow.count())]
