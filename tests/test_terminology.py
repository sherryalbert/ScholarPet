"""Terminology behaviour: the offline model needs corrections, users need to win."""

from __future__ import annotations

import pytest

from scholarpet import offline, translation
from scholarpet.glossary import OFFLINE_MODEL_CORRECTIONS, default_glossary, offline_corrections


def test_glossary_covers_the_common_communications_terms():
    glossary = default_glossary()
    assert glossary["beamforming"] == "波束成形"
    assert glossary["SINR"] == "信干噪比"
    assert glossary["bit error rate"] == "误比特率"
    assert glossary["frequency-hopping spread spectrum"] == "跳频扩频"


def test_sanitize_removes_decoder_artefacts():
    assert offline.sanitize("\u2581我们采用统一的线性天线阵列") == "我们采用统一的线性天线阵列"
    assert offline.sanitize("我们{\\fn黑体\\fs22\\bord1}提出") == "我们提出"
    assert offline.sanitize("波 束 成 形") == "波束成形"
    assert offline.sanitize("") == ""
    assert offline.sanitize("双 面  打印") == "双面打印"


def test_offline_corrections_fix_the_known_mistranslations():
    glossary = offline_corrections()
    cases = {
        "光束造型提高了信号-干扰-加-噪声比.": "波束成形提高了信干噪比.",
        "速度更快、位误率更低.": "速度更快、误比特率更低.",
        "频率跳跃散射频谱降低干扰.": "跳频扩频降低干扰.",
        "算法在十次迭代内趋同.": "算法在十次迭代内收敛.",
    }
    for produced, expected in cases.items():
        assert translation._apply_glossary(produced, glossary) == expected
    assert OFFLINE_MODEL_CORRECTIONS


def test_user_glossary_overrides_the_builtin_correction():
    merged = dict(offline_corrections())
    merged.update({"波束成形": "波束赋形"})
    assert translation._apply_glossary("光束造型", merged) == "波束赋形"


def test_offline_engine_applies_corrections_end_to_end(monkeypatch):
    monkeypatch.setattr(offline, "translate_offline",
                        lambda texts, settings, progress=None, cancel=None: ["光束造型提高了信号-干扰-加-噪声比."])
    result, label = translation.translate_blocks(["Beamforming improves SINR."], {"engine": "offline"})
    assert result == ["波束成形提高了信干噪比."]
    assert "术语校正" in label


def test_real_offline_model_returns_correct_terminology():
    pytest.importorskip("ctranslate2")
    pytest.importorskip("sentencepiece")
    try:
        offline.model_path({})
    except translation.TranslationError:
        pytest.skip("offline model package not installed")
    result, _ = translation.translate_blocks(
        ["Beamforming improves the signal-to-interference-plus-noise ratio."], {"engine": "offline"})
    text = result[0]
    assert "波束成形" in text, text
    assert "信干噪比" in text, text
    assert "\u2581" not in text, text
