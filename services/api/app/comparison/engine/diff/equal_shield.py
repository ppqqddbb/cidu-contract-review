from ..models.diff import DiffOp
from ..structure.normalizer import compact_text


def strip_equal_ops(ops: list[DiffOp]) -> list[DiffOp]:
    return [op for op in ops if op.op != "EQUAL" or op.text]


def has_real_change(ops: list[DiffOp]) -> bool:
    return any(op.op in {"DELETE", "INSERT"} and compact_text(op.text) for op in ops)


def normalized_equal(old_text: str | None, new_text: str | None) -> bool:
    if old_text is None or new_text is None:
        return False
    return compact_text(old_text) == compact_text(new_text)

