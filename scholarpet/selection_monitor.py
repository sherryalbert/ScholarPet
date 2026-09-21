"""Lightweight Windows selection monitor for ScholarPet.

It observes only mouse-button transitions (no keyboard logging). After a real
drag or double-click in another foreground window, it asks that application to
copy its current selection and reads the text back. This works for Chrome,
Acrobat, PDF readers and most native editors.

The clipboard belongs to the user, not to us. An earlier version blanked it
before sending Ctrl+C, so that "did the app answer?" could be read off the
clipboard turning non-empty. That was destructive: a screenshot taken with
Win+Shift+S or PrtSc lives on that same clipboard, and blanking it -- then
restoring a snapshot that could not carry a bitmap -- left WeChat and QQ with
nothing to paste. Nothing is blanked now. Windows bumps a clipboard sequence
number on every ``SetClipboardData``, so "the app answered" is read from that
counter instead; when it never moves the clipboard is left exactly as found.
When it does move, the previous contents go back -- bitmaps included, via
``QMimeData.setImageData`` -- and only if nothing else has claimed the clipboard
in the meantime. A drag on a screen-capture overlay is refused outright, since
it is a snip, not a text selection.

Image-only PDF regions still require the existing OCR frame tool, and that case
is reported back through ``unreadable`` so the bubble can explain it instead of
failing silently.

Every fresh left press is also reported through ``left_press``. Qt only sends
mouse events to the window under the pointer, so a click "anywhere else" is
invisible to the app's own widgets; polling the physical button is the only way
the translation bubble can learn that the user has moved on.
"""
from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes

from PySide6.QtCore import QMimeData, QObject, QPoint, QTimer, Signal
from PySide6.QtWidgets import QApplication

user32 = ctypes.windll.user32 if os.name == "nt" else None
kernel32 = ctypes.windll.kernel32 if os.name == "nt" else None
VK_LBUTTON = 0x01
VK_CONTROL, VK_C = 0x11, 0x43
KEYEVENTF_KEYUP = 0x0002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_NAME_BUFFER = 512

# Windows that must never be asked for a selection: terminals (Ctrl+C is
# interrupt), credential prompts, and password fields.
BLOCKED_WORDS = ("powershell", "windows terminal", "cmd.exe", "command prompt",
                 "conemu", "mintty", "git bash", "password", "credential", "pinentry")

# Dragging across a screen-capture overlay is a snip, not a text selection.
# Asking it for a selection would at best do nothing and at worst pop the
# "no text layer here" hint while the user is still framing the shot.
BLOCKED_PROCESSES = frozenset((
    "snippingtool.exe", "screensketch.exe", "screenclippinghost.exe",
    "snipaste.exe", "sharex.exe", "greenshot.exe", "pixpin.exe", "lightshot.exe",
))

if os.name == "nt":
    # A process HANDLE is pointer sized. Without an explicit restype ctypes
    # would truncate it to int on 64-bit Python and every call would fail.
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD))
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)


def _point():
    point = wintypes.POINT()
    if user32 and user32.GetCursorPos(ctypes.byref(point)):
        return QPoint(point.x, point.y)
    return QPoint(0, 0)


def _foreground():
    return user32.GetForegroundWindow() if user32 else 0


def _process_name(hwnd):
    """Lower-cased executable name behind a window, or "" when unavailable."""
    if not hwnd or not kernel32:
        return ""
    pid = wintypes.DWORD()
    if not user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)) or not pid.value:
        return ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(PROCESS_NAME_BUFFER)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return os.path.basename(buffer.value).lower()
    finally:
        kernel32.CloseHandle(handle)
    return ""


def _clipboard_sequence():
    """Windows' clipboard change counter (0 when the platform has none).

    Every ``SetClipboardData`` bumps it, by anyone. It is how the monitor tells
    "the app answered our Ctrl+C" apart from "the app ignored it" without having
    to blank the clipboard first to manufacture a known-empty baseline.
    """
    return int(user32.GetClipboardSequenceNumber()) if user32 else 0


def _window_class(hwnd):
    if not hwnd or not user32:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, len(buf))
    return buf.value


def _window_title(hwnd):
    if not hwnd or not user32:
        return ""
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, len(buf))
    return buf.value


def _clipboard_snapshot():
    """Everything on the clipboard, in a form that can actually be put back.

    A plain ``data()``/``setData()`` loop silently drops bitmaps: the format a
    snip arrives in reads back as null, and PySide6 exposes no
    ``QMimeData.setImage``. ``setImageData`` keeps the ``QImage`` itself, so the
    restore hands WeChat and QQ a real bitmap again.
    """
    clipboard = QApplication.clipboard()
    mime = clipboard.mimeData()
    copy = QMimeData()
    if mime is None:
        return copy
    for fmt in mime.formats():
        copy.setData(fmt, mime.data(fmt))
    if mime.hasImage():
        image = clipboard.image()
        if not image.isNull():
            copy.setImageData(image)
    return copy


def _restore_clipboard(mime, sequence=None):
    """Put the user's clipboard back, unless someone else has claimed it since.

    ``sequence`` is the counter read just after we consumed the selection. If it
    has moved, a newer copy -- a fresh screenshot, most likely -- owns the
    clipboard now and must not be overwritten with stale content.
    """
    if mime is None:
        return
    if sequence is not None and _clipboard_sequence() != sequence:
        return
    QApplication.clipboard().setMimeData(mime)


def _send_copy_keys():
    """Tap Ctrl+C through user32 so it lands in the focused application."""
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_C, 0, 0, 0)
    user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


class SelectionMonitor(QObject):
    selected = Signal(str, object, object)  # text, QPoint anchor, optional source rect
    unreadable = Signal(object)             # QPoint anchor, no text layer available
    gesture = Signal()
    left_press = Signal(object)             # QPoint: a fresh left press, anywhere

    def __init__(self, parent=None):
        super().__init__(parent)
        self.enabled = True
        self.paused = False
        self.clipboard_fallback = True
        self.min_drag = 12
        self.announce_unreadable = True
        self._down = False
        self._down_pos = QPoint()
        self._max_distance = 0
        self._last_release = 0.0
        self._last_release_pos = QPoint()
        self._capturing = False
        self._timer = QTimer(self)
        self._timer.setInterval(35)
        self._timer.timeout.connect(self._poll)

    def available(self):
        """True when global mouse observation is possible on this platform."""
        return bool(user32)

    def start(self):
        if self.available() and not self._timer.isActive():
            self._timer.start()

    def stop(self):
        self._timer.stop()

    def set_enabled(self, value):
        self.enabled = bool(value)

    def set_paused(self, value):
        self.paused = bool(value)

    def set_clipboard_fallback(self, value):
        self.clipboard_fallback = bool(value)

    def _poll(self):
        if not user32:
            return
        point = _point()
        down = bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
        if not down:
            # Book-keeping runs even while paused or capturing: leaving `_down`
            # stuck at True would swallow the next press entirely.
            if self._down:
                self._down = False
                self._max_distance = max(self._max_distance,
                                         (point - self._down_pos).manhattanLength())
                if self.enabled and not self.paused and not self._capturing:
                    self._released(point)
            return
        if not self._down:
            self._down = True; self._down_pos = point; self._max_distance = 0
            # Emitted before any of the gates above: a bubble that is already on
            # screen has to close when the user clicks away from it, whether or
            # not selection capture happens to be armed at that moment.
            self.left_press.emit(QPoint(point))
            return
        self._max_distance = max(self._max_distance, (point - self._down_pos).manhattanLength())

    def _released(self, point):
        now = time.monotonic()
        double = (now - self._last_release <= QApplication.doubleClickInterval() / 1000
                  and (point - self._last_release_pos).manhattanLength() <= 16)
        drag = self._max_distance >= self.min_drag
        self._last_release, self._last_release_pos = now, QPoint(point)
        if drag or double:
            self._request_selection(point)

    def _request_selection(self, anchor):
        hwnd = _foreground()
        if not hwnd or self._belongs_to_us(hwnd) or self._blocked_window(hwnd):
            return
        self._capturing = True
        self.gesture.emit()
        # Selection rendering and focus settle after mouse-up.
        QTimer.singleShot(90, lambda: self._copy_selection(hwnd, anchor))

    def _belongs_to_us(self, hwnd):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value) == os.getpid()

    def _blocked_window(self, hwnd):
        combined = (_window_class(hwnd) + " " + _window_title(hwnd)).lower()
        if any(word in combined for word in BLOCKED_WORDS):
            return True
        return _process_name(hwnd) in BLOCKED_PROCESSES

    def _copy_selection(self, hwnd, anchor):
        try:
            if not self.clipboard_fallback or not user32:
                return
            if _foreground() != hwnd or self._blocked_window(hwnd):
                return
            # Snapshot before anything is sent, and never blank the clipboard:
            # if the target ignores the keystroke, the user's clipboard -- a
            # screenshot, typically -- has to be left exactly as we found it.
            # The counter is read *after* the snapshot on purpose: if reading the
            # clipboard ever bumps it, the baseline must already include that.
            previous = _clipboard_snapshot()
            before = _clipboard_sequence()
            _send_copy_keys()
            text, answered = self._await_selection(before)
            if text:
                self.selected.emit(text[:40000], QPoint(anchor), None)
            elif self.announce_unreadable:
                # Also the scanned-PDF path: the viewer has no text layer to
                # copy, so it answers exactly like an app that ignored us.
                self.unreadable.emit(QPoint(anchor))
            if not answered:
                # The keystroke was ignored, so the clipboard still holds what
                # it held before -- the user's screenshot included. Nothing to
                # put back, and nothing to undo.
                return
            # Restore on the next event-loop turn so the receiver can read the
            # selection first, and only while the clipboard is still ours.
            QTimer.singleShot(45, lambda m=previous, s=_clipboard_sequence():
                              _restore_clipboard(m, s))
        finally:
            self._capturing = False

    def _await_selection(self, sequence):
        """Wait for the foreground app to answer our Ctrl+C.

        Returns ``(text, answered)``. ``answered`` stays False when the clipboard
        counter never moves, which means the keystroke was ignored and the
        user's clipboard is still intact.
        """
        deadline = time.monotonic() + .35
        while time.monotonic() < deadline:
            QApplication.processEvents()
            if _clipboard_sequence() != sequence:
                return self._read_back(), True
            time.sleep(.025)
        return "", False

    @staticmethod
    def _read_back():
        """The text the target copied, once it has finished publishing it."""
        clipboard = QApplication.clipboard()
        deadline = time.monotonic() + .12
        while time.monotonic() < deadline:
            text = clipboard.text().strip()
            if text:
                return text
            QApplication.processEvents()
            time.sleep(.02)
        return ""


__all__ = ["SelectionMonitor"]
