import re

from ..models.blocks import CoarseBlock, FineBlock
from ..models.config import ComparisonProfile
from ..models.document import AtomicElement
from ..structure.block_utils import content_hash
from ..structure.normalizer import compact_text, normalize_text


def build_fine_blocks(
    coarse_block: CoarseBlock,
    elements_by_id: dict[str, AtomicElement],
    profile: ComparisonProfile | None = None,
) -> list[FineBlock]:
    profile = profile or ComparisonProfile()
    blocks: list[FineBlock] = []
    current: list[AtomicElement] = []

    def flush() -> None:
        nonlocal current
        if not current:
            return
        text = "\n".join(element.text for element in current)
        blocks.append(_make_block(coarse_block.coarse_id, len(blocks), current, text))
        current = []

    for element_id in coarse_block.child_element_ids:
        element = elements_by_id[element_id]
        if element.element_type == "TABLE":
            flush()
            for row_no, row_text in enumerate(_table_rows(element.text)):
                pseudo = element.model_copy(update={"text": row_text, "normalized_text": normalize_text(row_text)})
                blocks.append(_make_block(coarse_block.coarse_id, len(blocks), [pseudo], row_text, fine_type="table_row", row_no=row_no))
            continue
        if _is_key_value(element.text):
            flush()
            blocks.append(_make_block(coarse_block.coarse_id, len(blocks), [element], element.text, fine_type="key_value"))
            continue
        current.append(element)
        current_size = len(compact_text("\n".join(item.text for item in current)))
        if current_size >= profile.fine_target_chars or element.element_type in {"HEADING", "LIST_ITEM"}:
            flush()
    flush()
    return blocks


def _make_block(
    parent_id: str,
    order_index: int,
    elements: list[AtomicElement],
    text: str,
    fine_type: str | None = None,
    row_no: int | None = None,
) -> FineBlock:
    normalized = compact_text(text)
    key_text = _key_text(text)
    block_type = fine_type or ("key_value" if key_text else "fine_text")
    return FineBlock(
        fine_id=f"{parent_id}.f{order_index}",
        parent_coarse_id=parent_id,
        fine_type=block_type,
        numbering=_numbering(text),
        key_text=key_text,
        order_index=order_index,
        text=text,
        normalized_text=normalized,
        element_ids=[element.element_id for element in elements],
        spans=[span for element in elements for span in element.spans],
        content_hash=content_hash(normalized),
        features={"row_no": row_no, "element_types": [element.element_type for element in elements]},
    )


def _table_rows(text: str) -> list[str]:
    return [line for line in (normalize_text(row) for row in text.splitlines()) if line]


def _is_key_value(text: str) -> bool:
    return _key_text(text) is not None


def _key_text(text: str) -> str | None:
    match = re.match(r"^\s*([^：:]{1,30})[：:]", text or "")
    return normalize_text(match.group(1)) if match else None


def _numbering(text: str) -> str | None:
    match = re.match(r"^\s*((第?\d+[条章节])|(\d+(\.\d+)*[、.)]?）?)|([一二三四五六七八九十]+[、.]))", text or "")
    return match.group(0).strip() if match else None

