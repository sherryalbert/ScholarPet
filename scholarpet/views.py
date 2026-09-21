import html
from PySide6.QtCore import Qt, QRect, QRectF, QPoint, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QFontMetrics, QKeySequence, QShortcut, QCursor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QTextBrowser, QApplication, QFrame, QToolTip, QPlainTextEdit)

from .winutil import raise_above_all

STYLE = """QWidget { font-family: 'Microsoft YaHei UI'; font-size: 14px; color: #28334d; }
QWidget#surface { background: #f5f7fc; }
QLabel#eyebrow { color: #6776df; font-size: 12px; font-weight: 600; }
QLabel#title { font-size: 27px; font-weight: 700; color: #202a44; }
QLabel#muted { color: #69748b; }
QPushButton { background: white; border: 1px solid #dee3ef; border-radius: 9px; padding: 9px 15px; }
QPushButton:hover { background: #edf0ff; border-color: #adb8f8; }
QPushButton#primary { background: #6574e7; color: white; border: 0; }
QPushButton#primary:hover { background: #5364d6; }
QPushButton:disabled { color: #9ba5b5; }
QTextBrowser, QPlainTextEdit, QLineEdit, QComboBox, QSpinBox { background: white; border: 1px solid #dee3ef; border-radius: 8px; padding: 7px; }
QTabWidget::pane { border: 0; }
QTabBar::tab { padding: 10px 18px; background: #edf0f8; margin-right: 6px; border-radius: 6px; }
QTabBar::tab:selected { color: #5565d8; background: white; }
QCheckBox { spacing: 8px; }
"""


class Selection(QWidget):
    chosen = Signal(QRect)
    cancelled = Signal()

    def __init__(self, pixmap, geometry):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setWindowTitle("研译 · 拖动框选")
        self.image = pixmap; self.start = None; self.end = None
        self.setGeometry(geometry); self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.topmost = True
        QShortcut(QKeySequence("Escape"), self, activated=self.cancel)

    def showEvent(self, event):
        super().showEvent(event)
        if self.topmost:
            raise_above_all(self)

    def cancel(self):
        self.hide(); self.cancelled.emit(); self.deleteLater()

    def paintEvent(self, event):
        p = QPainter(self); p.drawPixmap(self.rect(), self.image)
        p.fillRect(self.rect(), QColor(14, 23, 44, 125))
        if self.start is not None and self.end is not None:
            r = self.selection_rect(self.end)
            p.save(); p.setClipRect(r); p.drawPixmap(self.rect(), self.image); p.restore()
            p.setPen(QPen(QColor("#7fe1ce"), 2)); p.drawRect(r)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor("#1f2b47"))
        r = QRect(24, 24, min(460, self.width() - 48), 52)
        p.drawRoundedRect(r, 12, 12); p.setPen(QColor("white")); p.setFont(QFont("Microsoft YaHei UI", 12))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, "拖动鼠标框选英文区域 · Esc 取消")

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            self.cancel()
        elif e.button() == Qt.MouseButton.LeftButton:
            self.start = e.position().toPoint(); self.end = self.start; self.update()

    def mouseMoveEvent(self, e):
        if self.start is not None:
            self.end = e.position().toPoint(); self.update()

    def mouseReleaseEvent(self, e):
        if self.start is not None and e.button() == Qt.MouseButton.LeftButton:
            r = self.selection_rect(e.position().toPoint())
            if r.width() >= 12 and r.height() >= 12:
                self.hide(); self.chosen.emit(r); self.deleteLater()
            else:
                self.start = None; self.end = None; self.update()

    def selection_rect(self, end):
        return QRect(min(self.start.x(),end.x()), min(self.start.y(),end.y()),
                     abs(self.start.x()-end.x()), abs(self.start.y()-end.y())).intersected(self.rect())


class Reader(QWidget):
    overlay_requested = Signal()
    retry_requested = Signal()
    cancel_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("研译 ScholarPet · 中英对照")
        self.setObjectName("surface"); self.setStyleSheet(STYLE); self.resize(850, 730)
        layout = QVBoxLayout(self); layout.setContentsMargins(28, 24, 28, 24); layout.setSpacing(13)
        eyebrow = QLabel("SCHOLARPET  /  RESEARCH COMPANION"); eyebrow.setObjectName("eyebrow"); layout.addWidget(eyebrow)
        title = QLabel("把理解，留给研究。"); title.setObjectName("title"); layout.addWidget(title)
        self.status = QLabel("单击桌宠翻译当前屏幕，或点击桌宠下方的「框选翻译」。")
        self.status.setWordWrap(True); self.status.setObjectName("muted"); layout.addWidget(self.status)
        row = QHBoxLayout()
        self.overlay_btn = QPushButton("原位覆盖"); self.overlay_btn.clicked.connect(self.overlay_requested)
        row.addWidget(self.overlay_btn)
        self.copy_btn = QPushButton("复制中文"); self.copy_btn.clicked.connect(self.copy_translation); row.addWidget(self.copy_btn)
        self.retry_btn = QPushButton("重新翻译"); self.retry_btn.clicked.connect(self.retry_requested); row.addWidget(self.retry_btn)
        row.addStretch()
        self.cancel_btn = QPushButton("取消任务"); self.cancel_btn.clicked.connect(self.cancel_requested); row.addWidget(self.cancel_btn)
        layout.addLayout(row)
        self.browser = QTextBrowser(); self.browser.setOpenExternalLinks(False); layout.addWidget(self.browser, 1)
        foot = QLabel("划选文字即可翻译   ·   单击桌宠＝整屏翻译   ·   点击桌宠下方「框选翻译」＝框选 OCR   ·   双击桌宠打开设置")
        foot.setWordWrap(True); foot.setObjectName("muted"); layout.addWidget(foot)
        self.translations = []; self.blocks = []; self.font_size = 15
        self.busy(False)

    def busy(self, value):
        self.cancel_btn.setVisible(value)
        self.copy_btn.setEnabled(not value and bool(self.translations))
        self.retry_btn.setEnabled(not value and bool(self.blocks))
        self.overlay_btn.setEnabled(not value and bool(self.translations))

    def show_message(self, title, detail):
        self.status.setText(title)
        self.browser.setHtml(f'<div style="padding:22px;line-height:1.8"><h2>{html.escape(title)}</h2><p>{html.escape(detail).replace(chr(10), "<br>")}</p></div>')

    def set_result(self, blocks, translations, service, elapsed, font_size=15):
        self.blocks = blocks; self.translations = translations; self.font_size = font_size
        self.status.setText(f"已翻译 {len(blocks)} 个文本块 · {elapsed:.1f} 秒 · {service}")
        cards = []
        for i, (block, chinese) in enumerate(zip(blocks, translations), 1):
            low = ' · 识别置信度较低，请核对原文' if block.get('confidence', 1) < .8 else ''
            cards.append(f'<p style="color:#8490aa;font-size:11px">{i:02d}{low}</p>'
                         f'<p style="color:#65718b;font-size:{font_size-1}px">{html.escape(block["text"])}</p>'
                         f'<p style="color:#202c47;font-size:{font_size+1}px;line-height:1.6">{html.escape(chinese).replace(chr(10), "<br>")}</p><hr style="color:#e6eaf4">')
        self.browser.setHtml('<div style="padding:12px;">' + ''.join(cards) + '</div>')
        self.busy(False)

    def copy_translation(self):
        QApplication.clipboard().setText('\n\n'.join(self.translations))
        self.status.setText("中文译文已复制到剪贴板")


class SelectionPopup(QWidget):
    """Non-modal translation bubble placed beside a user's text selection.

    Placement rules that matter for reading: the bubble never covers the words
    the user just selected, and it never takes focus, so the paper or web page
    stays interactive and can be scrolled straight away.
    """
    dismissed = Signal()
    copy_requested = Signal(str)
    reader_requested = Signal()

    MARGIN = 8
    GAP = 16

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setObjectName("selectionPopup"); self.setStyleSheet(STYLE + "QWidget#selectionPopup { background:#f8faff; border:1px solid #cfd8ed; border-radius:14px; }")
        self.side = "auto"; self.width_hint = 430; self.font_size = 15
        self.topmost = True
        self.resize(self.width_hint, 210)
        layout = QVBoxLayout(self); layout.setContentsMargins(16, 13, 16, 13); layout.setSpacing(8)
        header = QHBoxLayout()
        self.caption = QLabel("研译 · 灰原哀"); self.caption.setStyleSheet("font-weight:700;color:#5868d9;border:0")
        header.addWidget(self.caption); header.addStretch()
        close = QPushButton("×"); close.setFixedSize(28, 28)
        # The shared QPushButton rule pads 15px per side, which is more than this
        # button is wide: the glyph gets laid out outside the visible area and the
        # button renders as an empty box. Clear the padding (and the border, so
        # the × reads as a close affordance rather than a second button).
        close.setStyleSheet(
            "QPushButton { padding: 0; border: 0; background: transparent;"
            " font-size: 17px; color: #8b95ab; }"
            "QPushButton:hover { background: #edf0ff; border-radius: 14px;"
            " color: #4d5bd4; }")
        self.close_btn = close
        close.clicked.connect(self.dismiss); header.addWidget(close)
        layout.addLayout(header)
        self.source = QLabel(); self.source.setWordWrap(True); self.source.setStyleSheet("color:#7b879d;font-size:12px;border:0")
        layout.addWidget(self.source)
        self.translation = QLabel(); self.translation.setWordWrap(True); self.translation.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.translation.setStyleSheet("color:#1e2c49;font-size:18px;line-height:1.5;border:0")
        layout.addWidget(self.translation, 1)
        footer = QHBoxLayout(); footer.addStretch()
        self.reader_btn = QPushButton("完整对照"); self.reader_btn.clicked.connect(self._open_reader)
        self.reader_btn.setVisible(False); footer.addWidget(self.reader_btn)
        self.copy_btn = QPushButton("复制中文"); self.copy_btn.clicked.connect(self._copy); footer.addWidget(self.copy_btn)
        layout.addLayout(footer)
        QShortcut(QKeySequence("Escape"), self, activated=self.dismiss)

    def _open_reader(self):
        self.dismiss(); self.reader_requested.emit()

    def configure(self, side="auto", width=430, font_size=15):
        """Apply the user's bubble preferences (called whenever settings change)."""
        self.side = side if side in ("auto", "right", "left") else "auto"
        self.width_hint = max(320, min(720, int(width)))
        self.font_size = max(12, min(28, int(font_size)))
        self.translation.setStyleSheet(
            f"color:#1e2c49;font-size:{self.font_size + 3}px;line-height:1.5;border:0")

    def _copy(self):
        self.copy_requested.emit(self.translation.text())
        self.caption.setText("已复制到剪贴板")

    def _place(self, anchor):
        if anchor is None:
            anchor = QCursor.pos()
        point = anchor if hasattr(anchor, "x") else QPoint(int(anchor[0]), int(anchor[1]))
        screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        width = min(self.width_hint, max(280, area.width() - 2 * self.MARGIN))
        height = min(self.height(), max(150, area.height() - 2 * self.MARGIN))
        self.resize(width, height)

        right_x = point.x() + self.GAP
        left_x = point.x() - width - self.GAP
        if self.side == "left":
            x = left_x
        elif self.side == "right":
            x = right_x
        else:
            # Prefer the right of the cursor, but stay fully on screen.
            x = right_x if right_x + width <= area.right() - self.MARGIN else left_x
        x = max(area.left() + self.MARGIN, min(x, area.right() - width - self.MARGIN))
        y = max(area.top() + self.MARGIN, min(point.y() - 24, area.bottom() - height - self.MARGIN))
        self.move(x, y)

    def _present(self, anchor):
        self.adjustSize()
        self._place(anchor)
        self.show(); self.raise_()
        # The bubble is often shown over a maximised browser or full screen PDF,
        # so it has to win the topmost band explicitly.
        if self.topmost:
            raise_above_all(self)

    def show_translation(self, source, translated, anchor=None, service="本地离线"):
        self.caption.setText(f"研译 · 灰原哀  ·  {service}")
        self.source.setText(str(source))
        self.translation.setText(str(translated))
        self.copy_btn.setVisible(True)
        # Long selections get clipped by the bubble: offer the full two-column view.
        self.reader_btn.setVisible(len(str(source)) > 480 or len(str(translated)) > 480)
        self._present(anchor)

    def show_hint(self, detail, anchor=None):
        """Explain why nothing was translated (e.g. a scanned PDF page)."""
        self.caption.setText("研译 · 灰原哀")
        self.source.setText("这段文字没有可读取的选区")
        self.translation.setText(str(detail))
        self.copy_btn.setVisible(False); self.reader_btn.setVisible(False)
        self._present(anchor)

    def dismiss(self):
        self.hide(); self.dismissed.emit()

    def click_away(self, point) -> bool:
        """Close on a left press anywhere outside the bubble.

        Returns True when that press closed it.  Presses inside are left to the
        bubble's own widgets, so "复制中文" and selecting the translation still
        work while a click back into the page makes the bubble get out of the
        way -- it covers exactly the words the user is trying to get back to.
        """
        if self.isVisible() and not self.frameGeometry().contains(point):
            self.dismiss()
            return True
        return False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.dismiss()


class Overlay(QWidget):
    reader_requested = Signal()
    dismissed = Signal()

    def __init__(self, pixmap, geometry, blocks, translations, font_size=15):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setWindowTitle("研译 · 当前屏幕中文快照")
        self.setGeometry(geometry); self.image = pixmap; self.blocks = blocks; self.translations = translations
        self.font_size = font_size; self.original = False; self.setMouseTracking(True)
        self.setStyleSheet(STYLE)
        self.toolbar = QFrame(self); self.toolbar.setStyleSheet("QFrame { background: #f6f8fe; border: 1px solid #dce2f0; border-radius: 12px; }")
        bar = QHBoxLayout(self.toolbar); bar.setContentsMargins(13, 7, 13, 7)
        label = QLabel("研译 · 中文快照"); label.setStyleSheet("border:0;font-weight:600"); bar.addWidget(label)
        original = QPushButton("按住看原文")
        original.pressed.connect(lambda: self.set_original(True)); original.released.connect(lambda: self.set_original(False)); bar.addWidget(original)
        reader = QPushButton("中英对照"); reader.clicked.connect(self.to_reader); bar.addWidget(reader)
        close = QPushButton("返回页面  Esc"); close.clicked.connect(self.dismiss); bar.addWidget(close)
        self.toolbar.adjustSize(); self.toolbar.move(max(0, (self.width() - self.toolbar.width()) // 2), 10)
        self.topmost = True
        QShortcut(QKeySequence("Escape"), self, activated=self.dismiss)
        QShortcut(QKeySequence("Space"), self, activated=lambda: self.set_original(not self.original))

    def showEvent(self, event):
        super().showEvent(event)
        if self.topmost:
            raise_above_all(self)

    def to_reader(self):
        self.hide(); self.reader_requested.emit()

    def dismiss(self):
        self.hide(); self.dismissed.emit()

    def set_original(self, value):
        self.original = value; self.update()

    def paintEvent(self, event):
        p = QPainter(self); p.drawPixmap(self.rect(), self.image)
        if self.original:
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        dpr = self.image.devicePixelRatio()
        for block, text in zip(self.blocks, self.translations):
            x, y, w, h = [v / dpr for v in block['rect']]
            rect = QRectF(x-2, y-1, w+4, h+3).intersected(QRectF(self.rect()))
            if rect.isEmpty():
                continue
            p.setPen(QPen(QColor("#d4deee"), .7)); p.setBrush(QColor(249, 252, 255, 250)); p.drawRoundedRect(rect, 3, 3)
            inner = rect.adjusted(3, 0, -3, 0)
            flags = Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignVCenter
            size = min(self.font_size, max(10, int(h * .67)))
            while size > 10:
                font = QFont("Microsoft YaHei UI"); font.setPixelSize(size)
                if QFontMetrics(font).boundingRect(inner.toRect(), int(flags), text).height() <= inner.height():
                    break
                size -= 1
            font = QFont("Microsoft YaHei UI"); font.setPixelSize(size); p.setFont(font)
            p.save(); p.setClipRect(inner); p.setPen(QColor("#203650")); p.drawText(inner, flags, text); p.restore()
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(28, 39, 61, 220))
        notice = QRectF(12, self.height()-39, min(self.width()-24, 610), 29)
        p.drawRoundedRect(notice, 8, 8); p.setPen(QColor("white")); p.setFont(QFont("Microsoft YaHei UI", 9))
        p.drawText(notice, Qt.AlignmentFlag.AlignCenter, "这是本次屏幕快照 · 悬停查看完整译文 · Esc 返回操作，翻页后再次点击翻译")

    def mouseMoveEvent(self, event):
        point = event.position(); dpr = self.image.devicePixelRatio()
        for block, text in zip(self.blocks, self.translations):
            x,y,w,h = [v / dpr for v in block['rect']]
            if QRectF(x,y,w,h).contains(point):
                QToolTip.showText(event.globalPosition().toPoint(), '<div style="max-width:550px">' + html.escape(text) + '<hr>' + html.escape(block['text']) + '</div>', self)
                return
        QToolTip.hideText()

    def contextMenuEvent(self, event):
        self.dismiss()
