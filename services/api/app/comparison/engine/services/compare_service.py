from pathlib import Path

from ..align.group_dp import group_align
from ..diff.char_diff import char_diff
from ..diff.equal_shield import normalized_equal
from ..diff.line_alignment import diff_lines
from ..diff.postprocess import refine_diff_ops
from ..diff.validator import validate_change
from ..matching.block_matcher import align_blocks
from ..models.config import ComparisonProfile
from ..models.diff import ChangeItem, DiffOp
from ..mapping.pdf_text_locator import locate_texts, locate_texts_in_spans
from ..parsers.document_ir_parser import parse_document_ir
from ..rendering.page_renderer import render_document_pages
from ..structure.fine_block_builder import build_fine_blocks
from ..structure.coarse_block_builder import build_coarse_blocks
from ..structure.normalizer import compact_text


def compare_documents(old_path: str | Path, new_path: str | Path, profile: ComparisonProfile | None = None) -> dict:
    profile = profile or ComparisonProfile()
    old_path = Path(old_path)
    new_path = Path(new_path)
    old_document = parse_document_ir(old_path)
    new_document = parse_document_ir(new_path)
    old_elements = old_document.elements
    new_elements = new_document.elements
    old_elements_by_id = {element.element_id: element for element in old_elements}
    new_elements_by_id = {element.element_id: element for element in new_elements}
    old_blocks = _logical_blocks(old_elements, old_elements_by_id, profile)
    new_blocks = _logical_blocks(new_elements, new_elements_by_id, profile)
    old_full_text = compact_text("\n".join(element.text for element in old_elements))
    new_full_text = compact_text("\n".join(element.text for element in new_elements))
    render_root = old_path.parent / "rendered"
    old_render = render_document_pages(old_path, render_root / "old", profile.render_dpi)
    new_render = render_document_pages(new_path, render_root / "new", profile.render_dpi)
    alignments = group_align(old_blocks, new_blocks, profile)
    changes: list[ChangeItem] = []
    change_no = 1
    for alignment in alignments:
        change = _change_from_group_alignment(
            alignment,
            old_blocks,
            new_blocks,
            change_no,
            profile,
            old_render["pdf_path"],
            new_render["pdf_path"],
            old_full_text,
            new_full_text,
        )
        if change:
            changes.append(change)
            change_no += 1
    changes = [change for change in _fuse_adjacent_replacements(changes, old_render["pdf_path"], new_render["pdf_path"]) if validate_change(change)]
    changes = _renumber_changes(changes)
    return {
        "summary": {
            "change_count": len(changes),
            "old_block_count": len(old_blocks),
            "new_block_count": len(new_blocks),
        },
        "metadata": {
            "parser": {
                "old": old_document.metadata,
                "new": new_document.metadata,
            },
            "pipeline": [
                "mineru_or_fallback_parse",
                "document_ir",
                "non_content_filter",
                "logical_line_rebuild",
                "group_sequence_alignment",
                "line_diff",
                "equal_shield",
                "bbox_mapping",
            ],
        },
        "documents": {
            "old": [_block_payload(block) for block in old_blocks],
            "new": [_block_payload(block) for block in new_blocks],
        },
        "pages": {
            "old": [_page_payload(old_path.parent, "old", page) for page in old_render["pages"]],
            "new": [_page_payload(new_path.parent, "new", page) for page in new_render["pages"]],
        },
        "changes": [item.model_dump() for item in changes],
        "block_alignment": [alignment.__dict__ for alignment in alignments],
    }


def _logical_blocks(elements, elements_by_id, profile: ComparisonProfile):
    coarse_blocks = build_coarse_blocks(elements, profile)
    blocks = []
    for coarse in coarse_blocks:
        blocks.extend(build_fine_blocks(coarse, elements_by_id, profile))
    return blocks


def _change_from_group_alignment(
    alignment,
    old_blocks,
    new_blocks,
    change_no: int,
    profile: ComparisonProfile,
    old_pdf_path: str,
    new_pdf_path: str,
    old_full_text: str,
    new_full_text: str,
) -> ChangeItem | None:
    old_group = old_blocks[alignment.old_range[0] : alignment.old_range[1]] if alignment.old_range else []
    new_group = new_blocks[alignment.new_range[0] : alignment.new_range[1]] if alignment.new_range else []
    old_block = _compound_block(old_group) if old_group else None
    new_block = _compound_block(new_group) if new_group else None
    if alignment.type == "MATCH":
        ops = diff_lines(alignment.old_text, alignment.new_text, profile)
        if not any(op.op != "EQUAL" for op in ops):
            return None
        return _change(change_no, old_block, new_block, ops, alignment.score or 1.0, old_pdf_path, new_pdf_path, old_full_text, new_full_text)
    if alignment.type == "DELETE":
        return _change(change_no, old_block, None, [DiffOp(op="DELETE", text=old_block.text)], 1.0, old_pdf_path, new_pdf_path, old_full_text, new_full_text)
    if alignment.type == "INSERT":
        return _change(change_no, None, new_block, [DiffOp(op="INSERT", text=new_block.text)], 1.0, old_pdf_path, new_pdf_path, old_full_text, new_full_text)
    return None


def _compound_block(blocks):
    if len(blocks) == 1:
        return blocks[0]
    first = blocks[0]
    text = "\n".join(block.text for block in blocks)
    normalized = "".join(block.normalized_text for block in blocks)
    return first.model_copy(
        update={
            "fine_id": f"{_id(blocks[0])}..{_id(blocks[-1])}",
            "text": text,
            "normalized_text": normalized,
            "spans": [span for block in blocks for span in block.spans],
            "element_ids": [element_id for block in blocks for element_id in getattr(block, "element_ids", [])],
        }
    )


def _change_from_alignment(
    alignment,
    old_blocks,
    new_blocks,
    change_no: int,
    profile: ComparisonProfile,
    old_pdf_path: str,
    new_pdf_path: str,
    old_full_text: str,
    new_full_text: str,
) -> ChangeItem | None:
    if alignment.op == "MATCH":
        old_block = old_blocks[alignment.old_index]
        new_block = new_blocks[alignment.new_index]
        ops = diff_lines(old_block.text, new_block.text, profile)
        if not any(op.op != "EQUAL" for op in ops):
            return None
        return _change(change_no, old_block, new_block, ops, alignment.score, old_pdf_path, new_pdf_path, old_full_text, new_full_text)
    if alignment.op == "DELETE":
        old_block = old_blocks[alignment.old_index]
        return _change(
            change_no,
            old_block,
            None,
            [DiffOp(op="DELETE", text=old_block.text)],
            1.0,
            old_pdf_path,
            new_pdf_path,
            old_full_text,
            new_full_text,
        )
    if alignment.op == "INSERT":
        new_block = new_blocks[alignment.new_index]
        return _change(
            change_no,
            None,
            new_block,
            [DiffOp(op="INSERT", text=new_block.text)],
            1.0,
            old_pdf_path,
            new_pdf_path,
            old_full_text,
            new_full_text,
        )
    return None


def _exists_elsewhere(text: str | None, other_document: str) -> bool:
    normalized = compact_text(text or "")
    if len(normalized) < 2:
        return False
    return normalized in other_document


def _renumber_changes(changes: list[ChangeItem]) -> list[ChangeItem]:
    for index, change in enumerate(changes, start=1):
        change.change_id = f"c{index}"
    return changes


def _fuse_adjacent_replacements(changes: list[ChangeItem], old_pdf_path: str, new_pdf_path: str) -> list[ChangeItem]:
    fused: list[ChangeItem] = []
    index = 0
    while index < len(changes):
        current = changes[index]
        next_change = changes[index + 1] if index + 1 < len(changes) else None
        if next_change and {current.display_type, next_change.display_type} == {"delete", "insert"}:
            delete_change = current if current.display_type == "delete" else next_change
            insert_change = current if current.display_type == "insert" else next_change
            ops = refine_diff_ops(
                delete_change.old_text,
                insert_change.new_text,
                char_diff(delete_change.old_text or "", insert_change.new_text or ""),
            )
            display_type = _display_type_from_ops(ops)
            if display_type is None:
                index += 2
                continue
            old_pages = _region_pages(delete_change.old_regions)
            new_pages = _region_pages(insert_change.new_regions)
            fused.append(
                ChangeItem(
                    change_id=current.change_id,
                    display_type=display_type,
                    old_text=delete_change.old_text,
                    new_text=insert_change.new_text,
                    old_regions=_locate_changed_text(
                        old_pdf_path,
                        delete_change.old_text,
                        [],
                        [op.text for op in ops if op.op == "DELETE"],
                        old_pages,
                    ),
                    new_regions=_locate_changed_text(
                        new_pdf_path,
                        insert_change.new_text,
                        [],
                        [op.text for op in ops if op.op == "INSERT"],
                        new_pages,
                    ),
                    old_block_ids=delete_change.old_block_ids,
                    new_block_ids=insert_change.new_block_ids,
                    operations=ops,
                    confidence=min(delete_change.confidence, insert_change.confidence),
                )
            )
            index += 2
            continue
        fused.append(current)
        index += 1
    return fused


def _change(
    no: int,
    old_block,
    new_block,
    ops: list[DiffOp],
    confidence: float,
    old_pdf_path: str,
    new_pdf_path: str,
    old_full_text: str,
    new_full_text: str,
) -> ChangeItem | None:
    if old_block and new_block and normalized_equal(old_block.text, new_block.text):
        return None
    ops = refine_diff_ops(old_block.text if old_block else None, new_block.text if new_block else None, ops)
    ops = _filter_unchanged_ops(ops, old_full_text, new_full_text)
    display_type = _display_type_from_ops(ops)
    if display_type is None:
        return None
    old_delete_texts = [op.text for op in ops if op.op == "DELETE"]
    new_insert_texts = [op.text for op in ops if op.op == "INSERT"]
    old_regions = _locate_changed_text(
        old_pdf_path,
        old_block.text if old_block else None,
        getattr(old_block, "spans", []) if old_block else [],
        old_delete_texts,
        _block_pages(old_block),
    )
    new_regions = _locate_changed_text(
        new_pdf_path,
        new_block.text if new_block else None,
        getattr(new_block, "spans", []) if new_block else [],
        new_insert_texts,
        _block_pages(new_block),
    )
    return ChangeItem(
        change_id=f"c{no}",
        display_type=display_type,
        old_text=old_block.text if old_block else None,
        new_text=new_block.text if new_block else None,
        old_regions=old_regions,
        new_regions=new_regions,
        old_block_ids=[_id(old_block)] if old_block else [],
        new_block_ids=[_id(new_block)] if new_block else [],
        operations=ops,
        confidence=confidence,
    )


def _filter_unchanged_ops(ops: list[DiffOp], old_full_text: str, new_full_text: str) -> list[DiffOp]:
    kept: list[DiffOp] = []
    for op in ops:
        if op.op == "DELETE" and (_exists_elsewhere(op.text, new_full_text) or _all_parts_exist_elsewhere(op.text, new_full_text)):
            continue
        if op.op == "INSERT" and (_exists_elsewhere(op.text, old_full_text) or _all_parts_exist_elsewhere(op.text, old_full_text)):
            continue
        kept.append(op)
    return kept


def _all_parts_exist_elsewhere(text: str | None, other_document: str) -> bool:
    parts = [compact_text(part) for part in (text or "").splitlines()]
    meaningful = [part for part in parts if len(part) >= 2]
    if len(meaningful) < 2:
        return False
    return all(part in other_document for part in meaningful)


def _locate_changed_text(
    pdf_path: str,
    container_text: str | None,
    spans: list,
    texts: list[str],
    page_numbers: set[int] | None,
) -> list[dict]:
    regions = locate_texts_in_spans(container_text, spans, texts)
    if regions:
        return regions
    return locate_texts(pdf_path, texts, page_numbers=page_numbers)




def _display_type_from_ops(ops: list[DiffOp]) -> str | None:
    has_delete = any(op.op == "DELETE" for op in ops)
    has_insert = any(op.op == "INSERT" for op in ops)
    if has_delete and has_insert:
        return "replace"
    if has_insert:
        return "insert"
    if has_delete:
        return "delete"
    return None


def _block_payload(block) -> dict:
    return {
        "block_id": _id(block),
        "block_type": getattr(block, "block_type", getattr(block, "fine_type", "block")),
        "heading_path": getattr(block, "heading_path", []),
        "text": block.text,
        "page_start": getattr(block, "page_start", None),
        "page_end": getattr(block, "page_end", None),
    }


def _id(block) -> str:
    return getattr(block, "block_id", getattr(block, "fine_id", getattr(block, "coarse_id", "")))


def _block_pages(block) -> set[int] | None:
    if not block:
        return None
    pages = {span.page_no for span in getattr(block, "spans", []) if span.page_no}
    return pages or None


def _region_pages(regions: list) -> set[int] | None:
    pages = {region.page_no for region in regions if region.page_no}
    return pages or None


def _page_payload(comparison_dir: Path, side: str, page: dict) -> dict:
    return {
        "page_no": page["page_no"],
        "image_url": f"/uploads/{comparison_dir.name}/rendered/{side}/{page['image']}",
        "width": page["width"],
        "height": page["height"],
        "scale": page["scale"],
    }

