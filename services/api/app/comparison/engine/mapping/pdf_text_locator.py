from pathlib import Path
import re

import fitz

from ..models.document import SourceSpan


def locate_texts(
    pdf_path: str | Path,
    texts: list[str],
    max_hits_per_text: int = 3,
    page_numbers: set[int] | None = None,
) -> list[dict]:
    grouped: dict[int, list[tuple[float, float, float, float]]] = {}
    if not texts:
        return []
    doc = fitz.open(str(pdf_path))
    pages = list(page_numbers) if page_numbers else list(range(1, len(doc) + 1))
    for text in texts:
        for snippet in _snippets(text):
            hits = 0
            for page_index in pages:
                if page_index < 1 or page_index > len(doc):
                    continue
                page = doc[page_index - 1]
                for rect in page.search_for(snippet):
                    grouped.setdefault(page_index, []).append((rect.x0, rect.y0, rect.x1, rect.y1))
                    hits += 1
                    if hits >= max_hits_per_text:
                        break
                if hits >= max_hits_per_text:
                    break
            if hits:
                break
    return [{"page_no": page_no, "rects": _merge_rects(rects)} for page_no, rects in grouped.items()]


def locate_texts_in_spans(
    container_text: str | None,
    spans: list[SourceSpan],
    texts: list[str],
) -> list[dict]:
    if not container_text or not spans or not texts:
        return []
    bbox_spans = [span for span in spans if span.bbox and span.page_no]
    if not bbox_spans:
        return []
    grouped: dict[int, list[tuple[float, float, float, float]]] = {}
    for text in texts:
        for start, end in _text_ranges(container_text, text):
            for span in bbox_spans:
                if span.original_end <= start or span.original_start >= end:
                    continue
                grouped.setdefault(int(span.page_no), []).append(span.bbox)
    return [{"page_no": page_no, "rects": _merge_rects(rects)} for page_no, rects in sorted(grouped.items())]


def _text_ranges(container_text: str, needle: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    if not needle:
        return ranges
    start = 0
    while True:
        index = container_text.find(needle, start)
        if index < 0:
            break
        ranges.append((index, index + len(needle)))
        start = index + max(1, len(needle))
    if ranges:
        return ranges
    compact_container, container_map = _compact_with_map(container_text)
    compact_needle, _ = _compact_with_map(needle)
    if not compact_needle:
        return []
    start = 0
    while True:
        index = compact_container.find(compact_needle, start)
        if index < 0:
            break
        source_start = container_map[index]
        source_end = container_map[index + len(compact_needle) - 1] + 1
        ranges.append((source_start, source_end))
        start = index + max(1, len(compact_needle))
    return ranges


def _compact_with_map(text: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    offsets: list[int] = []
    for index, char in enumerate(text or ""):
        if char.isspace():
            continue
        chars.append(char)
        offsets.append(index)
    return "".join(chars), offsets


def _snippets(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if not normalized:
        return []
    if len(normalized) <= 40:
        return [normalized]
    parts = [item.strip() for item in re.split(r"[\n。；;，,、：:（）()【】\[\]]+", text) if item.strip()]
    candidates = []
    for part in parts:
        compact = re.sub(r"\s+", " ", part).strip()
        if 6 <= len(compact) <= 40:
            candidates.append(compact)
        elif len(compact) > 40:
            candidates.extend(_window(compact, 24))
    candidates.extend(_window(normalized, 24))
    seen = set()
    ordered = []
    for item in sorted(candidates, key=len, reverse=True):
        if len(item) < 6:
            continue
        if item not in seen:
            ordered.append(item)
            seen.add(item)
    return ordered[:3]


def _window(text: str, size: int) -> list[str]:
    compact = text.strip()
    if len(compact) <= size:
        return [compact]
    return [compact[index : index + size] for index in range(0, min(len(compact), size * 4), size)]


def _merge_rects(rects: list[tuple[float, float, float, float]]) -> list[tuple[float, float, float, float]]:
    # Keep rectangles small and local; merge only near-identical duplicates from repeated searches.
    unique = []
    keys = set()
    for rect in rects:
        key = tuple(round(value, 1) for value in rect)
        if key not in keys:
            unique.append(rect)
            keys.add(key)
    return unique

