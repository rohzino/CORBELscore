"""
Design → Boards: a scoreboard designer.

1.x placed widgets on a resizable form and stored positions as ratios of the
window, so layouts drifted when the window changed size. Here a board is a
fixed canvas (1920 x 1080 by default) and the designer works in its pixels,
with:
  * drag to move, eight handles to resize, rubber-band and Shift multi-select;
  * snapping to a grid and to other elements' edges and centres (guides);
  * align, distribute and paint-order commands; arrow keys nudge 1px, Shift
    10px; copy, paste, duplicate; full undo and redo;
  * drag a field from the list onto the canvas to make a bound text element;
  * live values or raw templates ("Show values");
  * an inspector for text, box, picture and visibility properties.
"""

from __future__ import annotations

import json
import time
from typing import Dict, List, Optional

from PyQt6.QtCore import QMimeData, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QBrush, QColor, QKeySequence, QPainter, QPen, QShortcut)
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDoubleSpinBox,
                             QFileDialog, QFontComboBox, QFormLayout, QGraphicsItem, QGraphicsObject,
                             QGraphicsScene, QGraphicsView, QHBoxLayout, QLineEdit,
                             QListWidget, QListWidgetItem, QMenu, QScrollArea, QSpinBox, QSplitter,
                             QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..core.animation import Tracker, library, sample
from ..core.board import Board, Element, new_id, resolve_color
from . import theme
from .render import ImageCache, draw_checker, paint_element, qcolor
from .session import Session
from .widgets import ColorEdit, ConfirmButton, button, caps, label, make_narrow, panel

MIME = "application/x-telescore-elements"
FIELD_MIME = "application/x-telescore-field"
HANDLE = 8.0           # handle size in screen pixels
SNAP_PX = 6.0          # snap distance in screen pixels


# ----- history ---------------------------------------------------------------------

class History:
    """Undo/redo of one board, as whole-board snapshots. Consecutive edits of
    the same property within a moment merge into one step."""

    def __init__(self):
        self.undo: List[dict] = []
        self.redo: List[dict] = []
        self._tag = None
        self._at = 0.0

    def push(self, board: Board, tag: Optional[str] = None) -> None:
        now = time.monotonic()
        if tag is not None and tag == self._tag and now - self._at < 1.0:
            self._at = now
            return
        self.undo.append(board.to_dict())
        del self.undo[:-200]
        self.redo.clear()
        self._tag, self._at = tag, now

    def step(self, board: Board, back: bool) -> Optional[dict]:
        src, dst = (self.undo, self.redo) if back else (self.redo, self.undo)
        if not src:
            return None
        dst.append(board.to_dict())
        self._tag = None
        return src.pop()


# ----- canvas items ----------------------------------------------------------------

class ElementItem(QGraphicsObject):
    """One element on the canvas. Geometry lives in the model; the item
    mirrors it and reports user edits back through the canvas."""

    def __init__(self, canvas: "Canvas", el: Element):
        super().__init__()
        self.canvas, self.el = canvas, el
        # Moving is done by the canvas (one snapped delta for the whole selection),
        # so Qt's own per-item moving stays off.
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setPos(el.x, el.y)
        self._resize: Optional[str] = None
        self._start_rect = QRectF()
        self._press = QPointF()
        self._was_selected = False

    # geometry
    def boundingRect(self) -> QRectF:
        m = HANDLE / max(self.canvas.scale_factor(), 0.01)
        return QRectF(-m, -m, self.el.w + 2 * m, self.el.h + 2 * m)

    def shape(self):
        from PyQt6.QtGui import QPainterPath
        path = QPainterPath()
        path.addRect(self.boundingRect() if self.isSelected() else QRectF(0, 0, self.el.w, self.el.h))
        return path

    def paint(self, p: QPainter, option, widget=None) -> None:
        if not self.el.visible:
            return
        p.save()
        p.translate(-self.el.x, -self.el.y)
        values = self.canvas.values
        fx = {} if self.canvas.show_templates else self.canvas.fx.get(self.el.id, {})
        hidden = not Tracker.target_visible(self.el, values, fx) and not self.canvas.show_templates
        if hidden:
            p.setOpacity(0.25)  # conditional element whose condition is off: ghosted
        look = self.canvas.preview_look(self.el)
        paint_element(p, self.el, values, self.canvas.images, self.canvas.show_templates, fx, look)
        p.restore()
        s = max(self.canvas.scale_factor(), 0.01)
        c = theme.CURRENT
        if self.isSelected():
            pen = QPen(QColor(c["hi"]), 1.5 / s)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(0, 0, self.el.w, self.el.h))
            if len(self.canvas.selected_items()) == 1 and not self.el.locked:
                p.setBrush(QBrush(QColor(c["panel"])))
                for r in self.handle_rects().values():
                    p.drawRect(r)
        elif self.canvas.hover is self:
            p.setPen(QPen(QColor(c["accent-text"]), 1 / s, Qt.PenStyle.DashLine))
            p.drawRect(QRectF(0, 0, self.el.w, self.el.h))

    def handle_rects(self) -> Dict[str, QRectF]:
        s = max(self.canvas.scale_factor(), 0.01)
        h = HANDLE / s
        w, ht = self.el.w, self.el.h
        pts = {"nw": (0, 0), "n": (w / 2, 0), "ne": (w, 0), "e": (w, ht / 2), "se": (w, ht),
               "s": (w / 2, ht), "sw": (0, ht), "w": (0, ht / 2)}
        return {k: QRectF(x - h / 2, y - h / 2, h, h) for k, (x, y) in pts.items()}

    def handle_at(self, pos: QPointF) -> Optional[str]:
        if not self.isSelected() or self.el.locked or len(self.canvas.selected_items()) != 1:
            return None
        for k, r in self.handle_rects().items():
            if r.adjusted(-2, -2, 2, 2).contains(pos):
                return k
        return None

    CURSORS = {"nw": Qt.CursorShape.SizeFDiagCursor, "se": Qt.CursorShape.SizeFDiagCursor,
               "ne": Qt.CursorShape.SizeBDiagCursor, "sw": Qt.CursorShape.SizeBDiagCursor,
               "n": Qt.CursorShape.SizeVerCursor, "s": Qt.CursorShape.SizeVerCursor,
               "e": Qt.CursorShape.SizeHorCursor, "w": Qt.CursorShape.SizeHorCursor}

    def hoverMoveEvent(self, ev):
        h = self.handle_at(ev.pos())
        self.setCursor(self.CURSORS[h] if h else (Qt.CursorShape.ArrowCursor if self.el.locked
                                                  else Qt.CursorShape.SizeAllCursor))
        if self.canvas.hover is not self:
            self.canvas.hover = self
            self.update()

    def hoverLeaveEvent(self, ev):
        if self.canvas.hover is self:
            self.canvas.hover = None
            self.update()

    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(ev)
            return
        self._resize = self.handle_at(ev.pos())
        self._start_rect = QRectF(self.el.x, self.el.y, self.el.w, self.el.h)
        self._press = ev.scenePos()
        if self._resize:
            ev.accept()
            return
        toggling = bool(ev.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
        self._was_selected = self.isSelected()
        if toggling:
            self.setSelected(not self.isSelected())
        elif not self.isSelected():
            self.canvas.select_ids([self.el.id])
        # (a press on an already selected element keeps the group, to drag it)
        self.canvas.begin_move(ev.scenePos())
        ev.accept()

    def mouseMoveEvent(self, ev):
        if self._resize:
            self.canvas.resize_item(self, self._resize, self._start_rect, ev.scenePos() - self._press,
                                    ev.modifiers())
        else:
            self.canvas.drag_to(ev.scenePos(), ev.modifiers())
        ev.accept()

    def mouseReleaseEvent(self, ev):
        if self._resize:
            self._resize = None
            self.canvas.end_resize(self, self._start_rect)
        else:
            dragged = self.canvas.end_move()
            plain = not (ev.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
            if not dragged and plain and self._was_selected:
                self.canvas.select_ids([self.el.id])      # a click inside a group picks one
        ev.accept()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.prepareGeometryChange()
        return super().itemChange(change, value)

    def sync(self) -> None:
        self.prepareGeometryChange()
        self.setPos(self.el.x, self.el.y)
        self.update()


class BoardBackground(QGraphicsItem):
    def __init__(self, canvas: "Canvas"):
        super().__init__()
        self.canvas = canvas
        self.setZValue(-1e6)

    def boundingRect(self) -> QRectF:
        b = self.canvas.board
        return QRectF(0, 0, b.width, b.height) if b else QRectF()

    def paint(self, p: QPainter, option, widget=None):
        b = self.canvas.board
        if not b:
            return
        r = QRectF(0, 0, b.width, b.height)
        col = qcolor(resolve_color(b.background, self.canvas.values))
        if col is not None:
            p.fillRect(r, col)
        else:
            draw_checker(p, r, 24)
        if self.canvas.grid_on:
            g = self.canvas.grid
            pen = QPen(QColor(255, 255, 255, 18), 0)
            p.setPen(pen)
            x = g
            while x < b.width:
                p.drawLine(QPointF(x, 0), QPointF(x, b.height))
                x += g
            y = g
            while y < b.height:
                p.drawLine(QPointF(0, y), QPointF(b.width, y))
                y += g
        p.setPen(QPen(QColor(theme.CURRENT["rule-strong"]), 0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)


class Canvas(QGraphicsView):
    """The design surface."""

    selection = pyqtSignal(list)                  # element ids
    committed = pyqtSignal(str)                   # tag of a finished edit (move, resize)
    dropped_field = pyqtSignal(str, QPointF)      # field key, board position

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing |
                            QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.board: Optional[Board] = None
        self.values: Dict[str, str] = {}
        self.fx: Dict[str, dict] = {}
        self.images = ImageCache()
        self._previews: Dict[str, tuple] = {}     # element id -> (Animation, start)
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._anim_frame)
        self.items_by_id: Dict[str, ElementItem] = {}
        self.show_templates = False
        self.grid_on = True
        self.snap_on = True
        self.grid = 10
        self.hover: Optional[ElementItem] = None
        self.moving = False
        self._dragged = False
        self._press = QPointF()
        self._pending_resize = None
        self.guides: List[tuple] = []           # ("v"|"h", position)
        self._move_start: Dict[str, QPointF] = {}
        self._fit_pending = True      # keep fitting the board to the window until the user zooms
        self.scene().selectionChanged.connect(self._sel_changed)

    def scale_factor(self) -> float:
        return self.transform().m11()

    # ----- animation preview ------------------------------------------------------
    def play(self, eid: str, anim) -> None:
        """Play ``anim`` (core.animation.Animation) on one element, then show it at rest."""
        import time as _t
        self._previews[eid] = (anim, _t.monotonic())
        self._anim_timer.start()

    def preview_look(self, el: Element):
        hit = self._previews.get(el.id)
        if not hit:
            return None
        import time as _t
        anim, start = hit
        elapsed = (_t.monotonic() - start) * 1000.0
        if elapsed >= anim.total + 300:     # hold the end a moment, then back to normal
            return None
        return sample(anim, min(elapsed, anim.total))

    def _anim_frame(self) -> None:
        import time as _t
        now = _t.monotonic()
        self._previews = {k: v for k, v in self._previews.items() if (now - v[1]) * 1000.0 < v[0].total + 300}
        self.scene().update()
        if not self._previews:
            self._anim_timer.stop()

    # ----- model <-> items --------------------------------------------------
    def set_board(self, board: Optional[Board], keep_selection: bool = True) -> None:
        sel = self.selected_ids() if keep_selection else []
        self.scene().blockSignals(True)
        self.scene().clear()
        self.items_by_id = {}
        self.hover = None
        self.board = board
        if board is not None:
            self.scene().addItem(BoardBackground(self))
            for i, e in enumerate(board.elements):
                it = ElementItem(self, e)
                it.setZValue(i)
                self.scene().addItem(it)
                self.items_by_id[e.id] = it
            m = max(board.width, board.height) * 0.15
            self.scene().setSceneRect(QRectF(-m, -m, board.width + 2 * m, board.height + 2 * m))
            for eid in sel:
                if eid in self.items_by_id:
                    self.items_by_id[eid].setSelected(True)
        self.scene().blockSignals(False)
        self._sel_changed()
        if self._fit_pending:
            QTimer.singleShot(0, self.fit)

    def refresh(self) -> None:
        for it in self.items_by_id.values():
            it.sync()
        self.scene().update()

    def selected_items(self) -> List[ElementItem]:
        return [i for i in self.scene().selectedItems() if isinstance(i, ElementItem)]

    def selected_ids(self) -> List[str]:
        if self.board is None:
            return []
        order = {e.id: n for n, e in enumerate(self.board.elements)}
        return sorted((i.el.id for i in self.selected_items()), key=lambda k: order.get(k, 0))

    def select_ids(self, ids: List[str]) -> None:
        self.scene().blockSignals(True)
        for eid, it in self.items_by_id.items():
            it.setSelected(eid in ids)
        self.scene().blockSignals(False)
        self._sel_changed()

    def _sel_changed(self):
        for it in self.items_by_id.values():
            it.update()
        self.selection.emit(self.selected_ids())

    # ----- zoom -------------------------------------------------------------
    def fit(self) -> None:
        """Fit the board in the window, and keep it fitted as the window
        changes size until the user zooms. A hidden tab's view has no real
        size yet, so fitting waits until it is shown."""
        self._fit_pending = True
        if self.board is None or not self.isVisible() or self.viewport().width() < 50:
            return
        r = QRectF(0, 0, self.board.width, self.board.height).adjusted(-30, -30, 30, 30)
        self.fitInView(r, Qt.AspectRatioMode.KeepAspectRatio)

    def actual_size(self) -> None:
        self._fit_pending = False
        self.resetTransform()

    def showEvent(self, ev):
        super().showEvent(ev)
        if self._fit_pending:
            QTimer.singleShot(0, self.fit)

    def wheelEvent(self, ev):
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            f = 1.15 if ev.angleDelta().y() > 0 else 1 / 1.15
            s = self.scale_factor() * f
            if 0.05 <= s <= 8:
                self._fit_pending = False
                self.scale(f, f)
            ev.accept()
        else:
            super().wheelEvent(ev)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self._fit_pending:
            self.fit()

    # ----- moving and snapping ------------------------------------------------
    def begin_move(self, scene_pos: QPointF) -> None:
        self.moving = True
        self._dragged = False
        self._press = QPointF(scene_pos)
        self._move_start = {i.el.id: QPointF(i.el.x, i.el.y) for i in self.selected_items() if not i.el.locked}

    def _targets(self, exclude: set):
        """Snap lines: board edges and centre, and other elements' edges and centres."""
        b = self.board
        xs, ys = [0.0, b.width / 2, float(b.width)], [0.0, b.height / 2, float(b.height)]
        for e in b.elements:
            if e.id in exclude or not e.visible:
                continue
            xs += [e.x, e.x + e.w / 2, e.x + e.w]
            ys += [e.y, e.y + e.h / 2, e.y + e.h]
        return xs, ys

    def drag_to(self, scene_pos: QPointF, mods) -> None:
        """Move the whole selection by one snapped delta."""
        if not self.moving or not self._move_start or self.board is None:
            return
        d = scene_pos - self._press
        s = max(self.scale_factor(), 0.01)
        if not self._dragged and abs(d.x()) + abs(d.y()) < 3 / s:
            return
        self._dragged = True
        items = [self.items_by_id[k] for k in self._move_start if k in self.items_by_id]
        x0 = min(self._move_start[i.el.id].x() for i in items)
        y0 = min(self._move_start[i.el.id].y() for i in items)
        bw = max(self._move_start[i.el.id].x() + i.el.w for i in items) - x0
        bh = max(self._move_start[i.el.id].y() + i.el.h for i in items) - y0
        nx, ny = x0 + d.x(), y0 + d.y()
        self.guides = []
        if mods & Qt.KeyboardModifier.ShiftModifier:          # constrain to one axis
            if abs(d.x()) > abs(d.y()):
                ny = y0
            else:
                nx = x0
        if self.snap_on and not (mods & Qt.KeyboardModifier.AltModifier):
            tol = SNAP_PX / s
            xs, ys = self._targets(set(self._move_start))

            def best(start, size, lines):
                found = None
                for off in (0.0, size / 2, size):
                    for t in lines:
                        delta = t - (start + off)
                        if abs(delta) <= tol and (found is None or abs(delta) < abs(found[0])):
                            found = (delta, t)
                return found
            bx = best(nx, bw, xs)
            if bx:
                nx += bx[0]
                self.guides.append(("v", bx[1]))
            elif self.grid_on:
                nx = round(nx / self.grid) * self.grid
            by = best(ny, bh, ys)
            if by:
                ny += by[0]
                self.guides.append(("h", by[1]))
            elif self.grid_on:
                ny = round(ny / self.grid) * self.grid
        dx, dy = nx - x0, ny - y0
        for i in items:
            st = self._move_start[i.el.id]
            i.setPos(round(st.x() + dx, 2), round(st.y() + dy, 2))
        self.viewport().update()

    def end_move(self) -> bool:
        """Finish a drag. Returns True if anything moved."""
        if not self.moving:
            return False
        self.moving = False
        self.guides = []
        moved = self._dragged and any(
            (round(i.pos().x(), 2), round(i.pos().y(), 2)) != (round(i.el.x, 2), round(i.el.y, 2))
            for i in self.selected_items())
        if moved:
            self.committed.emit("move")   # the tab pushes history, then calls apply_positions()
        self.viewport().update()
        return self._dragged

    def apply_positions(self) -> None:
        for it in self.selected_items():
            if not it.el.locked:
                it.el.x, it.el.y = round(it.pos().x(), 2), round(it.pos().y(), 2)

    def resize_item(self, it: ElementItem, handle: str, start: QRectF, delta: QPointF, mods) -> None:
        x1, y1, x2, y2 = start.left(), start.top(), start.right(), start.bottom()
        dx, dy = delta.x(), delta.y()
        if "w" in handle:
            x1 += dx
        if "e" in handle:
            x2 += dx
        if "n" in handle:
            y1 += dy
        if "s" in handle:
            y2 += dy
        if mods & Qt.KeyboardModifier.ShiftModifier and len(handle) == 2 and start.height() > 0:
            ratio = start.width() / start.height()   # keep proportions from the corner
            w, h = x2 - x1, y2 - y1
            if abs(w) / ratio > abs(h):
                h = w / ratio
            else:
                w = h * ratio
            if "w" in handle:
                x1 = x2 - w
            else:
                x2 = x1 + w
            if "n" in handle:
                y1 = y2 - h
            else:
                y2 = y1 + h
        self.guides = []
        if self.snap_on and not (mods & Qt.KeyboardModifier.AltModifier):
            tol = SNAP_PX / max(self.scale_factor(), 0.01)
            xs, ys = self._targets({it.el.id})

            def snap(v, lines, axis):
                for t in lines:
                    if abs(v - t) <= tol:
                        self.guides.append((axis, t))
                        return t
                return round(v / self.grid) * self.grid if self.grid_on else v
            if "w" in handle:
                x1 = snap(x1, xs, "v")
            if "e" in handle:
                x2 = snap(x2, xs, "v")
            if "n" in handle:
                y1 = snap(y1, ys, "h")
            if "s" in handle:
                y2 = snap(y2, ys, "h")
        if x2 - x1 < 4:
            if "w" in handle:
                x1 = x2 - 4
            else:
                x2 = x1 + 4
        if y2 - y1 < 4:
            if "n" in handle:
                y1 = y2 - 4
            else:
                y2 = y1 + 4
        it.prepareGeometryChange()
        it.el.x, it.el.y = round(x1, 2), round(y1, 2)
        it.el.w, it.el.h = round(x2 - x1, 2), round(y2 - y1, 2)
        it.setPos(it.el.x, it.el.y)
        it.update()
        self.viewport().update()

    def end_resize(self, it: ElementItem, start: QRectF) -> None:
        self.guides = []
        now = QRectF(it.el.x, it.el.y, it.el.w, it.el.h)
        if now != start:
            # The model already holds the new size; hand history the old one.
            new = (it.el.x, it.el.y, it.el.w, it.el.h)
            it.el.x, it.el.y, it.el.w, it.el.h = start.x(), start.y(), start.width(), start.height()
            self._pending_resize = (it.el.id, new)
            self.committed.emit("resize")
        self.viewport().update()

    def apply_resize(self) -> None:
        pending = getattr(self, "_pending_resize", None)
        if not pending:
            return
        eid, (x, y, w, h) = pending
        it = self.items_by_id.get(eid)
        if it is not None:
            it.el.x, it.el.y, it.el.w, it.el.h = x, y, w, h
            it.sync()
        self._pending_resize = None

    def drawForeground(self, p: QPainter, rect: QRectF) -> None:
        if not self.guides or self.board is None:
            return
        pen = QPen(QColor(theme.CURRENT["user"]), 0)
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        b = self.board
        for axis, v in self.guides:
            if axis == "v":
                p.drawLine(QPointF(v, -b.height), QPointF(v, b.height * 2))
            else:
                p.drawLine(QPointF(-b.width, v), QPointF(b.width * 2, v))

    # ----- field drops --------------------------------------------------------
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasFormat(FIELD_MIME):
            ev.acceptProposedAction()
        else:
            super().dragEnterEvent(ev)

    def dragMoveEvent(self, ev):
        if ev.mimeData().hasFormat(FIELD_MIME):
            ev.acceptProposedAction()
        else:
            super().dragMoveEvent(ev)

    def dropEvent(self, ev):
        if ev.mimeData().hasFormat(FIELD_MIME):
            key = ev.mimeData().data(FIELD_MIME).data().decode("utf-8")
            pos = self.mapToScene(ev.position().toPoint())
            self.dropped_field.emit(key, pos)
            ev.acceptProposedAction()
        else:
            super().dropEvent(ev)


class FieldList(QListWidget):
    """Every published key; drag one onto the canvas, or double-click."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def mimeData(self, items):
        md = QMimeData()
        if items:
            key = items[0].data(Qt.ItemDataRole.UserRole)
            md.setData(FIELD_MIME, key.encode("utf-8"))
            md.setText("{%s}" % key)
        return md

    def mimeTypes(self):
        return [FIELD_MIME, "text/plain"]


# ----- inspector ----------------------------------------------------------------------

def _spin(lo: float, hi: float, step: float = 1.0, decimals: int = 0, suffix: str = "") -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(decimals)
    s.setSingleStep(step)
    s.setKeyboardTracking(False)
    if suffix:
        s.setSuffix(suffix)
    return s


class Inspector(QWidget):
    """Properties of the selection, or of the board when nothing is selected."""

    edit = pyqtSignal(str, object)          # property, value  -> applied to all selected elements
    board_edit = pyqtSignal(str, object)    # property, value  -> the board
    browse_image = pyqtSignal()
    try_anim = pyqtSignal(str)              # play an animation on the selection
    open_library = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        self.title = label("", "dialog-title")
        root.addWidget(self.title)

        # Board ------------------------------------------------------------
        self.board_box, bl = panel(pad=12)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.b_name = QLineEdit()
        self.b_name.editingFinished.connect(lambda: self._board("name", self.b_name.text().strip() or "Board"))
        self.b_size = QComboBox()
        for txt, wh in (("1920 × 1080 (HD)", (1920, 1080)), ("1280 × 720", (1280, 720)),
                        ("3840 × 2160 (4K)", (3840, 2160)), ("1080 × 1920 (vertical)", (1080, 1920)),
                        ("1080 × 1080 (square)", (1080, 1080)), ("Custom", None)):
            self.b_size.addItem(txt, wh)
        self.b_size.activated.connect(self._size_preset)
        self.b_w = QSpinBox()
        self.b_h = QSpinBox()
        for s in (self.b_w, self.b_h):
            s.setRange(16, 8192)
            s.setKeyboardTracking(False)
        self.b_w.valueChanged.connect(lambda v: self._board("width", v))
        self.b_h.valueChanged.connect(lambda v: self._board("height", v))
        wh = QHBoxLayout()
        wh.addWidget(self.b_w)
        wh.addWidget(label("×", "body", muted=True))
        wh.addWidget(self.b_h)
        self.b_bg = ColorEdit()
        self.b_bg.edit.setPlaceholderText("transparent")
        self.b_bg.changed.connect(lambda v: self._board("background", v))
        form.addRow(caps("Name"), self.b_name)
        form.addRow(caps("Size"), self.b_size)
        form.addRow("", wh)
        form.addRow(caps("Background"), self.b_bg)
        bl.addLayout(form)
        bl.addWidget(label("Leave the background empty for a transparent graphic to key over video. "
                           "The projector shows it on black.", "small", muted=True, wrap=True))
        root.addWidget(self.board_box)

        # Element: general ------------------------------------------------------
        self.gen_box, gl = panel(pad=12)
        f = QFormLayout()
        self.e_name = QLineEdit()
        self.e_name.editingFinished.connect(lambda: self._set("name", self.e_name.text().strip()))
        self.e_x, self.e_y = _spin(-10000, 10000, 1, 1), _spin(-10000, 10000, 1, 1)
        self.e_w, self.e_h = _spin(1, 10000, 1, 1), _spin(1, 10000, 1, 1)
        for sp, k in ((self.e_x, "x"), (self.e_y, "y"), (self.e_w, "w"), (self.e_h, "h")):
            sp.valueChanged.connect(lambda v, k=k: self._set(k, round(v, 2)))
        xy, wh2 = QHBoxLayout(), QHBoxLayout()
        xy.addWidget(self.e_x)
        xy.addWidget(self.e_y)
        wh2.addWidget(self.e_w)
        wh2.addWidget(self.e_h)
        self.e_opacity = _spin(0, 100, 5, 0, " %")
        self.e_opacity.valueChanged.connect(lambda v: self._set("opacity", round(v / 100, 3)))
        self.e_show = QComboBox()
        self.e_show.setEditable(False)
        self.e_show.activated.connect(lambda _: self._set("show_when", self.e_show.currentData() or ""))
        self.e_lock = QCheckBox("Locked")
        self.e_lock.toggled.connect(lambda v: self._set("locked", v))
        f.addRow(caps("Name"), self.e_name)
        f.addRow(caps("X  Y"), xy)
        f.addRow(caps("W  H"), wh2)
        f.addRow(caps("Opacity"), self.e_opacity)
        f.addRow(caps("Show when"), self.e_show)
        f.addRow("", self.e_lock)
        gl.addLayout(f)
        root.addWidget(self.gen_box)

        # Text ------------------------------------------------------------------
        self.text_box, tl = panel(pad=12)
        f = QFormLayout()
        self.t_text = QLineEdit()
        self.t_text.setPlaceholderText("Text, or fields like {home.score}")
        self.t_text.setFont(theme.font(13, 500, family="Consolas"))
        self.t_text.editingFinished.connect(lambda: self._set("text", self.t_text.text()))
        self.t_font = QFontComboBox()
        self.t_font.currentFontChanged.connect(lambda fnt: self._set("font", fnt.family()))
        self.t_size = _spin(4, 2000, 1, 0, " px")
        self.t_size.valueChanged.connect(lambda v: self._set("size", v))
        self.t_weight = QComboBox()
        for w in (100, 200, 300, 400, 500, 600, 700, 800, 900):
            self.t_weight.addItem(str(w), w)
        self.t_weight.activated.connect(lambda _: self._set("weight", self.t_weight.currentData()))
        self.t_color = ColorEdit(allow_empty=False)
        self.t_color.changed.connect(lambda v: self._set("color", v or "#ffffff"))
        self.t_align = QComboBox()
        for a in ("left", "center", "right"):
            self.t_align.addItem(a.title(), a)
        self.t_align.activated.connect(lambda _: self._set("align", self.t_align.currentData()))
        self.t_valign = QComboBox()
        for a in ("top", "middle", "bottom"):
            self.t_valign.addItem(a.title(), a)
        self.t_valign.activated.connect(lambda _: self._set("valign", self.t_valign.currentData()))
        self.t_track = _spin(-0.2, 1, 0.01, 2, " em")
        self.t_track.valueChanged.connect(lambda v: self._set("tracking", round(v, 3)))
        self.t_pad = _spin(0, 500, 1, 0, " px")
        self.t_pad.valueChanged.connect(lambda v: self._set("padding", v))
        self.t_fit = QCheckBox("Shrink to fit")
        self.t_fit.toggled.connect(lambda v: self._set("fit", v))
        self.t_upper = QCheckBox("Capitals")
        self.t_upper.toggled.connect(lambda v: self._set("uppercase", v))
        self.t_italic = QCheckBox("Italic")
        self.t_italic.toggled.connect(lambda v: self._set("italic", v))
        self.t_tab = QCheckBox("Tabular figures")
        self.t_tab.setToolTip("Every digit the same width, so a running clock does not jiggle")
        self.t_tab.toggled.connect(lambda v: self._set("tabular", v))
        f.addRow(caps("Text"), self.t_text)
        f.addRow(caps("Font"), self.t_font)
        f.addRow(caps("Size"), self.t_size)
        f.addRow(caps("Weight"), self.t_weight)
        f.addRow(caps("Colour"), self.t_color)
        al = QHBoxLayout()
        al.addWidget(self.t_align)
        al.addWidget(self.t_valign)
        f.addRow(caps("Align"), al)
        f.addRow(caps("Tracking"), self.t_track)
        f.addRow(caps("Padding"), self.t_pad)
        checks = QHBoxLayout()
        checks.addWidget(self.t_fit)
        checks.addWidget(self.t_upper)
        f.addRow("", checks)
        checks2 = QHBoxLayout()
        checks2.addWidget(self.t_italic)
        checks2.addWidget(self.t_tab)
        f.addRow("", checks2)
        tl.addLayout(f)
        self.t_missing = label("", "small", wrap=True)
        self.t_missing.setProperty("alerttext", True)
        tl.addWidget(self.t_missing)
        root.addWidget(self.text_box)

        # Box -------------------------------------------------------------------
        self.box_box, xl = panel(pad=12)
        f = QFormLayout()
        self.x_fill = ColorEdit()
        self.x_fill.changed.connect(lambda v: self._set("fill", v))
        self.x_stroke = ColorEdit()
        self.x_stroke.changed.connect(lambda v: self._set("stroke", v))
        self.x_sw = _spin(0, 100, 1, 1, " px")
        self.x_sw.valueChanged.connect(lambda v: self._set("stroke_width", v))
        self.x_radius = _spin(0, 1000, 1, 0, " px")
        self.x_radius.valueChanged.connect(lambda v: self._set("radius", v))
        f.addRow(caps("Fill"), self.x_fill)
        f.addRow(caps("Border"), self.x_stroke)
        f.addRow(caps("Border width"), self.x_sw)
        f.addRow(caps("Corners"), self.x_radius)
        xl.addLayout(f)
        root.addWidget(self.box_box)

        # Image -----------------------------------------------------------------
        self.img_box, il = panel(pad=12)
        f = QFormLayout()
        src = QHBoxLayout()
        self.i_src = QLineEdit()
        self.i_src.setPlaceholderText("A file, or a field like {home.logo}")
        self.i_src.editingFinished.connect(lambda: self._set("src", self.i_src.text().strip()))
        src.addWidget(self.i_src, 1)
        src.addWidget(button("Browse…", "", self.browse_image.emit))
        self.i_contain = QCheckBox("Keep proportions")
        self.i_contain.toggled.connect(lambda v: self._set("contain", v))
        f.addRow(caps("Picture"), src)
        f.addRow("", self.i_contain)
        il.addLayout(f)
        root.addWidget(self.img_box)

        # Rules and motion ---------------------------------------------------------
        self.motion_box, ml = panel(pad=12)
        ml.addWidget(caps("Rules and motion"))
        f = QFormLayout()
        self.m_rules = QLineEdit()
        self.m_rules.setPlaceholderText("0:00=FINAL|NULL=—  (this graphic only)")
        self.m_rules.setToolTip("Replace shown values on this element only. Field rules (Setup → Fields) also reach "
                                ".txt and .xml; these do not.")
        self.m_rules.editingFinished.connect(lambda: self._set("rules", self.m_rules.text().strip()))
        f.addRow(caps("Rules"), self.m_rules)
        self.m_combos = {}
        for prop, cap, kinds in (("anim_in", "Appears", ("in",)), ("anim_out", "Disappears", ("out",)),
                                 ("anim_change", "On change", ("emphasis", "in"))):
            row = QHBoxLayout()
            cb = QComboBox()
            cb.setMinimumWidth(170)
            cb.activated.connect(lambda _i, prop=prop, cb=cb: self._set(prop, cb.currentData() or ""))
            tr = button("Try", "", lambda cb=cb: cb.currentData() and self.try_anim.emit(cb.currentData()))
            row.addWidget(cb, 1)
            row.addWidget(tr)
            f.addRow(caps(cap), row)
            self.m_combos[prop] = (cb, kinds)
        ml.addLayout(f)
        ml.addWidget(label("Appears and Disappears play when Show when, or a condition in Logic, shows or hides it. "
                           "On change plays when its text or picture changes.", "small", muted=True, wrap=True))
        ml.addWidget(button("Edit animations", "", self.open_library.emit, tip="Design → Animations: make your own"))
        root.addWidget(self.motion_box)
        root.addStretch(1)
        self._lib = library()
        self.set_animations(self._lib)
        self.show_board(None)

    # ----- loading ------------------------------------------------------------
    def set_fields(self, keys: List[str], values: Dict[str, str]) -> None:
        self._values = values
        cur = self.e_show.currentData()
        self.e_show.blockSignals(True)
        self.e_show.clear()
        self.e_show.addItem("Always", "")
        for k in keys:
            self.e_show.addItem(k, k)
        i = self.e_show.findData(cur)
        self.e_show.setCurrentIndex(max(0, i))
        self.e_show.blockSignals(False)
        for ce in (self.t_color, self.x_fill, self.x_stroke, self.b_bg):
            ce.setValues(values)

    def set_animations(self, lib) -> None:
        self._lib = lib
        for prop, (cb, kinds) in self.m_combos.items():
            cur = cb.currentData()
            cb.blockSignals(True)
            cb.clear()
            cb.addItem("None", "")
            for name, a in lib.items():
                if a.kind in kinds:
                    cb.addItem(name if a.builtin else f"{name}  (custom)", name)
            cb.setCurrentIndex(max(0, cb.findData(cur)))
            cb.blockSignals(False)

    def show_board(self, board: Optional[Board]) -> None:
        self._loading = True
        for w in (self.gen_box, self.text_box, self.box_box, self.img_box, self.motion_box):
            w.hide()
        self.board_box.setVisible(board is not None)
        self.title.setText("BOARD" if board else "")
        if board:
            self.b_name.setText(board.name)
            self.b_w.setValue(board.width)
            self.b_h.setValue(board.height)
            idx = self.b_size.findData((board.width, board.height))
            self.b_size.setCurrentIndex(idx if idx >= 0 else self.b_size.count() - 1)
            self.b_bg.setValue(board.background)
        self._loading = False

    def show_elements(self, els: List[Element], missing: List[str]) -> None:
        if not els:
            return
        self._loading = True
        e = els[0]
        kinds = {x.kind for x in els}
        self.board_box.hide()
        self.gen_box.show()
        self.title.setText(e.kind.upper() if len(els) == 1 else f"{len(els)} ELEMENTS")
        self.text_box.setVisible(kinds == {"text"})
        self.img_box.setVisible(kinds == {"image"})
        self.box_box.show()
        self.e_name.setText(e.name if len(els) == 1 else "")
        self.e_name.setEnabled(len(els) == 1)
        for sp, v in ((self.e_x, e.x), (self.e_y, e.y), (self.e_w, e.w), (self.e_h, e.h)):
            sp.setValue(v)
        self.e_opacity.setValue(e.opacity * 100)
        i = self.e_show.findData(e.show_when)
        if i < 0 and e.show_when:
            self.e_show.addItem(f"{e.show_when} (missing)", e.show_when)
            i = self.e_show.count() - 1
        self.e_show.setCurrentIndex(max(0, i))
        self.e_lock.setChecked(e.locked)
        self.t_text.setText(e.text)
        from PyQt6.QtGui import QFont
        self.t_font.setCurrentFont(QFont(e.font))
        self.t_size.setValue(e.size)
        self.t_weight.setCurrentIndex(max(0, self.t_weight.findData(int(e.weight))))
        self.t_color.setValue(e.color)
        self.t_align.setCurrentIndex(max(0, self.t_align.findData(e.align)))
        self.t_valign.setCurrentIndex(max(0, self.t_valign.findData(e.valign)))
        self.t_track.setValue(e.tracking)
        self.t_pad.setValue(e.padding)
        self.t_fit.setChecked(e.fit)
        self.t_upper.setChecked(e.uppercase)
        self.t_italic.setChecked(e.italic)
        self.t_tab.setChecked(e.tabular)
        self.x_fill.setValue(e.fill)
        self.x_stroke.setValue(e.stroke)
        self.x_sw.setValue(e.stroke_width)
        self.x_radius.setValue(e.radius)
        self.i_src.setText(e.src)
        self.i_contain.setChecked(e.contain)
        self.motion_box.show()
        self.m_rules.setText(e.rules)
        for prop, (cb, _k) in self.m_combos.items():
            val = getattr(e, prop)
            i = cb.findData(val)
            if i < 0 and val:
                cb.addItem(f"{val} (missing)", val)
                i = cb.count() - 1
            cb.setCurrentIndex(max(0, i))
        self.t_missing.setText(("Unknown fields: " + ", ".join("{%s}" % k for k in missing) +
                                ". Check the spelling or add them in Data.") if missing else "")
        self._loading = False

    def _set(self, prop: str, value) -> None:
        if not self._loading:
            self.edit.emit(prop, value)

    def _board(self, prop: str, value) -> None:
        if not self._loading:
            self.board_edit.emit(prop, value)

    def _size_preset(self, _):
        wh = self.b_size.currentData()
        if wh and not self._loading:
            self.board_edit.emit("size", wh)


# ----- the tab ------------------------------------------------------------------------

class BuildTab(QWidget):
    library_requested = pyqtSignal()        # Design → Animations

    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.session = session
        self.history: Dict[str, History] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # Toolbar ---------------------------------------------------------------
        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(caps("Board"))
        self.board_pick = QComboBox()
        self.board_pick.setMinimumWidth(180)
        self.board_pick.currentIndexChanged.connect(self._board_picked)
        bar.addWidget(self.board_pick)
        new_menu = QMenu(self)
        new_menu.addAction("Blank board", lambda: self.new_board(None))
        new_menu.addAction("Copy of this board", self.duplicate_board)
        b_new = button("New board", "")
        b_new.setMenu(new_menu)
        bar.addWidget(b_new)
        self.b_del_board = ConfirmButton("Delete board", "Press again to delete this board")
        self.b_del_board.confirmed.connect(self.delete_board)
        bar.addWidget(self.b_del_board)
        bar.addSpacing(14)
        add_menu = QMenu(self)
        add_menu.addAction("Text", lambda: self.add_element("text"))
        add_menu.addAction("Box", lambda: self.add_element("box"))
        add_menu.addAction("Picture", lambda: self.add_element("image"))
        b_add = button("Add", "accent")
        b_add.setMenu(add_menu)
        bar.addWidget(b_add)
        arrange = QMenu(self)
        for txt, how in (("Align left", "left"), ("Align centre", "hcenter"), ("Align right", "right"),
                         ("Align top", "top"), ("Align middle", "vcenter"), ("Align bottom", "bottom")):
            arrange.addAction(txt, lambda _=False, how=how: self.arrange(lambda b, ids: b.align(ids, how)))
        arrange.addSeparator()
        arrange.addAction("Distribute across", lambda: self.arrange(lambda b, ids: b.distribute(ids, "h")))
        arrange.addAction("Distribute down", lambda: self.arrange(lambda b, ids: b.distribute(ids, "v")))
        arrange.addSeparator()
        for txt, where in (("Bring to front", "front"), ("Bring forward", "forward"),
                           ("Send backward", "backward"), ("Send to back", "back")):
            arrange.addAction(txt, lambda _=False, where=where: self.reorder(where))
        b_arr = button("Arrange", "")
        b_arr.setMenu(arrange)
        bar.addWidget(b_arr)
        bar.addWidget(button("Duplicate", "", self.duplicate, tip="Ctrl+D"))
        self.b_delete = button("Delete", "alert", self.delete_selected, tip="Delete")
        bar.addWidget(self.b_delete)
        bar.addSpacing(14)
        self.b_undo = button("Undo", "", self.undo, tip="Ctrl+Z")
        self.b_redo = button("Redo", "", self.redo, tip="Ctrl+Y")
        bar.addWidget(self.b_undo)
        bar.addWidget(self.b_redo)
        bar.addStretch(1)
        self.c_values = QCheckBox("Show values")
        self.c_values.setChecked(True)
        self.c_values.setToolTip("Off shows the templates, such as {home.score}")
        self.c_values.toggled.connect(self._toggle_values)
        bar.addWidget(self.c_values)
        self.c_snap = QCheckBox("Snap")
        self.c_snap.setChecked(True)
        self.c_snap.setToolTip("Snap to the grid and to other elements. Hold Alt while dragging to place freely.")
        self.c_snap.toggled.connect(self._toggle_snap)
        bar.addWidget(self.c_snap)
        self.grid_size = QSpinBox()
        self.grid_size.setRange(2, 200)
        self.grid_size.setValue(10)
        self.grid_size.setSuffix(" px")
        self.grid_size.setToolTip("Grid size")
        self.grid_size.valueChanged.connect(self._grid_changed)
        bar.addWidget(self.grid_size)
        bar.addWidget(button("Fit", "", lambda: self.canvas.fit(), tip="Fit the board in the window"))
        bar.addWidget(button("100%", "", lambda: self.canvas.actual_size(), tip="Actual pixels. Ctrl+wheel zooms."))
        root.addLayout(bar)

        # Body ------------------------------------------------------------------
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 8, 0)
        ll.setSpacing(6)
        ll.addWidget(caps("Layers · top is in front"))
        self.layers = QTreeWidget()
        self.layers.setHeaderLabels(["Name", "Show", "Lock"])
        self.layers.setRootIsDecorated(False)
        self.layers.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.layers.setColumnWidth(0, 150)
        self.layers.setColumnWidth(1, 44)
        self.layers.setColumnWidth(2, 44)
        self.layers.itemSelectionChanged.connect(self._layers_selected)
        self.layers.itemChanged.connect(self._layer_edited)
        ll.addWidget(self.layers, 3)
        ll.addWidget(caps("Fields · drag onto the board"))
        self.fields = FieldList()
        self.fields.itemDoubleClicked.connect(lambda it: self.add_field_text(it.data(Qt.ItemDataRole.UserRole), None))
        ll.addWidget(self.fields, 2)
        split.addWidget(left)

        self.canvas = Canvas()
        self.canvas.selection.connect(self._canvas_selected)
        self.canvas.committed.connect(self._canvas_committed)
        self.canvas.dropped_field.connect(self.add_field_text)
        split.addWidget(self.canvas)

        self.inspector = Inspector()
        self.inspector.edit.connect(self._inspector_edit)
        self.inspector.board_edit.connect(self._board_edit)
        self.inspector.browse_image.connect(self._browse_image)
        self.inspector.try_anim.connect(self._try_anim)
        self.inspector.open_library.connect(self._open_library)
        make_narrow(self.inspector)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self.inspector)
        scroll.setMinimumWidth(320)
        split.addWidget(scroll)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setStretchFactor(2, 0)
        split.setSizes([220, 900, 360])
        root.addWidget(split, 1)

        # Shortcuts (only while this tab has focus) ----------------------------------
        def sc(keys, fn):
            s = QShortcut(QKeySequence(keys), self)
            s.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            s.activated.connect(fn)
        sc(QKeySequence.StandardKey.Undo, self.undo)
        sc(QKeySequence.StandardKey.Redo, self.redo)
        sc("Ctrl+Y", self.redo)
        sc("Ctrl+D", self.duplicate)
        sc(QKeySequence.StandardKey.Copy, self.copy)
        sc(QKeySequence.StandardKey.Paste, self.paste)
        sc(QKeySequence.StandardKey.Cut, self.cut)
        sc(QKeySequence.StandardKey.SelectAll, self.select_all)
        sc("Esc", lambda: self.canvas.select_ids([]))
        for key, dx, dy in (("Left", -1, 0), ("Right", 1, 0), ("Up", 0, -1), ("Down", 0, 1)):
            sc(key, lambda dx=dx, dy=dy: self.nudge(dx, dy))
            sc("Shift+" + key, lambda dx=dx, dy=dy: self.nudge(dx * 10, dy * 10))
        self.canvas.installEventFilter(self)

        session.boards.connect(self.rebuild_boards)
        session.structure.connect(self.rebuild_fields)
        session.snapshot.connect(self._on_snapshot)
        session.board_edited.connect(self._external_edit)
        session.animations.connect(self._animations_changed)
        self.rebuild_boards()
        self.rebuild_fields()
        self._animations_changed()

    # ----- helpers -------------------------------------------------------------
    @property
    def board(self) -> Optional[Board]:
        return self.canvas.board

    def hist(self) -> History:
        return self.history.setdefault(self.board.id, History())

    def eventFilter(self, obj, ev):
        from PyQt6.QtCore import QEvent
        if obj is self.canvas and ev.type() == QEvent.Type.KeyPress and ev.key() in (Qt.Key.Key_Delete,
                                                                                     Qt.Key.Key_Backspace):
            self.delete_selected()
            return True
        return False

    def _commit(self, tag: Optional[str] = None, structural: bool = False, before: Optional[dict] = None) -> None:
        """After a model change: refresh the canvas and lists, tell the session."""
        if structural:
            self.canvas.set_board(self.board)
        else:
            self.canvas.refresh()
        self._fill_layers()
        self._update_inspector()
        self._update_buttons()
        self._editing_self = True
        self.session.board_changed(self.board)
        self._editing_self = False

    def _push(self, tag: Optional[str] = None) -> None:
        if self.board is not None:
            self.hist().push(self.board, tag)

    def _update_buttons(self) -> None:
        has = self.board is not None
        sel = bool(self.canvas.selected_ids()) if has else False
        self.b_delete.setEnabled(sel)
        self.b_undo.setEnabled(has and bool(self.history.get(self.board.id, History()).undo))
        self.b_redo.setEnabled(has and bool(self.history.get(self.board.id, History()).redo))
        self.b_del_board.setEnabled(len(self.session.project.boards) > 1)

    # ----- boards --------------------------------------------------------------
    def rebuild_boards(self) -> None:
        cur = self.board_pick.currentData()
        self.board_pick.blockSignals(True)
        self.board_pick.clear()
        for b in self.session.project.boards:
            self.board_pick.addItem(b.name, b.id)
        i = self.board_pick.findData(cur)
        self.board_pick.setCurrentIndex(i if i >= 0 else 0)
        self.board_pick.blockSignals(False)
        self._board_picked()

    def _board_picked(self, *_):
        bid = self.board_pick.currentData()
        b = self.session.board(bid) if bid else None
        if b is not self.canvas.board:
            self.canvas._fit_pending = True
        self.canvas.set_board(b, keep_selection=False)
        self._fill_layers()
        self._update_inspector()
        self._update_buttons()

    def select_board(self, bid: str) -> None:
        i = self.board_pick.findData(bid)
        if i >= 0:
            self.board_pick.setCurrentIndex(i)

    def new_board(self, template: Optional[Board]) -> None:
        b = template.copy() if template else Board(name=f"Board {len(self.session.project.boards) + 1}")
        self.session.project.boards.append(b)
        self.session.boards_changed()
        self.select_board(b.id)

    def duplicate_board(self) -> None:
        if self.board is not None:
            b = self.board.copy()
            b.name = self.board.name + " copy"
            for e in b.elements:
                e.id = new_id()
            self.session.project.boards.append(b)
            self.session.boards_changed()
            self.select_board(b.id)

    def delete_board(self) -> None:
        boards = self.session.project.boards
        if self.board is None or len(boards) <= 1:
            return
        boards.remove(self.board)
        self.history.pop(self.board.id, None)
        self.session.boards_changed()

    def _board_edit(self, prop: str, value) -> None:
        b = self.board
        if b is None:
            return
        self._push("board-" + prop)
        if prop == "size":
            b.width, b.height = value
        elif prop == "width":
            b.width = int(value)
        elif prop == "height":
            b.height = int(value)
        elif prop == "name":
            b.name = value
            i = self.board_pick.findData(b.id)
            if i >= 0:
                self.board_pick.setItemText(i, value)
            self.session.boards.emit()
        elif prop == "background":
            b.background = value
        self.canvas._fit_pending = prop in ("size", "width", "height")
        self._commit(structural=True)

    # ----- lists ---------------------------------------------------------------
    def rebuild_fields(self) -> None:
        self.fields.clear()
        snap = self.session.engine.snapshot()
        values = snap.values if snap else {}
        for key in values:
            top = key in (snap.types if snap else {})
            it = QListWidgetItem(key if top else "   " + key)
            it.setData(Qt.ItemDataRole.UserRole, key)
            it.setToolTip(snap.labels.get(key, key) if top else "Part of " + key.rsplit(".", 1)[0])
            if not top:
                it.setForeground(QColor(theme.CURRENT["muted"]))
            self.fields.addItem(it)
        self.inspector.set_fields(list(values), values)
        self.canvas.values = dict(values)
        self.canvas.scene().update()
        self._update_inspector()

    def _fill_layers(self) -> None:
        self.layers.blockSignals(True)
        self.layers.clear()
        if self.board is not None:
            sel = set(self.canvas.selected_ids())
            for e in reversed(self.board.elements):
                it = QTreeWidgetItem([e.name or e.kind.title(), "", ""])
                it.setData(0, Qt.ItemDataRole.UserRole, e.id)
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(1, Qt.CheckState.Checked if e.visible else Qt.CheckState.Unchecked)
                it.setCheckState(2, Qt.CheckState.Checked if e.locked else Qt.CheckState.Unchecked)
                if e.show_when:
                    it.setToolTip(0, f"Shown when {e.show_when} is on")
                self.layers.addTopLevelItem(it)
                it.setSelected(e.id in sel)
        self.layers.blockSignals(False)

    def _layers_selected(self):
        ids = [it.data(0, Qt.ItemDataRole.UserRole) for it in self.layers.selectedItems()]
        self.canvas.select_ids(ids)

    def _layer_edited(self, item: QTreeWidgetItem, col: int):
        e = self.board.element(item.data(0, Qt.ItemDataRole.UserRole)) if self.board else None
        if e is None:
            return
        self._push("layer")
        if col == 0:
            e.name = item.text(0).strip()
        elif col == 1:
            e.visible = item.checkState(1) == Qt.CheckState.Checked
        elif col == 2:
            e.locked = item.checkState(2) == Qt.CheckState.Checked
        self._commit()

    # ----- selection & inspector ---------------------------------------------------
    def _canvas_selected(self, ids: List[str]):
        self.layers.blockSignals(True)
        for i in range(self.layers.topLevelItemCount()):
            it = self.layers.topLevelItem(i)
            it.setSelected(it.data(0, Qt.ItemDataRole.UserRole) in ids)
        self.layers.blockSignals(False)
        self._update_inspector()
        self._update_buttons()

    def _selected(self) -> List[Element]:
        if self.board is None:
            return []
        ids = set(self.canvas.selected_ids())
        return [e for e in self.board.elements if e.id in ids]

    def _update_inspector(self):
        els = self._selected()
        if els:
            have = set(self.session.values())
            missing = [k for k in dict.fromkeys(k for e in els for k in e.keys()) if k not in have]
            self.inspector.show_elements(els, missing)
        else:
            self.inspector.show_board(self.board)

    def _inspector_edit(self, prop: str, value) -> None:
        els = self._selected()
        if not els:
            return
        if all(getattr(e, prop) == value for e in els):
            return
        self._push(prop)
        for e in els:
            setattr(e, prop, value)
        self._commit(structural=prop in ("x", "y", "w", "h", "locked"))

    def _lib(self):
        return library(self.session.project.animations)

    def _try_anim(self, name: str):
        a = self._lib().get(name)
        if a is None:
            return
        for e in self._selected():
            self.canvas.play(e.id, a)

    def _open_library(self):
        self.library_requested.emit()

    def _animations_changed(self):
        self.inspector.set_animations(self._lib())
        self._update_inspector()

    def _browse_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a picture", "",
                                              "Pictures (*.png *.jpg *.jpeg *.gif *.webp *.svg *.bmp)")
        if path:
            self.inspector.i_src.setText(path)
            self._inspector_edit("src", path)

    def _canvas_committed(self, tag: str):
        if tag == "move":
            # Snapshot first (model still has the old positions), then apply.
            self._push(None)
            self.canvas.apply_positions()
        elif tag == "resize":
            self._push(None)
            self.canvas.apply_resize()
        self._commit()

    # ----- element commands -----------------------------------------------------
    def _place(self, e: Element, center: Optional[QPointF]) -> None:
        b = self.board
        if center is None:
            vc = self.canvas.mapToScene(self.canvas.viewport().rect().center())
            center = vc if QRectF(0, 0, b.width, b.height).contains(vc) else QPointF(b.width / 2, b.height / 2)
        e.x = round(center.x() - e.w / 2)
        e.y = round(center.y() - e.h / 2)

    def add_element(self, kind: str) -> None:
        if self.board is None:
            return
        self._push()
        if kind == "text":
            e = Element(kind="text", name="Text", text="Text", w=360, h=90, size=64, weight=800)
        elif kind == "box":
            e = Element(kind="box", name="Box", w=300, h=120, fill="#18211e", radius=3)
        else:
            e = Element(kind="image", name="Picture", w=240, h=240)
        self._place(e, None)
        self.board.elements.append(e)
        self._commit(structural=True)
        self.canvas.select_ids([e.id])

    def add_field_text(self, key: str, pos: Optional[QPointF]) -> None:
        if self.board is None or not key:
            return
        snap = self.session.engine.snapshot()
        ftype = snap.types.get(key, "") if snap else ""
        self._push()
        if ftype == "image":
            e = Element(kind="image", name=snap.labels.get(key, key), src="{%s}" % key, w=200, h=200)
        else:
            big = ftype in ("counter", "clock")
            e = Element(kind="text", name=(snap.labels.get(key, key) if snap else key), text="{%s}" % key,
                        w=320 if big else 420, h=120 if big else 80, size=96 if big else 56, weight=900)
        self._place(e, pos)
        self.board.elements.append(e)
        self._commit(structural=True)
        self.canvas.select_ids([e.id])

    def delete_selected(self) -> None:
        ids = set(self.canvas.selected_ids())
        if not ids:
            return
        self._push()
        self.board.elements = [e for e in self.board.elements if e.id not in ids]
        self._commit(structural=True)

    def duplicate(self) -> None:
        els = self._selected()
        if not els:
            return
        self._push()
        new = []
        for e in els:
            c = e.copy()
            c.x += 20
            c.y += 20
            c.name = (e.name or e.kind.title()) + " copy"
            new.append(c)
        self.board.elements.extend(new)
        self._commit(structural=True)
        self.canvas.select_ids([c.id for c in new])

    def copy(self) -> None:
        els = self._selected()
        if els:
            md = QMimeData()
            data = json.dumps([e.to_dict() for e in els])
            md.setData(MIME, data.encode("utf-8"))
            md.setText(data)
            QApplication.clipboard().setMimeData(md)

    def cut(self) -> None:
        self.copy()
        self.delete_selected()

    def paste(self) -> None:
        md = QApplication.clipboard().mimeData()
        if self.board is None or md is None or not md.hasFormat(MIME):
            return
        try:
            items = json.loads(md.data(MIME).data().decode("utf-8"))
            els = [Element.from_dict(d) for d in items]
        except (ValueError, TypeError):
            return
        self._push()
        for e in els:
            e.id = new_id()
            e.x += 20
            e.y += 20
        self.board.elements.extend(els)
        self._commit(structural=True)
        self.canvas.select_ids([e.id for e in els])

    def select_all(self) -> None:
        if self.board is not None:
            self.canvas.select_ids([e.id for e in self.board.elements])

    def nudge(self, dx: float, dy: float) -> None:
        els = [e for e in self._selected() if not e.locked]
        if not els:
            return
        self._push("nudge")
        for e in els:
            e.x = round(e.x + dx, 2)
            e.y = round(e.y + dy, 2)
        self._commit()

    def arrange(self, fn) -> None:
        ids = self.canvas.selected_ids()
        if not ids:
            self.session.message.emit("Select elements to arrange first. One element aligns to the board.", False)
            return
        self._push()
        fn(self.board, ids)
        self._commit()

    def reorder(self, where: str) -> None:
        ids = self.canvas.selected_ids()
        if not ids:
            return
        self._push()
        seq = ids if where in ("front", "backward") else list(reversed(ids))
        for eid in seq:
            self.board.reorder(eid, where)
        self._commit(structural=True)

    def undo(self) -> None:
        self._step(True)

    def redo(self) -> None:
        self._step(False)

    def _step(self, back: bool) -> None:
        if self.board is None:
            return
        state = self.hist().step(self.board, back)
        if state is None:
            return
        restored = Board.from_dict(state)
        b = self.board
        b.name, b.width, b.height, b.background = restored.name, restored.width, restored.height, restored.background
        b.elements = restored.elements
        self._commit(structural=True)

    # ----- live values ------------------------------------------------------------
    def _on_snapshot(self, snap, changed):
        self.canvas.values = snap.values
        self.canvas.fx = snap.fx
        if self.board is not None and not self.canvas.show_templates:
            keys = set(self.board.keys())
            if changed & keys or "#fx" in changed:
                self.canvas.scene().update()

    def _toggle_values(self, on: bool):
        self.canvas.show_templates = not on
        self.canvas.scene().update()

    def _toggle_snap(self, on: bool):
        self.canvas.snap_on = on
        self.canvas.grid_on = on
        self.canvas.scene().update()

    def _grid_changed(self, v: int):
        self.canvas.grid = v
        self.canvas.scene().update()

    def _external_edit(self, bid: str):
        if getattr(self, "_editing_self", False):
            return
        if self.board is not None and bid == self.board.id:
            self.canvas.set_board(self.board)
            self._fill_layers()
            self._update_inspector()
