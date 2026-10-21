"""Frozen entry point for the desktop application's local FastAPI service."""

from __future__ import annotations

import os

import uvicorn

from app.main import app


def main() -> None:
    uvicorn.run(
        app,
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
        log_level=os.getenv("API_LOG_LEVEL", "warning"),
    )


if __name__ == "__main__":
    main()
