"""The selection bubble is the primary reading flow, so its placement matters."""

from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from scholarpet.config import DEFAULTS
from scholarpet.selection_monitor import SelectionMonitor
from scholarpet.views import SelectionPopup

NARROW = 320  # keeps the bubble inside the small virtual screen used by tests


def _area():
    return QApplication.primaryScreen().availableGeometry()


def _popup(side, width=NARROW):
    popup = SelectionPopup()
    popup.configure(side, width, 15)
    return popup


def test_defaults_enable_selection_translation():
    assert DEFAULTS["selection_enabled"] is True
    assert DEFAULTS["popup_side"] == "auto"
    assert DEFAULTS["pet_avatar"] is True


def test_popup_sits_beside_the_cursor_without_covering_it(qapp):
    area = _area()
    anchor = QPoint(area.left() + 4, area.center().y())
    popup = _popup("right")
    popup.show_translation("Beamforming", "波束成形", anchor)
    assert popup.isVisible()
    assert popup.x() == anchor.x() + popup.GAP
    assert not popup.geometry().contains(anchor)
    popup.dismiss()


def test_popup_can_be_pinned_to_the_left(qapp):
    area = _area()
    anchor = QPoint(area.right() - 4, area.center().y())
    popup = _popup("left")
    popup.show_translation("Beamforming", "波束成形", anchor)
    assert popup.x() + popup.width() == anchor.x() - popup.GAP
    popup.dismiss()


def test_auto_mode_flips_side_at_the_screen_edge(qapp):
    area = _area()
    near_right = QPoint(area.right() - 4, area.center().y())
    popup = _popup("auto")
    popup.show_translation("Beamforming", "波束成形", near_right)
    # Not enough room on the right, so the bubble flips to the left.
    assert popup.x() + popup.width() <= near_right.x()
    popup.dismiss()


def test_popup_never_leaves_the_screen(qapp):
    area = _area()
    popup = _popup("auto", 430)
    for anchor in (QPoint(area.left(), area.top()), QPoint(area.right(), area.bottom()),
                   QPoint(area.left() - 400, area.center().y())):
        popup.show_translation("Beamforming", "波束成形", anchor)
        assert area.contains(popup.geometry()), (anchor, popup.geometry())
    popup.dismiss()


def test_hint_mode_hides_the_copy_button(qapp):
    anchor = _area().center()
    popup = SelectionPopup()
    popup.show_translation("Beamforming", "波束成形", anchor)
    assert popup.copy_btn.isVisibleTo(popup)
    popup.show_hint("这块区域没有文字层。", anchor)
    assert not popup.copy_btn.isVisibleTo(popup)
    popup.dismiss()


def test_long_selection_offers_the_two_column_view(qapp):
    anchor = _area().center()
    popup = SelectionPopup()
    popup.show_translation("x" * 700, "字" * 700, anchor)
    assert popup.reader_btn.isVisibleTo(popup)
    popup.show_translation("short", "短", anchor)
    assert not popup.reader_btn.isVisibleTo(popup)
    popup.dismiss()


def test_copy_button_emits_the_current_translation(qapp):
    popup = SelectionPopup()
    received = []
    popup.copy_requested.connect(received.append)
    popup.show_translation("Beamforming", "波束成形", _area().center())
    popup.copy_btn.click()
    assert received == ["波束成形"]
    popup.dismiss()


def test_monitor_reports_availability_and_can_be_paused(qapp):
    monitor = SelectionMonitor()
    assert monitor.available() in (True, False)
    monitor.set_enabled(False)
    assert not monitor.enabled
    monitor.start()
    assert monitor.available() == monitor._timer.isActive()
    monitor.stop()
    assert not monitor._timer.isActive()


def test_avatar_asset_loads_with_transparency(qapp):
    from scholarpet.pet import _haibara_pixmap, paint_pet
    pix = _haibara_pixmap()
    assert not pix.isNull(), "assets/haibara_head.png is missing"
    assert pix.hasAlphaChannel(), "the avatar must stay transparent"


def _render(size, colour, label=None, use_avatar=True, hover=False, dpr=1.0):
    """Render the pet exactly like the widget does, at its real height."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPainter, QPixmap
    from scholarpet.pet import Pet, paint_pet

    pix = QPixmap(size, Pet.preferred_height(size))
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    try:
        paint_pet(painter, size, colour, 0, False, use_avatar, dpr, hover, label)
    finally:
        painter.end()
    return pix.toImage()


def test_skin_colour_shows_on_the_badge(qapp):
    """The skin colour must stay visible now that the art has no ring."""
    badge = "框选翻译 ⌗"
    assert _render(120, "#6475ed", badge) != _render(120, "#d99a4c", badge)


def test_hover_rim_is_tinted_by_the_skin_colour(qapp):
    hovering = _render(120, "#6475ed", hover=True)
    assert hovering != _render(120, "#d99a4c", hover=True)
    # ... and the rim only exists while hovering or translating.
    assert _render(120, "#6475ed") == _render(120, "#6475ed")


def test_portrait_is_never_ringed(qapp):
    """Regression: the first avatar build stroked a purple circle round the head.

    Nothing may be painted outside the portrait box and the badge, which is
    exactly what a decorative ring used to violate.
    """
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QColor
    from scholarpet.pet import Pet, art_box, badge_rect

    size = 120
    height = Pet.preferred_height(size)
    image = _render(size, "#6475ed")
    left, top, side = art_box(size)
    portrait = QRectF(left - 1.5, top - 1.5, side + 3, side + 3)
    badge = QRectF(badge_rect(size))
    stray = [QPointF(x + .5, y + .5)
             for y in range(height) for x in range(size)
             if QColor.fromRgba(image.pixel(x, y)).alpha() > 0
             and not portrait.contains(QPointF(x + .5, y + .5))
             and not badge.contains(QPointF(x + .5, y + .5))]
    assert not stray, f"{len(stray)} painted pixel(s) outside the portrait box: {stray[:6]}"


def test_avatar_is_prescaled_once_for_crispness(qapp):
    """The old build rescaled the 1254px asset every frame, which looked blurry."""
    from scholarpet.pet import avatar_pixmap

    first = avatar_pixmap(90, 1.0)
    assert first.width() == 90 and first.devicePixelRatio() == 1.0
    assert avatar_pixmap(90, 1.0) is first, "the scaled portrait must be cached"
    retina = avatar_pixmap(90, 2.0)
    assert retina.width() == 180 and retina.devicePixelRatio() == 2.0


def test_avatar_can_be_switched_off(qapp):
    assert _render(120, "#6475ed", use_avatar=True) != _render(120, "#6475ed", use_avatar=False)


def test_topmost_is_on_by_default_and_can_be_switched_off(qapp):
    from PySide6.QtWidgets import QWidget
    from scholarpet.winutil import TopmostKeeper, raise_above_all

    assert DEFAULTS["topmost"] is True
    keeper = TopmostKeeper()
    widget = QWidget()
    keeper.watch(widget); keeper.watch(widget)
    assert len(keeper._refs) == 1, "watching twice must not duplicate a window"
    keeper.reassert()                       # hidden windows are skipped, never raised
    assert keeper.enabled
    keeper.set_enabled(False)
    assert not keeper.enabled and not keeper._timer.isActive()
    keeper.set_enabled(True)
    assert keeper.enabled and keeper._timer.isActive()
    assert isinstance(raise_above_all(widget), bool)
    keeper.stop()


def test_fullscreen_browsers_do_not_bury_the_bubble(qapp):
    """The bubble asks to be restored to the topmost band every time it shows."""
    from scholarpet import views

    calls = []
    original = views.raise_above_all
    views.raise_above_all = lambda widget: calls.append(widget) or True
    try:
        popup = SelectionPopup()
        popup.show_translation("Beamforming", "波束成形", _area().center())
        assert calls == [popup]
        popup.topmost = False
        calls.clear()
        popup.show_translation("Beamforming", "波束成形", _area().center())
        assert calls == []
        popup.dismiss()
    finally:
        views.raise_above_all = original


def test_a_left_press_anywhere_else_closes_the_bubble(qapp):
    """Select, read, click back into the page -- the bubble must get out of the way."""
    area = _area()
    anchor = QPoint(area.left() + 4, area.center().y())
    popup = _popup("right")
    popup.show_translation("Beamforming", "波束成形", anchor)
    assert popup.isVisible()

    inside = popup.frameGeometry().center()
    assert popup.click_away(inside) is False, "a press inside must not close it"
    assert popup.isVisible()

    outside = QPoint(popup.frameGeometry().right() + 40,
                     popup.frameGeometry().bottom() + 40)
    assert popup.click_away(outside) is True
    assert not popup.isVisible()


def test_a_press_away_from_a_hidden_bubble_is_ignored(qapp):
    popup = _popup("right")
    fired = []
    popup.dismissed.connect(lambda: fired.append(True))
    assert popup.click_away(QPoint(10, 10)) is False
    assert fired == []


def test_the_close_button_clears_the_shared_button_padding(qapp):
    """A 28px button cannot live with the 15px-per-side padding of ``STYLE``.

    With the shared rule in force the × is laid out entirely outside the button's
    own rectangle, so the control reads as an empty box: still clickable, but
    invisible. The padding has to be cleared on this one button -- which is why
    this asserts on the stylesheet rather than on a rendered image, since a
    glyph that never gets drawn still leaves a border behind to measure.
    """
    popup = _popup("right")
    button = popup.close_btn
    assert button.width() == 28 and button.height() == 28
    rule = button.styleSheet().replace(" ", "").lower()
    assert "padding:0" in rule, "the × would be clipped out of its own button"
    assert button.text() == "×"
