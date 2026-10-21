from dataclasses import dataclass
from difflib import SequenceMatcher
from collections import Counter

from ..models.config import ComparisonProfile
from ..models.document import LogicalBlock


@dataclass(frozen=True)
class BlockAlignment:
    op: str
    old_index: int | None
    new_index: int | None
    score: float = 0.0


def similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right, autojunk=False).ratio()


def align_blocks(
    old_blocks: list[LogicalBlock],
    new_blocks: list[LogicalBlock],
    profile: ComparisonProfile | None = None,
) -> list[BlockAlignment]:
    profile = profile or ComparisonProfile()
    exact_matches = _unique_exact_matches(old_blocks, new_blocks)
    used_old = set(exact_matches)
    used_new = set(exact_matches.values())
    fuzzy_matches = _greedy_fuzzy_matches(old_blocks, new_blocks, used_old, used_new, profile)
    all_matches = {**exact_matches, **fuzzy_matches}
    if all_matches:
        return _matched_alignment(old_blocks, new_blocks, all_matches)
    return _ordered_dp_alignment(old_blocks, new_blocks, profile)


def _unique_exact_matches(old_blocks: list[LogicalBlock], new_blocks: list[LogicalBlock]) -> dict[int, int]:
    old_counts = Counter(block.content_hash for block in old_blocks)
    new_counts = Counter(block.content_hash for block in new_blocks)
    new_by_hash = {block.content_hash: index for index, block in enumerate(new_blocks)}
    matches: dict[int, int] = {}
    for old_index, old_block in enumerate(old_blocks):
        if len(old_block.normalized_text) < 3:
            continue
        if old_counts[old_block.content_hash] == 1 and new_counts[old_block.content_hash] == 1:
            matches[old_index] = new_by_hash[old_block.content_hash]
    return matches


def _greedy_fuzzy_matches(
    old_blocks: list[LogicalBlock],
    new_blocks: list[LogicalBlock],
    used_old: set[int],
    used_new: set[int],
    profile: ComparisonProfile,
) -> dict[int, int]:
    candidates: list[tuple[float, int, int]] = []
    for old_index, old_block in enumerate(old_blocks):
        if old_index in used_old or len(old_block.normalized_text) < 3:
            continue
        for new_index, new_block in enumerate(new_blocks):
            if new_index in used_new or len(new_block.normalized_text) < 3:
                continue
            score = similarity(old_block.normalized_text, new_block.normalized_text)
            if score >= profile.block_match_threshold:
                candidates.append((score, old_index, new_index))
    matches: dict[int, int] = {}
    for score, old_index, new_index in sorted(candidates, reverse=True):
        if old_index in used_old or new_index in used_new:
            continue
        matches[old_index] = new_index
        used_old.add(old_index)
        used_new.add(new_index)
    return matches


def _matched_alignment(
    old_blocks: list[LogicalBlock],
    new_blocks: list[LogicalBlock],
    matches: dict[int, int],
) -> list[BlockAlignment]:
    result: list[BlockAlignment] = []
    used_new = set(matches.values())
    pending_inserts = sorted(set(range(len(new_blocks))) - used_new)
    for old_index, old_block in enumerate(old_blocks):
        if old_index in matches:
            new_index = matches[old_index]
            while pending_inserts and pending_inserts[0] < new_index:
                result.append(BlockAlignment("INSERT", None, pending_inserts.pop(0), 0.0))
            score = similarity(old_block.normalized_text, new_blocks[new_index].normalized_text)
            result.append(BlockAlignment("MATCH", old_index, new_index, score))
        else:
            result.append(BlockAlignment("DELETE", old_index, None, 0.0))
    for new_index in pending_inserts:
        result.append(BlockAlignment("INSERT", None, new_index, 0.0))
    return result


def _ordered_dp_alignment(
    old_blocks: list[LogicalBlock],
    new_blocks: list[LogicalBlock],
    profile: ComparisonProfile,
) -> list[BlockAlignment]:
    n, m = len(old_blocks), len(new_blocks)
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    back: list[list[str | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    delete_penalty = 0.35
    insert_penalty = 0.35
    for i in range(1, n + 1):
        dp[i][0] = dp[i - 1][0] - delete_penalty
        back[i][0] = "DELETE"
    for j in range(1, m + 1):
        dp[0][j] = dp[0][j - 1] - insert_penalty
        back[0][j] = "INSERT"
    scores: dict[tuple[int, int], float] = {}
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            score = 1.0 if old_blocks[i - 1].content_hash == new_blocks[j - 1].content_hash else similarity(
                old_blocks[i - 1].normalized_text, new_blocks[j - 1].normalized_text
            )
            scores[(i, j)] = score
            match_value = dp[i - 1][j - 1] + (score if score >= profile.block_match_threshold else -0.5)
            delete_value = dp[i - 1][j] - delete_penalty
            insert_value = dp[i][j - 1] - insert_penalty
            best = max(match_value, delete_value, insert_value)
            dp[i][j] = best
            back[i][j] = "MATCH" if best == match_value else "DELETE" if best == delete_value else "INSERT"
    result: list[BlockAlignment] = []
    i, j = n, m
    while i > 0 or j > 0:
        action = back[i][j]
        if action == "MATCH":
            score = scores[(i, j)]
            if score >= profile.block_match_threshold:
                result.append(BlockAlignment("MATCH", i - 1, j - 1, score))
            else:
                result.append(BlockAlignment("DELETE", i - 1, None, 0.0))
                result.append(BlockAlignment("INSERT", None, j - 1, 0.0))
            i -= 1
            j -= 1
        elif action == "DELETE":
            result.append(BlockAlignment("DELETE", i - 1, None, 0.0))
            i -= 1
        else:
            result.append(BlockAlignment("INSERT", None, j - 1, 0.0))
            j -= 1
    return list(reversed(result))

