from pydantic import BaseModel


class MinerUParseResult(BaseModel):
    payload: dict
    output_dir: str | None = None
    source: str = "mineru"
    version: str | None = None

