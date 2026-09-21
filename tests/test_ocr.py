import numpy as np

from scholarpet.ocr import extract_blocks, group_paragraphs, order_blocks


def block(text, x, y, w=80, h=20, confidence=0.95):
    return {"text": text, "rect": [x, y, w, h], "confidence": confidence}


def test_two_columns_stay_separate_and_read_left_then_right():
    source = [
        block("left first", 20, 20),
        block("right first", 520, 20),
        block("left second", 20, 48),
        block("right second", 520, 48),
    ]
    ordered = order_blocks(source)
    assert [item["text"] for item in ordered] == [
        "left first",
        "left second",
        "right first",
        "right second",
    ]
    paragraphs = group_paragraphs(source)
    assert len(paragraphs) == 2
    assert [p["text"] for p in paragraphs] == [
        "left first left second",
        "right first right second",
    ]
    assert all(p["column"] in (0, 1) for p in paragraphs)


def test_line_break_hyphenation_is_joined_without_a_space():
    source = [
        block("trans-", 20, 20),
        block("lation", 20, 48),
    ]
    paragraphs = group_paragraphs(source)
    assert len(paragraphs) == 1
    assert paragraphs[0]["text"] == "translation"


def test_empty_and_non_english_noise_are_ignored(monkeypatch):
    class FakeEngine:
        def __call__(self, image):
            return [
                ([[1, 1], [41, 1], [41, 20], [1, 20]], "IEEE", 0.99),
                ([[1, 30], [41, 30], [41, 50], [1, 50]], "中文", 0.99),
                ([[1, 60], [41, 60], [41, 80], [1, 80]], "∑÷", 0.99),
            ], 0.01

    import scholarpet.ocr as ocr

    monkeypatch.setattr(ocr, "_ENGINE", FakeEngine())
    monkeypatch.setattr(ocr, "_ENGINE_IMPORT_ERROR", None)
    result = extract_blocks(np.zeros((100, 100, 3), dtype=np.uint8))
    assert [item["text"] for item in result] == ["IEEE"]


def test_blank_ocr_result_is_clean(monkeypatch):
    class EmptyEngine:
        def __call__(self, image):
            return None

    import scholarpet.ocr as ocr

    monkeypatch.setattr(ocr, "_ENGINE", EmptyEngine())
    monkeypatch.setattr(ocr, "_ENGINE_IMPORT_ERROR", None)
    assert extract_blocks(np.zeros((10, 10, 3), dtype=np.uint8)) == []
