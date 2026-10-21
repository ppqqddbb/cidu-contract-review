from dataclasses import dataclass
from math import inf, log1p
from typing import Literal

from ..align.similarity import similarity
from ..models.config import ComparisonProfile


@dataclass(frozen=True)
class AlignmentOp:
    type: Literal["MATCH", "DELETE", "INSERT"]
    old_range: tuple[int, int] | None
    new_range: tuple[int, int] | None
    score: float | None
    old_text: str
    new_text: str


def group_align(old_blocks: list, new_blocks: list, profile: ComparisonProfile | None = None) -> list[AlignmentOp]:
    profile = profile or ComparisonProfile()
    n, m = len(old_blocks), len(new_blocks)
    old_texts = [_join([block]) for block in old_blocks]
    new_texts = [_join([block]) for block in new_blocks]
    dp = [[inf] * (m + 1) for _ in range(n + 1)]
    back: list[list[tuple | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0

    for i in range(n + 1):
        for j in range(m + 1):
            if dp[i][j] == inf:
                continue
            if not _within_alignment_band(i, j, n, m, profile.alignment_band):
                continue
            for k in range(1, profile.max_group_old + 1):
                if i + k <= n:
                    cost = dp[i][j] + _gap_cost(_join(old_blocks[i : i + k]), profile)
                    if cost < dp[i + k][j]:
                        dp[i + k][j] = cost
                        back[i + k][j] = ("DELETE", i, i + k, j, j, None)
            for l in range(1, profile.max_group_new + 1):
                if j + l <= m:
                    cost = dp[i][j] + _gap_cost(_join(new_blocks[j : j + l]), profile)
                    if cost < dp[i][j + l]:
                        dp[i][j + l] = cost
                        back[i][j + l] = ("INSERT", i, i, j, j + l, None)
            for k in range(1, profile.max_group_old + 1):
                for l in range(1, profile.max_group_new + 1):
                    if i + k > n or j + l > m:
                        continue
                    if not _within_alignment_band(i + k, j + l, n, m, profile.alignment_band):
                        continue
                    old_text = "".join(old_texts[i : i + k])
                    new_text = "".join(new_texts[j : j + l])
                    if _length_reject(old_text, new_text, profile.max_length_ratio_for_match):
                        continue
                    old_type = _group_type(old_blocks[i : i + k])
                    new_type = _group_type(new_blocks[j : j + l])
                    sim = similarity(old_text, new_text, old_type, new_type)
                    if sim.score < profile.hard_reject:
                        continue
                    match_cost = 1.0 - sim.score
                    cost = dp[i][j] + match_cost
                    if cost < dp[i + k][j + l]:
                        dp[i + k][j + l] = cost
                        back[i + k][j + l] = ("MATCH", i, i + k, j, j + l, sim.score)

    ops: list[AlignmentOp] = []
    i, j = n, m
    while i > 0 or j > 0:
        step = back[i][j]
        if step is None:
            # Fallback should be rare; prefer explicit gap over forcing a bad match.
            if i > 0:
                step = ("DELETE", i - 1, i, j, j, None)
            else:
                step = ("INSERT", i, i, j - 1, j, None)
        op_type, old_start, old_end, new_start, new_end, score = step
        ops.append(
            AlignmentOp(
                type=op_type,
                old_range=(old_start, old_end) if old_start != old_end else None,
                new_range=(new_start, new_end) if new_start != new_end else None,
                score=score,
                old_text=_join(old_blocks[old_start:old_end]),
                new_text=_join(new_blocks[new_start:new_end]),
            )
        )
        i, j = old_start, new_start
    return _stable_gap_order(list(reversed(ops)))


def _within_alignment_band(i: int, j: int, n: int, m: int, band: int) -> bool:
    if not n or not m:
        return True
    expected_j = i * (m / n)
    return abs(j - expected_j) <= band


def _length_reject(old_text: str, new_text: str, max_ratio: float) -> bool:
    old_len = max(1, len(old_text))
    new_len = max(1, len(new_text))
    ratio = max(old_len, new_len) / min(old_len, new_len)
    if ratio <= max_ratio:
        return False
    shorter, longer = (old_text, new_text) if old_len <= new_len else (new_text, old_text)
    return shorter not in longer


def _join(blocks: list) -> str:
    return "".join(getattr(block, "normalized_text", getattr(block, "text", "")) for block in blocks)


def _group_type(blocks: list) -> str:
    types = {getattr(block, "fine_type", getattr(block, "block_type", "")) for block in blocks}
    return next(iter(types)) if len(types) == 1 else "mixed"


def _gap_cost(text: str, profile: ComparisonProfile) -> float:
    return profile.base_gap_cost + profile.length_weight * min(log1p(max(1, len(text))), 8)


def _stable_gap_order(ops: list[AlignmentOp]) -> list[AlignmentOp]:
    ordered: list[AlignmentOp] = []
    index = 0
    while index < len(ops):
        current = ops[index]
        next_op = ops[index + 1] if index + 1 < len(ops) else None
        if next_op and {current.type, next_op.type} == {"DELETE", "INSERT"}:
            delete_op = current if current.type == "DELETE" else next_op
            insert_op = current if current.type == "INSERT" else next_op
            ordered.extend([delete_op, insert_op])
            index += 2
            continue
        ordered.append(current)
        index += 1
    return ordered

