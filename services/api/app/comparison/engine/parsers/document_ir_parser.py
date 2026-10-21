from pathlib import Path

from ..mineru.adapter import MinerUAdapter
from ..mineru.client import MinerUClient
from ..models.document import DocumentIR
from ..parsers.docx_parser import parse_docx
from ..parsers.pdf_parser import parse_pdf
from ..preprocessing.logical_line import rebuild_logical_lines
from ..preprocessing.non_content_filter import filter_non_content


def parse_document_ir(path: str | Path) -> DocumentIR:
    path = Path(path)
    mineru_result = MinerUClient().parse(path)
    if mineru_result:
        document = MinerUAdapter().from_payload(
            mineru_result.payload,
            path,
            {"mineru_output_dir": mineru_result.output_dir, "mineru_version": mineru_result.version},
        )
    else:
        document = _fallback_ir(path)
    elements = rebuild_logical_lines(filter_non_content(document.elements))
    return document.model_copy(update={"elements": elements})


def _fallback_ir(path: Path) -> DocumentIR:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        elements = parse_docx(path)
    elif suffix == ".pdf":
        elements = parse_pdf(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")
    return DocumentIR(
        document_id=path.stem,
        source_file_type=suffix.lstrip("."),
        elements=elements,
        metadata={"parser": "fallback", "fallback_reason": "mineru unavailable, disabled, or unsupported format"},
    )

