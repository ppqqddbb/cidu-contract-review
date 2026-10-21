from ..models.blocks import CoarseBlock
from ..models.config import ComparisonProfile
from ..models.document import AtomicElement
from ..structure.block_utils import content_hash
from ..structure.normalizer import compact_text


def build_coarse_blocks(
    elements: list[AtomicElement],
    profile: ComparisonProfile | None = None,
) -> list[CoarseBlock]:
    profile = profile or ComparisonProfile()
    blocks: list[CoarseBlock] = []
    current: list[AtomicElement] = []
    heading_path: list[str] = []

    def flush() -> None:
        nonlocal current
        if not current:
            return
        normalized = compact_text("\n".join(element.text for element in current))
        first_heading = next((element.text for element in current if element.element_type == "HEADING"), None)
        block_type = "table" if len(current) == 1 and current[0].element_type == "TABLE" else "coarse_section"
        blocks.append(
            CoarseBlock(
                coarse_id=f"c{len(blocks)}",
                block_type=block_type,
                heading_path=heading_path.copy(),
                heading_text=first_heading,
                order_start=current[0].order_index,
                order_end=current[-1].order_index,
                text="\n".join(element.text for element in current),
                normalized_text=normalized,
                child_element_ids=[element.element_id for element in current],
                spans=[span for element in current for span in element.spans],
                content_hash=content_hash(normalized),
                features={"element_types": [element.element_type for element in current]},
            )
        )
        current = []

    for element in elements:
        if element.element_type == "HEADING":
            is_high_level = (element.heading_level or 1) <= 2
            if is_high_level:
                flush()
                heading_path = heading_path[: max((element.heading_level or 1) - 1, 0)]
                heading_path.append(element.text)
        if element.element_type == "TABLE":
            flush()
            current.append(element)
            flush()
            continue

        current.append(element)
        current_size = len(compact_text("\n".join(item.text for item in current)))
        if current_size >= profile.coarse_max_chars:
            flush()
        elif current_size >= profile.coarse_target_chars and element.element_type in {"PARAGRAPH", "LIST_ITEM"}:
            flush()

    flush()
    return blocks

