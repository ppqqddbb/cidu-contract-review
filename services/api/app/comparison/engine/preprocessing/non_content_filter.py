import re
from collections import defaultdict

from ..models.document import AtomicElement
from ..structure.normalizer import compact_text

PAGE_NUMBER = re.compile(r"^\d{1,4}(?:[/／]\d{1,4})?$")
TOC_DOTTED_LINE = re.compile(r".*[.·]{6,}\s*\d{0,4}$")
TOC_HEADING_TOKEN = re.compile(r"(?:第[一二三四五六七八九十百千万零〇0-9]+[章节条款部分]|[一二三四五六七八九十]+部分)")
TOC_ENTRY = re.compile(
    r"^(?:第[一二三四五六七八九十百千万零〇0-9]+[章节条款部分]|[一二三四五六七八九十]+部分).*\d{1,4}$"
)


def filter_non_content(elements: list[AtomicElement]) -> list[AtomicElement]:
    marked = set()
    in_toc = False
    for element in elements:
        raw_type = str(element.metadata.get("mineru_type", "")).lower()
        text = compact_text(element.text)
        if text.startswith("目录"):
            in_toc = True
            marked.add(element.element_id)
            continue
        if in_toc and _is_toc_entry(text):
            marked.add(element.element_id)
            continue
        if in_toc and text:
            in_toc = False
        if (
            element.element_type == "HEADER_FOOTER"
            or raw_type in {"page_header", "page_footer", "page_number"}
            or _is_page_number(element, text)
            or _is_toc_dotted_line(element.text)
            or _is_toc_block(text)
        ):
            marked.add(element.element_id)

    page_count = len({element.page_no for element in elements if element.page_no})
    if page_count >= 3:
        by_text: dict[str, list[AtomicElement]] = defaultdict(list)
        for element in elements:
            text = compact_text(element.text)
            if len(text) >= 2:
                by_text[text].append(element)
        for matches in by_text.values():
            pages = {element.page_no for element in matches if element.page_no}
            if len(pages) / page_count >= 0.30 and _stable_top_or_bottom(matches):
                marked.update(element.element_id for element in matches)

    return [element for element in elements if element.element_id not in marked]


def _is_page_number(element: AtomicElement, text: str) -> bool:
    if not PAGE_NUMBER.fullmatch(text):
        return False
    if "/" in text or "／" in text:
        return True
    if not _is_top_or_bottom(element):
        return False
    try:
        return 1 <= int(text) <= 500
    except ValueError:
        return False


def _is_toc_dotted_line(text: str) -> bool:
    return bool(TOC_DOTTED_LINE.fullmatch((text or "").strip()))


def _is_toc_block(text: str) -> bool:
    return text.startswith("目录") and len(TOC_HEADING_TOKEN.findall(text)) >= 3


def _is_toc_entry(text: str) -> bool:
    return bool(TOC_ENTRY.fullmatch(text))


def _is_top_or_bottom(element: AtomicElement) -> bool:
    bbox = element.spans[0].bbox if element.spans else None
    if not bbox:
        return False
    return bbox[1] < 120 or bbox[1] > 700


def _stable_top_or_bottom(elements: list[AtomicElement]) -> bool:
    positions = []
    for element in elements:
        bbox = element.spans[0].bbox if element.spans else None
        if bbox:
            positions.append(bbox[1])
    if not positions:
        return False
    avg = sum(positions) / len(positions)
    return avg < 120 or avg > 700

