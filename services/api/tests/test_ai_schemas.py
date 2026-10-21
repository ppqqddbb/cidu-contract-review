from uuid import uuid4

import pytest
from pydantic import ValidationError

from services.api.app.schemas.ai import ReviewOutputV1


def test_review_output_rejects_unknown_fields() -> None:
    payload = {
        "schema_version": "review-output.v1",
        "workflow_version": "contract-review-v1.0.0",
        "knowledge_release_id": str(uuid4()),
        "run_id": "run-1",
        "risks": [],
        "unexpected": True,
    }

    with pytest.raises(ValidationError):
        ReviewOutputV1.model_validate(payload)
