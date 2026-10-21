from pydantic import BaseModel

from ..models.document import SourceSpan


class CoarseBlock(BaseModel):
    coarse_id: str
    block_type: str
    heading_path: list[str] = []
    heading_text: str | None = None
    order_start: int
    order_end: int
    text: str
    normalized_text: str
    child_element_ids: list[str]
    spans: list[SourceSpan] = []
    content_hash: str
    features: dict = {}


class FineBlock(BaseModel):
    fine_id: str
    parent_coarse_id: str
    fine_type: str
    numbering: str | None = None
    key_text: str | None = None
    order_index: int
    text: str
    normalized_text: str
    element_ids: list[str]
    spans: list[SourceSpan] = []
    content_hash: str
    features: dict = {}

