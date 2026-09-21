"""The desktop pet: a crisp HiDPI portrait that stays on top of other windows.

Two rendering rules keep the avatar looking good, and both used to be wrong:

* the 1254x1254 asset is down-scaled **once**, with ``SmoothTransformation``,
  into a cached pixmap sized for the current device pixel ratio, instead of
  being re-scaled every frame by a scaled ``QPainter`` (that produced the
  blocky, washed-out look);
* no circular decoration is painted around the head.  The skin colour lives in
  the badge under the portrait and in a soft rim that only appears while
  hovering or translating, so the artwork itself is never ringed.

On top of that the portrait is *rigged* (see :mod:`scholarpet.face`): it blinks
on its own schedule, mouths along while a translation is running, and its eyes
follow the cursor.  All of that rides on the same cached pixmap, so the idle
cost is one small composite per frame.
"""

from __future__ import annotations

import math
import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QCursor, QFont, QIcon, QPainter, QPainterPath,
                           QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from .face import FaceClock, face_for, load_rig
from .winutil import raise_above_all

# Geometry, all relative to the widget width.  The portrait keeps a small
# transparent margin so the hover rim and the idle sway never get clipped.
ART_RATIO = 0.90
ART_TOP = 0.025
BADGE_HEIGHT = 26
BADGE_GAP = 6

# 30fps: a blink lasts 0.15s, and at 60ms per frame it would land in three
# steps and read as a flicker rather than a blink.
FRAME_MS = 33
IDLE_FRAME_MS = 1000

_HAIBARA = None
_SCALED: dict[tuple, QPixmap] = {}
_TINTED: dict[tuple, QPixmap] = {}


def _asset_path() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "haibara_head.png"


def _haibara_pixmap() -> QPixmap:
    global _HAIBARA
    if _HAIBARA is None:
        path = _asset_path()
        _HAIBARA = QPixmap(str(path)) if path.is_file() else QPixmap()
    return _HAIBARA


def avatar_pixmap(logical_side, dpr=1.0) -> QPixmap:
    """High quality, DPR aware copy of the portrait for ``logical_side`` pixels.

    Cached by physical size so a repainting widget never pays for a rescale.
    """
    source = _haibara_pixmap()
    logical = float(logical_side)
    if source.isNull() or logical <= 1:
        return source
    dpr = max(1.0, float(dpr))
    physical = max(24, int(round(logical * dpr)))
    key = (physical, round(dpr, 3))
    cached = _SCALED.get(key)
    if cached is None:
        cached = source.scaled(physical, physical, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        cached.setDevicePixelRatio(physical / logical)
        if len(_SCALED) > 24:
            _SCALED.clear()
        _SCALED[key] = cached
    return cached


def _tinted(pixmap: QPixmap, color) -> QPixmap:
    """A flat silhouette of ``pixmap`` in ``color`` (used for the hover rim)."""
    accent = QColor(color)
    key = (pixmap.cacheKey(), accent.name(), QColor(color).alpha())
    cached = _TINTED.get(key)
    if cached is not None:
        return cached
    out = QPixmap(pixmap.size())
    out.setDevicePixelRatio(pixmap.devicePixelRatio())
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(out.rect(), accent)
    painter.end()
    if len(_TINTED) > 24:
        _TINTED.clear()
    _TINTED[key] = out
    return out


def art_box(size):
    """Return ``(left, top, side)`` of the portrait for a widget ``size`` wide."""
    side = size * ART_RATIO
    return (size - side) / 2.0, size * ART_TOP, side


def pin_above_all(widget, enabled=True):
    """Best effort: put ``widget`` back on top of every other window."""
    if enabled:
        return raise_above_all(widget)
    return False


def _paint_portrait(painter, size, color, phase, busy=False, dpr=1.0, hover=False,
                    enabled=True, frame=None):
    pixmap = frame if frame is not None else avatar_pixmap(size * ART_RATIO, dpr)
    if pixmap is None or pixmap.isNull():
        return False
    accent = QColor(color)
    left, top, side = art_box(size)
    bob = math.sin(phase) * 0.9                            # sub-pixel on purpose
    centre = QPointF(size / 2.0, top + side / 2.0 + bob)

    ratio = pixmap.devicePixelRatio() or 1.0
    art_w = pixmap.width() / ratio
    art_h = pixmap.height() / ratio

    scale = 1.0 + 0.006 * math.sin(phase * 0.55)          # gentle breathing
    if hover:
        scale *= 1.04
    if busy:
        scale *= 1.0 + 0.012 * math.sin(phase * 2.4)

    painter.save()
    painter.translate(centre)
    painter.rotate(math.sin(phase * 0.42) * 1.1)          # barely-there sway
    painter.scale(scale, scale)
    target = QPointF(-art_w / 2, -art_h / 2)
    if enabled and (hover or busy):
        # A soft rim in the skin colour that follows the hair, so a colour
        # change is obvious without ever drawing a circle around the art.
        rim = _tinted(pixmap, accent)
        spread = 1.10 if busy else 1.085
        painter.save()
        painter.setOpacity(0.60 if busy else 0.45)
        painter.scale(spread, spread)
        painter.drawPixmap(target, rim)
        painter.restore()
    painter.drawPixmap(target, pixmap)
    painter.restore()
    return True


def _paint_owl(painter, size, color, phase, busy):
    """The vector owl, kept as a switchable alternative to the portrait."""
    painter.save()
    painter.scale(size / 120.0, size / 120.0)
    c = QColor(color)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(25, 34, 64, 26))
    painter.drawEllipse(QRectF(28, 104, 64, 9))
    painter.setBrush(c.darker(118))
    ears = QPainterPath()
    ears.moveTo(27, 40); ears.lineTo(22, 13); ears.lineTo(48, 30)
    ears.moveTo(73, 30); ears.lineTo(98, 13); ears.lineTo(94, 42)
    painter.drawPath(ears)
    painter.setBrush(c)
    painter.drawRoundedRect(QRectF(20, 27, 80, 74), 31, 31)
    painter.setBrush(c.lighter(126))
    painter.drawEllipse(QRectF(10, 53, 24, 33)); painter.drawEllipse(QRectF(87, 53, 24, 33))
    painter.setBrush(QColor("#f5f5ff"))
    painter.drawEllipse(QRectF(28, 40, 33, 36)); painter.drawEllipse(QRectF(59, 40, 33, 36))
    painter.setBrush(QColor("#263051"))
    blink = math.sin(phase / 2) > .993 and not busy
    for x in (44, 75):
        if blink:
            painter.drawRoundedRect(QRectF(x - 5, 57, 10, 3), 1, 1)
        else:
            painter.drawEllipse(QRectF(x - 5, 51, 10, 14))
            painter.setBrush(QColor("white")); painter.drawEllipse(QRectF(x - 2, 52, 3, 4))
            painter.setBrush(QColor("#263051"))
    painter.setBrush(QColor("#ffbd70"))
    beak = QPainterPath(); beak.moveTo(55, 68); beak.lineTo(65, 68); beak.lineTo(60, 75); beak.closeSubpath()
    painter.drawPath(beak)
    painter.setPen(QPen(QColor("#ffffff"), 2))
    painter.drawLine(43, 85, 58, 89); painter.drawLine(58, 89, 58, 100)
    painter.drawLine(61, 89, 78, 85); painter.drawLine(61, 89, 61, 100)
    painter.restore()


def paint_pet(painter, size, color, phase=0, busy=False, use_avatar=True, dpr=1.0,
              hover=False, label=None, tinted_badge=True, frame=None):
    """Paint the whole pet at ``size`` logical pixels wide.

    ``label`` draws the status badge under the portrait; the badge carries the
    skin colour so a colour change stays visible without ringing the artwork.
    ``frame`` is an already-rigged portrait (see :mod:`scholarpet.face`).
    """
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    accent = QColor(color)

    drew_portrait = False
    if use_avatar:
        drew_portrait = _paint_portrait(painter, size, color, phase, busy, dpr, hover,
                                        frame=frame)
    if not drew_portrait:
        _paint_owl(painter, size, color, phase, busy)
    painter.restore()

    if label is None:
        return
    badge = badge_rect(size)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    if busy:
        painter.setBrush(accent)
    elif tinted_badge:
        painter.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 46))
    else:
        painter.setBrush(QColor(255, 255, 255, 230))
    painter.drawRoundedRect(QRectF(badge), badge.height() / 2, badge.height() / 2)
    painter.setPen(accent.darker(150) if not busy else QColor("#ffffff"))
    painter.setFont(QFont("Microsoft YaHei UI", 9))
    painter.drawText(QRectF(badge), Qt.AlignmentFlag.AlignCenter, label)
    painter.restore()


def badge_rect(size):
    """The clickable status strip under the portrait."""
    width = size - 12
    return QRect(6, int(size + BADGE_GAP), int(width), BADGE_HEIGHT)


def pet_icon(color="#6475ed", size=128):
    pix = QPixmap(size, size); pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    paint_pet(painter, size, color)
    painter.end()
    return QIcon(pix)


class Pet(QWidget):
    full = Signal(); region = Signal(); settings_requested = Signal()
    reader_requested = Signal(); clipboard_requested = Signal(); quit_requested = Signal()

    def __init__(self, settings):
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setWindowTitle("研译 · 桌宠")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setMouseTracking(True)
        self.phase = 0; self.busy = False; self.dragging = False; self.double_click = False
        self.hover = False; self.origin = None
        self.rig = load_rig()
        self.clock = FaceClock()
        self.expression = (1.0, 0.0, (0.0, 0.0))
        self._last_tick = time.monotonic()
        self.click_timer = QTimer(self); self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(self.full.emit)
        self.animation = QTimer(self); self.animation.timeout.connect(self.tick)
        self.apply(settings)
        self.setToolTip("研译 ScholarPet · 灰原哀\n任意划选文字：翻译选中内容\n单击头像：整屏翻译\n点击下方「框选翻译」：拖动框选做 OCR\n双击：设置\n右键：更多功能\n拖动：移动桌宠")

    # -- geometry ---------------------------------------------------------
    @staticmethod
    def preferred_height(size):
        return int(size + BADGE_GAP + BADGE_HEIGHT)

    def apply(self, settings):
        self.settings = settings
        size = settings["pet_size"]
        self.resize(size, self.preferred_height(size))
        self.setWindowOpacity(settings["opacity"] / 100)
        alive = bool(settings["animate"])
        self.clock.alive = alive
        self.animation.start(FRAME_MS if alive else IDLE_FRAME_MS)
        self.update()

    def tick(self):
        now = time.monotonic()
        dt, self._last_tick = now - self._last_tick, now
        if self.settings["animate"] or self.busy:
            self.phase += .12
        self.expression = self.clock.update(dt, talking=self.busy, look=self._look())
        if self.settings["animate"] or self.busy:
            self.update()

    def _look(self):
        """Where the pet should be looking: the cursor, if it is nearby."""
        try:
            cursor = QCursor.pos()
        except RuntimeError:
            return None
        centre = self.mapToGlobal(self.rect().center())
        dx = cursor.x() - centre.x()
        dy = cursor.y() - centre.y()
        reach = max(120.0, self.width() * 5.0)
        if math.hypot(dx, dy) > reach:
            return None
        return (max(-1.0, min(1.0, dx / (self.width() * 1.8))),
                max(-1.0, min(1.0, dy / (self.height() * 1.8))))

    # -- painting ---------------------------------------------------------
    def frame(self):
        """The rigged portrait for the current size, or None for the vector owl."""
        if not self.settings.get("pet_avatar", True):
            return None
        try:
            portrait = avatar_pixmap(self.width() * ART_RATIO, self.devicePixelRatioF())
            face = face_for(portrait, _haibara_pixmap(), self.rig)
        except (RuntimeError, ValueError):
            return None
        return face.render(*self.expression)

    def paintEvent(self, event):
        label = "翻译中…" if self.busy else "框选翻译 ⌗"
        painter = QPainter(self)
        try:
            paint_pet(painter, self.width(), self.settings["color"], self.phase, self.busy,
                      self.settings.get("pet_avatar", True), self.devicePixelRatioF(),
                      self.hover, label, frame=self.frame())
        finally:
            painter.end()

    # -- showing ----------------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        pin_above_all(self, self.settings.get("topmost", True))

    def enterEvent(self, event):
        self.hover = True; self.update()

    def leaveEvent(self, event):
        self.hover = False; self.update()

    # -- interaction ------------------------------------------------------
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.origin = e.globalPosition().toPoint(); self.start_pos = self.pos(); self.dragging = False

    def mouseMoveEvent(self, e):
        if self.origin is not None and e.buttons() & Qt.MouseButton.LeftButton:
            delta = e.globalPosition().toPoint() - self.origin
            if delta.manhattanLength() > QApplication.startDragDistance():
                self.dragging = True; self.click_timer.stop()
            if self.dragging:
                self.move(self.start_pos + delta)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if not self.dragging and not self.double_click:
            # A blink acknowledges the click, the way a pet looks up when you
            # touch it.  Cheap, and it makes the portrait feel responsive.
            self.clock.blink()
            self.update()
            if badge_rect(self.width()).contains(e.position().toPoint()):
                self.region.emit()
            else:
                self.click_timer.start(QApplication.doubleClickInterval() + 30)
        self.origin = None; self.double_click = False

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.click_timer.stop(); self.double_click = True; self.settings_requested.emit()

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        for label, callback in [("整屏翻译", self.full.emit),
                                ("框选翻译（OCR）", self.region.emit),
                                ("翻译剪贴板文字", self.clipboard_requested.emit),
                                ("查看上次中英对照", self.reader_requested.emit),
                                ("外观与翻译设置", self.settings_requested.emit)]:
            menu.addAction(label, callback)
        menu.addSeparator(); menu.addAction("退出研译", self.quit_requested.emit)
        menu.exec(e.globalPos())
