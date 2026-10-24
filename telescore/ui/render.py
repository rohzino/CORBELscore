"""
Paint boards with QPainter: the builder canvas, the Operate preview, the
projector window and PNG output all use these functions, so what the operator
sees is what goes to air. The browser source (outputs/overlay.py) follows the
same rules: same defaults, same templates, same colour resolution, same
shrink-to-fit.
"""

from __future__ import annotations

import os
from typing import Dict, Mapping, Optional, Tuple

from PyQt6.QtCore import QPointF, QRectF, QSizeF, Qt
from PyQt6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen)

from ..core.board import Board, Element, render_template, resolve_color
from .theme import set_tabular

__all__ = ["qcolor", "paint_board", "paint_element", "element_font", "ImageCache", "render_png",
           "fit_rect"]

WEIGHTS = (100, 200, 300, 400, 500, 600, 700, 800, 900)


def qcolor(hexstr: str) -> Optional[QColor]:
    """#rrggbb or #rrggbbaa -> QColor. (QColor itself reads 8 digits as
    #aarrggbb, the opposite of CSS, so it is parsed by hand.)"""
    if not hexstr:
        return None
    h = hexstr.lstrip("#")
    try:
        if len(h) == 6:
            return QColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        if len(h) == 8:
            return QColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16))
    except ValueError:
        return None
    return None


class ImageCache:
    """Pixmaps by path, reloaded when the file changes on disk."""

    def __init__(self) -> None:
        self._cache: Dict[str, Tuple[float, QImage]] = {}

    def get(self, path: str) -> Optional[QImage]:
        if not path:
            return None
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return None
        hit = self._cache.get(path)
        if hit and hit[0] == mtime:
            return hit[1]
        img = QImage(path)
        if img.isNull():
            return None
        self._cache[path] = (mtime, img)
        return img


DEFAULT_IMAGES = ImageCache()


def element_font(e: Element, size: Optional[float] = None) -> QFont:
    f = QFont(e.font or "Archivo")
    px = max(1.0, float(size if size is not None else e.size))
    f.setPixelSize(max(1, round(px)))
    w = min(WEIGHTS, key=lambda v: abs(v - int(e.weight or 400)))
    f.setWeight(QFont.Weight(w))
    f.setItalic(bool(e.italic))
    if e.uppercase:
        f.setCapitalization(QFont.Capitalization.AllUppercase)
    if e.tracking:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, float(e.tracking) * px)
    if e.tabular:
        set_tabular(f)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def _fitted_font(e: Element, text: str, avail_w: float, avail_h: float) -> QFont:
    f = element_font(e)
    if not e.fit or not text:
        return f
    size = float(e.size)
    for _ in range(6):
        fm = QFontMetricsF(f)
        w = fm.horizontalAdvance(text)
        h = fm.height()
        if w <= avail_w + 0.5 and h <= avail_h + 0.5:
            break
        ratio = min(avail_w / max(w, 1.0), avail_h / max(h, 1.0), 0.97)
        size = max(6.0, size * ratio)
        f = element_font(e, size)
        if size <= 6.0:
            break
    return f


def fit_rect(src: QSizeF, dst: QRectF) -> QRectF:
    """Largest rect with ``src``'s aspect ratio centred in ``dst``."""
    if src.width() <= 0 or src.height() <= 0:
        return QRectF(dst)
    s = min(dst.width() / src.width(), dst.height() / src.height())
    w, h = src.width() * s, src.height() * s
    return QRectF(dst.x() + (dst.width() - w) / 2, dst.y() + (dst.height() - h) / 2, w, h)


def paint_element(p: QPainter, e: Element, values: Mapping[str, str], images: ImageCache = DEFAULT_IMAGES,
                  show_templates: bool = False) -> None:
    """Paint ``e`` in board coordinates. ``show_templates`` draws the raw
    template text (the builder's design view) instead of live values."""
    rect = QRectF(e.x, e.y, e.w, e.h)
    p.save()
    p.setOpacity(max(0.0, min(1.0, float(e.opacity))))
    fill = qcolor(resolve_color(e.fill, values))
    stroke = qcolor(resolve_color(e.stroke, values))
    sw = float(e.stroke_width or 0)
    path = QPainterPath()
    if e.radius:
        path.addRoundedRect(rect, float(e.radius), float(e.radius))
    else:
        path.addRect(rect)
    if fill is not None:
        p.fillPath(path, QBrush(fill))

    if e.kind == "text":
        text = e.text if show_templates else render_template(e.text, values)
        if text:
            inset = float(e.padding or 0) + sw
            area = rect.adjusted(inset, inset, -inset, -inset)
            f = _fitted_font(e, text, area.width(), area.height())
            p.setFont(f)
            col = qcolor(resolve_color(e.color, values)) or QColor("#ffffff")
            p.setPen(col)
            h = {"left": Qt.AlignmentFlag.AlignLeft, "right": Qt.AlignmentFlag.AlignRight}.get(
                e.align, Qt.AlignmentFlag.AlignHCenter)
            v = {"top": Qt.AlignmentFlag.AlignTop, "bottom": Qt.AlignmentFlag.AlignBottom}.get(
                e.valign, Qt.AlignmentFlag.AlignVCenter)
            p.setClipRect(rect)
            p.drawText(area, h.value | v.value | Qt.TextFlag.TextSingleLine.value, text)
            p.setClipping(False)
    elif e.kind == "image":
        src = e.src if show_templates else render_template(e.src, values)
        img = images.get(src.strip()) if src and not show_templates else None
        if img is not None:
            target = fit_rect(QSizeF(img.size()), rect) if e.contain else rect
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p.setClipPath(path)
            p.drawImage(target, img)
            p.setClipping(False)
        elif show_templates or src:
            # Placeholder so an empty picture is still findable in the builder.
            p.setPen(QPen(QColor(128, 128, 128, 160), 1, Qt.PenStyle.DashLine))
            p.drawRect(rect.adjusted(0.5, 0.5, -0.5, -0.5))

    if stroke is not None and sw > 0:
        pen = QPen(stroke, sw)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        half = sw / 2
        inner = rect.adjusted(half, half, -half, -half)
        if e.radius:
            p.drawRoundedRect(inner, max(0.0, e.radius - half), max(0.0, e.radius - half))
        else:
            p.drawRect(inner)
    p.restore()


def paint_board(p: QPainter, board: Board, values: Mapping[str, str], target: QRectF,
                images: ImageCache = DEFAULT_IMAGES, letterbox: Optional[QColor] = None,
                checker: bool = False, show_templates: bool = False) -> QRectF:
    """Paint ``board`` scaled to fit ``target``. Returns the rect the canvas
    occupies. ``checker`` draws a transparency checkerboard behind a board
    with no background, so a keying graphic is visible in the UI."""
    canvas = fit_rect(QSizeF(board.width, board.height), target)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    if letterbox is not None:
        p.fillRect(target, letterbox)
    bg = qcolor(resolve_color(board.background, values))
    if bg is not None:
        p.fillRect(canvas, bg)
    elif checker:
        draw_checker(p, canvas)
    p.translate(canvas.topLeft())
    s = canvas.width() / board.width
    p.scale(s, s)
    p.setClipRect(QRectF(0, 0, board.width, board.height))
    for e in board.elements:
        if show_templates:
            if not e.visible:
                continue
        elif not e.shown(values):
            continue
        paint_element(p, e, values, images, show_templates)
    p.restore()
    return canvas


def draw_checker(p: QPainter, rect: QRectF, size: float = 12.0) -> None:
    a, b = QColor(46, 52, 50), QColor(36, 41, 39)
    p.save()
    p.setClipRect(rect)
    p.fillRect(rect, a)
    y = rect.top()
    row = 0
    while y < rect.bottom():
        x = rect.left() + (size if row % 2 else 0)
        while x < rect.right():
            p.fillRect(QRectF(x, y, size, size), b)
            x += size * 2
        y += size
        row += 1
    p.restore()


def render_png(board: Board, values: Mapping[str, str], path: str, images: ImageCache = DEFAULT_IMAGES) -> bool:
    """Write ``board`` at its own size as a transparent PNG."""
    img = QImage(board.width, board.height, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    paint_board(p, board, values, QRectF(0, 0, board.width, board.height), images)
    p.end()
    tmp = path + ".tmp.png"
    if not img.save(tmp, "PNG"):
        return False
    try:
        os.replace(tmp, path)
    except OSError:
        return False
    return True


def board_point(canvas: QRectF, board: Board, pt: QPointF) -> QPointF:
    s = canvas.width() / board.width
    return QPointF((pt.x() - canvas.x()) / s, (pt.y() - canvas.y()) / s)
