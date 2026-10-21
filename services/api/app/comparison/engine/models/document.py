from pydantic import BaseModel


class SourceSpan(BaseModel):
    page_no: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    original_start: int = 0
    original_end: int = 0
    element_id: str
    ocr_confidence: float | None = None


class AtomicElement(BaseModel):
    element_id: str
    element_type: str
    text: str
    normalized_text: str
    order_index: int
    heading_level: int | None = None
    list_level: int | None = None
    page_no: int | None = None
    spans: list[SourceSpan] = []
    metadata: dict = {}


class PageIR(BaseModel):
    page_no: int
    width: float | None = None
    height: float | None = None
    metadata: dict = {}


class DocumentIR(BaseModel):
    document_id: str
    source_file_type: str
    pages: list[PageIR] = []
    elements: list[AtomicElement]
    metadata: dict = {}


class LogicalBlock(BaseModel):
    block_id: str
    block_type: str
    heading_path: list[str] = []
    order_index: int
    text: str
    normalized_text: str
    element_ids: list[str]
    spans: list[SourceSpan] = []
    page_start: int | None = None
    page_end: int | None = None
    content_hash: str
    features: dict = {}


class LogicalLine(BaseModel):
    line_id: str
    text: str
    normalized_text: str
    order_index: int
    spans: list[SourceSpan] = []

