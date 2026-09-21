import os
import importlib.util
from pathlib import Path
import pytest
from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtTest import QTest
import scholarpet
from scholarpet.config import DEFAULTS, load_settings, save_settings
from scholarpet.pet import Pet
from scholarpet.views import Selection, Reader, Overlay
from scholarpet.settings import SettingsDialog


def test_settings_key_never_written_plaintext(tmp_path, monkeypatch):
    if os.name != 'nt': pytest.skip('Windows DPAPI')
    monkeypatch.setenv('SCHOLARPET_DATA_DIR', str(tmp_path))
    settings = dict(DEFAULTS, api_key='test-only-key-not-a-real-credential')
    save_settings(settings)
    text = (tmp_path/'settings.json').read_text('utf-8')
    assert settings['api_key'] not in text
    assert load_settings()['api_key'] == settings['api_key']


def test_pet_single_and_double_click_are_distinct(qapp):
    pet = Pet(DEFAULTS.copy()); pet.show()
    events = []
    pet.full.connect(lambda: events.append('full'))
    pet.settings_requested.connect(lambda: events.append('settings'))
    QTest.mouseClick(pet, Qt.MouseButton.LeftButton, pos=QPoint(50,50))
    QTest.qWait(qapp.doubleClickInterval()+100)
    assert events == ['full']
    events.clear()
    QTest.mouseClick(pet, Qt.MouseButton.LeftButton, pos=QPoint(50,50))
    QTest.mouseDClick(pet, Qt.MouseButton.LeftButton, pos=QPoint(50,50))
    QTest.qWait(qapp.doubleClickInterval()+100)
    assert events == ['settings']
    pet.close()


def test_region_reverse_drag_and_cancel(qapp):
    pix = QPixmap(800,600); pix.fill(QColor('white'))
    picker = Selection(pix, QRect(0,0,800,600)); picker.show()
    regions=[]; picker.chosen.connect(regions.append)
    QTest.mousePress(picker, Qt.MouseButton.LeftButton, pos=QPoint(500,400))
    QTest.mouseMove(picker, QPoint(100,100))
    QTest.mouseRelease(picker, Qt.MouseButton.LeftButton, pos=QPoint(100,100))
    assert len(regions)==1 and regions[0].left()==100 and regions[0].width()==400
    picker2 = Selection(pix, QRect(0,0,800,600)); picker2.show(); events=[]
    picker2.cancelled.connect(lambda:events.append(True)); picker2.cancel()
    assert events==[True]


def test_dpi_overlay_and_html_escaping(qapp):
    pix = QPixmap(1600,1200); pix.setDevicePixelRatio(2); pix.fill(QColor('white'))
    blocks=[dict(text='<script> & beamforming',rect=[200,200,500,80],confidence=.7)]
    reader = Reader(); reader.set_result(blocks,['<术语> & 波束成形'],'test',.1)
    assert '<script>' in reader.browser.toPlainText()
    overlay = Overlay(pix,QRect(0,0,800,600),blocks,['波束成形'])
    assert not overlay.grab().isNull()
    overlay.set_original(True)
    assert overlay.original
    reader.close(); overlay.close()


def test_settings_save_updates_skin_and_glossary(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv('SCHOLARPET_DATA_DIR',str(tmp_path))
    dialog = SettingsDialog(DEFAULTS.copy()); saved=[]; dialog.saved.connect(saved.append)
    dialog.pick_color('#35a99a'); dialog.size_spin.setValue(120)
    dialog.glossary.setPlainText('beamforming = 波束成形')
    dialog.save()
    assert saved[0]['color']=='#35a99a'
    assert load_settings()['glossary']['beamforming']=='波束成形'


def test_the_package_registers_no_global_hotkeys():
    """Ctrl+Alt+T / S / V were dropped: nothing may claim the keyboard."""
    root = Path(scholarpet.__file__).parent
    sources = {path.name: path.read_text('utf-8') for path in root.glob('*.py')}
    offenders = sorted(name for name, text in sources.items()
                       if 'RegisterHotKey' in text or 'Ctrl+Alt' in text)
    assert offenders == [], f"global hotkeys crept back into {offenders}"
    assert importlib.util.find_spec('scholarpet.hotkeys') is None, \
        "the hotkey module is still importable"


def test_the_pet_tooltip_advertises_only_mouse_actions(qapp):
    """Every action has to be discoverable without a keyboard."""
    pet = Pet(DEFAULTS.copy())
    tip = pet.toolTip()
    assert 'Ctrl' not in tip and 'Alt' not in tip, f"tooltip still sells hotkeys: {tip!r}"
    for phrase in ('划选', '单击头像', '框选翻译', '双击'):
        assert phrase in tip, f"the tooltip never mentions {phrase}"
    pet.close()
