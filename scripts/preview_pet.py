"""Render the assembled pet widget, at a realistic device pixel ratio.

The face previews draw the rig straight into an image, which is the one place
the canvas's device pixel ratio cannot hurt: a painter on a plain QImage has
nothing to inherit.  The widget is different -- it hands the same canvas back
and forth every frame -- so the bug that made the whole face sit zoomed in on
screen was invisible in `preview_face.py` and obvious here.

    python scripts/preview_pet.py

Prints a fidelity check per frame: a frame that no longer resembles the
artwork is a crop or a rescale, and that is exactly the failure this catches.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np                                          # noqa: E402
from PySide6.QtCore import QPointF, Qt                       # noqa: E402
from PySide6.QtGui import (QColor, QFont, QImage, QPainter,  # noqa: E402
                           QPixmap)
from PySide6.QtWidgets import QApplication                   # noqa: E402

from scholarpet import pet as P                              # noqa: E402
from scholarpet.face import face_for, load_rig               # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SIZE = 100                 # the settings default, i.e. what users actually see
DPR = 1.25                 # the display scale this was reported on
LABEL_H = 24
GAP = 10
BACKGROUND = QColor("#f4f5f9")
INK = QColor("#1d2436")

# The last entry repeats an earlier pose on purpose: a frame that changes just
# because it is the second frame drawn is the bug this script exists for.
FRAMES = [
    ("idle", (1.0, 0.0, (0.0, 0.0))),
    ("看右下", (1.0, 0.0, (0.7, 0.5))),
    ("半眨眼", (0.55, 0.0, (0.0, 0.2))),
    ("说话", (1.0, 0.6, (0.0, 0.0))),
    ("再看右下", (1.0, 0.0, (0.7, 0.5))),
]


def render_widget(expression, dpr=DPR):
    """The widget's own paint path, onto a device that carries the ratio."""
    width = int(round(SIZE * dpr))
    height = int(round(P.Pet.preferred_height(SIZE) * dpr))
    image = QImage(width, height, QImage.Format.Format_RGBA8888)
    image.setDevicePixelRatio(dpr)
    image.fill(0)

    portrait = P.avatar_pixmap(SIZE * P.ART_RATIO, dpr)
    face = face_for(portrait, P._haibara_pixmap(), load_rig())
    frame = face.render(*expression)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    P.paint_pet(painter, SIZE, "#6475ed", 0.0, False, True, dpr, False,
                "翻译中…" if expression[1] else "框选翻译 ⌗", frame=frame)
    painter.end()
    return image, frame


def array_of(image):
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    stride, height = image.bytesPerLine(), image.height()
    raw = np.frombuffer(image.constBits(), np.uint8, count=stride * height)
    return raw.reshape(height, stride // 4, 4)[:, :image.width()].copy()


def fidelity(image, dpr=DPR):
    """How far the painted portrait is from the artwork it is made of."""
    pixels = array_of(image).astype(int)
    top = int(round(P.ART_TOP * SIZE * dpr))
    left = int(round((SIZE - SIZE * P.ART_RATIO) / 2 * dpr))
    side = int(round(SIZE * P.ART_RATIO * dpr))
    painted = pixels[top:top + side, left:left + side]
    if painted.shape[0] != side or painted.shape[1] != side:
        return 255.0
    artwork = QPixmap(str(ROOT / "assets" / "haibara_head.png")).toImage() \
        .scaled(side, side, Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
    want = array_of(artwork).astype(int)
    alpha = painted[..., 3:4] / 255.0
    flat = painted[..., :3] * alpha + 255.0 * (1 - alpha)
    want_alpha = want[..., 3:4] / 255.0
    flat_want = want[..., :3] * want_alpha + 255.0 * (1 - want_alpha)
    return float(np.abs(flat - flat_want).max(axis=2).mean())


def strip(destination):
    cells = []
    worst = 0.0
    for name, expression in FRAMES:
        image, _frame = render_widget(expression)
        score = fidelity(image)
        worst = max(worst, score)
        print(f"  {name:10s} drift vs artwork: mean {score:5.2f}/255")
        cells.append((name, image))

    # Layout is in logical units: the sheet carries the device pixel ratio, so
    # the painter works in 1/dpr-sized steps and each cell image (which carries
    # the ratio too) lands at its own logical size.
    cell_w = SIZE
    cell_h = P.Pet.preferred_height(SIZE)
    gap = 8
    width = gap + len(cells) * (cell_w + gap)
    height = gap * 2 + LABEL_H + cell_h
    sheet = QImage(int(round(width * DPR)), int(round(height * DPR)),
                   QImage.Format.Format_RGB32)
    sheet.setDevicePixelRatio(DPR)
    sheet.fill(BACKGROUND)
    painter = QPainter(sheet)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.setPen(INK)
    painter.setFont(QFont("Microsoft YaHei UI", 8))
    for index, (name, image) in enumerate(cells):
        x = gap + index * (cell_w + gap)
        painter.drawText(QPointF(x, gap + 16), name)
        painter.drawImage(QPointF(x, gap + LABEL_H), image)
    painter.end()
    out = ROOT / "docs" / destination
    sheet.save(str(out))
    print(f"wrote {out}")
    return worst


def main():
    app = QApplication.instance() or QApplication([])
    print(f"pet widget {SIZE} logical px at {DPR}x -> "
          f"{SIZE * DPR:.0f}x{P.Pet.preferred_height(SIZE) * DPR:.0f} device px")
    worst = strip("pet-widget-strip.png")
    if worst >= 12:
        print(f"FAIL: a frame is {worst:.1f}/255 away from the artwork -- "
              "the portrait is being drawn cropped or rescaled")
        return 1
    print(f"ok: worst frame {worst:.2f}/255 from the artwork")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
