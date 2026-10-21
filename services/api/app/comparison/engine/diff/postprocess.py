import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from ..diff.char_diff import char_diff
from ..models.diff import DiffOp
from ..structure.normalizer import compact_text


_PUNCT_TRANSLATION = str.maketrans(
    {
        "，": ",",
        "。": ".",
        "：": ":",
        "；": ";",
        "（": "(",
        "）": ")",
        "【": "[",
        "】": "]",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "、": ",",
        "　": " ",
    }
)

_FIELD_LABEL_RE = re.compile(
    r"(统一社会信用代码为|统一社会信用代码|合同编号|签署日期|签订日期|发布日期|签订地点|住所为|住所|买方|卖方|名称|数量|规格|单位|序号)\s*[:：]?"
)
_SEPARATOR_RE = re.compile(r"(\n+|[。；;，,])")
_MAX_GROUP = 3


@dataclass(frozen=True)
class AtomicFragment:
    text: str
    normalized_text: str
    role: str


def refine_diff_ops(old_text: str | None, new_text: str | None, ops: list[DiffOp]) -> list[DiffOp]:
    """Keep only the meaningful changed fragments for front-end highlighting."""
    if old_text and new_text and _has_delete_and_insert(ops):
        refined = _best_refined_ops(old_text, new_text)
        if _should_use_refined_ops(refined, ops):
            ops = refined
    return _drop_cosmetic_ops(ops)


def _best_refined_ops(old: str, new: str) -> list[DiffOp]:
    fragment_ops = _atomic_fragment_diff(old, new)
    if fragment_ops:
        return fragment_ops
    line_scoped = _line_scoped_diff(old, new)
    if line_scoped and (len(old.splitlines()) > 1 or len(new.splitlines()) > 1):
        return line_scoped
    candidates = [char_diff(old, new)]
    if line_scoped:
        candidates.append(line_scoped)
    return min(candidates, key=lambda item: (_changed_len(item), -_equal_len(item)))


def _atomic_fragment_diff(old: str, new: str) -> list[DiffOp] | None:
    old_fragments = _split_atomic_fragments(old)
    new_fragments = _split_atomic_fragments(new)
    if len(old_fragments) < 2 and len(new_fragments) < 2:
        return None
    alignments = _align_atomic_fragments(old_fragments, new_fragments)
    ops: list[DiffOp] = []
    for old_group, new_group in alignments:
        old_text = "".join(fragment.text for fragment in old_group)
        new_text = "".join(fragment.text for fragment in new_group)
        if old_group and new_group and _canonical(old_text) == _canonical(new_text):
            ops.append(DiffOp(op="EQUAL", text=new_text))
            continue
        if old_group and not new_group:
            ops.append(DiffOp(op="DELETE", text=old_text))
            continue
        if new_group and not old_group:
            ops.append(DiffOp(op="INSERT", text=new_text))
            continue
        if _same_business_unit(old_group, new_group):
            ops.extend(_diff_matched_fragment(old_text, new_text, old_group, new_group))
        else:
            ops.append(DiffOp(op="DELETE", text=old_text))
            ops.append(DiffOp(op="INSERT", text=new_text))
    return _merge_adjacent(ops)


def _split_atomic_fragments(text: str) -> list[AtomicFragment]:
    fragments: list[AtomicFragment] = []
    for piece in _split_preserving_separators(text):
        if not piece:
            continue
        _append_field_fragments(piece, fragments)
    return [fragment for fragment in fragments if fragment.text]


def _split_preserving_separators(text: str) -> list[str]:
    return [part for part in _SEPARATOR_RE.split(text or "") if part]


def _append_field_fragments(piece: str, fragments: list[AtomicFragment]) -> None:
    matches = list(_FIELD_LABEL_RE.finditer(piece))
    if not matches:
        _append_plain_fragment(piece, fragments)
        return
    cursor = 0
    for index, match in enumerate(matches):
        if match.start() > cursor:
            _append_plain_fragment(piece[cursor : match.start()], fragments)
        label = _complete_label(match.group(0))
        fragments.append(_fragment(label, "label"))
        value_start = match.end()
        value_end = matches[index + 1].start() if index + 1 < len(matches) else len(piece)
        value = piece[value_start:value_end]
        if value:
            fragments.append(_fragment(value, "field_value"))
        cursor = value_end
    if cursor < len(piece):
        _append_plain_fragment(piece[cursor:], fragments)


def _append_plain_fragment(text: str, fragments: list[AtomicFragment]) -> None:
    if not text:
        return
    role = "span_group" if text.strip() else "separator"
    fragments.append(_fragment(text, role))


def _complete_label(text: str) -> str:
    stripped = text.rstrip()
    if stripped.endswith((":", "：")):
        return text
    return f"{text}："


def _fragment(text: str, role: str) -> AtomicFragment:
    return AtomicFragment(text=text, normalized_text=_canonical(text), role=role)


def _align_atomic_fragments(
    old_fragments: list[AtomicFragment],
    new_fragments: list[AtomicFragment],
) -> list[tuple[list[AtomicFragment], list[AtomicFragment]]]:
    n = len(old_fragments)
    m = len(new_fragments)
    dp = [[float("inf")] * (m + 1) for _ in range(n + 1)]
    prev: list[list[tuple[int, int] | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            if dp[i][j] == float("inf"):
                continue
            for old_take in range(0, min(_MAX_GROUP, n - i) + 1):
                for new_take in range(0, min(_MAX_GROUP, m - j) + 1):
                    if old_take == 0 and new_take == 0:
                        continue
                    if old_take > 0 and new_take > 0 and max(old_take, new_take) == 1:
                        pass
                    elif old_take > 0 and new_take > 0 and min(old_take, new_take) != 1:
                        continue
                    cost = _alignment_cost(
                        old_fragments[i : i + old_take],
                        new_fragments[j : j + new_take],
                    )
                    next_i = i + old_take
                    next_j = j + new_take
                    value = dp[i][j] + cost
                    if value < dp[next_i][next_j]:
                        dp[next_i][next_j] = value
                        prev[next_i][next_j] = (old_take, new_take)
    alignments: list[tuple[list[AtomicFragment], list[AtomicFragment]]] = []
    i, j = n, m
    while i or j:
        step = prev[i][j]
        if step is None:
            return [(old_fragments, new_fragments)]
        old_take, new_take = step
        old_start = i - old_take
        new_start = j - new_take
        alignments.append((old_fragments[old_start:i], new_fragments[new_start:j]))
        i, j = old_start, new_start
    alignments.reverse()
    return alignments


def _alignment_cost(old_group: list[AtomicFragment], new_group: list[AtomicFragment]) -> float:
    if not old_group:
        return 0.72 * max(1, len(new_group))
    if not new_group:
        return 0.72 * max(1, len(old_group))
    old_text = "".join(fragment.normalized_text for fragment in old_group)
    new_text = "".join(fragment.normalized_text for fragment in new_group)
    if old_text == new_text:
        return 0.0
    if _group_role(old_group) == "label" and _group_role(new_group) == "label":
        return 1.8
    ratio = SequenceMatcher(None, old_text, new_text, autojunk=False).ratio()
    role_penalty = 0.0 if _group_role(old_group) == _group_role(new_group) else 0.28
    size_penalty = 0.04 * (len(old_group) + len(new_group) - 2)
    return 1.0 - ratio + role_penalty + size_penalty


def _group_role(group: list[AtomicFragment]) -> str:
    roles = {fragment.role for fragment in group if fragment.role != "separator"}
    if len(roles) == 1:
        return next(iter(roles))
    if "field_value" in roles:
        return "field_value"
    if "label" in roles:
        return "label"
    return "span_group"


def _same_business_unit(old_group: list[AtomicFragment], new_group: list[AtomicFragment]) -> bool:
    old_role = _group_role(old_group)
    new_role = _group_role(new_group)
    if old_role != new_role:
        return False
    if old_role in {"label", "field_value"}:
        return True
    old_text = "".join(fragment.normalized_text for fragment in old_group)
    new_text = "".join(fragment.normalized_text for fragment in new_group)
    return SequenceMatcher(None, old_text, new_text, autojunk=False).ratio() >= 0.55


def _diff_matched_fragment(
    old_text: str,
    new_text: str,
    old_group: list[AtomicFragment],
    new_group: list[AtomicFragment],
) -> list[DiffOp]:
    if _group_role(old_group) == "field_value" or _group_role(new_group) == "field_value":
        return [DiffOp(op="DELETE", text=old_text), DiffOp(op="INSERT", text=new_text)]
    return char_diff(old_text, new_text)


def _line_scoped_diff(old: str, new: str) -> list[DiffOp] | None:
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    if len(old_lines) != len(new_lines):
        return None
    ops: list[DiffOp] = []
    for old_line, new_line in zip(old_lines, new_lines):
        ops.extend(_trimmed_replace_ops(old_line, new_line))
        ops.append(DiffOp(op="EQUAL", text="\n"))
    return ops[:-1] if ops else None


def _trimmed_replace_ops(old: str, new: str) -> list[DiffOp]:
    if old == new:
        return [DiffOp(op="EQUAL", text=old)]
    prefix_len = _common_prefix_len(old, new)
    suffix_len = _common_suffix_len(old[prefix_len:], new[prefix_len:])
    old_mid_end = len(old) - suffix_len
    new_mid_end = len(new) - suffix_len
    pieces = [
        DiffOp(op="EQUAL", text=old[:prefix_len]),
        DiffOp(op="DELETE", text=old[prefix_len:old_mid_end]),
        DiffOp(op="INSERT", text=new[prefix_len:new_mid_end]),
        DiffOp(op="EQUAL", text=old[old_mid_end:]),
    ]
    return [piece for piece in pieces if piece.text]


def _common_prefix_len(old: str, new: str) -> int:
    limit = min(len(old), len(new))
    index = 0
    while index < limit and old[index] == new[index]:
        index += 1
    return index


def _common_suffix_len(old: str, new: str) -> int:
    limit = min(len(old), len(new))
    index = 0
    while index < limit and old[-index - 1] == new[-index - 1]:
        index += 1
    return index


def _has_delete_and_insert(ops: list[DiffOp]) -> bool:
    return any(op.op == "DELETE" for op in ops) and any(op.op == "INSERT" for op in ops)


def _should_use_refined_ops(refined: list[DiffOp], original: list[DiffOp]) -> bool:
    original_changed = _changed_len(original)
    refined_changed = _changed_len(refined)
    equal_chars = _equal_len(refined)
    if refined_changed == 0:
        return True
    if equal_chars >= 2:
        return True
    return refined_changed <= original_changed


def _changed_len(ops: list[DiffOp]) -> int:
    return sum(len(compact_text(op.text)) for op in ops if op.op != "EQUAL")


def _equal_len(ops: list[DiffOp]) -> int:
    return sum(len(compact_text(op.text)) for op in ops if op.op == "EQUAL")


def _drop_cosmetic_ops(ops: list[DiffOp]) -> list[DiffOp]:
    kept: list[DiffOp] = []
    index = 0
    while index < len(ops):
        current = ops[index]
        next_op = ops[index + 1] if index + 1 < len(ops) else None
        if (
            current.op == "DELETE"
            and next_op
            and next_op.op == "INSERT"
            and _cosmetically_equal(current.text, next_op.text)
        ):
            kept.append(DiffOp(op="EQUAL", text=next_op.text, old_range=current.old_range, new_range=next_op.new_range))
            index += 2
            continue
        if current.op in {"DELETE", "INSERT"} and not _meaningful_text(current.text):
            index += 1
            continue
        kept.append(current)
        index += 1
    return _merge_adjacent(kept)


def _cosmetically_equal(old: str, new: str) -> bool:
    return _canonical(old) == _canonical(new)


def _canonical(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").translate(_PUNCT_TRANSLATION)).lower()


def _meaningful_text(text: str) -> bool:
    canonical = _canonical(text)
    if not canonical:
        return False
    return bool(re.search(r"[\w\u4e00-\u9fff]", canonical))


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

