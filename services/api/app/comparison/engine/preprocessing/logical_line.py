from ..models.document import AtomicElement
from ..structure.normalizer import normalize_text


def rebuild_logical_lines(elements: list[AtomicElement]) -> list[AtomicElement]:
    rebuilt: list[AtomicElement] = []
    buffer: list[AtomicElement] = []

    def flush() -> None:
        nonlocal buffer
        if not buffer:
            return
        if len(buffer) == 1:
            rebuilt.append(buffer[0])
        else:
            text = "".join(item.text for item in buffer)
            first = buffer[0]
            rebuilt.append(
                first.model_copy(
                    update={
                        "text": text,
                        "normalized_text": normalize_text(text),
                        "spans": [span for item in buffer for span in item.spans],
                        "metadata": {**first.metadata, "merged_from": [item.element_id for item in buffer]},
                    }
                )
            )
        buffer = []

    for element in elements:
        if element.element_type not in {"PARAGRAPH", "LIST_ITEM"}:
            flush()
            rebuilt.append(element)
            continue
        if buffer and _should_merge(buffer[-1].text, element.text):
            buffer.append(element)
        else:
            flush()
            buffer.append(element)
    flush()
    for index, element in enumerate(rebuilt):
        rebuilt[index] = element.model_copy(update={"order_index": index})
    return rebuilt


def _should_merge(left: str, right: str) -> bool:
    return left.endswith(("（", "(")) or right.startswith(("）", ")"))

