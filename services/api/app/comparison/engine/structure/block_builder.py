import hashlib

from ..models.config import ComparisonProfile
from ..models.document import AtomicElement, LogicalBlock
from ..structure.normalizer import compact_text, normalize_text


def _hash(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=8).hexdigest()


def build_blocks(elements: list[AtomicElement], profile: ComparisonProfile | None = None) -> list[LogicalBlock]:
    profile = profile or ComparisonProfile()
    blocks: list[LogicalBlock] = []
    current: list[AtomicElement] = []
    heading_path: list[str] = []

    def flush() -> None:
        nonlocal current
        if not current:
            return
        text = "\n".join(item.text for item in current)
        normalized = normalize_text(text)
        pages = [span.page_no for item in current for span in item.spans if span.page_no]
        block_type = "table" if len(current) == 1 and current[0].element_type == "TABLE" else "section_text"
        blocks.append(
            LogicalBlock(
                block_id=f"b{len(blocks)}",
                block_type=block_type,
                heading_path=heading_path.copy(),
                order_index=len(blocks),
                text=text,
                normalized_text=compact_text(normalized),
                element_ids=[item.element_id for item in current],
                spans=[span for item in current for span in item.spans],
                page_start=min(pages) if pages else None,
                page_end=max(pages) if pages else None,
                content_hash=_hash(compact_text(normalized)),
                features={"element_types": [item.element_type for item in current]},
            )
        )
        current = []

    for element in elements:
        if element.element_type == "HEADING":
            flush()
            heading_path = heading_path[: max((element.heading_level or 1) - 1, 0)]
            heading_path.append(element.text)
            current.append(element)
            continue
        if element.element_type == "TABLE":
            flush()
            current.append(element)
            flush()
            continue
        current.append(element)
        if not heading_path and element.element_type in {"PARAGRAPH", "LIST_ITEM"} and len(element.normalized_text) <= 80:
            flush()
            continue
        size = len("".join(item.normalized_text for item in current))
        if size >= profile.block_target_max_chars or size >= profile.block_hard_max_chars:
            flush()
    flush()
    return blocks

