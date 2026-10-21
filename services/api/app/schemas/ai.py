from typing import Literal
from uuid import UUID

from pydantic import Field

from services.api.app.schemas.common import StrictModel


class ClassificationType(StrictModel):
    code: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=200)


class ClassificationAlternative(StrictModel):
    type: ClassificationType
    confidence: float = Field(ge=0, le=1)


class ClassificationOutputV1(StrictModel):
    schema_version: Literal["classification-output.v1"]
    workflow_version: str
    type_catalog_version: str
    run_id: str
    primary_type: ClassificationType
    secondary_tags: list[str]
    alternatives: list[ClassificationAlternative]
    confidence: float = Field(ge=0, le=1)
    evidence_summary: list[str]
    requires_human_confirmation: bool


class RagEvidence(StrictModel):
    dataset_id: str
    document_id: str
    segment_id: str


class ReviewRiskV1(StrictModel):
    clause_id: UUID
    rule_id: str
    risk_level: Literal["critical", "high", "medium", "low", "info", "needs_human"]
    title: str
    reason: str
    source_quote: str
    suggestion: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[RagEvidence]


class ReviewOutputV1(StrictModel):
    schema_version: Literal["review-output.v1"]
    workflow_version: str
    knowledge_release_id: UUID
    run_id: str
    risks: list[ReviewRiskV1]
