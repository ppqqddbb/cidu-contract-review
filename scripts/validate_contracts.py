import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_ROOT = Path("contracts/dify")


def main() -> None:
    files = sorted(SCHEMA_ROOT.glob("*.schema.json"))
    if not files:
        raise SystemExit("no Dify JSON Schema files found")
    for path in files:
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        print(f"valid {path}")


if __name__ == "__main__":
    main()
