import ctypes
import os
import sys
import threading
import time
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt, QObject, QThread, Signal, QTimer, QRect, QLockFile
from PySide6.QtGui import QGuiApplication, QImage, QCursor
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox
from .config import load_settings, save_settings, data_dir
from .pet import Pet, pet_icon
from .views import Reader, Selection, Overlay, SelectionPopup
from .settings import SettingsDialog
from .selection_monitor import SelectionMonitor
from .winutil import TopmostKeeper, raise_above_all


def image_array(image):
    rgb = image.convertToFormat(QImage.Format.Format_RGB888)
    return np.frombuffer(rgb.bits(), dtype=np.uint8).reshape(rgb.height(), rgb.bytesPerLine())[:, :rgb.width()*3].reshape(rgb.height(), rgb.width(), 3).copy()


class Worker(QObject):
    status = Signal(str)
    result = Signal(object, object, str, float)
    error = Signal(str)
    finished = Signal()

    def __init__(self, settings, pixels=None, offset=(0, 0), blocks=None):
        super().__init__(); self.settings = dict(settings); self.pixels = pixels
        self.offset = offset; self.blocks = blocks; self.cancelled = threading.Event()

    def run(self):
        start = time.monotonic()
        try:
            from .translation import translate_blocks
            blocks = self.blocks
            if blocks is None:
                from .ocr import extract_blocks, group_paragraphs
                self.status.emit("正在本地识别英文…首次使用会初始化 OCR 模型")
                blocks = group_paragraphs(extract_blocks(self.pixels))
                for block in blocks:
                    block['rect'][0] += self.offset[0]; block['rect'][1] += self.offset[1]
            if self.cancelled.is_set():
                return
            if not blocks:
                raise RuntimeError("没有识别到可翻译的英文。请放大页面或重新框选清晰的文字区域。")
            self.status.emit(f"已识别 {len(blocks)} 个文本块，正在翻译…")
            translated, label = translate_blocks([b['text'] for b in blocks], self.settings,
                progress=lambda *args: self.status.emit(' '.join(str(v) for v in args)), cancel=self.cancelled)
            if not self.cancelled.is_set():
                if len(translated) != len(blocks):
                    raise RuntimeError("翻译服务返回的文本数量不完整，请重试。")
                self.result.emit(blocks, translated, label, time.monotonic()-start)
        except Exception as exc:
            if not self.cancelled.is_set():
                self.error.emit(str(exc)[:600])
        finally:
            self.finished.emit()


class Controller(QObject):
    def __init__(self, app):
        super().__init__(); self.app = app; self.settings = load_settings()
        self.pet = Pet(self.settings); self.reader = Reader(); self.overlay = None; self.selection = None
        self.dialog = None; self.thread = None; self.worker = None; self.snapshot = None; self.geometry = None
        self.selection_popup = SelectionPopup(); self.selection_anchor = None
        self.selection_popup.copy_requested.connect(self.copy_text)
        self.selection_popup.reader_requested.connect(self.show_reader)
        # Qt only applies WindowStaysOnTopHint once, so a full screen browser can
        # bury our windows later. The keeper re-asserts the topmost band.
        self.topmost = TopmostKeeper(self)
        self.topmost.watch(self.pet); self.topmost.watch(self.selection_popup)
        self.topmost.set_enabled(self.settings.get('topmost', True))
        self.selection_monitor = SelectionMonitor(self)
        self.selection_monitor.selected.connect(self.selected_text)
        self.selection_monitor.unreadable.connect(self.selection_unreadable)
        self.selection_monitor.gesture.connect(self.selection_gesture)
        self.selection_monitor.left_press.connect(self.selection_click_away)
        self.selection_monitor.start()
        self._last_worker_cancelled = False
        self._pending_selection = None
        self.blocks = []; self.translations = []; self.pending = False; self.quitting = False; self.clipboard_job = False
        self.pet.full.connect(lambda: self.capture(False)); self.pet.region.connect(lambda: self.capture(True))
        self.pet.settings_requested.connect(self.show_settings); self.pet.reader_requested.connect(self.show_reader)
        self.pet.clipboard_requested.connect(self.clipboard); self.pet.quit_requested.connect(self.quit)
        self.reader.overlay_requested.connect(self.show_overlay); self.reader.retry_requested.connect(self.retry)
        self.reader.cancel_requested.connect(self.cancel)
        self.tray = QSystemTrayIcon(pet_icon(), self); self.tray.setToolTip("研译 ScholarPet · 灰原哀 · 单击桌宠翻译")
        menu = QMenu()
        menu.addAction("翻译当前屏幕", lambda: self.capture(False))
        menu.addAction("框选翻译", lambda: self.capture(True))
        menu.addAction("翻译剪贴板文字", self.clipboard)
        menu.addAction("中英对照", self.show_reader); menu.addAction("外观与翻译设置", self.show_settings)
        menu.addAction("找回桌宠", self.reset_pet); menu.addSeparator(); menu.addAction("退出", self.quit)
        self.tray.setContextMenu(menu); self.tray.activated.connect(self.tray_clicked); self.tray.show()
        self.apply_selection_settings()
        self.reset_pet()
        if self.settings.get('first_run', True):
            QTimer.singleShot(350, self.welcome)

    def welcome(self):
        self.reader.show_message("研译已就绪 · 灰原哀阅读搭子", "日常用法：在论文、网页或技术报告里用鼠标划选一个词、一句话或一整段，研译会在鼠标旁边弹出中文译文，不遮挡你选中的内容，也不会抢走焦点——选完就能继续滚动页面。读完译文后，在浮窗以外的任何地方点一下左键，浮窗就会立刻收起；浮窗上的「复制中文」「完整对照」照常可用。\n\n记四个动作就够了，不需要任何快捷键：\n· 鼠标划选——选中哪里就翻译哪里，双击单词或按住拖动划过句子都行；\n· 单击灰原哀头像——翻译当前整屏；\n· 点击头像下方的「框选翻译」——拖动框选任意区域，用本地 OCR 识别后再翻译，扫描版 PDF 就用这个；\n· 双击头像——打开外观、划词、翻译引擎和术语表设置。\n\n若某个页面没有可复制的文字层，浮窗会提示你改用「框选翻译」。\n\n桌宠和翻译浮窗默认「始终显示在其它窗口之上」：浏览器按 F11 全屏、阅读器全屏时它们依然可见。不需要时可在双击头像后的「外观」里取消勾选。\n\n灰原哀会自己眨眼，视线跟着你的鼠标走，点她一下她会眨眼回应；翻译进行中她会轻轻动嘴，像在念给你听。动作幅度都很小，不打扰阅读；想要安静可在「外观」里关掉「活灵活现」。\n\n研译不注册任何全局快捷键，不会占用你的键盘。\n\n默认使用本地离线英中模型，无需密钥；也可切换到 Google 或你自己的 DeepSeek / 兼容接口。内置通信、抗干扰术语。机器翻译与 OCR 都可能出错，请结合中英对照核对关键结论。")
        self.reader.show(); self.settings['first_run'] = False; save_settings(self.settings)

    def reset_pet(self):
        rect = QGuiApplication.primaryScreen().availableGeometry()
        self.pet.move(rect.right()-self.pet.width()-26, rect.bottom()-self.pet.height()-70); self.pet.show()
        if self.settings.get('topmost', True):
            raise_above_all(self.pet)

    def tray_clicked(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_settings()

    def is_busy(self):
        return self.pending or self.thread is not None

    def capture(self, region=False):
        if self.is_busy():
            self.show_reader(); return
        if self.selection is not None and self.selection.isVisible():
            return
        self.pending = True
        self.clear_results(clear_snapshot=True)
        self.target_screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        self.pet.hide(); self.reader.hide()
        if self.overlay: self.overlay.hide()
        if self.dialog: self.dialog.hide()
        # Give the compositor time to remove our own windows before grabbing pixels.
        QTimer.singleShot(220, lambda: self.take_snapshot(region))

    def take_snapshot(self, region):
        self.pending = False
        try:
            screen = self.target_screen; self.snapshot = screen.grabWindow(0); self.geometry = screen.geometry()
            if self.snapshot.isNull(): raise RuntimeError("屏幕截图失败，请确认当前不是安全桌面或受保护内容。")
            self.clipboard_job = False
            if region:
                self.selection = Selection(self.snapshot, self.geometry)
                self.selection.topmost = self.settings.get('topmost', True)
                self.selection.chosen.connect(self.selected)
                self.selection.cancelled.connect(self.selection_cancelled)
                self.topmost.watch(self.selection)
                self.selection.show(); self.selection.activateWindow(); self.selection.raise_()
            else:
                self.start_worker(image_array(self.snapshot.toImage()))
        except Exception as exc:
            self.fail(str(exc)); self.pet.show()

    def selection_cancelled(self):
        self.selection = None; self.pet.show()

    def selected(self, rect):
        """Region picked on the frozen screenshot: OCR it and translate."""
        self.selection = None
        dpr = self.snapshot.devicePixelRatio()
        physical = QRect(round(rect.x()*dpr), round(rect.y()*dpr), round(rect.width()*dpr), round(rect.height()*dpr))
        pixels = image_array(self.snapshot.toImage().copy(physical))
        self.start_worker(pixels, (physical.x(), physical.y()))

    def selection_gesture(self):
        # A new selection replaces the previous bubble immediately.
        if self.selection_popup.isVisible():
            self.selection_popup.hide()

    def selection_click_away(self, point):
        """Forward a left press from anywhere on screen to the bubble.

        Qt only delivers mouse events to the window under the pointer, so the
        bubble cannot see a click on the page behind it; the selection monitor
        polls the physical button instead (see ``SelectionMonitor.left_press``).
        """
        self.selection_popup.click_away(point)

    def selection_unreadable(self, anchor):
        """Selection gesture found no text: usually a scanned PDF page."""
        if self.is_busy():
            return
        self.selection_popup.show_hint(
            "该区域没有可复制的文字层，可能是扫描版 PDF 或图片。\n"
            "点桌宠下方的「框选翻译」拖动框选这块区域，研译会用本地 OCR 识别后再翻译。", anchor)

    def selected_text(self, text, anchor, _bbox=None):
        text = (text or "").strip()
        if not text:
            return
        # Keep only the newest selection: translating an older one would pop a
        # bubble for text the user has already moved past.
        self._pending_selection = (text, anchor)
        if self.is_busy():
            if self.clipboard_job:
                self.cancel()
            return
        self._start_selection_job()

    def _start_selection_job(self):
        if not self._pending_selection:
            return
        text, anchor = self._pending_selection
        self._pending_selection = None
        self.selection_anchor = anchor
        self.clipboard_job = True
        blocks = [dict(text=text, rect=[0, 0, 0, 0], confidence=1.0)]
        self.start_worker(blocks=blocks, selection_mode=True)

    def start_worker(self, pixels=None, offset=(0,0), blocks=None, selection_mode=False):
        self.pet.show(); self.pet.busy = True; self.reader.busy(True)
        if not selection_mode:
            self.reader.show_message("正在准备翻译…", "截图在本机识别，识别出的文字将发送到你选择的翻译服务。\n可以点击「取消任务」停止后续请求。")
            self.reader.show(); self.reader.raise_()
        self.thread = QThread(self); self.worker = Worker(self.settings, pixels, offset, blocks)
        self.worker.moveToThread(self.thread); self.thread.started.connect(self.worker.run)
        self.worker.status.connect(self.reader.status.setText); self.worker.result.connect(self.succeeded)
        self.worker.error.connect(self.fail); self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(lambda: setattr(self, '_last_worker_cancelled', self.worker.cancelled.is_set()))
        self.worker.finished.connect(self.worker.deleteLater); self.thread.finished.connect(self.worker_done)
        self.thread.finished.connect(self.thread.deleteLater); self.thread.start()

    def worker_done(self):
        cancelled = self._last_worker_cancelled
        self.thread = None; self.worker = None; self.pet.busy = False; self.pet.update(); self.reader.busy(False)
        self.reader.overlay_btn.setEnabled(bool(self.translations) and not self.clipboard_job and self.snapshot is not None)
        if self.quitting:
            self.app.quit(); return
        if self._pending_selection:
            # The user selected something else while we were busy.
            self._start_selection_job(); return
        if cancelled:
            self.reader.show_message("已取消翻译", "你可以继续阅读，或重新点击桌宠开始。")

    def clear_results(self, clear_snapshot=False):
        self.blocks = []; self.translations = []
        self.reader.blocks = []; self.reader.translations = []; self.reader.busy(False)
        if clear_snapshot:
            self.snapshot = None; self.geometry = None

    def succeeded(self, blocks, translations, service, elapsed):
        self.blocks = blocks; self.translations = translations
        self.reader.set_result(blocks, translations, service, elapsed, self.settings['font_size'])
        anchor, self.selection_anchor = self.selection_anchor, None
        if anchor is not None:
            # Primary flow: selected text -> bubble beside the cursor.
            self.reader.hide()
            self.selection_popup.show_translation(blocks[0]['text'], translations[0], anchor, service)
        elif self.settings['view'] == 'overlay' and not self.clipboard_job:
            self.show_overlay()
        else:
            self.show_reader()

    def fail(self, message):
        self.selection_anchor = None
        self.reader.show_message("这次翻译没有完成", message + "\n\n可在双击桌宠后的「翻译与隐私」中检查引擎设置；文字太小可先放大页面。")
        self.reader.show(); self.reader.raise_()

    def copy_text(self, text):
        QApplication.clipboard().setText(text)

    def show_reader(self):
        if self.overlay: self.overlay.hide()
        self.reader.show(); self.reader.raise_(); self.reader.activateWindow()

    def show_overlay(self):
        if not self.snapshot or not self.translations or self.clipboard_job:
            return
        self.reader.hide(); self.pet.hide()
        if self.overlay: self.overlay.close(); self.overlay.deleteLater()
        self.overlay = Overlay(self.snapshot, self.geometry, self.blocks, self.translations, self.settings['font_size'])
        self.overlay.topmost = self.settings.get('topmost', True)
        self.overlay.reader_requested.connect(self.overlay_to_reader); self.overlay.dismissed.connect(self.pet.show)
        self.topmost.watch(self.overlay)
        self.overlay.show(); self.overlay.raise_(); self.overlay.activateWindow()

    def overlay_to_reader(self):
        self.pet.show(); self.show_reader()

    def cancel(self):
        if self.worker:
            self.worker.cancelled.set()
            self.reader.status.setText("正在取消，等待当前网络请求结束…")
            self.reader.cancel_btn.setEnabled(False)
            self.thread.finished.connect(lambda: self.reader.cancel_btn.setEnabled(True))

    def clipboard(self):
        if self.is_busy(): return
        text = QApplication.clipboard().text().strip()
        if not text:
            self.fail("剪贴板中没有文字。先选中英文并按 Ctrl+C 复制，再从桌宠右键菜单点「翻译剪贴板文字」。"); return
        if len(text) > 40000:
            self.fail("剪贴板文字过长，请选取 40,000 字符以内的片段。"); return
        self.clipboard_job = True
        self.clear_results(clear_snapshot=False)
        blocks = [dict(text=p.strip(), rect=[0,0,0,0], confidence=1) for p in text.split('\n\n') if p.strip()]
        self.start_worker(blocks=blocks)

    def retry(self):
        if not self.is_busy() and self.blocks:
            self.start_worker(blocks=self.blocks)

    def show_settings(self):
        if self.dialog and self.dialog.isVisible():
            self.dialog.raise_(); return
        self.dialog = SettingsDialog(self.settings); self.dialog.saved.connect(self.apply_settings)
        self.dialog.show(); self.dialog.raise_(); self.dialog.activateWindow()

    def apply_settings(self, settings):
        self.settings = settings; self.pet.apply(settings); self.apply_selection_settings()
        topmost = bool(settings.get('topmost', True))
        self.topmost.set_enabled(topmost)
        self.selection_popup.topmost = topmost
        if self.selection: self.selection.topmost = topmost
        if self.overlay: self.overlay.topmost = topmost
        if topmost:
            self.topmost.reassert()

    def apply_selection_settings(self):
        """Push selection-translation preferences to the monitor and the bubble."""
        settings = self.settings
        enabled = bool(settings.get('selection_enabled', True))
        self.selection_monitor.set_enabled(enabled)
        if enabled:
            self.selection_monitor.start()
        else:
            self.selection_monitor.stop()
            self.selection_popup.hide()
        self.selection_popup.configure(settings.get('popup_side', 'auto'),
                                       settings.get('popup_width', 430),
                                       settings.get('font_size', 15))
        self.selection_popup.topmost = bool(settings.get('topmost', True))

    def quit(self):
        self.selection_monitor.stop(); self.selection_popup.hide(); self.tray.hide(); self.pet.hide(); self.reader.hide()
        if self.overlay: self.overlay.hide()
        if self.dialog: self.dialog.hide()
        if self.selection: self.selection.hide()
        if self.worker:
            self.quitting = True; self.worker.cancelled.set()
        else:
            self.app.quit()


def main():
    if os.name == 'nt':
        try: ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ScholarPet.Research.Translator")
        except OSError: pass
    app = QApplication(sys.argv); app.setApplicationName("ScholarPet"); app.setApplicationDisplayName("研译")
    app.setQuitOnLastWindowClosed(False); app.setWindowIcon(pet_icon())
    lock = QLockFile(str(data_dir() / "instance.lock")); lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None, "研译已运行", "桌宠已经在运行，请查看屏幕右下角或系统托盘中的灰原哀图标。"); return 0
    controller = Controller(app)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
