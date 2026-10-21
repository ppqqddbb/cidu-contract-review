from difflib import SequenceMatcher

from ..models.diff import DiffOp


def char_diff(old: str, new: str) -> list[DiffOp]:
    ops: list[DiffOp] = []
    matcher = SequenceMatcher(None, old, new, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            ops.append(DiffOp(op="EQUAL", text=old[i1:i2], old_range=(i1, i2), new_range=(j1, j2)))
        elif tag == "delete":
            ops.append(DiffOp(op="DELETE", text=old[i1:i2], old_range=(i1, i2), new_range=None))
        elif tag == "insert":
            ops.append(DiffOp(op="INSERT", text=new[j1:j2], old_range=None, new_range=(j1, j2)))
        else:
            ops.append(DiffOp(op="DELETE", text=old[i1:i2], old_range=(i1, i2), new_range=None))
            ops.append(DiffOp(op="INSERT", text=new[j1:j2], old_range=None, new_range=(j1, j2)))
    return _merge_adjacent(ops)


def _merge_adjacent(ops: list[DiffOp]) -> list[DiffOp]:
    merged: list[DiffOp] = []
    for op in ops:
        if not op.text:
            continue
        if merged and merged[-1].op == op.op:
            previous = merged[-1]
            previous.text += op.text
            if previous.old_range and op.old_range:
                previous.old_range = (previous.old_range[0], op.old_range[1])
            if previous.new_range and op.new_range:
                previous.new_range = (previous.new_range[0], op.new_range[1])
        else:
            merged.append(op)
    return merged

