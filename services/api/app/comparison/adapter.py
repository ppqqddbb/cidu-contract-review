from __future__ import annotations

import difflib
import os
import shutil
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import fitz


@lru_cache(maxsize=1)
def _source_engine() -> tuple[Any, Any, Any, Any]:
    """Load the canonical implementation from the sibling docx-pdf project."""
    configured = os.getenv("DOCX_PDF_ROOT", "").strip()
    project_root = Path(__file__).resolve().parents[4]
    source_root = Path(configured).resolve() if configured else project_root.parent / "docx-pdf"
    if not (source_root / "backend" / "comparison" / "service.py").is_file():
        raise RuntimeError(
            "未找到 docx-pdf 对比引擎；请设置 DOCX_PDF_ROOT 指向 docx-pdf 项目根目录"
        )
    source_text = str(source_root)
    if source_text not in sys.path:
        sys.path.insert(0, source_text)

    from backend.comparison import compare_markdown_documents
    from backend.mineru_runner import parse_document_outputs
    from backend.preview_locator import attach_preview_locations
    from backend.preview_renderer import render_document_preview

    return (
        parse_document_outputs,
        compare_markdown_documents,
        render_document_preview,
        attach_preview_locations,
    )


def compare_files_with_engine(
    old: Path,
    new: Path,
    compare_dir: Path,
    ignore_whitespace: bool,
    ignore_case: bool,
) -> dict[str, Any]:
    parse_outputs, compare_markdown, render_preview, attach_locations = _source_engine()

    old_output = parse_outputs(old)
    new_output = parse_outputs(new)
    render_root = compare_dir / "rendered"
    old_render = render_preview(old, render_root / "old")
    new_render = render_preview(new, render_root / "new")
    comparison = compare_markdown(
        old_output["markdown"],
        new_output["markdown"],
        old_auxiliary_structured=old_output["structured_content"],
        new_auxiliary_structured=new_output["structured_content"],
    )
    attach_locations(comparison, old_render["pdf_path"], new_render["pdf_path"])

    old_preview = _preview(old, old_render, compare_dir, "old")
    new_preview = _preview(new, new_render, compare_dir, "new")
    annotations = _annotations(
        comparison.get("changes", []),
        old_render["pdf_path"],
        new_render["pdf_path"],
    )
    old_text = old_output["markdown"]
    new_text = new_output["markdown"]
    similarity = difflib.SequenceMatcher(None, old_text, new_text, autojunk=False).ratio()

    return {
        "compare_id": compare_dir.name,
        "old": old_preview,
        "new": new_preview,
        "annotations": annotations,
        "added_count": sum(item["kind"] == "added" for item in annotations),
        "removed_count": sum(item["kind"] == "removed" for item in annotations),
        "modified_count": sum(item["kind"] == "modified" for item in annotations),
        "similarity": round(similarity, 4),
        "ignore_whitespace": ignore_whitespace,
        "ignore_case": ignore_case,
        "engine": "docx-pdf",
        "engine_summary": comparison.get("summary", {}),
    }


def _preview(
    source: Path,
    rendered: dict[str, Any],
    compare_dir: Path,
    side: str,
) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    for page in rendered["pages"]:
        page_no = int(page["page_index"]) + 1
        image_name = str(page["image"])
        image_source = compare_dir / "rendered" / side / image_name
        image_target = compare_dir / f"{side}_p{page_no}.png"
        shutil.copyfile(image_source, image_target)
        pages.append(
            {
                "page": page_no,
                "url": f"/api/v1/compare/{compare_dir.name}/files/{image_target.name}",
                "width_px": page["width"],
                "height_px": page["height"],
            }
        )

    with fitz.open(str(rendered["pdf_path"])) as document:
        rect = document[0].rect if document.page_count else fitz.Rect(0, 0, 595, 842)
    return {
        "filename": source.name,
        "ext": source.suffix.lower().lstrip("."),
        "display_format": "pdf",
        "page_count": len(pages),
        "page_width_pt": float(rect.width),
        "page_height_pt": float(rect.height),
        "pages": pages,
        "text_extracted": True,
        "text_error": "",
    }


def _annotations(
    changes: list[dict[str, Any]],
    old_pdf: Path,
    new_pdf: Path,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for index, change in enumerate(changes):
        metadata = change.get("metadata") or {}
        group_id = str(metadata.get("group_id") or f"change-{index}")
        grouped.setdefault(group_id, []).append(change)

    old_sizes = _page_sizes(old_pdf)
    new_sizes = _page_sizes(new_pdf)
    annotations: list[dict[str, Any]] = []
    for diff_id, members in enumerate(grouped.values(), 1):
        deletes = [item for item in members if item.get("type") == "DELETE"]
        inserts = [item for item in members if item.get("type") == "INSERT"]
        old_text = "".join(str(item.get("text") or "") for item in deletes)
        new_text = "".join(str(item.get("text") or "") for item in inserts)
        kind = "modified" if deletes and inserts else "removed" if deletes else "added"
        marks = _marks_for_side(deletes, "old", old_sizes)
        marks.extend(_marks_for_side(inserts, "new", new_sizes))
        score = None
        if kind == "modified":
            score = round(
                difflib.SequenceMatcher(None, old_text, new_text, autojunk=False).ratio(),
                4,
            )
        annotations.append(
            {
                "diff_id": diff_id,
                "kind": kind,
                "old_text": old_text,
                "new_text": new_text,
                "page_marks": marks,
                "similarity": score,
            }
        )
    return annotations


def _page_sizes(pdf_path: Path) -> dict[int, tuple[float, float]]:
    with fitz.open(str(pdf_path)) as document:
        return {
            index: (float(page.rect.width), float(page.rect.height))
            for index, page in enumerate(document)
        }


def _marks_for_side(
    changes: list[dict[str, Any]],
    side: str,
    page_sizes: dict[int, tuple[float, float]],
) -> list[dict[str, Any]]:
    boxes_by_page: dict[int, list[list[float]]] = {}
    for change in changes:
        source = change.get(side) or {}
        page_index = source.get("page_index")
        preview_bboxes = source.get("preview_bboxes")
        if not isinstance(preview_bboxes, list) or not preview_bboxes:
            bbox = source.get("preview_bbox")
            preview_bboxes = [bbox] if isinstance(bbox, list) else []
        valid_boxes = [
            [float(value) for value in bbox[:4]]
            for bbox in preview_bboxes
            if isinstance(bbox, list) and len(bbox) >= 4
        ]
        if page_index is None or not valid_boxes:
            continue
        boxes_by_page.setdefault(int(page_index), []).extend(valid_boxes)

    marks: list[dict[str, Any]] = []
    for page_index, boxes in boxes_by_page.items():
        width, height = page_sizes.get(page_index, (595.0, 842.0))
        for box in _deduplicate_boxes(boxes):
            marks.append(
                {
                    "side": side,
                    "page": page_index + 1,
                    "box": {
                        "x0": round(box[0] / 1000.0 * width, 4),
                        "y0": round(box[1] / 1000.0 * height, 4),
                        "x1": round(box[2] / 1000.0 * width, 4),
                        "y1": round(box[3] / 1000.0 * height, 4),
                    },
                },
            )
    return marks


def _deduplicate_boxes(boxes: list[list[float]]) -> list[list[float]]:
    unique: list[list[float]] = []
    for box in boxes:
        if not any(
            all(abs(left - right) < 0.5 for left, right in zip(box, seen, strict=True))
            for seen in unique
        ):
            unique.append(box)
    return unique
