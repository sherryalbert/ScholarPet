"""Bring the still portrait to life: blink, talk, and let the eyes follow you.

We only ship one PNG and no artist, so the animation is done by *rigging* that
image the way a paper puppet is rigged -- every moving part is a piece of the
original artwork, moved or covered, never repainted from scratch:

* **Blink.**  Squeezing the eye patch vertically does *not* work: at one pixel
  tall the lash line, the iris and the white average out into a grey smear.
  So the artwork's own lash band is lifted out as a separate layer and slid
  down over the eye, while the eyeball is clipped to the opening left between
  the descending lid and the rising lower lid.  A closed eye is then literally
  the character's own lash line, moved.  Skin is only laid down where the lid
  actually travelled, which is why an open eye ends up pixel-identical to the
  artwork instead of having its fringe painted over.
* **Talk.**  The mouth is a thin stroke.  We erase it, draw a small opening
  between the lips, then lay the original stroke back on top as the lip line.
* **Look.**  The irises are extracted from the artwork at calibration time
  (``scripts/calibrate_face.py``), erased from a copy of the portrait, and drawn
  back with a small offset.  Sliding them inside the untouched sclera is what
  turns a picture into something that watches the cursor.

Everything is deliberately *small*: a pet that jerks around is annoying.  Idle
motion is a couple of pixels, and the amplitudes below are the honest limits of
what a head-only chibi drawing can take before the composite shows seams.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (QColor, QImage, QLinearGradient, QPainter,
                           QPainterPath, QPixmap)

RIG_FILE = "haibara_head.rig.json"

# --- amplitudes (fractions of the part being moved, so the pet scales) ---
LID_TRAVEL = 0.60        # how far the lash band slides down when fully shut:
                         # the upper lid is what closes an eye, so it carries
                         # most of the distance and the lower lid only helps
LID_RISE = 0.35          # how far the lower lid climbs, so that a shut eye
                         # leaves no sliver of white at the corners
LASH_BAND = 0.46         # top slice of the eye box searched for the lash
GAZE_X = 0.085           # iris travel, fraction of the eye box width
GAZE_Y = 0.055           # ...and height
MOUTH_OPEN = 0.95        # tallest mouth opening, fraction of stroke height
MOUTH_WIDEN = 0.10       # the corners pull apart a little as it opens
BLINK_SECONDS = 0.19     # fast: a slow blink reads as sleepy, not alive
BLINK_CLOSE = 0.35       # fraction of the blink spent closing.  At 30fps this
                         # is what guarantees a frame where the eye is really
                         # shut, instead of a shallow dip

MOUTH_DEEP = QColor("#5b2229")
MOUTH_INNER = QColor("#8a3b45")
MOUTH_TONGUE = QColor("#d98f96")

# Used when the sidecar is missing, so a partially unpacked install still
# animates (slightly off-target) instead of failing to start.
FALLBACK_RIG = {
    "source": "haibara_head.png",
    "left_eye": [0.2432, 0.5973, 0.2041, 0.1268],
    "right_eye": [0.5797, 0.5941, 0.1962, 0.1069],
    "mouth": [0.4785, 0.8038, 0.1021, 0.0144],
    "left_iris": [0.3022, 0.6523, 0.0941, 0.0574],
    "right_iris": [0.6364, 0.6404, 0.0901, 0.0486],
}
RECT_KEYS = ("left_eye", "right_eye", "mouth", "left_iris", "right_iris")
LAYER_KEYS = ("base", "iris", "lips", "lash", "hair")
SIDES = ("left", "right")


def load_rig(asset_dir=None, name=RIG_FILE) -> dict:
    """Read the calibration sidecar, falling back to the baked-in numbers."""
    rig = dict(FALLBACK_RIG)
    if asset_dir is None:
        asset_dir = Path(__file__).resolve().parents[1] / "assets"
    try:
        raw = json.loads((Path(asset_dir) / name).read_text("utf-8"))
    except (OSError, ValueError):
        return rig
    for key in RECT_KEYS:
        value = raw.get(key)
        if isinstance(value, (list, tuple)) and len(value) == 4:
            try:
                rig[key] = [float(v) for v in value]
            except (TypeError, ValueError):
                continue
    if isinstance(raw.get("source"), str):
        rig["source"] = raw["source"]
    if isinstance(raw.get("size"), (list, tuple)) and len(raw["size"]) == 2:
        rig["size"] = [int(raw["size"][0]), int(raw["size"][1])]
    return rig


def rig_matches(rig, size) -> bool:
    """True when ``rig`` was calibrated for a ``size`` artwork."""
    recorded = rig.get("size")
    return bool(recorded and list(recorded) == [int(size[0]), int(size[1])])


# --- Qt <-> numpy -------------------------------------------------------
def _to_array(pixmap: QPixmap):
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    buffer = image.constBits()
    stride = image.bytesPerLine()
    array = np.frombuffer(buffer, np.uint8, count=stride * image.height())
    return array.reshape(image.height(), stride // 4, 4)[:, :image.width()].copy()


def _to_pixmap(array) -> QPixmap:
    array = np.ascontiguousarray(array, dtype=np.uint8)
    height, width = array.shape[:2]
    image = QImage(array.tobytes(), width, height, width * 4, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(image.copy())


def _plain(pixmap: QPixmap) -> QPixmap:
    """Drop the device pixel ratio so we can compose in raw device pixels.

    ``QPixmap.fromImage`` is documented to carry the image's ratio over, not to
    clear it, so the ratio is set explicitly rather than assumed away.
    """
    out = QPixmap.fromImage(pixmap.toImage())
    out.setDevicePixelRatio(1.0)
    return out


def _pixels(rect, width, height, pad=0, top=0.0, bottom=1.0):
    """Normalised rect -> pixel rect, optionally clipped to a vertical slice."""
    x, y, w, h = rect
    x0 = max(0, int(round(x * width)) - pad)
    y0 = max(0, int(round((y + h * top) * height)) - pad)
    x1 = min(width, int(round((x + w) * width)) + pad)
    y1 = min(height, int(round((y + h * bottom) * height)) + pad)
    return x0, y0, max(1, x1 - x0), max(1, y1 - y0)


def _long_runs(mask, minimum):
    """Keep only horizontal runs at least ``minimum`` long, row by row.

    The lash band sits under the character's fringe, so a few strands of hair
    land inside the eye box.  A lash line is a long horizontal stroke while a
    strand is a short diagonal one, which makes run length a clean separator --
    and it matters, because a stray strand would blink along with the eye.
    Keep this generous: the eye's dark outline curves away steeply at the
    corners, so runs get short fast as you move down the lid.
    """
    out = np.zeros_like(mask)
    for y in range(mask.shape[0]):
        row = mask[y]
        if not row.any():
            continue
        edges = np.diff(np.concatenate(([0], row.astype(np.int8), [0])))
        for start, end in zip(np.nonzero(edges == 1)[0], np.nonzero(edges == -1)[0]):
            if end - start >= minimum:
                out[y, start:end] = True
    return out


def _alpha_layer(array, mask) -> QPixmap:
    layer = np.zeros_like(array)
    layer[..., :3] = array[..., :3]
    layer[..., 3] = (array[..., 3].astype(np.float32) * mask).astype(np.uint8)
    return _to_pixmap(layer)


def _sclera_colour(rgb, box, fallback=(243, 240, 237)):
    """The white of the eye: bright, unsaturated pixels inside ``box``."""
    x, y, w, h = box
    patch = rgb[y:y + h, x:x + w]
    if patch.size == 0:
        return np.array(fallback, np.float32)
    luma = (patch[..., 0] * 299 + patch[..., 1] * 587 + patch[..., 2] * 114) // 1000
    mask = (luma > 200) & ((patch.max(2) - patch.min(2)) < 22)
    if mask.sum() < 24:
        return np.array(fallback, np.float32)
    return np.median(patch[mask], axis=0).astype(np.float32)


def split_features(pixmap: QPixmap, rig: dict) -> dict:
    """Cut the moving parts out of the untouched portrait.

    Returns same-sized layers plus the measured geometry the compositor needs:

    ``base``   the portrait with the irises painted out (filled with the
               surrounding sclera white) so a displaced iris never uncovers a
               copy of itself;
    ``iris``   just the irises, alpha masked;
    ``lips``   just the mouth stroke, used as the lip line over an open mouth;
    ``lash``   just the two lash bands -- the layer that blinks;
    ``metrics`` the lash band's bottom and the eye's own lower lid, both as
               fractions of the eye box, so lid travel is measured rather than
               guessed.

    Doing this once at full resolution instead of per display size also means
    the anti-aliased mask edges get averaged away when we downscale.
    """
    array = _to_array(pixmap)
    height, width = array.shape[:2]
    rgb = array[..., :3].astype(np.int32)
    chroma = rgb.max(2) - rgb.min(2)
    cool = rgb[..., 2] >= rgb[..., 0] - 4
    luma = (rgb[..., 0] * 299 + rgb[..., 1] * 587 + rgb[..., 2] * 114) // 1000
    solid = array[..., 3] > 0

    iris_mask = np.zeros((height, width), np.float32)
    lash_mask = np.zeros((height, width), np.float32)
    hair_mask = np.zeros((height, width), np.float32)
    metrics = {}
    warm = (rgb[..., 0] > rgb[..., 2] + 12) & (chroma > 16)
    for side in SIDES:
        x, y, w, h = _pixels(rig[f"{side}_iris"], width, height, pad=3)
        region = np.zeros((height, width), bool)
        region[y:y + h, x:x + w] = True
        iris_mask = np.maximum(iris_mask, np.clip((chroma - 10) / 30.0, 0, 1) * cool * region)

        bx, by, bw, bh = _pixels(rig[f"{side}_eye"], width, height)
        x, y, w, h = _pixels(rig[f"{side}_eye"], width, height, pad=1, bottom=LASH_BAND)
        band = np.zeros((height, width), bool)
        band[y:y + h, x:x + w] = True
        dark = np.clip((150 - luma) / 45.0, 0, 1) * band
        dark = dark * _long_runs(dark > 0.45, max(4, int(w * 0.20)))
        lash_mask = np.maximum(lash_mask, dark)
        rows = np.nonzero(dark[by:by + bh, bx:bx + bw].max(axis=1) > 0.35)[0]
        lash_bottom = float(rows.max() / bh) if len(rows) else 0.30
        # The artwork's own lower lid, measured from the iris rather than from
        # "the lowest dark pixel in the box": a strand of fringe crosses the
        # corner of the box and would drag it down to the chin.
        ix, iy, iw, ih = _pixels(rig[f"{side}_iris"], width, height)
        eye_bottom = (iy + ih - by) / bh + 0.03
        metrics[side] = {"lash_bottom": lash_bottom,
                         "eye_bottom": min(0.95, max(0.80, eye_bottom))}

        # The fringe hangs into the eye box.  When the lid comes down we paint
        # skin over the eye -- but the hair is *in front of* the lid in this
        # drawing, so it has to be laid back on top of the skin afterwards, or
        # a blink would shave the bottom off her fringe.  Hair here means
        # brown and dark; the lash is brown and dark too, so it is subtracted
        # explicitly: it must disappear under the descending lid.
        x, y, w, h = _pixels(rig[f"{side}_eye"], width, height, pad=2)
        zone = np.zeros((height, width), bool)
        zone[y:y + h, x:x + w] = True
        hair_mask = np.maximum(hair_mask, np.clip(
            (178 - luma) / 38.0, 0, 1) * warm * zone * np.clip(1.0 - dark * 2.0, 0, 1))
    iris_mask *= solid
    lash_mask *= solid

    sclera = _sclera_colour(rgb, _pixels(rig["left_eye"], width, height))
    alpha = iris_mask[..., None]
    base = array.copy()
    base[..., :3] = np.clip(rgb * (1 - alpha) + sclera * alpha, 0, 255).astype(np.uint8)

    mx, my, mw, mh = _pixels(rig["mouth"], width, height)
    lip_mask = np.zeros((height, width), np.float32)
    lip_mask[my:my + mh, mx:mx + mw] = np.clip(
        (222 - luma[my:my + mh, mx:mx + mw]) / 42.0, 0, 1)
    lip_mask *= solid

    return {"base": _to_pixmap(base), "iris": _alpha_layer(array, iris_mask),
            "lips": _alpha_layer(array, lip_mask), "lash": _alpha_layer(array, lash_mask),
            "hair": _alpha_layer(array, hair_mask), "metrics": metrics}


_LAYERS: dict = {}


def feature_layers(source: QPixmap, rig: dict) -> dict:
    """Full resolution layers, computed once per process (they are 1254px)."""
    key = (source.cacheKey(),) + tuple(tuple(rig.get(k, ())) for k in RECT_KEYS)
    cached = _LAYERS.get(key)
    if cached is None:
        cached = split_features(source, rig)
        if len(_LAYERS) > 3:
            _LAYERS.clear()
        _LAYERS[key] = cached
    return cached


def _skin_patch(source: QPixmap, rect: QRect, below=True, feather=(0.04, 0.96)) -> QPixmap:
    """Cheek-coloured skin to lay over ``rect``.

    Sampled from *below* the rect by default: the bottom rows of an eye box
    still contain the lower lash line, and smearing those made the lid come
    down in eye-white instead of skin.  Smeared rather than flat-filled so the
    cheek's own shading survives and the cover-up leaves no visible rectangle.
    """
    band = max(3, int(rect.height() * 0.20))
    width = max(2, int(rect.width() * 0.6))
    x = max(0, rect.x() + (rect.width() - width) // 2)
    y = rect.bottom() + 2 if below else max(0, rect.bottom() + 1 - band)
    y = max(0, min(y, source.height() - 1))
    strip = source.copy(x, y, min(width, source.width() - x),
                        max(1, min(band, source.height() - y)))
    out = strip.scaled(rect.width(), rect.height(), Qt.AspectRatioMode.IgnoreAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
    # Fade the left and right edges so no rectangle shows at the corners, where
    # the eye box runs into her fringe.
    veil = QPixmap(out.size())
    veil.fill(Qt.GlobalColor.transparent)
    across = QLinearGradient(0, 0, out.width(), 0)
    across.setColorAt(0.0, QColor(255, 255, 255, 0))
    across.setColorAt(feather[0], QColor(255, 255, 255, 255))
    across.setColorAt(feather[1], QColor(255, 255, 255, 255))
    across.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter = QPainter(veil)
    painter.fillRect(QRectF(0, 0, out.width(), out.height()), across)
    painter.end()
    punch = QPainter(out)
    punch.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    punch.drawPixmap(0, 0, veil)
    punch.end()
    return out


class Face:
    """The animatable parts of one already-scaled portrait."""

    def __init__(self, portrait: QPixmap, rig: dict, layers=None):
        self.portrait = portrait
        self.rig = rig
        self.dpr = portrait.devicePixelRatio() or 1.0
        self.size = (portrait.width(), portrait.height())
        self._canvas = None
        full = layers or split_features(portrait, rig)
        self.layers = {key: _plain(full[key].scaled(
            self.size[0], self.size[1], Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation)) for key in LAYER_KEYS}
        self.metrics = full.get("metrics") or {}
        self._built = self._build()

    def _build(self):
        """Pre-cut the patches each frame would otherwise re-copy."""
        width, height = self.size
        eyes = []
        for side in SIDES:
            box = QRect(*_pixels(self.rig[f"{side}_eye"], width, height))
            eyes.append({
                "side": side,
                "box": box,
                "eye": self.layers["base"].copy(box),
                "iris": self.layers["iris"].copy(box),
                "lash": self.layers["lash"].copy(box),
                "hair": self.layers["hair"].copy(box),
                "cover": _skin_patch(self.layers["base"], box),
                "lash_bottom": self.metrics.get(side, {}).get("lash_bottom", 0.30),
                "eye_bottom": self.metrics.get(side, {}).get("eye_bottom", 0.92),
            })
        rect = QRect(*_pixels(self.rig["mouth"], width, height))
        pad_x = int(rect.width() * 0.42)
        top = int(rect.height() * 2.1)
        bottom = int(rect.height() * 2.6)
        mouth_box = QRect(rect.x() - pad_x, rect.y() - top,
                          rect.width() + 2 * pad_x, rect.height() + top + bottom)
        mouth_box = mouth_box.intersected(QRect(0, 0, width, height))
        return {"eyes": eyes, "mouth_box": mouth_box, "mouth_rect": rect,
                "mouth_cover": _skin_patch(self.layers["base"], mouth_box, below=False),
                "lips": self.layers["lips"].copy(mouth_box)}

    # -- rendering -------------------------------------------------------
    def render(self, blink=1.0, mouth=0.0, gaze=(0.0, 0.0)) -> QPixmap:
        """Composite one frame.  Returns the portrait itself when nothing moves."""
        blink = min(1.0, max(0.0, float(blink)))
        mouth = min(1.0, max(0.0, float(mouth)))
        gx = min(1.0, max(-1.0, float(gaze[0])))
        gy = min(1.0, max(-1.0, float(gaze[1])))
        if blink > 0.998 and mouth < 0.012 and abs(gx) < 0.012 and abs(gy) < 0.012:
            return self.portrait

        width, height = self.size
        out = self._canvas
        if out is None or out.width() != width or out.height() != height:
            out = QPixmap(width, height)
            self._canvas = out
        # The canvas goes back to the caller with a device pixel ratio on it, so
        # the widget can blit it at the right logical size -- and we reuse that
        # same pixmap next frame.  A painter built on it would inherit the
        # ratio and scale every layer up by it, which left only the top-left
        # 1/dpr of the portrait on screen: she blinked once, then the whole
        # face stayed zoomed in and cropped.  Composite in raw device pixels
        # and put the ratio back before returning.
        out.setDevicePixelRatio(1.0)
        out.fill(Qt.GlobalColor.transparent)
        painter = QPainter(out)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.drawPixmap(0, 0, self.layers["base"])
        painter.drawPixmap(0, 0, self.layers["iris"])
        painter.drawPixmap(0, 0, self.layers["lips"])
        for eye in self._built["eyes"]:
            self._paint_eye(painter, eye, blink, gx, gy)
        self._paint_mouth(painter, mouth)
        painter.end()
        out.setDevicePixelRatio(self.dpr)
        return out

    def _lid_path(self, eye, openness):
        """The almond opening left between the two lids.

        A plain rectangle would slice the iris along a dead straight line, and
        a flat cut is the one thing that instantly reads as "photo being
        clipped" rather than "eyelid".  The lower boundary therefore bows down
        across the middle and the bow shrinks to nothing as the eye shuts.
        """
        box = eye["box"]
        height = box.height()
        travel = 1.0 - openness
        # Overlap the lash by a third of its thickness: the lash tapers at the
        # corners, so starting the clip exactly at its lowest row left a one
        # pixel sliver of white at each end.
        top = box.y() + height * (LID_TRAVEL * travel + 0.30 * eye["lash_bottom"])
        floor = box.y() + height * (eye["eye_bottom"] - LID_RISE * travel)
        if floor - top < 1.0:
            return None
        bow = (floor - top) * 0.30
        center = box.center().x()
        path = QPainterPath()
        path.moveTo(box.x(), top)
        path.lineTo(box.x(), floor)
        path.quadTo(center, floor + bow * 2.0, box.right(), floor)
        path.lineTo(box.right(), top)
        path.closeSubpath()
        return path

    def _paint_eye(self, painter, eye, openness, gx, gy):
        box = eye["box"]
        if openness > 0.998 and abs(gx) < 0.012 and abs(gy) < 0.012:
            return
        travel = 1.0 - openness
        moved = box.height() * LID_TRAVEL * travel
        rise = box.height() * LID_RISE * travel
        # Skin where the lid has actually travelled, plus a little slack above
        # and below so the edge of the painted patch never lands on the lid
        # line itself.  Travel-scaled: at full openness this is empty and an
        # open eye stays pixel-identical to the artwork.
        bands = []
        if moved > 0.2:
            slack = min(box.height() * 0.5, moved * 1.5)
            bands.append(QRectF(box.x(), box.y() - slack, box.width(), moved + slack))
        if rise > 0.2:
            floor = box.y() + box.height() * eye["eye_bottom"]
            bands.append(QRectF(box.x(), floor - rise, box.width(),
                                rise + box.height() * 0.35))
        for band in bands:
            painter.save()
            painter.setClipRect(band)
            painter.drawPixmap(box.topLeft(), eye["cover"])
            # Her fringe is in front of the lid, so put it back on top of the
            # skin.  Without this a blink shaves the hair off the eye box.
            painter.drawPixmap(box.topLeft(), eye["hair"])
            painter.restore()
        opening = self._lid_path(eye, openness)
        if opening is not None:
            painter.save()
            painter.setClipPath(opening)
            source = QRectF(0, 0, eye["eye"].width(), eye["eye"].height())
            painter.drawPixmap(QRectF(box), eye["eye"], source)
            if abs(gx) > 0.012 or abs(gy) > 0.012:
                offset = QPointF(gx * box.width() * GAZE_X, gy * box.height() * GAZE_Y)
                painter.drawPixmap(QRectF(box).translated(offset), eye["iris"], source)
            painter.restore()
        # The artwork's own lash band slides down as the lid closes, so a
        # closed eye is the character's lash line, moved -- not a smeared copy
        # of the whole eye, which is what squeezing the patch produced.
        painter.drawPixmap(QPointF(box.x(), box.y() + moved), eye["lash"])

    def _paint_mouth(self, painter, open_amount):
        if open_amount < 0.012:
            return
        rect = self._built["mouth_rect"]
        box = self._built["mouth_box"]
        grow = rect.height() * MOUTH_OPEN * open_amount
        cover = QRectF(box.x(), rect.y() - rect.height() * 0.6,
                       box.width(), grow + rect.height() * 1.9)
        painter.save()
        painter.setClipRect(cover)
        painter.drawPixmap(box.topLeft(), self._built["mouth_cover"])
        painter.restore()
        centre = rect.center()
        lip_y = rect.y() + rect.height() * 0.42
        width = rect.width() * (1.0 + MOUTH_WIDEN * open_amount)
        height = max(1.0, grow)
        shape = QPainterPath()
        shape.moveTo(centre.x() - width / 2, lip_y)
        shape.quadTo(centre.x(), lip_y + height * 1.5, centre.x() + width / 2, lip_y)
        shape.quadTo(centre.x(), lip_y + height * 0.45, centre.x() - width / 2, lip_y)
        shape.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(MOUTH_DEEP)
        painter.drawPath(shape)
        if open_amount > 0.34:
            inner = shape.boundingRect().adjusted(width * 0.16, height * 0.30,
                                                  -width * 0.16, -height * 0.08)
            painter.setBrush(MOUTH_INNER)
            painter.drawRoundedRect(inner, inner.height() / 2, inner.height() / 2)
        if open_amount > 0.58:
            tongue = QRectF(centre.x() - width * 0.22, lip_y + height * 0.60,
                            width * 0.44, max(1.0, height * 0.36))
            painter.setBrush(MOUTH_TONGUE)
            painter.drawRoundedRect(tongue, tongue.height() / 2, tongue.height() / 2)
        # The original stroke goes back on top: it is the lip line, and leaving
        # it in place is what keeps the mouth looking like *this* character.
        painter.drawPixmap(box.topLeft(), self._built["lips"])


_FACES: dict = {}


def face_for(portrait: QPixmap, source: QPixmap, rig: dict) -> Face:
    """A cached :class:`Face` for one scaled portrait."""
    key = (portrait.cacheKey(), source.cacheKey())
    cached = _FACES.get(key)
    if cached is None:
        cached = Face(portrait, rig, layers=feature_layers(source, rig))
        if len(_FACES) > 12:
            _FACES.clear()
        _FACES[key] = cached
    return cached


# --- timing -------------------------------------------------------------
class FaceClock:
    """Decides when to blink, how much to talk, and where to look.

    Kept apart from the painting so the behaviour is testable without a window.
    """

    def __init__(self, rng=None, alive=True):
        self.rng = rng or random.Random()
        self.alive = alive
        self.t = 0.0
        self.blinks = 0
        self._blink_start = None
        self._blink_length = BLINK_SECONDS
        self._blink_at = self.rng.uniform(1.2, 3.0)
        self._double = False
        self._gaze = [0.0, 0.0]
        self._gaze_target = [0.0, 0.0]
        self._gaze_at = 0.0
        self._mouth = 0.0
        self._talk_phase = 0.0

    def blink(self, double=False):
        """Trigger a blink now; used when the user clicks the pet."""
        if self._blink_start is not None:
            return False
        self.blinks += 1
        self._blink_start = self.t
        self._blink_length = BLINK_SECONDS * (1.25 if double else 1.0)
        self._double = double
        return True

    def openness(self) -> float:
        if self._blink_start is None:
            return 1.0
        u = (self.t - self._blink_start) / self._blink_length
        if u >= 1.0:
            return 1.0
        if u < BLINK_CLOSE:
            shade = u / BLINK_CLOSE
        else:
            shade = 1.0 - (u - BLINK_CLOSE) / (1.0 - BLINK_CLOSE)
        # The exponent sharpens the bottom of the curve: a linear triangle
        # spends too little time fully shut, so at 30fps the eye never looks
        # closed at all, it just dips.
        return 1.0 - max(0.0, min(1.0, shade)) ** 1.6

    def update(self, dt, talking=False, look=None):
        """Advance by ``dt`` seconds and return ``(openness, mouth, (gx, gy))``."""
        dt = max(0.0, min(0.25, float(dt)))
        self.t += dt

        if self._blink_start is not None and self.t - self._blink_start >= self._blink_length:
            self._blink_start = None
            if self._double:
                # A double blink is two blinks in a row, not one long one.
                self._double = False
                self._blink_at = self.t + self.rng.uniform(0.14, 0.24)
            else:
                self._blink_at = self.t + self.rng.uniform(2.2, 6.6)
                if self.rng.random() < 0.18:
                    self._double = True
        if self._blink_start is None and self.t >= self._blink_at:
            self.blink()

        # Talk.  Syllables are quicker than a blink and never fully close.
        if talking:
            self._talk_phase += dt * 7.6
            wave = abs(math.sin(self._talk_phase))
            envelope = 0.55 + 0.45 * abs(math.sin(self._talk_phase * 0.21))
            target = (0.20 + 0.80 * wave ** 1.5) * envelope
        else:
            target = 0.0
        rate = 18.0 if target > self._mouth else 9.0
        self._mouth += (target - self._mouth) * min(1.0, dt * rate)

        # Gaze: follow ``look`` when the cursor is interesting, otherwise drift
        # to a new small target every couple of seconds.
        if look is not None:
            self._gaze_target = [float(look[0]), float(look[1])]
            self._gaze_at = self.t + 1.0
        elif self.t >= self._gaze_at:
            self._gaze_target = [self.rng.uniform(-0.7, 0.7), self.rng.uniform(-0.45, 0.45)]
            self._gaze_at = self.t + self.rng.uniform(1.6, 4.2)
        blend = min(1.0, dt * (5.5 if look is not None else 2.4))
        for index in (0, 1):
            self._gaze[index] += (self._gaze_target[index] - self._gaze[index]) * blend

        if not self.alive:
            return 1.0, 0.0, (0.0, 0.0)
        return self.openness(), self._mouth, (self._gaze[0], self._gaze[1])


__all__ = ["Face", "FaceClock", "face_for", "feature_layers", "load_rig",
           "rig_matches", "split_features", "FALLBACK_RIG", "RECT_KEYS"]
