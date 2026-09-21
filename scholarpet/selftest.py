"""Frozen-build self check.

PyInstaller collects DLLs by walking import graphs, so a bundle can look
complete while Qt or OpenSSL still fails to load at startup. This module gives
the build script something stronger than "the process stayed alive": it really
creates the GUI objects, really loads the offline translation model and really
runs the OCR engine, then reports each result.

Run it as ``ScholarPet.exe --selftest``. Results are printed to stdout (useful
for source runs) and written to ``<data dir>/selftest.json`` because the frozen
executable has no console.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path


def _record(results, name, fn):
    start = time.monotonic()
    try:
        detail = fn()
        ok = True
    except Exception as exc:  # noqa: BLE001 - the report must never raise
        detail = f"{type(exc).__name__}: {exc}"
        ok = False
        results.append({"check": name, "ok": ok, "detail": detail,
                        "seconds": round(time.monotonic() - start, 2),
                        "trace": traceback.format_exc()[-2000:]})
        return False
    results.append({"check": name, "ok": ok, "detail": detail,
                    "seconds": round(time.monotonic() - start, 2)})
    return True


def _check_qt_core():
    from PySide6.QtCore import qVersion
    return f"Qt {qVersion()}"


def _check_application():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    return f"platform={app.platformName()}"


def _check_widgets():
    from PySide6.QtWidgets import QApplication
    from .config import DEFAULTS
    from .pet import Pet, pet_icon
    from .views import Overlay, Reader, SelectionPopup
    from .settings import SettingsDialog
    app = QApplication.instance() or QApplication([])
    # Widgets are rendered with grab() instead of show(): this proves painting
    # works without flashing windows across the user's desktop.
    made = []
    pet = Pet(DEFAULTS.copy())
    assert not pet.grab().isNull(), "pet rendered an empty pixmap"
    made.append("Pet")
    reader = Reader(); reader.set_result([{"text": "Beamforming improves SNR.", "rect": [0, 0, 40, 12], "confidence": .9}],
                                        ["波束成形提高信噪比。"], "selftest", 0.0)
    assert not reader.grab().isNull(), "reader rendered an empty pixmap"
    made.append("Reader")
    dialog = SettingsDialog(DEFAULTS.copy())
    assert not dialog.grab().isNull(), "settings rendered an empty pixmap"
    made.append("SettingsDialog")
    popup = SelectionPopup(); popup.resize(430, 200)
    popup.show_translation("Beamforming", "波束成形", None)
    popup.hide()
    assert not popup.grab().isNull(), "selection popup rendered an empty pixmap"
    made.append("SelectionPopup")
    assert not pet_icon().isNull(), "tray icon is empty"
    made.append("TrayIcon")
    for widget in (pet, reader, dialog, popup):
        widget.deleteLater()
    app.processEvents()
    return "constructed: " + ", ".join(made)


def _check_pet_avatar():
    """Guards against forgetting to bundle assets/ into the frozen build."""
    from PySide6.QtGui import QGuiApplication
    QGuiApplication.instance() or __import__("PySide6.QtWidgets", fromlist=["QApplication"]).QApplication([])
    from .pet import _haibara_pixmap
    pix = _haibara_pixmap()
    assert not pix.isNull(), "灰原哀 avatar asset was not bundled (assets/haibara_head.png)"
    assert pix.hasAlphaChannel(), "avatar lost its alpha channel"
    return f"{pix.width()}x{pix.height()} with alpha"


def _check_offline_translation():
    """Exercise the real user path so terminology correction is covered too."""
    from .config import DEFAULTS
    from .offline import model_path
    from .translation import translate_blocks
    settings = DEFAULTS.copy()
    settings["engine"] = "offline"
    source = "Beamforming improves the signal-to-interference-plus-noise ratio."
    out, label = translate_blocks([source], settings)
    text = out[0] if out else ""
    assert text.strip(), "offline model returned no text"
    assert any("\u4e00" <= ch <= "\u9fff" for ch in text), f"translation is not Chinese: {text!r}"
    assert "\u2581" not in text, f"decoder artefact leaked into the translation: {text!r}"
    assert "波束成形" in text and "信干噪比" in text, (
        f"terminology correction is not active in this build: {text!r}")
    return f"model={model_path(settings).name} · {label} -> {text}"


def _check_face_rig():
    """Guards the animated face: the rig sidecar must ship *and* move real pixels.

    Two distinct failures are possible in a frozen build and neither shows up as
    a crash: ``assets/haibara_head.rig.json`` may be missing (the face then
    silently falls back to the baked-in coordinates), or the compositor may be
    present but produce identical frames. This check rules both out.
    """
    import numpy as np
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    from .face import face_for, load_rig, rig_matches
    from .pet import _haibara_pixmap, avatar_pixmap
    QApplication.instance() or QApplication([])

    source = _haibara_pixmap()
    assert not source.isNull(), "avatar asset missing, so the rig cannot be exercised"
    rig = load_rig()
    geometry = (source.width(), source.height())
    assert rig_matches(rig, geometry), (
        "assets/haibara_head.rig.json was not bundled -- the face would animate "
        f"from baked-in coordinates instead of the calibration for {geometry[0]}x{geometry[1]}")

    face = face_for(avatar_pixmap(220, 1.0), source, rig)

    def frame(blink, mouth, gaze=(0.0, 0.0)):
        image = face.render(blink, mouth, gaze).toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        return np.frombuffer(image.constBits(), np.uint8, count=image.sizeInBytes()).copy()

    # 0.995 (not 1.0) keeps the compositor on its slow path for every pose, so the
    # three frames are compared like for like instead of against the untouched art.
    neutral = frame(0.995, 0.0)
    shut = frame(0.0, 0.0)
    talking = frame(0.995, 0.9)

    total = neutral.size
    blinking = int(np.count_nonzero(neutral != shut))
    speaking = int(np.count_nonzero(neutral != talking))
    assert blinking > 0, "closing the eyes changed no pixels: the blink rig is dead"
    assert speaking > 0, "opening the mouth changed no pixels: the mouth rig is dead"
    assert blinking < total, "the blink repainted the whole portrait"

    return (f"{geometry[0]}x{geometry[1]} rig · blink {100 * blinking / total:.1f}% "
            f"of pixels · mouth {100 * speaking / total:.1f}%")


def _check_ocr():
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    from .ocr import extract_blocks
    image = Image.new("RGB", (1000, 140), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 30)
    except OSError:
        font = ImageFont.load_default()
    draw.text((20, 30), "Beamforming improves signal quality.", font=font, fill="black")
    blocks = extract_blocks(np.array(image))
    text = " ".join(block.get("text", "") for block in blocks)
    assert "Beamforming" in text or "beamforming" in text.lower(), f"OCR could not read the sample: {text!r}"
    return f"recognised {len(blocks)} block(s): {text.strip()[:70]}"


def _check_tls():
    import ssl
    return ssl.OPENSSL_VERSION


def _check_data_dir():
    from .config import data_dir
    path = data_dir()
    probe = path / ".selftest-write"
    probe.write_text("ok", "utf-8")
    probe.unlink()
    return str(path)


def _check_selection_monitor():
    """Guards the clipboard path that ships to users.

    A frozen build once shipped a monitor that blanked the clipboard before
    asking for a selection and then restored a snapshot that could not carry a
    bitmap, so a screenshot taken with Win+Shift+S could no longer be pasted
    into WeChat or QQ. This check really round-trips a bitmap through the frozen
    code, so that cannot come back unnoticed.
    """
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    from .selection_monitor import (SelectionMonitor, _clipboard_snapshot,
                                    _restore_clipboard)
    QApplication.instance() or QApplication([])
    monitor = SelectionMonitor()
    available = monitor.available()

    clipboard = QApplication.clipboard()
    previous = _clipboard_snapshot()
    image = QImage(16, 12, QImage.Format.Format_RGB32)
    image.fill(0xFF3366FF)
    try:
        clipboard.setImage(image)
        saved = _clipboard_snapshot()
        clipboard.clear()
        _restore_clipboard(saved)
        back = clipboard.image()
        assert not back.isNull(), "a snapshot could not put a bitmap back"
        assert back.pixel(0, 0) == 0xFF3366FF, "the bitmap came back corrupted"
    finally:
        _restore_clipboard(previous)
    return f"windows_api={available} · clipboard keeps bitmaps"


def run(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    results: list[dict] = []
    for name, fn in [("qt_core", _check_qt_core),
                     ("qapplication", _check_application),
                     ("widgets", _check_widgets),
                     ("pet_avatar", _check_pet_avatar),
                     ("face_rig", _check_face_rig),
                     ("selection_monitor", _check_selection_monitor),
                     ("offline_translation", _check_offline_translation),
                     ("ocr", _check_ocr),
                     ("tls", _check_tls),
                     ("data_dir", _check_data_dir)]:
        _record(results, name, fn)

    ok = all(item["ok"] for item in results)
    report = {"ok": ok, "frozen": bool(getattr(sys, "frozen", False)),
              "executable": sys.executable, "python": sys.version.split()[0],
              "results": results}

    destination = None
    for arg in argv:
        if arg.startswith("--selftest-out="):
            destination = Path(arg.split("=", 1)[1])
    if destination is None:
        try:
            from .config import data_dir
            destination = data_dir() / "selftest.json"
        except Exception:  # noqa: BLE001
            destination = Path(os.environ.get("TEMP", ".")) / "scholarpet-selftest.json"
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        report["report"] = str(destination)
    except OSError as exc:
        report["report"] = f"could not write report: {exc}"

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


__all__ = ["run"]
