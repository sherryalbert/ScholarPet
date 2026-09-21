"""Tests for the portrait rig: calibration, compositing and the behaviour clock.

The rig moves pieces of a single still image around, which is exactly the kind
of code that quietly paints outside the box it is supposed to stay in.  So the
tests here are mostly about *containment*: a blink may only change pixels
inside the eye boxes, a gaze shift may only move the irises, a mouth may only
redraw the mouth.  Anything else and the pet starts wearing a grey rectangle.
"""
import random
import sys
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage, QPixmap

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scholarpet.config import DEFAULTS                       # noqa: E402
from scholarpet.face import (Face, FaceClock, RECT_KEYS,      # noqa: E402
                             face_for, feature_layers, load_rig,
                             rig_matches, split_features)

ASSET = "assets/haibara_head.png"


@pytest.fixture(scope="module")
def source(qapp):
    pixmap = QPixmap(ASSET)
    if pixmap.isNull():
        pytest.skip("avatar asset missing")
    return pixmap


@pytest.fixture(scope="module")
def portrait(source):
    return source.scaled(400, 400, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)


@pytest.fixture(scope="module")
def face(portrait, source):
    return Face(portrait, load_rig(), layers=feature_layers(source, load_rig()))


def array_of(pixmap):
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    stride, height = image.bytesPerLine(), image.height()
    raw = np.frombuffer(image.constBits(), np.uint8, count=stride * height)
    return raw.reshape(height, stride // 4, 4)[:, :image.width()].copy()


def eye_boxes(face, pad=3):
    width, height = face.size
    boxes = []
    for key in ("left_eye", "right_eye"):
        x, y, w, h = face.rig[key]
        boxes.append(QRect(int(x * width) - pad, int(y * height) - pad,
                           int(w * width) + 2 * pad, int(h * height) + 2 * pad))
    return boxes


def mouth_box(face, pad=6):
    width, height = face.size
    x, y, w, h = face.rig["mouth"]
    # The cover patch is deliberately wider than the stroke: it has to hide
    # the brushwork around the lips, not just the line itself.
    pad_x = int(w * width * 0.42) + pad
    return QRect(int(x * width) - pad_x, int(y * height) - int(h * height * 2.5),
                 int(w * width) + 2 * pad_x, int(h * height * 5.5))


def neutral(face):
    """A *composited* neutral frame.

    Comparing against ``render(1, 0, (0, 0))`` would cheat: that path returns
    the untouched artwork and skips the layer stack entirely, so every pixel
    the layers reconstruct slightly differently would look like collateral
    damage.  Nudging the blink just under its shortcut threshold forces the
    real composite, with a sub-pixel lid offset.
    """
    return array_of(face.render(0.995, 0.0, (0.0, 0.0)))


def luma_of(array):
    return (array[..., 0].astype(int) * 299 + array[..., 1].astype(int) * 587
            + array[..., 2].astype(int) * 114) // 1000


def changed_outside(before, after, allowed, threshold=26):
    """Pixels that differ by more than ``threshold``, outside every allowed rect."""
    delta = np.abs(before.astype(int) - after.astype(int)).max(axis=2)
    mask = delta > threshold
    height, width = mask.shape
    outside = mask.copy()
    for rect in allowed:
        x0, y0 = max(0, rect.x()), max(0, rect.y())
        x1, y1 = min(width, rect.right() + 1), min(height, rect.bottom() + 1)
        outside[y0:y1, x0:x1] = False
    return int(outside.sum())


# --- calibration --------------------------------------------------------
def test_rig_covers_every_feature_and_matches_the_artwork(source):
    rig = load_rig()
    for key in RECT_KEYS:
        x, y, w, h = rig[key]
        assert 0.0 <= x < 1.0 and 0.0 <= y < 1.0
        assert 0.0 < w <= 1.0 and 0.0 < h <= 1.0
        assert x + w <= 1.001 and y + h <= 1.001
    assert rig_matches(rig, (source.width(), source.height())), (
        "assets/haibara_head.rig.json is stale -- rerun scripts/calibrate_face.py")


def test_irises_sit_inside_their_eye_boxes():
    rig = load_rig()
    for side in ("left", "right"):
        ex, ey, ew, eh = rig[f"{side}_eye"]
        ix, iy, iw, ih = rig[f"{side}_iris"]
        assert ex <= ix and iy >= ey
        assert ix + iw <= ex + ew and iy + ih <= ey + eh


def test_calibration_rejects_a_backwards_face(tmp_path):
    """A silhouette with no irises is not a face we can rig."""
    from PIL import Image
    from scripts.calibrate_face import measure

    plain = Image.new("RGBA", (400, 400), (250, 214, 190, 255))
    path = tmp_path / "no-face.png"
    plain.save(path)
    with pytest.raises(SystemExit):
        measure(path)


def test_split_features_cuts_a_lash_and_an_iris_for_each_eye(source, portrait):
    layers = split_features(source, load_rig())
    assert layers["lash"].size() == source.size()
    for key in ("base", "iris", "lips", "lash", "hair"):
        assert not layers[key].isNull(), f"{key} layer missing"
    alpha = array_of(layers["lash"])[..., 3]
    assert int((alpha > 40).sum()) > 400, "no lash stroke was extracted"
    iris = array_of(layers["iris"])[..., 3]
    assert int((iris > 40).sum()) > 500, "no iris was extracted"
    assert set(layers["metrics"]) == {"left", "right"}
    for side, metric in layers["metrics"].items():
        assert 0.05 < metric["lash_bottom"] < 0.5, side
        assert 0.6 < metric["eye_bottom"] <= 0.95, side


# --- compositing --------------------------------------------------------
def test_neutral_pose_is_the_artwork_itself(face, portrait):
    assert face.render(1.0, 0.0, (0.0, 0.0)) is portrait


def test_composite_drift_stays_small(face):
    """The 'nothing moves' path must not visibly alter the artwork."""
    reference = array_of(face.portrait)
    composed = array_of(face.render(0.995, 0.0, (0.0, 0.0)))
    delta = np.abs(reference.astype(int) - composed.astype(int))
    assert delta.mean() < 2.5
    assert (delta.max(axis=2) > 48).mean() < 0.02


def test_blink_only_touches_the_eye_boxes(face):
    open_frame = neutral(face)
    for openness in (0.75, 0.5, 0.25, 0.0):
        closed = array_of(face.render(openness, 0.0, (0.0, 0.0)))
        assert changed_outside(open_frame, closed, eye_boxes(face)) == 0, openness


def test_blink_actually_covers_the_eye(face):
    """A shut eye must lose its white: the lash stroke is allowed to stay."""
    white = []
    for openness in (0.995, 0.0):
        frame = array_of(face.render(openness, 0.0, (0.0, 0.0)))[..., :3].astype(int)
        luma = luma_of(frame)
        chroma = frame.max(axis=2) - frame.min(axis=2)
        total = 0
        for rect in eye_boxes(face, pad=0):
            window = (slice(rect.y(), rect.bottom() + 1), slice(rect.x(), rect.right() + 1))
            total += int(((luma[window] > 200) & (chroma[window] < 24)).sum())
        white.append(total)
    assert white[0] > 300, f"the open eye has no sclera to begin with: {white}"
    assert white[1] < white[0] * 0.2, f"a shut eye still shows its white: {white}"


def test_gaze_moves_pixels_only_inside_the_eye_boxes(face):
    centre = neutral(face)
    for gaze in ((-1.0, 0.0), (1.0, 0.0), (0.0, -1.0), (0.0, 1.0)):
        moved = array_of(face.render(0.995, 0.0, gaze))
        assert changed_outside(centre, moved, eye_boxes(face)) == 0, gaze
        inside = sum(
            int((np.abs(centre.astype(int) - moved.astype(int)).max(axis=2) > 26)[
                r.y():r.bottom() + 1, r.x():r.right() + 1].sum()) for r in eye_boxes(face))
        assert inside > 20, f"gaze {gaze} did not move the iris"


def test_mouth_only_touches_the_mouth(face):
    rest = array_of(face.render(1.0, 0.02, (0.0, 0.0)))
    for amount in (0.4, 0.8, 1.0):
        talking = array_of(face.render(1.0, amount, (0.0, 0.0)))
        assert changed_outside(rest, talking, [mouth_box(face)]) == 0, amount


def test_mouth_opens_upwards_not_sideways(face):
    rest = luma_of(array_of(face.render(1.0, 0.02, (0.0, 0.0))))
    wide = luma_of(array_of(face.render(1.0, 1.0, (0.0, 0.0))))
    rect = mouth_box(face, pad=0)
    window = (slice(rect.y(), rect.bottom() + 1), slice(rect.x(), rect.right() + 1))
    assert int((wide[window] < 200).sum()) > int((rest[window] < 200).sum()), (
        "opening the mouth added no darkness")


def test_face_for_is_cached(portrait, source):
    rig = load_rig()
    assert face_for(portrait, source, rig) is face_for(portrait, source, rig)


def test_render_keeps_the_device_pixel_ratio(source):
    scaled = source.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
    scaled.setDevicePixelRatio(2.0)
    face = Face(scaled, load_rig(), layers=feature_layers(source, load_rig()))
    frame = face.render(0.5)
    assert frame.devicePixelRatio() == pytest.approx(2.0)


def test_rig_falls_back_when_the_sidecar_is_missing(tmp_path):
    rig = load_rig(asset_dir=tmp_path)
    assert rig["source"] == "haibara_head.png"
    assert rig["left_eye"] and len(rig["left_eye"]) == 4


# --- behaviour ----------------------------------------------------------
def test_clock_blinks_on_its_own_and_returns_to_open():
    clock = FaceClock(rng=random.Random(7))
    seen, closed, elapsed = set(), 0, 0.0
    dt = 1 / 120
    while elapsed < 30.0:
        openness, _, _ = clock.update(dt)
        seen.add(round(openness, 3))
        if openness < 0.25:
            closed += 1
        elapsed += dt
    assert clock.blinks >= 4, "the pet barely blinks"
    assert 1.0 in seen, "the eye never returns fully open between blinks"
    assert closed >= 2, "no blink was ever seen shutting"
    assert min(seen) < 0.05, "a blink never gets dark enough to read as shut"


def test_clock_stays_open_when_not_alive():
    clock = FaceClock(alive=False)
    for _ in range(600):
        openness, mouth, gaze = clock.update(1 / 60, talking=True, look=(1.0, 1.0))
    assert (openness, mouth, gaze) == (1.0, 0.0, (0.0, 0.0))


def test_clock_talks_while_busy_and_shuts_up_afterwards():
    clock = FaceClock(rng=random.Random(3))
    peak = 0.0
    for _ in range(120):
        peak = max(peak, clock.update(1 / 60, talking=True)[1])
    assert 0.2 < peak <= 1.0
    for _ in range(240):
        mute = clock.update(1 / 60, talking=False)[1]
    assert mute < 0.02


def test_clock_gaze_follows_the_cursor_and_drifts_when_ignored():
    clock = FaceClock(rng=random.Random(11))
    for _ in range(120):
        _, _, gaze = clock.update(1 / 60, look=(-1.0, 0.5))
    assert gaze[0] < -0.8 and gaze[1] > 0.4
    for _ in range(1200):
        _, _, gaze = clock.update(1 / 60)
    assert abs(gaze[0]) <= 0.75 and abs(gaze[1]) <= 0.5


def test_openness_curve_is_fast_then_slow():
    clock = FaceClock(rng=random.Random(5))
    clock.t = 0.0
    clock._blink_at = 0.0
    clock.update(0.0)
    assert clock.blinks == 1
    steps = 200
    samples = []
    for step in range(1, steps + 1):
        clock.t = step / steps * clock._blink_length
        samples.append(clock.openness())
    peak = samples.index(min(samples))
    assert samples[peak] < 0.01, "the lid never actually shuts"
    assert steps * 0.2 < peak < steps * 0.5, "the lid closes late in the blink"
    assert samples[-1] > 0.9, "the eye does not reopen"


def test_a_30fps_blink_contains_a_shut_frame():
    """Sampled at the frame rate the widget actually uses, not ideally."""
    clock = FaceClock(rng=random.Random(2))
    clock._blink_at = 0.0
    frames = []
    for _ in range(12):
        frames.append(clock.update(1 / 30)[0])
    assert frames[0] == 1.0
    assert min(frames) < 0.1, f"no shut frame at 30fps: {[round(f, 2) for f in frames]}"


def test_pet_widget_animates_without_painting_outside_itself(qapp):
    from scholarpet.pet import Pet
    pet = Pet(dict(DEFAULTS, pet_size=120))
    assert pet.clock.alive
    frames = []
    for state in ((1.0, 0.0, (0.0, 0.0)), (0.0, 0.0, (0.0, 0.0)),
                  (1.0, 1.0, (0.9, 0.0))):
        pet.expression = state
        pet.phase = 0.5
        frames.append(pet.grab())
    assert all(not frame.isNull() for frame in frames)
    assert len({bytes(frame.toImage().constBits()) for frame in frames}) == len(frames)
    pet.close()


def test_pet_click_triggers_a_blink(qapp):
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    from scholarpet.pet import Pet
    pet = Pet(dict(DEFAULTS, pet_size=120)); pet.show()
    before = pet.clock.blinks
    QTest.mouseClick(pet, Qt.MouseButton.LeftButton, pos=QPoint(40, 40))
    assert pet.clock.blinks == before + 1
    pet.close()


def test_rig_sidecar_is_calibrated_for_the_bundled_artwork(source):
    """The shipped sidecar must describe *this* PNG, not a stale calibration."""
    rig = load_rig()
    assert rig_matches(rig, (source.width(), source.height())), (
        "assets/haibara_head.rig.json is missing or was calibrated for another artwork")


def test_selftest_reports_the_face_rig(qapp):
    from scholarpet.selftest import _check_face_rig
    report = _check_face_rig()
    assert "rig" in report and "blink" in report


def test_build_spec_ships_the_face_sidecar():
    """A frozen build without the sidecar still runs, just with worse aim.

    Nothing fails loudly when the line is dropped from the spec, so it gets a
    test of its own instead of relying on someone noticing a subtle drift.
    """
    spec = (ROOT / "ScholarPet.spec").read_text("utf-8")
    assert "assets/haibara_head.rig.json" in spec, (
        "ScholarPet.spec no longer bundles the face rig sidecar")


def test_reused_canvas_does_not_inherit_the_previous_frames_ratio(source):
    """Frames must not drift once the canvas has been handed to the widget.

    ``render`` gives the canvas back with a device pixel ratio on it so the
    widget can blit it at the right logical size -- and then reuses that same
    pixmap next frame.  A painter built on it inherits the ratio, so every
    layer was composited scaled up by dpr and only the top-left 1/dpr of the
    portrait survived.  On a 125% display she blinked once and then stayed
    zoomed in, cropped below the eyes, for the rest of the session.
    """
    rig = load_rig()
    retina = source.scaled(400, 400, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
    retina.setDevicePixelRatio(2.0)
    assert retina.devicePixelRatio() == 2.0, "this test needs a non-unity ratio"
    face = Face(retina, rig, layers=feature_layers(source, rig))

    frames = [array_of(face.render(1.0, 0.0, (0.35, 0.25))) for _ in range(4)]
    for index, frame in enumerate(frames[1:], start=2):
        drift = np.abs(frame.astype(int) - frames[0].astype(int))
        assert drift.max() <= 2, (
            f"frame {index} drifted from frame 1 by up to {drift.max()}/255 -- "
            "the canvas is carrying state between frames")


def test_a_gaze_frame_still_shows_the_whole_portrait(source):
    """Cheap guard against exactly the failure above: a crop shows up at once."""
    rig = load_rig()
    retina = source.scaled(360, 360, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
    retina.setDevicePixelRatio(2.0)
    face = Face(retina, rig, layers=feature_layers(source, rig))

    for _ in range(3):                      # burn the frames that used to go wrong
        frame = face.render(1.0, 0.0, (0.35, 0.25))
    painted = array_of(frame).astype(int)

    side = retina.width()
    reference = source.scaled(side, side, Qt.AspectRatioMode.IgnoreAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
    want = array_of(reference).astype(int)
    alpha = painted[..., 3:4] / 255.0
    flat = painted[..., :3] * alpha + 255.0 * (1 - alpha)
    drift = np.abs(flat - want[..., :3] * (want[..., 3:4] / 255.0)
                   - 255.0 * (1 - want[..., 3:4] / 255.0)).max(axis=2)
    assert drift.mean() < 12, (
        f"a gaze frame no longer resembles the artwork (mean drift {drift.mean():.1f}/255 "
        "-- the portrait is being drawn cropped or scaled)")
