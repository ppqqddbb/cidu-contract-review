from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from ..models.document import AtomicElement, SourceSpan
from ..normalize.list_parser import parse_list_marker
from ..structure.normalizer import normalize_text


def _paragraph_type(style_name: str, text: str) -> tuple[str, int | None]:
    lowered = (style_name or "").lower()
    if lowered.startswith("heading") or lowered.startswith("标题"):
        digits = "".join(ch for ch in style_name if ch.isdigit())
        return "HEADING", int(digits) if digits else 1
    if text.lstrip().startswith(("-", "*")) or parse_list_marker(text).marker:
        return "LIST_ITEM", None
    return "PARAGRAPH", None


def _iter_block_items(doc: Document):
    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, doc)
        elif child.tag.endswith("}tbl"):
            yield Table(child, doc)


def parse_docx(path: str | Path) -> list[AtomicElement]:
    doc = Document(str(path))
    elements: list[AtomicElement] = []
    order = 0
    table_index = 0
    for item in _iter_block_items(doc):
        if isinstance(item, Paragraph):
            text = normalize_text(item.text)
            if not text:
                continue
            element_type, heading_level = _paragraph_type(item.style.name, text)
            element_id = f"e{order}"
            elements.append(
                AtomicElement(
                    element_id=element_id,
                    element_type=element_type,
                    text=text,
                    normalized_text=normalize_text(text),
                    order_index=order,
                    heading_level=heading_level,
                    spans=[SourceSpan(element_id=element_id, original_start=0, original_end=len(text))],
                )
            )
            order += 1
        elif isinstance(item, Table):
            for row_index, row in enumerate(item.rows):
                cells = [normalize_text(cell.text) for cell in row.cells]
                if not any(cells):
                    continue
                text = " | ".join(cells)
                element_id = f"e{order}"
                elements.append(
                    AtomicElement(
                        element_id=element_id,
                        element_type="TABLE",
                        text=text,
                        normalized_text=normalize_text(text),
                        order_index=order,
                        metadata={"table_index": table_index, "row_index": row_index},
                        spans=[SourceSpan(element_id=element_id, original_start=0, original_end=len(text))],
                    )
                )
                order += 1
            table_index += 1
    return elements

