"""OCR and reading-order helpers for ScholarPet.

The application deliberately keeps OCR separate from the translation and UI
layers.  :func:`extract_blocks` returns small, serialisable dictionaries that
can be drawn over a screenshot, while :func:`group_paragraphs` turns those
boxes into text suitable for a translation request.

RapidOCR is imported lazily.  This keeps application start-up fast and lets a
window open even when the optional OCR package is unavailable (the caller gets
a useful ``RuntimeError`` when OCR is first requested).
"""

from __future__ import annotations

import math
import os
import re
import threading
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from statistics import median
from typing import Any

import numpy as np

__all__ = [
    "extract_blocks",
    "group_paragraphs",
    "order_blocks",
    "reset_engine",
]


# RapidOCR uses ONNX Runtime and OpenMP.  The screenshot OCR path should not
# occupy every CPU core while the user is reading a paper.  These are defaults
# (an administrator or caller can still set them before importing this module).
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("ORT_INTRA_OP_NUM_THREADS", "2")
os.environ.setdefault("ORT_INTER_OP_NUM_THREADS", "1")

_ENGINE: Any | None = None
_ENGINE_IMPORT_ERROR: Exception | None = None
_ENGINE_LOCK = threading.Lock()
_INFERENCE_LOCK = threading.Lock()

_MIN_CONFIDENCE = 0.25
_CJK_RE = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff]")
_ASCII_LETTER_RE = re.compile(r"[A-Za-z]")
_ALNUM_RE = re.compile(r"[A-Za-z0-9]")
_SPACE_RE = re.compile(r"\s+")


def _get_engine() -> Any:
    """Return the process-wide RapidOCR engine, constructing it once.

    RapidOCR's model is several hundred megabytes once loaded.  Keeping one
    engine avoids repeated model startup and the lock makes first use safe when
    screenshots are requested from worker threads.
    """

    global _ENGINE, _ENGINE_IMPORT_ERROR
    if _ENGINE is not None:
        return _ENGINE
    if _ENGINE_IMPORT_ERROR is not None:
        raise RuntimeError(
            "RapidOCR is unavailable; install rapidocr-onnxruntime to enable OCR"
        ) from _ENGINE_IMPORT_ERROR
    with _ENGINE_LOCK:
        if _ENGINE is not None:
            return _ENGINE
        try:
            # Importing only here is intentional: importing ScholarPet itself
            # should not force the ONNX model to initialise.
            from rapidocr_onnxruntime import RapidOCR  # type: ignore

            _ENGINE = RapidOCR()
        except Exception as exc:  # pragma: no cover - depends on local install
            _ENGINE_IMPORT_ERROR = exc
            raise RuntimeError(
                "RapidOCR is unavailable; install rapidocr-onnxruntime to enable OCR"
            ) from exc
    return _ENGINE


def reset_engine() -> None:
    """Drop the lazy engine (primarily useful after a settings change/tests)."""

    global _ENGINE, _ENGINE_IMPORT_ERROR
    with _ENGINE_LOCK:
        _ENGINE = None
        _ENGINE_IMPORT_ERROR = None


def _normalise_text(value: Any) -> str:
    if value is None:
        return ""
    # NFKC fixes full-width Latin characters commonly found in browser OCR.
    text = unicodedata.normalize("NFKC", str(value))
    return _SPACE_RE.sub(" ", text).strip()


def _useful_text(text: str) -> bool:
    """Reject CJK-only strings, confidence-like noise, and symbol blobs.

    OCR occasionally returns a row of mathematical glyphs or Chinese text
    despite the English-language target.  A Latin letter is a strong signal
    for a translatable label.  Short labels (``OK``, ``PDF``, ``Go``) are kept;
    single-character lower-case algebra variables are the one deliberate
    exception.
    """

    if not text or not _ALNUM_RE.search(text):
        return False
    letters = _ASCII_LETTER_RE.findall(text)
    if not letters:
        # Digits alone are page numbers/equation coefficients, not translation
        # text.  Mixed strings such as "5G" contain a letter and are retained.
        return False
    if _CJK_RE.search(text) and not letters:
        return False
    if len(text) <= 2 and text.islower() and text in {"x", "y", "z", "t", "i", "j", "n", "m"}:
        return False
    # A very short Latin token is often a useful UI button.  Longer strings
    # with many operators are usually equation fragments.
    alnum_count = len(_ALNUM_RE.findall(text))
    symbol_count = len(text) - alnum_count - text.count(" ")
    if alnum_count <= 1 and symbol_count > 2:
        return False
    return True


def _points_to_rect(points: Any, image_width: int, image_height: int) -> list[int] | None:
    """Convert a RapidOCR quadrilateral (or xywh fallback) into xywh pixels."""

    try:
        arr = np.asarray(points, dtype=float)
    except (TypeError, ValueError):
        return None
    if arr.size < 4 or not np.isfinite(arr).all():
        return None
    flat = arr.reshape(-1)
    if flat.size == 4 and arr.ndim <= 1:
        x, y, w, h = flat.tolist()
        x2, y2 = x + w, y + h
    elif flat.size >= 8:
        xs, ys = flat[0::2], flat[1::2]
        x, x2, y, y2 = float(xs.min()), float(xs.max()), float(ys.min()), float(ys.max())
    else:
        # Some wrappers expose four points as a flat list but with an extra
        # singleton dimension; treating the extrema is the safest option.
        xs, ys = flat[0::2], flat[1::2]
        if len(xs) < 2:
            return None
        x, x2, y, y2 = float(xs.min()), float(xs.max()), float(ys.min()), float(ys.max())
    x = max(0.0, min(float(image_width), x))
    y = max(0.0, min(float(image_height), y))
    x2 = max(0.0, min(float(image_width), x2))
    y2 = max(0.0, min(float(image_height), y2))
    if x2 <= x or y2 <= y:
        return None
    return [int(round(x)), int(round(y)), max(1, int(round(x2 - x))), max(1, int(round(y2 - y)))]


def _iter_result_items(raw: Any) -> Iterable[tuple[Any, Any, Any]]:
    """Yield ``(box, text, score)`` across RapidOCR package versions."""

    if raw is None:
        return
    # The onnxruntime package traditionally returns ``(items, elapsed)``.
    if isinstance(raw, tuple) and len(raw) >= 1:
        first = raw[0]
        if isinstance(first, (list, tuple)) or hasattr(first, "boxes"):
            raw = first
    if isinstance(raw, Mapping):
        boxes = raw.get("boxes", raw.get("box", []))
        texts = raw.get("texts", raw.get("txts", raw.get("text", [])))
        scores = raw.get("scores", raw.get("score", []))
        for box, text, score in zip(boxes or [], texts or [], scores or []):
            yield box, text, score
        return
    # Newer RapidOCR result objects expose parallel arrays.
    if hasattr(raw, "boxes") and (hasattr(raw, "txts") or hasattr(raw, "texts")):
        boxes = getattr(raw, "boxes")
        texts = getattr(raw, "txts", getattr(raw, "texts", []))
        scores = getattr(raw, "scores", [])
        for box, text, score in zip(boxes or [], texts or [], scores or []):
            yield box, text, score
        return
    if not isinstance(raw, (list, tuple)):
        return
    for item in raw:
        if isinstance(item, Mapping):
            yield item.get("box", item.get("boxes")), item.get("text", item.get("txt")), item.get(
                "score", item.get("confidence", 0.0)
            )
        elif isinstance(item, (list, tuple)) and len(item) >= 3:
            yield item[0], item[1], item[2]


def _coerce_image(image: np.ndarray) -> np.ndarray:
    if not isinstance(image, np.ndarray):
        raise TypeError("image must be a numpy.ndarray")
    if image.ndim == 2:
        image = np.repeat(image[:, :, None], 3, axis=2)
    if image.ndim != 3 or image.shape[2] not in (3, 4):
        raise ValueError("image must have shape (height, width, 3) or (height, width, 4)")
    if image.dtype != np.uint8:
        image = np.clip(image, 0, 255).astype(np.uint8)
    # RapidOCR expects RGB; ignore alpha if a screenshot includes it.
    return np.ascontiguousarray(image[:, :, :3])


def extract_blocks(image: np.ndarray) -> list[dict[str, Any]]:
    """OCR an RGB screenshot and return boxes in reading order.

    Each result has exactly the fields ``text``, ``rect`` (``[x, y, w, h]``),
    and ``confidence``.  Empty or unsupported OCR output returns ``[]``.
    """

    image = _coerce_image(image)
    engine = _get_engine()
    # ONNX sessions are usually safe for concurrent reads, but serialising this
    # small CPU operation avoids races in older RapidOCR/onnxruntime releases.
    with _INFERENCE_LOCK:
        raw = engine(image)
    blocks: list[dict[str, Any]] = []
    height, width = image.shape[:2]
    for points, value, score in _iter_result_items(raw):
        try:
            confidence = float(score)
        except (TypeError, ValueError):
            confidence = 0.0
        if not math.isfinite(confidence) or confidence < _MIN_CONFIDENCE:
            continue
        text = _normalise_text(value)
        if not _useful_text(text):
            continue
        rect = _points_to_rect(points, width, height)
        if rect is None:
            continue
        blocks.append({"text": text, "rect": rect, "confidence": confidence})
    return order_blocks(blocks)


def _column_groups(blocks: Sequence[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Split clear vertical reading columns without merging IEEE columns."""

    if not blocks:
        return []
    work = list(blocks)
    centers = sorted((b["rect"][0] + b["rect"][2] / 2, i) for i, b in enumerate(work))
    xs = [p[0] for p in centers]
    if len(xs) < 4:
        return [work]
    gaps = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
    gap_i = max(range(len(gaps)), key=gaps.__getitem__)
    span = max(xs) - min(xs)
    # A column break is a conspicuous horizontal gap.  Require at least two
    # blocks on each side so a single indented heading does not form a column.
    threshold = max(80.0, span * 0.22)
    if gaps[gap_i] <= threshold or gap_i + 1 < 2 or len(xs) - gap_i - 1 < 2:
        return [work]
    left_indices = {idx for _, idx in centers[: gap_i + 1]}
    left = [b for i, b in enumerate(work) if i in left_indices]
    right = [b for i, b in enumerate(work) if i not in left_indices]
    # A second split is useful for three-column abstracts, while the same
    # minimum-size/gap safeguards prevent normal text indentation from doing it.
    result: list[list[dict[str, Any]]] = []
    for group in (left, right):
        if len(group) >= 6:
            nested = _column_groups(group)
            result.extend(nested)
        else:
            result.append(group)
    return result


def _same_line(a: dict[str, Any], b: dict[str, Any], median_height: float) -> bool:
    ax, ay, aw, ah = a["rect"]
    bx, by, bw, bh = b["rect"]
    ac, bc = ay + ah / 2, by + bh / 2
    return abs(ac - bc) <= max(3.0, 0.62 * max(median_height, ah, bh))


def _join_text(parts: Sequence[str]) -> str:
    result = ""
    for part in parts:
        part = _normalise_text(part)
        if not part:
            continue
        if not result:
            result = part
        elif result.endswith("-") and part[:1].islower():
            # Preserve ordinary hyphens (e.g. "state-of-the-art") while
            # joining a line-break hyphen before a lower-case continuation.
            result = result[:-1] + part
        elif part[0] in ",.;:!?)]}%":
            result += part
        else:
            result += " " + part
    return result


def order_blocks(blocks: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return OCR boxes in left-column/top-to-bottom reading order."""

    if not blocks:
        return []
    clean = [b for b in blocks if isinstance(b, Mapping) and b.get("rect")]
    if not clean:
        return []
    output: list[dict[str, Any]] = []
    for column in _column_groups(clean):
        heights = [max(1, int(b["rect"][3])) for b in column]
        mh = float(median(heights))
        pending: list[dict[str, Any]] = []
        lines: list[list[dict[str, Any]]] = []
        for block in sorted(column, key=lambda b: (b["rect"][1], b["rect"][0])):
            if pending and _same_line(pending[-1], block, mh):
                pending.append(block)
            else:
                if pending:
                    lines.append(sorted(pending, key=lambda b: b["rect"][0]))
                pending = [block]
        if pending:
            lines.append(sorted(pending, key=lambda b: b["rect"][0]))
        for line in lines:
            output.extend(line)
    return output


def group_paragraphs(blocks: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group OCR boxes into column-safe paragraphs for translation.

    Returned records contain ``text``, ``rect``, ``confidence``, ``blocks`` and
    ``column``.  ``blocks`` retains the original source boxes, allowing the UI
    to draw a translated overlay at source locations.
    """

    ordered = order_blocks(blocks)
    if not ordered:
        return []
    paragraphs: list[dict[str, Any]] = []
    offset = 0
    for column_index, column in enumerate(_column_groups(ordered)):
        # Build visual lines within one column.
        heights = [max(1, int(b["rect"][3])) for b in column]
        mh = float(median(heights))
        lines: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        for block in sorted(column, key=lambda b: (b["rect"][1], b["rect"][0])):
            if current and _same_line(current[-1], block, mh):
                current.append(block)
            else:
                if current:
                    lines.append(sorted(current, key=lambda b: b["rect"][0]))
                current = [block]
        if current:
            lines.append(sorted(current, key=lambda b: b["rect"][0]))
        line_records: list[dict[str, Any]] = []
        for line in lines:
            text = _join_text([b["text"] for b in line])
            x = min(b["rect"][0] for b in line)
            y = min(b["rect"][1] for b in line)
            x2 = max(b["rect"][0] + b["rect"][2] for b in line)
            y2 = max(b["rect"][1] + b["rect"][3] for b in line)
            line_records.append({"text": text, "blocks": line, "rect": [x, y, x2 - x, y2 - y]})
        current_para: list[dict[str, Any]] = []
        for line in line_records:
            if current_para:
                prev = current_para[-1]
                gap = line["rect"][1] - (prev["rect"][1] + prev["rect"][3])
                indent = abs(line["rect"][0] - current_para[0]["rect"][0])
                if gap > max(8.0, 1.25 * mh) or indent > max(30.0, 2.5 * mh):
                    paragraphs.append(_paragraph_record(current_para, column_index))
                    current_para = []
            current_para.append(line)
        if current_para:
            paragraphs.append(_paragraph_record(current_para, column_index))
        offset += len(column)
    return paragraphs


def _paragraph_record(lines: Sequence[dict[str, Any]], column: int) -> dict[str, Any]:
    source_blocks = [b for line in lines for b in line["blocks"]]
    text = _join_text([line["text"] for line in lines])
    x = min(line["rect"][0] for line in lines)
    y = min(line["rect"][1] for line in lines)
    x2 = max(line["rect"][0] + line["rect"][2] for line in lines)
    y2 = max(line["rect"][1] + line["rect"][3] for line in lines)
    total_chars = sum(max(1, len(str(b.get("text", "")))) for b in source_blocks)
    confidence = sum(float(b.get("confidence", 0.0)) * max(1, len(str(b.get("text", "")))) for b in source_blocks) / total_chars
    return {
        "text": text,
        "rect": [x, y, x2 - x, y2 - y],
        "confidence": float(confidence),
        "blocks": source_blocks,
        "column": column,
    }
