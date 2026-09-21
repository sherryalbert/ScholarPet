"""Small integration checks for the OCR -> translation worker seam."""

from __future__ import annotations

from scholarpet import translation
from scholarpet.app import Worker


def test_worker_translates_synthetic_ocr_blocks(monkeypatch):
    """The worker preserves OCR metadata and applies the selection offset."""

    source = [{"text": "Beamforming improves SNR.", "rect": [4, 6, 80, 20], "confidence": 0.91}]
    monkeypatch.setattr("scholarpet.ocr.extract_blocks", lambda pixels: list(source))
    monkeypatch.setattr("scholarpet.ocr.group_paragraphs", lambda blocks: blocks)

    calls = {}

    def fake_translate(texts, settings, progress=None, cancel=None):
        calls["texts"] = list(texts)
        if progress:
            progress(1, 1)
        return ["波束成形提高信噪比。"], "synthetic"

    monkeypatch.setattr(translation, "translate_blocks", fake_translate)
    worker = Worker({"engine": "offline"}, pixels=object(), offset=(10, 20))
    results, finished = [], []
    worker.result.connect(lambda *args: results.append(args))
    worker.finished.connect(lambda: finished.append(True))

    worker.run()

    assert calls["texts"] == [source[0]["text"]]
    assert finished == [True]
    assert len(results) == 1
    blocks, translated, label, _elapsed = results[0]
    assert translated == ["波束成形提高信噪比。"]
    assert label == "synthetic"
    assert blocks[0]["rect"][:2] == [14, 26]


def test_worker_cancelled_before_translation_emits_no_result(monkeypatch):
    monkeypatch.setattr("scholarpet.ocr.extract_blocks", lambda pixels: [{"text": "English", "rect": [0, 0, 10, 10]}])
    monkeypatch.setattr("scholarpet.ocr.group_paragraphs", lambda blocks: blocks)
    worker = Worker({"engine": "offline"}, pixels=object())
    worker.cancelled.set()
    results, errors, finished = [], [], []
    worker.result.connect(lambda *args: results.append(args))
    worker.error.connect(errors.append)
    worker.finished.connect(lambda: finished.append(True))

    worker.run()

    assert not results and not errors
    assert finished == [True]
