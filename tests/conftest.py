import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope='session')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _release_clipboard(qapp):
    """Hand the clipboard back before the test that took it ends.

    ``QClipboard.setMimeData`` makes *us* the clipboard owner, and the offscreen
    platform plugin crashes in its own teardown while that is still true.  The
    symptom is nasty: pytest prints every test as passed and the process then
    dies with ``STATUS_ACCESS_VIOLATION`` (0xC0000005), which the build script
    reads as "Tests failed" on a suite that was entirely green.

    Measured with ``_off_probe.py``, one process per case:

        offscreen  setMimeData round trip (text or bitmap)  -> -1073741819
        offscreen  the same, after a plain text reset       -> 0
        windows    setMimeData round trip (text or bitmap)  -> 0

    So it is an offscreen teardown artefact, not a defect in the app: the same
    calls are clean on the platform the app actually ships on.  Dropping
    ownership with a text reset is enough to end every test cleanly.
    """
    yield
    qapp.clipboard().setText("")


@pytest.fixture(scope='session', autouse=True)
def _dispose_qt_before_shutdown(qapp):
    """Destroy every widget while a live QApplication can still do it.

    Tests that call ``show()`` leave top-level widgets registered with the
    platform plugin.  If any of them survive into interpreter shutdown, Qt's
    own teardown walks a half-destroyed object graph and the process dies with

        Fatal Python error: Aborted / Windows fatal exception: access violation
        Current thread 0x... (most recent call first): <no Python frame>

    *after* pytest has already printed ``67 passed``.  The run therefore looks
    green but exits non-zero, which aborted roughly one build in six until this
    fixture was added.  ``close()`` alone is not enough: it hides the window but
    the C++ side stays alive until an event-loop pass actually processes the
    deferred delete.
    """
    yield
    qapp.processEvents()
    for widget in qapp.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
