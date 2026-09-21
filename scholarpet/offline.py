"""Small direct adapter for the bundled Argos English→Chinese model.

The model is the official ``translate-en_zh-1_9.argosmodel`` package from
Argos Open Technologies.  Using CTranslate2 directly keeps ScholarPet's
runtime small and avoids importing the full Argos GUI/package manager.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
from pathlib import Path
from typing import Any, Sequence

from .translation import TranslationCancelled, TranslationError, _cancelled, _check_cancel

# SentencePiece marks word starts with U+2581; the general-domain model also
# occasionally answers odd input with subtitle styling tags. Both must never
# reach the reading window.
_WORD_MARKER = "\u2581"
_ASS_TAG = re.compile(r"\{[^{}]*\\[^{}]*\}")
_SPACED_CJK = re.compile(r"(?<=[\u4e00-\u9fff]) +(?=[\u4e00-\u9fff])")


def sanitize(text: str) -> str:
    """Strip decoder artefacts from a translated segment."""
    if not text:
        return text
    text = text.replace(_WORD_MARKER, "")
    text = _ASS_TAG.sub("", text)
    text = _SPACED_CJK.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


_MODEL_LOCK = threading.Lock()
_TRANSLATOR = None
_SP = None
_MODEL_PATH: Path | None = None


def _candidates(settings: dict[str, Any]) -> list[Path]:
    configured = str(settings.get("offline_model_dir", "")).strip()
    result = [Path(configured)] if configured else []
    roots = [Path(__file__).resolve().parents[1]]
    if getattr(sys, "_MEIPASS", None):
        roots.insert(0, Path(sys._MEIPASS))
    roots.append(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ScholarPet")
    for root in roots:
        result.append(root / "models" / "translate-en_zh-1_9")
        result.append(root / "translate-en_zh-1_9")
    # De-duplicate while retaining the portable build's path first.
    seen = set(); unique = []
    for path in result:
        key = str(path.resolve())
        if key not in seen:
            seen.add(key); unique.append(path)
    return unique


def model_path(settings: dict[str, Any] | None = None) -> Path:
    settings = settings or {}
    for candidate in _candidates(settings):
        if (candidate / "model" / "model.bin").is_file() and (candidate / "sentencepiece.model").is_file():
            return candidate
    raise TranslationError("未找到本地英中模型，请确认 models/translate-en_zh-1_9 文件夹完整")


def _load(settings: dict[str, Any]):
    global _TRANSLATOR, _SP, _MODEL_PATH
    path = model_path(settings)
    if _TRANSLATOR is not None and _SP is not None and _MODEL_PATH == path:
        return _TRANSLATOR, _SP
    with _MODEL_LOCK:
        if _TRANSLATOR is not None and _SP is not None and _MODEL_PATH == path:
            return _TRANSLATOR, _SP
        try:
            import ctranslate2
            import sentencepiece as spm
            translator = ctranslate2.Translator(str(path / "model"), device="cpu",
                                                 inter_threads=1, intra_threads=2)
            processor = spm.SentencePieceProcessor(model_file=str(path / "sentencepiece.model"))
        except Exception as exc:
            raise TranslationError("本地英中模型初始化失败，请重新安装或检查模型文件") from exc
        _TRANSLATOR, _SP, _MODEL_PATH = translator, processor, path
    return _TRANSLATOR, _SP


def _split(text: str, limit: int = 220) -> list[str]:
    """Keep individual translation requests below the model's safe token size."""
    if len(text) <= limit:
        return [text]
    pieces, current = [], ""
    for sentence in __import__("re").split(r"(?<=[.!?。！？])\s+", text):
        if current and len(current) + len(sentence) + 1 > limit:
            pieces.append(current); current = ""
        current = f"{current} {sentence}".strip()
    if current: pieces.append(current)
    if not pieces: pieces = [text]
    # A long sentence without punctuation still needs bounded model input.
    result = []
    for piece in pieces:
        while len(piece) > limit:
            cut = piece.rfind(" ", 0, limit)
            if cut < max(40, limit // 2): cut = limit
            result.append(piece[:cut].strip()); piece = piece[cut:].strip()
        if piece: result.append(piece)
    return result


def translate_offline(texts: Sequence[str], settings: dict[str, Any], progress=None, cancel=None):
    _check_cancel(cancel)
    translator, processor = _load(settings)
    result: list[str] = []
    total = len(texts)
    for index, source in enumerate(texts):
        _check_cancel(cancel)
        if not source or not any(ch.isascii() and ch.isalpha() for ch in source):
            result.append(source)
            if progress: progress(index + 1, total)
            continue
        sentences = _split(source)
        tokens = [processor.encode(sentence, out_type=str) for sentence in sentences]
        try:
            batches = translator.translate_batch(tokens, beam_size=4, max_batch_size=8,
                                                 batch_type="tokens", replace_unknowns=True)
            translated = [sanitize(processor.decode(batch.hypotheses[0])) for batch in batches]
        except Exception as exc:
            raise TranslationError("本地离线模型推理失败，请重试") from exc
        result.append("".join(translated))
        if progress: progress(index + 1, total)
    return result


__all__ = ["model_path", "sanitize", "translate_offline"]
