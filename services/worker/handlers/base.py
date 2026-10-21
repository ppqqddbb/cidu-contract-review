from typing import Any, Protocol


class JobHandler(Protocol):
    async def __call__(self, payload: dict[str, Any]) -> None: ...
