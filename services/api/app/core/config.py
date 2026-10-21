from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "合同智审"
    app_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    database_url: str = (
        "postgresql+asyncpg://contract_review:change_me@127.0.0.1:5432/contract_review"
    )
    file_storage_root: Path = Path(".data/files")

    dify_base_url: str = "http://127.0.0.1"
    dify_api_key: str = Field(default="", repr=False)
    dify_classification_workflow_id: str = ""
    dify_review_workflow_id: str = ""
    dify_connect_timeout_seconds: float = 5.0
    dify_read_timeout_seconds: float = 60.0

    worker_poll_interval_seconds: float = 2.0
    worker_lease_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
