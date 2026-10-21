import json
import os
import subprocess
import tempfile
from pathlib import Path

from ..mineru.schemas import MinerUParseResult


class MinerUClient:
    def __init__(self, enabled: bool | None = None) -> None:
        self.enabled = enabled if enabled is not None else os.getenv("COMPARE_USE_MINERU", "0") == "1"

    def parse(self, path: str | Path) -> MinerUParseResult | None:
        if not self.enabled:
            return None
        source = Path(path)
        if source.suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg"}:
            return None
        output_dir = Path(tempfile.mkdtemp(prefix="mineru_"))
        command = [
            "mineru",
            "--path",
            str(source),
            "--output",
            str(output_dir),
            "--backend",
            os.getenv("MINERU_BACKEND", "pipeline"),
            "--method",
            os.getenv("MINERU_METHOD", "auto"),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=int(os.getenv("MINERU_TIMEOUT", "180")))
        except Exception:
            return None
        payload_path = self._find_payload(output_dir)
        if not payload_path:
            return None
        try:
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return MinerUParseResult(payload=payload, output_dir=str(output_dir), version=self.version())

    def version(self) -> str | None:
        try:
            result = subprocess.run(["mineru", "--version"], capture_output=True, text=True, timeout=10)
            return (result.stdout or result.stderr).strip() or None
        except Exception:
            return None

    def _find_payload(self, output_dir: Path) -> Path | None:
        names = ("middle.json", "middle_json.json", "structured_content.json", "content_list.json")
        for name in names:
            matches = list(output_dir.rglob(name))
            if matches:
                return matches[0]
        json_files = list(output_dir.rglob("*.json"))
        return json_files[0] if json_files else None

