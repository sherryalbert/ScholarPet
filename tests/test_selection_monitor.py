import os
import time
import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from scholarpet.selection_monitor import SelectionMonitor


def test_monitor_defaults_are_selection_only(qapp):
    monitor = SelectionMonitor()
    assert monitor.enabled and monitor.clipboard_fallback
    assert not monitor.paused
    monitor.set_paused(True); assert monitor.paused
    monitor.set_enabled(False); assert not monitor.enabled
    monitor.set_clipboard_fallback(False); assert not monitor.clipboard_fallback
    monitor.stop()


def test_monitor_is_noop_off_windows(monkeypatch, qapp):
    import scholarpet.selection_monitor as m
    old = m.user32; m.user32 = None
    try:
        monitor = SelectionMonitor(); monitor.start(); assert not monitor._timer.isActive()
    finally:
        m.user32 = old


class _Keys:
    """Stands in for user32: only the button state _poll actually reads."""

    def __init__(self):
        self.down = False
        self.point = None

    def GetAsyncKeyState(self, vk):
        return 0x8000 if self.down else 0


def _prepare(monkeypatch, paused=False):
    import scholarpet.selection_monitor as m
    keys = _Keys()
    monkeypatch.setattr(m, "user32", keys)
    monkeypatch.setattr(m, "_point", lambda: keys.point)
    monitor = SelectionMonitor()
    monitor.set_paused(paused)
    return monitor, keys


def _at(keys, x, y):
    keys.point = QPoint(x, y)


def test_a_left_press_anywhere_is_reported_once(monkeypatch, qapp):
    monitor, keys = _prepare(monkeypatch)
    seen = []
    monitor.left_press.connect(seen.append)

    _at(keys, 640, 480)
    keys.down = True; monitor._poll()          # press
    monitor._poll(); monitor._poll()           # held: not a second press
    keys.down = False; monitor._poll()         # release
    _at(keys, 700, 500)
    keys.down = True; monitor._poll()          # next press
    keys.down = False; monitor._poll()

    assert seen == [QPoint(640, 480), QPoint(700, 500)]


def test_a_drag_still_asks_for_the_selection(monkeypatch, qapp):
    """The refactor must not cost us the gesture the module exists for."""
    monitor, keys = _prepare(monkeypatch)
    asked = []
    monitor._request_selection = asked.append

    _at(keys, 100, 100); keys.down = True; monitor._poll()
    _at(keys, 160, 100); monitor._poll()
    keys.down = False; monitor._poll()

    assert asked == [QPoint(160, 100)]


def test_a_press_while_paused_still_closes_things(monkeypatch, qapp):
    """The bubble is on screen whenever it is on screen -- paused or not."""
    monitor, keys = _prepare(monkeypatch, paused=True)
    seen = []
    monitor.left_press.connect(seen.append)
    asked = []
    monitor._request_selection = asked.append

    _at(keys, 50, 60); keys.down = True; monitor._poll()
    _at(keys, 200, 60); monitor._poll()
    keys.down = False; monitor._poll()

    assert seen == [QPoint(50, 60)], "a paused monitor stopped reporting presses"
    assert asked == [], "a paused monitor started capturing selections"


def test_pausing_mid_press_does_not_swallow_the_next_one(monkeypatch, qapp):
    """Holding the button through a pause used to leave `_down` stuck True."""
    monitor, keys = _prepare(monkeypatch, paused=True)
    seen = []
    monitor.left_press.connect(seen.append)

    _at(keys, 10, 10); keys.down = True; monitor._poll()
    monitor._poll()
    keys.down = False; monitor._poll()          # released while still paused
    monitor.set_paused(False)
    _at(keys, 30, 30); keys.down = True; monitor._poll()

    assert len(seen) == 2, "the press after the pause was missed"


# -- the clipboard is the user's, not ours ----------------------------------
#
# Regression: Win+Shift+S (or PrtSc) put a screenshot on the clipboard, and
# pasting it into WeChat or QQ did nothing.  Copying a selection used to blank
# the clipboard first and then restore a snapshot that could not carry a
# bitmap, so the screenshot was destroyed before it was ever pasted.


def _flush(app, seconds=1.0):
    """Let the 45 ms restore timer actually fire."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)


class _Clipboard:
    """Stands in for the clipboard counter and for the target app's Ctrl+C."""

    def __init__(self, monkeypatch, answering=None):
        import scholarpet.selection_monitor as m
        self.sequence = 100
        self.sent = 0
        self.answering = answering
        monkeypatch.setattr(m, "_foreground", lambda: 42)
        monkeypatch.setattr(m, "_clipboard_sequence", lambda: self.sequence)
        monkeypatch.setattr(m, "_send_copy_keys", self._send_copy_keys)

    def _send_copy_keys(self):
        self.sent += 1
        if self.answering is None:
            return                       # the app ignored the keystroke
        self.sequence += 1
        QApplication.clipboard().setText(self.answering)


def _monitor(monkeypatch):
    monitor = SelectionMonitor()
    monitor._blocked_window = lambda hwnd: False
    return monitor


def test_a_screenshot_survives_a_capture_that_finds_no_text(monkeypatch, qapp):
    """The reported bug, in one assertion."""
    clip = _Clipboard(monkeypatch, answering=None)
    clipboard = QApplication.clipboard()
    clipboard.setText("the user's screenshot")
    monitor = _monitor(monkeypatch)
    hints = []
    monitor.unreadable.connect(hints.append)

    monitor._copy_selection(42, QPoint(10, 20))

    assert clip.sent == 1, "the monitor never even asked for a selection"
    assert clipboard.text() == "the user's screenshot", \
        "the clipboard was destroyed by a capture that produced nothing"
    assert hints == [QPoint(10, 20)], \
        "the scanned-PDF hint was lost along with the blanking"


def test_a_selection_is_read_and_the_clipboard_is_handed_back(monkeypatch, qapp):
    clip = _Clipboard(monkeypatch, answering="beamforming")
    clipboard = QApplication.clipboard()
    clipboard.setText("the user's screenshot")
    monitor = _monitor(monkeypatch)
    seen = []
    monitor.selected.connect(lambda text, anchor, box: seen.append((text, anchor)))

    monitor._copy_selection(42, QPoint(5, 6))

    assert seen == [("beamforming", QPoint(5, 6))]
    assert clipboard.text() == "beamforming", "the receiver had nothing to read"
    _flush(qapp)
    assert clipboard.text() == "the user's screenshot", \
        "the user's clipboard was never put back"


def test_a_snapshot_can_put_a_bitmap_back(monkeypatch, qapp):
    """A snip is a bitmap. A raw data()/setData() round trip reads back null."""
    import scholarpet.selection_monitor as m
    clipboard = QApplication.clipboard()
    image = QImage(24, 16, QImage.Format.Format_RGB32)
    image.fill(0xFF3366FF)
    clipboard.setImage(image)

    saved = m._clipboard_snapshot()
    clipboard.clear()
    m._restore_clipboard(saved)

    back = clipboard.image()
    assert not back.isNull(), "the bitmap did not survive the round trip"
    assert back.pixel(0, 0) == 0xFF3366FF


def test_a_restore_never_overwrites_a_newer_copy(monkeypatch, qapp):
    """A second snip during the restore window belongs to the user."""
    import scholarpet.selection_monitor as m
    clipboard = QApplication.clipboard()
    clipboard.setText("older")
    saved = m._clipboard_snapshot()

    monkeypatch.setattr(m, "_clipboard_sequence", lambda: 500)
    clipboard.setText("newer snip")
    m._restore_clipboard(saved, sequence=499)
    assert clipboard.text() == "newer snip", "a newer copy was overwritten"

    m._restore_clipboard(saved, sequence=500)
    assert clipboard.text() == "older", "the user's clipboard was not put back"


def test_a_snip_tool_is_never_asked_for_a_selection(monkeypatch, qapp):
    import scholarpet.selection_monitor as m
    monitor = SelectionMonitor()
    monkeypatch.setattr(m, "_window_class", lambda hwnd: "WinUIDesktopWin32WindowClass")
    monkeypatch.setattr(m, "_window_title", lambda hwnd: "")
    monkeypatch.setattr(m, "_process_name", lambda hwnd: "snippingtool.exe")
    assert monitor._blocked_window(1), "a screen-capture overlay was treated as text"

    monkeypatch.setattr(m, "_process_name", lambda hwnd: "chrome.exe")
    assert not monitor._blocked_window(1)
    monkeypatch.setattr(m, "_window_title", lambda hwnd: "Windows PowerShell")
    assert monitor._blocked_window(1), "the terminal guard was lost"


def test_a_snip_drag_does_not_arm_the_capture(monkeypatch, qapp):
    """The real guard, end to end: the foreground window is the snipping tool."""
    import scholarpet.selection_monitor as m
    monitor, keys = _prepare(monkeypatch)
    monkeypatch.setattr(m, "_foreground", lambda: 42)
    monkeypatch.setattr(m, "_process_name", lambda hwnd: "snippingtool.exe")
    monkeypatch.setattr(m, "_window_class", lambda hwnd: "WinUIDesktopWin32WindowClass")
    monkeypatch.setattr(m, "_window_title", lambda hwnd: "截图")
    monitor._belongs_to_us = lambda hwnd: False
    gestures = []
    monitor.gesture.connect(lambda: gestures.append(True))

    _at(keys, 100, 100); keys.down = True; monitor._poll()
    _at(keys, 160, 140); monitor._poll()
    keys.down = False; monitor._poll()

    assert gestures == [], "a snip drag armed the selection capture"
    assert not monitor._capturing
