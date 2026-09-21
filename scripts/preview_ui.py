"""Render the real windows to PNGs for the README.

The pet preview (`preview_pet.py`) deliberately exercises the *frame loop*; this
script produces presentable stills of every surface a user actually sees:

    docs/ui-pet.png       the desktop pet with the rigged portrait
    docs/ui-popup.png     the selection bubble beside a word
    docs/ui-reader.png    the two-column reading window
    docs/ui-settings.png  the settings dialog

    python scripts/preview_ui.py

It renders at 2x (``QT_SCALE_FACTOR=2``, overridable) so the images stay sharp on
a high-DPI screen, and it uses the **native** platform plugin rather than the
offscreen one: the offscreen plugin ships no font database, so every label comes
out as a tofu box. That is acceptable for ``preview_pet.py`` (which only needs
the portrait) and useless here, where text is most of the picture.

Each image is checked for actually having content: a widget that silently fails
to paint would otherwise ship a blank rectangle into the README, and a blank
rectangle is hard to notice by filename.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Must be set before Qt is imported: the scale factor is read once, when
# QApplication is constructed.  The platform plugin is deliberately left alone --
# see the note about fonts in the module docstring.
os.environ.setdefault("QT_SCALE_FACTOR", "2")

import numpy as np                                            # noqa: E402
from PySide6.QtCore import QPoint, QEventLoop, QPointF, QRectF, QTimer, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter      # noqa: E402
from PySide6.QtWidgets import QApplication                     # noqa: E402

from scholarpet import pet as P                                # noqa: E402
from scholarpet.config import load_settings                    # noqa: E402
from scholarpet.face import face_for, load_rig                 # noqa: E402
from scholarpet.settings import SettingsDialog                 # noqa: E402
from scholarpet.views import Reader, SelectionPopup            # noqa: E402

DOCS = ROOT / "docs"
CARD = QColor("#f4f5f9")
SKIN = "#6475ed"

# A realistic sample of what the app is for: communications / anti-jamming
# papers, which is also what the bundled glossary is tuned to.
SAMPLE = [
    ("Beamforming improves the signal-to-interference-plus-noise ratio.",
     "波束成形能够提高信干噪比。"),
    ("Spread spectrum modulation makes the transmitted waveform harder to "
     "intercept and harder to jam.",
     "扩频调制使发射波形更难被截获，也更难被干扰。"),
    ("A narrowband jammer concentrates its power on the victim receiver's band.",
     "窄带干扰机把功率集中在受害接收机的频段上。"),
    ("The adaptive array places a null towards the direction of arrival of the "
     "interference.",
     "自适应阵列在干扰的到达方向上形成零陷。"),
    ("Antenna selection reduces the number of radio frequency chains that have "
     "to be built.",
     "天线选择可以减少需要构建的射频链路数量。"),
]


def pixels(image: QImage) -> np.ndarray:
    """An (h, w, 4) uint8 view of the image, copied out of Qt's buffer."""
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    stride, height = image.bytesPerLine(), image.height()
    raw = np.frombuffer(image.constBits(), np.uint8, count=stride * height)
    return raw.reshape(height, stride // 4, 4)[:, :image.width()].copy()


def ink_share(image: QImage) -> float:
    """Fraction of pixels that differ from the flat card colour by any amount.

    Used only as a "did anything paint at all?" tripwire, so it errs towards
    finding content: the pet image is the only one on a known background.
    """
    data = pixels(image)[..., :3].astype(int)
    reference = np.array([CARD.red(), CARD.green(), CARD.blue()])
    differing = np.abs(data - reference).max(axis=2) > 6
    return float(differing.mean())


def save(image: QImage, name: str) -> float:
    path = DOCS / name
    image.save(str(path))
    share = ink_share(image)
    print(f"  {name:22s} {image.width():4d}x{image.height():<4d}  "
          f"content {share * 100:5.1f}%  {path.stat().st_size:>8,} B")
    return share


def pet_image(dpr: float) -> QImage:
    """The pet on a light card, so it reads on GitHub's light *and* dark theme."""
    logical_w, logical_h = 190, 252
    image = QImage(int(logical_w * dpr), int(logical_h * dpr),
                   QImage.Format.Format_RGB32)
    image.setDevicePixelRatio(dpr)
    image.fill(CARD)

    size = 120
    portrait = P.avatar_pixmap(size * P.ART_RATIO, dpr)
    face = face_for(portrait, P._haibara_pixmap(), load_rig())
    frame = face.render(blink=1.0, mouth=0.0, gaze=(0.55, 0.35))

    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.translate((logical_w - size) / 2, 26)
        P.paint_pet(painter, size, SKIN, 0.0, False, True, dpr, False,
                    "框选翻译 ⌗", frame=frame)
        painter.resetTransform()
        painter.setPen(QColor("#7b879d"))
        painter.setFont(QFont("Microsoft YaHei UI", 9))
        painter.drawText(QRectF(0, logical_h - 44, logical_w, 44),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                         "灰原哀会眨眼\n视线跟着鼠标走")
    finally:
        painter.end()
    return image


def drained(widget, milliseconds=250):
    """Let the widget lay itself out and finish painting before it is grabbed.

    A real window needs an actual event-loop turn to paint; spinning
    ``processEvents`` immediately afterwards grabs a half-drawn frame.
    """
    widget.show()
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()
    QApplication.instance().processEvents()
    return widget


def widget_image(widget, name: str) -> float:
    drained(widget)
    image = widget.grab().toImage()
    widget.hide()
    return save(image, name)


def main() -> int:
    app = QApplication.instance() or QApplication([])
    DOCS.mkdir(exist_ok=True)
    dpr = float(app.primaryScreen().devicePixelRatio())
    platform = app.platformName()
    print(f"platform={platform} dpr={dpr}")
    if platform.startswith("offscreen"):
        print("warning: the offscreen plugin has no fonts -- every label will "
              "render as a tofu box. Unset QT_QPA_PLATFORM for usable images.")

    problems = []

    if save(pet_image(dpr), "ui-pet.png") < 0.02:
        problems.append("ui-pet.png looks empty")

    popup = SelectionPopup()
    popup.configure(side="right", width=470, font_size=15)
    popup.show_translation(*SAMPLE[0], anchor=QPoint(600, 300))
    if widget_image(popup, "ui-popup.png") < 0.02:
        problems.append("ui-popup.png looks empty")

    reader = Reader()
    reader.resize(880, 720)
    reader.set_result(
        [{"text": text, "confidence": 0.97} for text, _ in SAMPLE],
        [chinese for _, chinese in SAMPLE],
        "本地离线 · Argos EN→ZH", 2.4)
    if widget_image(reader, "ui-reader.png") < 0.02:
        problems.append("ui-reader.png looks empty")

    dialog = SettingsDialog(load_settings())
    dialog.resize(760, 620)
    if widget_image(dialog, "ui-settings.png") < 0.02:
        problems.append("ui-settings.png looks empty")

    if problems:
        for problem in problems:
            print("FAIL: " + problem)
        return 1
    print("ok: every surface produced content")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
