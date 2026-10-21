from pathlib import Path

import fitz

from ..models.document import AtomicElement, SourceSpan
from ..structure.normalizer import normalize_text


def parse_pdf(path: str | Path) -> list[AtomicElement]:
    elements: list[AtomicElement] = []
    doc = fitz.open(str(path))
    order = 0
    for page_index, page in enumerate(doc, start=1):
        for paragraph in _logical_paragraphs(page, page_index):
            element_id = f"e{order}"
            text, spans = _paragraph_text_and_spans(paragraph, element_id)
            if not text:
                continue
            elements.append(
                AtomicElement(
                    element_id=element_id,
                    element_type=_element_type(text),
                    text=text,
                    normalized_text=normalize_text(text),
                    order_index=order,
                    page_no=page_index,
                    spans=spans,
                    metadata={"parser": "pymupdf_rawdict", "line_count": len(paragraph)},
                )
            )
            order += 1
    return elements


def _logical_paragraphs(page: fitz.Page, page_no: int) -> list[list[dict]]:
    lines = _extract_lines(page, page_no)
    paragraphs: list[list[dict]] = []
    current: list[dict] = []
    for line in lines:
        if not current:
            current.append(line)
            continue
        if _should_join(current[-1], line):
            current.append(line)
        else:
            paragraphs.append(current)
            current = [line]
    if current:
        paragraphs.append(current)
    return paragraphs


def _extract_lines(page: fitz.Page, page_no: int) -> list[dict]:
    raw = page.get_text("rawdict")
    lines: list[dict] = []
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = "".join(
                char.get("c", "")
                for span in line.get("spans", [])
                for char in span.get("chars", [])
            )
            text = normalize_text(text)
            if not text:
                continue
            bbox = tuple(float(value) for value in line.get("bbox", (0, 0, 0, 0)))
            lines.append({"text": text, "bbox": bbox, "page_no": page_no})
    return sorted(lines, key=lambda item: (item["page_no"], item["bbox"][1], item["bbox"][0]))


def _paragraph_text_and_spans(lines: list[dict], element_id: str) -> tuple[str, list[SourceSpan]]:
    text_parts: list[str] = []
    spans: list[SourceSpan] = []
    cursor = 0
    for index, line in enumerate(lines):
        if index:
            text_parts.append("\n")
            cursor += 1
        line_text = line["text"]
        start = cursor
        text_parts.append(line_text)
        cursor += len(line_text)
        spans.append(
            SourceSpan(
                page_no=line["page_no"],
                bbox=line["bbox"],
                original_start=start,
                original_end=cursor,
                element_id=element_id,
            )
        )
    return "".join(text_parts), spans


def _should_join(left: dict, right: dict) -> bool:
    left_text = left["text"].rstrip()
    right_text = right["text"].lstrip()
    if not left_text or not right_text:
        return False
    if _looks_like_heading(left_text) or _looks_like_heading(right_text):
        return False
    left_bbox = left["bbox"]
    right_bbox = right["bbox"]
    line_height = max(left_bbox[3] - left_bbox[1], 1.0)
    vertical_gap = right_bbox[1] - left_bbox[3]
    indent_delta = abs(right_bbox[0] - left_bbox[0])
    if vertical_gap > line_height * 1.45:
        return False
    if indent_delta > 36 and left_text.endswith(("。", "；", ";", "：", ":")):
        return False
    if left_text.endswith(("。", "；", ";", "！", "？", ":", "：")) and indent_delta > 12:
        return False
    return True


def _element_type(text: str) -> str:
    return "HEADING" if _looks_like_heading(text) else "PARAGRAPH"


def _looks_like_heading(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) > 40:
        return False
    prefixes = ("第", "一、", "二、", "三、", "四、", "五、", "六、", "七、", "八、", "九、")
    return stripped.startswith(prefixes) and not stripped.endswith(("。", "；", ";"))

