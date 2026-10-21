from pathlib import Path
from typing import Any

from ..models.document import AtomicElement, DocumentIR, PageIR, SourceSpan
from ..structure.normalizer import normalize_text


class MinerUAdapter:
    def from_payload(self, payload: dict, source_path: str | Path, metadata: dict | None = None) -> DocumentIR:
        elements: list[AtomicElement] = []
        pages = self._pages(payload)
        for block in self._blocks(payload):
            text = normalize_text(self._text(block))
            if not text:
                continue
            page_no = self._page_no(block)
            bbox = self._bbox(block)
            element_type = self._element_type(block)
            element_id = f"mu_{len(elements)}"
            elements.append(
                AtomicElement(
                    element_id=element_id,
                    element_type=element_type,
                    text=text,
                    normalized_text=normalize_text(text),
                    order_index=len(elements),
                    heading_level=self._heading_level(block, element_type),
                    page_no=page_no,
                    spans=[
                        SourceSpan(
                            page_no=page_no,
                            bbox=bbox,
                            original_start=0,
                            original_end=len(text),
                            element_id=element_id,
                            ocr_confidence=self._confidence(block),
                        )
                    ],
                    metadata={"source_locator": self._locator(block), "mineru_type": self._raw_type(block)},
                )
            )
        return DocumentIR(
            document_id=Path(source_path).stem,
            source_file_type=Path(source_path).suffix.lower().lstrip("."),
            pages=pages,
            elements=elements,
            metadata={"parser": "mineru", **(metadata or {})},
        )

    def _blocks(self, payload: dict) -> list[dict]:
        for key in ("pdf_info", "pages"):
            if isinstance(payload.get(key), list):
                flattened: list[dict] = []
                for page in payload[key]:
                    for block_key in ("para_blocks", "blocks", "content", "items"):
                        if isinstance(page.get(block_key), list):
                            for block in page[block_key]:
                                if isinstance(block, dict):
                                    block = {**block, "_page_idx": page.get("page_idx", page.get("page_no"))}
                                    flattened.append(block)
                if flattened:
                    return flattened
        for key in ("blocks", "content", "items", "structured_content"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    def _pages(self, payload: dict) -> list[PageIR]:
        pages: list[PageIR] = []
        source_pages = payload.get("pdf_info") if isinstance(payload.get("pdf_info"), list) else payload.get("pages")
        if isinstance(source_pages, list):
            for index, page in enumerate(source_pages, start=1):
                size = page.get("page_size") or page.get("size") or []
                pages.append(
                    PageIR(
                        page_no=int(page.get("page_idx", page.get("page_no", index - 1))) + 1,
                        width=float(size[0]) if len(size) > 0 else None,
                        height=float(size[1]) if len(size) > 1 else None,
                        metadata={"source_locator": {"page_index": index - 1}},
                    )
                )
        return pages

    def _text(self, block: dict) -> str:
        if isinstance(block.get("text"), str):
            return block["text"]
        if isinstance(block.get("content"), str):
            return block["content"]
        lines = []
        for key in ("lines", "spans"):
            if isinstance(block.get(key), list):
                for item in block[key]:
                    if isinstance(item, dict):
                        lines.append(str(item.get("text") or item.get("content") or ""))
        return "\n".join(line for line in lines if line)

    def _element_type(self, block: dict) -> str:
        raw_type = self._raw_type(block).lower()
        if raw_type in {"title", "heading", "header"}:
            return "HEADING"
        if raw_type in {"table", "table_body"}:
            return "TABLE"
        if raw_type in {"page_header", "page_footer", "page_number", "header_footer"}:
            return "HEADER_FOOTER"
        if raw_type in {"list", "list_item"}:
            return "LIST_ITEM"
        return "PARAGRAPH"

    def _raw_type(self, block: dict) -> str:
        return str(block.get("type") or block.get("block_type") or block.get("category") or "unknown")

    def _heading_level(self, block: dict, element_type: str) -> int | None:
        if element_type != "HEADING":
            return None
        level = block.get("level") or block.get("heading_level")
        try:
            return int(level)
        except Exception:
            return 1

    def _page_no(self, block: dict) -> int | None:
        page = block.get("page_no", block.get("page_idx", block.get("_page_idx")))
        if page is None:
            return None
        try:
            return int(page) + (0 if int(page) >= 1 and block.get("page_no") else 1)
        except Exception:
            return None

    def _bbox(self, block: dict) -> tuple[float, float, float, float] | None:
        bbox = block.get("bbox") or block.get("box")
        if isinstance(bbox, list) and len(bbox) >= 4:
            return (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
        return None

    def _confidence(self, block: dict) -> float | None:
        value = block.get("ocr_confidence") or block.get("confidence") or block.get("score")
        try:
            return float(value)
        except Exception:
            return None

    def _locator(self, block: dict) -> dict[str, Any]:
        return {
            "page_no": self._page_no(block),
            "bbox": self._bbox(block),
            "type": self._raw_type(block),
        }

