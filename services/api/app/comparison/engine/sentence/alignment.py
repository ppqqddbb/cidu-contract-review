from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from rapidfuzz import fuzz

from .splitter import Sentence


STRONG_MATCH = 0.90
MATCH_THRESHOLD = 0.82
WEAK_MATCH = 0.70
INSERT_PENALTY = -0.75
DELETE_PENALTY = -0.75
MAX_WINDOW_SIZE = 120
BASE_BAND_WIDTH = 16


@dataclass(frozen=True)
class SentenceAlignment:
    type: Literal["MATCH", "DELETE", "INSERT"]
    old_sentences: list[Sentence]
    new_sentences: list[Sentence]
    score: float


def align_sentences(
    old_sentences: list[Sentence],
    new_sentences: list[Sentence],
    threshold: float = MATCH_THRESHOLD,
    max_merge: int = 1,
) -> list[SentenceAlignment]:
    anchors = _monotonic_unique_anchors(old_sentences, new_sentences)
    windows = _anchor_windows(len(old_sentences), len(new_sentences), anchors)
    aligned: list[SentenceAlignment] = []
    for old_start, old_end, new_start, new_end, anchor in windows:
        aligned.extend(_align_window_recursive(old_sentences, new_sentences, old_start, old_end, new_start, new_end, threshold))
        if anchor:
            old_index, new_index = anchor
            aligned.append(SentenceAlignment("MATCH", [old_sentences[old_index]], [new_sentences[new_index]], 1.0))
    return _drop_moved_exact(aligned)


def _align_window_recursive(
    old_sentences: list[Sentence],
    new_sentences: list[Sentence],
    old_start: int,
    old_end: int,
    new_start: int,
    new_end: int,
    threshold: float,
) -> list[SentenceAlignment]:
    old_window = old_sentences[old_start:old_end]
    new_window = new_sentences[new_start:new_end]
    if not old_window and not new_window:
        return []
    split_merge = _exact_split_merge(old_window, new_window)
    if split_merge:
        return split_merge
    if Counter(_content_key(sentence) for sentence in old_window) == Counter(_content_key(sentence) for sentence in new_window):
        return []
    if len(old_window) > MAX_WINDOW_SIZE or len(new_window) > MAX_WINDOW_SIZE:
        secondary = _monotonic_unique_anchors(old_window, new_window)
        if secondary:
            result: list[SentenceAlignment] = []
            cursor_old = old_start
            cursor_new = new_start
            for rel_old, rel_new in secondary:
                anchor_old = old_start + rel_old
                anchor_new = new_start + rel_new
                result.extend(_align_window_recursive(old_sentences, new_sentences, cursor_old, anchor_old, cursor_new, anchor_new, threshold))
                result.append(SentenceAlignment("MATCH", [old_sentences[anchor_old]], [new_sentences[anchor_new]], 1.0))
                cursor_old = anchor_old + 1
                cursor_new = anchor_new + 1
            result.extend(_align_window_recursive(old_sentences, new_sentences, cursor_old, old_end, cursor_new, new_end, threshold))
            return result
    return _align_window_banded(old_window, new_window, threshold)


def _monotonic_unique_anchors(old_sentences: list[Sentence], new_sentences: list[Sentence]) -> list[tuple[int, int]]:
    old_counts = Counter(_anchor_key(sentence) for sentence in old_sentences)
    new_positions: dict[str, list[int]] = {}
    for index, sentence in enumerate(new_sentences):
        new_positions.setdefault(_anchor_key(sentence), []).append(index)
    candidates = []
    for old_index, sentence in enumerate(old_sentences):
        key = _anchor_key(sentence)
        positions = new_positions.get(key, [])
        if old_counts[key] == 1 and len(positions) == 1 and len(key) >= 4:
            candidates.append((old_index, positions[0], _anchor_weight(sentence)))
    candidates.sort(key=lambda item: (item[0], item[1]))
    return [(candidates[index][0], candidates[index][1]) for index in _weighted_lis(candidates)]


def _anchor_weight(sentence: Sentence) -> int:
    key = _anchor_key(sentence)
    title_bonus = 50 if sentence.normalized_title else 0
    return title_bonus + min(len(key), 100)


def _anchor_key(sentence: Sentence) -> str:
    content = (sentence.normalized_title + sentence.normalized_body).strip()
    return content or _strip_leading_number(sentence.normalized_text)


def _weighted_lis(candidates: list[tuple[int, int, int]]) -> list[int]:
    if not candidates:
        return []
    n = len(candidates)
    dp = [weight for _, _, weight in candidates]
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if candidates[j][0] < candidates[i][0] and candidates[j][1] < candidates[i][1]:
                value = dp[j] + candidates[i][2]
                if value > dp[i]:
                    dp[i] = value
                    prev[i] = j
    best = max(range(n), key=lambda index: dp[index])
    result: list[int] = []
    while best != -1:
        result.append(best)
        best = prev[best]
    return list(reversed(result))


def _anchor_windows(
    old_len: int,
    new_len: int,
    anchors: list[tuple[int, int]],
) -> list[tuple[int, int, int, int, tuple[int, int] | None]]:
    windows = []
    old_cursor = 0
    new_cursor = 0
    for anchor in anchors:
        old_index, new_index = anchor
        windows.append((old_cursor, old_index, new_cursor, new_index, anchor))
        old_cursor = old_index + 1
        new_cursor = new_index + 1
    windows.append((old_cursor, old_len, new_cursor, new_len, None))
    return windows


def _align_window_banded(old_window: list[Sentence], new_window: list[Sentence], threshold: float) -> list[SentenceAlignment]:
    n = len(old_window)
    m = len(new_window)
    if not n:
        return [SentenceAlignment("INSERT", [], [sentence], 0.0) for sentence in new_window]
    if not m:
        return [SentenceAlignment("DELETE", [sentence], [], 0.0) for sentence in old_window]
    matrix = _similarity_matrix(old_window, new_window)
    neg = -10**9
    dp = [[neg] * (m + 1) for _ in range(n + 1)]
    back: list[list[tuple | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    band = _band_width(n, m)
    for i in range(n + 1):
        j_start, j_end = _band_range(i, n, m, band)
        for j in range(j_start, j_end + 1):
            if dp[i][j] <= neg / 2:
                continue
            if i < n and _in_band(i + 1, j, n, m, band):
                value = dp[i][j] + DELETE_PENALTY
                if value > dp[i + 1][j]:
                    dp[i + 1][j] = value
                    back[i + 1][j] = ("DELETE", i, i + 1, j, j, 0.0)
            if j < m and _in_band(i, j + 1, n, m, band):
                value = dp[i][j] + INSERT_PENALTY
                if value > dp[i][j + 1]:
                    dp[i][j + 1] = value
                    back[i][j + 1] = ("INSERT", i, i, j, j + 1, 0.0)
            if i < n and j < m:
                sim = matrix[i][j]
                value = dp[i][j] + _match_score(sim)
                if sim >= WEAK_MATCH and value > dp[i + 1][j + 1]:
                    dp[i + 1][j + 1] = value
                    back[i + 1][j + 1] = ("MATCH", i, i + 1, j, j + 1, sim)
    if back[n][m] is None and (n or m):
        return _align_window_unbanded(old_window, new_window, matrix, threshold)
    return _traceback(old_window, new_window, back, n, m, threshold)


def _align_window_unbanded(
    old_window: list[Sentence],
    new_window: list[Sentence],
    matrix: list[list[float]],
    threshold: float,
) -> list[SentenceAlignment]:
    n = len(old_window)
    m = len(new_window)
    dp = [[-10**9] * (m + 1) for _ in range(n + 1)]
    back: list[list[tuple | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            if i < n and dp[i][j] + DELETE_PENALTY > dp[i + 1][j]:
                dp[i + 1][j] = dp[i][j] + DELETE_PENALTY
                back[i + 1][j] = ("DELETE", i, i + 1, j, j, 0.0)
            if j < m and dp[i][j] + INSERT_PENALTY > dp[i][j + 1]:
                dp[i][j + 1] = dp[i][j] + INSERT_PENALTY
                back[i][j + 1] = ("INSERT", i, i, j, j + 1, 0.0)
            if i < n and j < m:
                sim = matrix[i][j]
                value = dp[i][j] + _match_score(sim)
                if sim >= WEAK_MATCH and value > dp[i + 1][j + 1]:
                    dp[i + 1][j + 1] = value
                    back[i + 1][j + 1] = ("MATCH", i, i + 1, j, j + 1, sim)
    return _traceback(old_window, new_window, back, n, m, threshold)


def _traceback(
    old_window: list[Sentence],
    new_window: list[Sentence],
    back: list[list[tuple | None]],
    n: int,
    m: int,
    threshold: float,
) -> list[SentenceAlignment]:
    aligned: list[SentenceAlignment] = []
    i, j = n, m
    while i or j:
        step = back[i][j]
        if step is None:
            if i:
                step = ("DELETE", i - 1, i, j, j, 0.0)
            else:
                step = ("INSERT", i, i, j - 1, j, 0.0)
        op, old_start, old_end, new_start, new_end, score = step
        if op == "MATCH" and score < threshold:
            if _should_keep_weak_match(old_window[old_start], new_window[new_start], score):
                aligned.append(SentenceAlignment(op, old_window[old_start:old_end], new_window[new_start:new_end], score))
            else:
                aligned.extend(_clause_realign(old_window[old_start], new_window[new_start], threshold))
        else:
            aligned.append(SentenceAlignment(op, old_window[old_start:old_end], new_window[new_start:new_end], score))
        i, j = old_start, new_start
    return list(reversed(aligned))


def _similarity_matrix(old_window: list[Sentence], new_window: list[Sentence]) -> list[list[float]]:
    return [
        [
            _sentence_similarity(old_sentence, new_sentence, old_index, new_index, len(old_window), len(new_window))
            for new_index, new_sentence in enumerate(new_window)
        ]
        for old_index, old_sentence in enumerate(old_window)
    ]


def _sentence_similarity(
    old_sentence: Sentence,
    new_sentence: Sentence,
    old_index: int,
    new_index: int,
    old_total: int,
    new_total: int,
) -> float:
    old_text = _content_key(old_sentence)
    new_text = _content_key(new_sentence)
    if old_text == new_text:
        return 1.0
    if _length_ratio(old_text, new_text) > 4:
        return 0.0
    char_similarity = fuzz.ratio(old_text, new_text) / 100
    prefix_similarity = _prefix_similarity(old_text, new_text)
    title_similarity = _field_similarity(old_sentence.normalized_title, new_sentence.normalized_title)
    body_similarity = _field_similarity(old_sentence.normalized_body, new_sentence.normalized_body)
    length_similarity = 1.0 / _length_ratio(old_text, new_text)
    old_pos = old_index / max(old_total, 1)
    new_pos = new_index / max(new_total, 1)
    local_position = max(0.0, 1.0 - abs(old_pos - new_pos))
    content_similarity = 0.70 * body_similarity + 0.30 * title_similarity if (old_sentence.normalized_title or new_sentence.normalized_title) else char_similarity
    return 0.60 * content_similarity + 0.15 * prefix_similarity + 0.10 * length_similarity + 0.10 * local_position + 0.05 * char_similarity


def _match_score(similarity: float) -> float:
    if similarity >= STRONG_MATCH:
        return 2.0 + similarity
    if similarity >= MATCH_THRESHOLD:
        return 1.0 + similarity
    if similarity >= WEAK_MATCH:
        return -0.25
    return -2.0


def _band_width(old_len: int, new_len: int) -> int:
    return BASE_BAND_WIDTH + abs(old_len - new_len)


def _band_range(i: int, old_len: int, new_len: int, band: int) -> tuple[int, int]:
    if old_len == 0:
        return 0, new_len
    expected = round(i * new_len / old_len)
    return max(0, expected - band), min(new_len, expected + band)


def _in_band(i: int, j: int, old_len: int, new_len: int, band: int) -> bool:
    start, end = _band_range(i, old_len, new_len, band)
    return start <= j <= end


def _length_ratio(left: str, right: str) -> float:
    return max(len(left), len(right), 1) / max(min(len(left), len(right)), 1)


def _prefix_similarity(left: str, right: str, size: int = 12) -> float:
    left_prefix = left[: min(size, len(left))]
    right_prefix = right[: min(size, len(right))]
    if not left_prefix or not right_prefix:
        return 0.0
    return fuzz.ratio(left_prefix, right_prefix) / 100


def _content_key(sentence: Sentence) -> str:
    content = (sentence.normalized_title + sentence.normalized_body).strip()
    return content or _strip_leading_number(sentence.normalized_text)


def _exact_split_merge(old_window: list[Sentence], new_window: list[Sentence]) -> list[SentenceAlignment]:
    if len(old_window) == len(new_window):
        return []
    if not (1 <= len(old_window) <= 3 and 1 <= len(new_window) <= 3):
        return []
    old_key = "".join(_content_key(sentence) for sentence in old_window)
    new_key = "".join(_content_key(sentence) for sentence in new_window)
    if old_key and old_key == new_key:
        return [SentenceAlignment("MATCH", old_window, new_window, 1.0)]
    return []


def _field_similarity(left: str, right: str) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return fuzz.ratio(left, right) / 100


def _should_keep_weak_match(old_sentence: Sentence, new_sentence: Sentence, score: float) -> bool:
    if score < 0.60:
        return False
    old_key = _content_key(old_sentence)
    new_key = _content_key(new_sentence)
    return max(len(old_key), len(new_key)) <= 24 and fuzz.ratio(old_key, new_key) >= 60


def _strip_leading_number(text: str) -> str:
    return re.sub(r"^(第[一二三四五六七八九十百零〇0-9]+[章节条款部分]|\d+(?:\.\d+)*|[（(][一二三四五六七八九十百零〇0-9]+[）)]|\d+[）).、])", "", text or "")


def _clause_number_similarity(left: str, right: str) -> float:
    left_no = _clause_number(left)
    right_no = _clause_number(right)
    if not left_no and not right_no:
        return 0.5
    if left_no and right_no and left_no == right_no:
        return 1.0
    if left_no and right_no:
        return 0.0
    return 0.25


def _clause_number(text: str) -> str | None:
    match = re.match(r"^(第[一二三四五六七八九十百零〇0-9]+[章节条款部分]|\d+(?:\.\d+)*|[（(][一二三四五六七八九十百零〇0-9]+[）)]|\d+[）).、])", text or "")
    return match.group(0) if match else None


def _clause_realign(old_sentence: Sentence, new_sentence: Sentence, threshold: float) -> list[SentenceAlignment]:
    old_clauses = _split_clauses(old_sentence, "old_c")
    new_clauses = _split_clauses(new_sentence, "new_c")
    if len(old_clauses) <= 1 and len(new_clauses) <= 1:
        return [
            SentenceAlignment("DELETE", [old_sentence], [], 0.0),
            SentenceAlignment("INSERT", [], [new_sentence], 0.0),
        ]
    return _align_window_banded(old_clauses, new_clauses, threshold)


def _split_clauses(sentence: Sentence, prefix: str) -> list[Sentence]:
    text = sentence.text
    boundaries = {0, len(text)}
    for match in re.finditer(r"[；;：:]", text):
        boundaries.add(match.end())
    for match in re.finditer(r"，(?=(但|并且|以及|其中|同时|因此|另外|此外))", text):
        boundaries.add(match.end())
    ordered = sorted(boundaries)
    clauses: list[Sentence] = []
    for index in range(len(ordered) - 1):
        start = ordered[index]
        end = ordered[index + 1]
        raw_slice = text[start:end]
        raw = raw_slice.strip()
        if not raw:
            continue
        actual_start = sentence.original_start + start + (len(raw_slice) - len(raw_slice.lstrip()))
        actual_end = sentence.original_start + end - (len(raw_slice) - len(raw_slice.rstrip()))
        clauses.append(
            Sentence(
                id=f"{prefix}{len(clauses)}",
                text=raw,
                normalized_text=re.sub(r"\s+", "", raw),
                index=len(clauses),
                original_start=actual_start,
                original_end=actual_end,
                number=None,
                title=None,
                body=raw,
                normalized_title="",
                normalized_body=re.sub(r"\s+", "", raw),
            )
        )
    return clauses or [sentence]


def _drop_moved_exact(items: list[SentenceAlignment]) -> list[SentenceAlignment]:
    items = _pair_moved_replacements(items)
    deleted = {_content_key(item.old_sentences[0]) for item in items if item.type == "DELETE" and len(item.old_sentences) == 1}
    inserted = {_content_key(item.new_sentences[0]) for item in items if item.type == "INSERT" and len(item.new_sentences) == 1}
    moved = deleted & inserted
    return [
        item
        for item in items
        if not (
            (item.type == "DELETE" and item.old_sentences and _content_key(item.old_sentences[0]) in moved)
            or (item.type == "INSERT" and item.new_sentences and _content_key(item.new_sentences[0]) in moved)
        )
    ]


def _pair_moved_replacements(items: list[SentenceAlignment]) -> list[SentenceAlignment]:
    delete_indexes = [index for index, item in enumerate(items) if item.type == "DELETE" and len(item.old_sentences) == 1]
    insert_indexes = [index for index, item in enumerate(items) if item.type == "INSERT" and len(item.new_sentences) == 1]
    used_inserts: set[int] = set()
    replacements: dict[int, SentenceAlignment] = {}

    for delete_index in delete_indexes:
        old_sentence = items[delete_index].old_sentences[0]
        old_key = _content_key(old_sentence)
        best_insert = None
        best_score = 0.0
        for insert_index in insert_indexes:
            if insert_index in used_inserts:
                continue
            new_sentence = items[insert_index].new_sentences[0]
            score = _sentence_similarity(old_sentence, new_sentence, 0, 0, 1, 1)
            if score > best_score:
                best_score = score
                best_insert = insert_index
        if best_insert is None or best_score < 0.82:
            continue
        new_sentence = items[best_insert].new_sentences[0]
        if _content_key(new_sentence) == old_key:
            continue
        replacements[delete_index] = SentenceAlignment("MATCH", [old_sentence], [new_sentence], best_score)
        used_inserts.add(best_insert)

    if not replacements:
        return items
    result: list[SentenceAlignment] = []
    for index, item in enumerate(items):
        if index in used_inserts:
            continue
        result.append(replacements.get(index, item))
    return result
