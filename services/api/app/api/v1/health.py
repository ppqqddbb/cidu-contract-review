from typing import Annotated

from fastapi import APIRouter, Depends, Request

from services.api.app.core.config import Settings, get_settings
from services.api.app.schemas.common import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
async def live(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    return HealthResponse(
        service="api",
        version=settings.app_version,
        environment=settings.environment,
        request_id=request.state.request_id,
    )
