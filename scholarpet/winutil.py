"""Keep our borderless windows genuinely above everything else on Windows.

Qt applies ``WindowStaysOnTopHint`` once, when the window is created.  Anything
that goes full screen afterwards -- Chrome, Edge, a PDF reader, a video player --
can reshuffle the topmost band, which is exactly why the desktop pet used to
disappear as soon as a browser was maximised.  Re-asserting ``HWND_TOPMOST`` on
a slow timer wins that race without ever stealing focus (``SWP_NOACTIVATE``).

Everything here degrades to a no-op off Windows so the module stays importable
on other platforms and inside the test suite.
"""

from __future__ import annotations

import ctypes
import os
import weakref

from PySide6.QtCore import QObject, QTimer

HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010

IS_WINDOWS = os.name == "nt"

# 1.2s is frequent enough to beat a window that grabs the topmost band, and
# cheap enough to be invisible: SetWindowPos with no move/size change is a
# z-order no-op when we are already on top.
DEFAULT_INTERVAL_MS = 1200


def raise_above_all(widget) -> bool:
    """Place ``widget`` at the top of the topmost band. True when it worked."""
    if not IS_WINDOWS:
        return False
    try:
        hwnd = int(widget.winId())
        if not hwnd:
            return False
        ctypes.windll.user32.SetWindowPos(
            hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
        return True
    except Exception:
        return False


class TopmostKeeper(QObject):
    """Re-assert ``HWND_TOPMOST`` for registered widgets on one shared timer."""

    def __init__(self, parent=None, interval=DEFAULT_INTERVAL_MS):
        super().__init__(parent)
        self._refs: list[weakref.ReferenceType] = []
        self._enabled = True
        self._timer = QTimer(self)
        self._timer.setInterval(interval)
        self._timer.timeout.connect(self.reassert)

    # -- registration ----------------------------------------------------
    def _prune(self):
        alive = []
        for ref in self._refs:
            widget = ref()
            if widget is not None:
                alive.append(ref)
        self._refs = alive

    def watch(self, widget):
        """Register ``widget`` and make sure the timer is running."""
        if widget is None:
            return widget
        self._prune()
        if all(ref() is not widget for ref in self._refs):
            self._refs.append(weakref.ref(widget))
        self.start()
        return widget

    # -- lifecycle -------------------------------------------------------
    def set_enabled(self, value: bool):
        self._enabled = bool(value)
        if self._enabled:
            self.start()
        else:
            self.stop()

    def start(self):
        if self._enabled and IS_WINDOWS and not self._timer.isActive():
            self._timer.start()

    def stop(self):
        self._timer.stop()

    @property
    def enabled(self) -> bool:
        return self._enabled

    # -- work ------------------------------------------------------------
    def reassert(self):
        if not self._enabled or not IS_WINDOWS:
            return
        self._prune()
        for ref in list(self._refs):
            widget = ref()
            if widget is None:
                continue
            try:
                if widget.isVisible():
                    raise_above_all(widget)
            except RuntimeError:
                # The C++ object is already gone; drop it on the next prune.
                continue


__all__ = ["IS_WINDOWS", "TopmostKeeper", "raise_above_all"]
