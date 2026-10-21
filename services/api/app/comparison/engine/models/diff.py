from typing import Literal

from pydantic import BaseModel


class DiffOp(BaseModel):
    op: Literal["EQUAL", "DELETE", "INSERT"]
    text: str
    old_range: tuple[int, int] | None = None
    new_range: tuple[int, int] | None = None


class Region(BaseModel):
    page_no: int
    rects: list[tuple[float, float, float, float]]


class ChangeItem(BaseModel):
    change_id: str
    display_type: Literal["insert", "delete", "replace"]
    old_text: str | None = None
    new_text: str | None = None
    old_regions: list[Region] = []
    new_regions: list[Region] = []
    old_block_ids: list[str] = []
    new_block_ids: list[str] = []
    operations: list[DiffOp] = []
    confidence: float = 1.0

