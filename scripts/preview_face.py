"""Render the animation poses to a PNG so a human eye can judge them.

The pet's motion is built by compositing pieces of one still image, which is
exactly the kind of thing that looks fine in theory and awful on screen: a lid
that settles too low, an iris that slides over the lash line, a mouth hole that
pokes out past the lip.  This script draws every pose next to the untouched
portrait so those mistakes are obvious without launching the app, and prints a
numeric fidelity check for the pose that is supposed to be invisible.

    python scripts/preview_face.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np                                          # noqa: E402
from PySide6.QtCore import QRectF, Qt                       # noqa: E402
from PySide6.QtGui import (QColor, QFont, QImage, QPainter,  # noqa: E402
                           QPixmap)
from PySide6.QtWidgets import QApplication                   # noqa: E402

from scholarpet.face import (Face, feature_layers, load_rig,  # noqa: E402
                             split_features)

ROOT = Path(__file__).resolve().parents[1]
CELL = 240
COLUMNS = 4
BACKGROUND = QColor("#f4f5f9")
INK = QColor("#1d2436")

POSES = [
    ("idle", dict(blink=1.0)),
    ("blink 0.7", dict(blink=0.7)),
    ("blink 0.4", dict(blink=0.4)),
    ("blink 0.0 闭眼", dict(blink=0.0)),
    ("mouth 0.35", dict(mouth=0.35)),
    ("mouth 0.7", dict(mouth=0.7)),
    ("mouth 1.0", dict(mouth=1.0)),
    ("说话+半眨眼", dict(mouth=0.6, blink=0.5)),
    ("看左", dict(gaze=(-1.0, 0.0))),
    ("看右", dict(gaze=(1.0, 0.0))),
    ("看上", dict(gaze=(0.0, -1.0))),
    ("看下", dict(gaze=(0.0, 1.0))),
]


def build_face(side):
    source = QPixmap(str(ROOT / "assets" / "haibara_head.png"))
    if source.isNull():
        raise SystemExit("assets/haibara_head.png is missing")
    scaled = source.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
    return Face(scaled, load_rig(), layers=feature_layers(source, load_rig()))


def fidelity(face):
    """How far the 'nothing is moving' composite drifts from the artwork."""
    reference = face.portrait.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    composed = face.render(blink=0.995, mouth=0.0, gaze=(0.0, 0.0)).toImage()
    composed = composed.convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = reference.width(), reference.height()
    a = np.frombuffer(reference.constBits(), np.uint8, count=reference.bytesPerLine() * height)
    a = a.reshape(height, reference.bytesPerLine() // 4, 4)[:, :width].astype(int)
    b = np.frombuffer(composed.constBits(), np.uint8, count=composed.bytesPerLine() * height)
    b = b.reshape(height, composed.bytesPerLine() // 4, 4)[:, :width].astype(int)
    delta = np.abs(a - b)
    return delta.mean(), delta.max(), (delta.max(axis=2) > 24).mean() * 100


def layer_sheet(source, cell=260, crop=(0.20, 0.55, 0.60, 0.26)):
    """Show the extracted layers, zoomed on the face, so a bad mask is obvious."""
    full = feature_layers(source, load_rig())
    strip = (full["lash"], full["iris"], full["base"], full["lips"])
    names = ("lash 睫毛层", "iris 虹膜层", "base 去虹膜底图", "lips 唇线层")
    width, height = source.width(), source.height()
    window = QRectF(crop[0] * width, crop[1] * height, crop[2] * width, crop[3] * height)
    aspect = window.height() / window.width()
    box = (cell, cell * aspect)
    canvas = QPixmap(int(cell * len(strip)), int(box[1]) + 26)
    canvas.fill(BACKGROUND)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    for index, (layer, name) in enumerate(zip(strip, names)):
        x = index * cell
        # A mid grey plate makes the semi-transparent masks readable.
        painter.fillRect(QRectF(x, 0, box[0], box[1]), QColor("#6f7690"))
        painter.drawPixmap(QRectF(x, 0, box[0], box[1]), layer, window)
        painter.setPen(INK)
        painter.setFont(QFont("Microsoft YaHei UI", 9))
        painter.drawText(QRectF(x, box[1] + 2, box[0], 22), Qt.AlignmentFlag.AlignCenter, name)
    painter.end()
    return canvas


def cell_rect(source_size, cell):
    """Fit ``source_size`` inside a square cell without distorting it."""
    scale = min(cell / source_size[0], cell / source_size[1])
    width, height = source_size[0] * scale, source_size[1] * scale
    return QRectF((cell - width) / 2, (cell - height) / 2, width, height)


def sheet(face, poses, cell, columns, crop=None, title=""):
    rows = (len(poses) + columns - 1) // columns
    header = 34 if title else 0
    width = columns * cell
    height = rows * (cell + 26) + header
    canvas = QPixmap(width, height)
    canvas.fill(BACKGROUND)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if title:
        painter.setPen(INK)
        painter.setFont(QFont("Microsoft YaHei UI", 11))
        painter.drawText(QRectF(14, 6, width - 28, 22),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
    for index, (label, kwargs) in enumerate(poses):
        row, column = divmod(index, columns)
        x, y = column * cell, header + row * (cell + 26)
        frame = face.render(**kwargs)
        painter.setPen(QColor("#c9cddb"))
        painter.drawRect(QRectF(x + 0.5, y + 0.5, cell - 1, cell - 1))
        if crop:
            source = QRectF(crop[0] * face.size[0], crop[1] * face.size[1],
                            crop[2] * face.size[0], crop[3] * face.size[1])
            target = cell_rect((source.width(), source.height()), cell).translated(x, y)
            painter.drawPixmap(target, frame, source)
        else:
            target = cell_rect((frame.width(), frame.height()), cell).translated(x, y)
            painter.drawPixmap(target, frame, QRectF(0, 0, frame.width(), frame.height()))
        painter.setPen(INK)
        painter.setFont(QFont("Microsoft YaHei UI", 9))
        painter.drawText(QRectF(x, y + cell + 2, cell, 22),
                         Qt.AlignmentFlag.AlignCenter, label)
    painter.end()
    return canvas


def main():
    app = QApplication.instance() or QApplication([])  # noqa: F841
    destination = ROOT / "docs"
    destination.mkdir(parents=True, exist_ok=True)
    source = QPixmap(str(ROOT / "assets" / "haibara_head.png"))
    rig = load_rig()
    metrics = split_features(source, rig)["metrics"]
    print("measured geometry:", {k: {n: round(v, 3) for n, v in m.items()}
                                 for k, m in metrics.items()})
    layer_sheet(source).save(str(destination / "face-layers.png"))
    print(f"wrote {destination / 'face-layers.png'}")
    for side in (240, 100):
        face = build_face(side)
        mean, worst, changed = fidelity(face)
        print(f"portrait {side}px · composite drift vs artwork: "
              f"mean {mean:.2f}/255, max {worst}, pixels off by >24: {changed:.2f}%")
        suffix = "" if side == 240 else "-small"
        sheet(face, POSES, CELL, COLUMNS,
              title=f"研译桌宠 · 表情帧（头像渲染尺寸 {side}px）").save(
            str(destination / f"face-preview{suffix}.png"))
        sheet(face, POSES, CELL, COLUMNS, crop=(0.20, 0.52, 0.60, 0.34),
              title=f"五官特写（头像渲染尺寸 {side}px）").save(
            str(destination / f"face-preview{suffix}-zoom.png"))
        print(f"wrote {destination / f'face-preview{suffix}.png'} (+ zoom)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
