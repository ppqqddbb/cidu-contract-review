from typing import Any

import httpx

from services.api.app.core.config import Settings
from services.api.app.core.errors import AppError


class DifyClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def run_workflow(
        self,
        *,
        workflow_id: str,
        inputs: dict[str, Any],
        user: str,
    ) -> dict[str, Any]:
        if not self._settings.dify_api_key:
            raise AppError(
                "DIFY_NOT_CONFIGURED",
                "Dify API Key尚未配置",
                status_code=503,
            )
        timeout = httpx.Timeout(
            connect=self._settings.dify_connect_timeout_seconds,
            read=self._settings.dify_read_timeout_seconds,
            write=self._settings.dify_read_timeout_seconds,
            pool=self._settings.dify_connect_timeout_seconds,
        )
        headers = {"Authorization": f"Bearer {self._settings.dify_api_key}"}
        payload = {
            "inputs": inputs,
            "response_mode": "blocking",
            "user": user,
        }
        async with httpx.AsyncClient(
            base_url=self._settings.dify_base_url,
            headers=headers,
            timeout=timeout,
        ) as client:
            response = await client.post(f"/v1/workflows/run/{workflow_id}", json=payload)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data
