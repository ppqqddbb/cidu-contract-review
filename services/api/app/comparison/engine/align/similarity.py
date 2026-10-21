from dataclasses import dataclass
from math import sqrt
from collections import Counter

from rapidfuzz import fuzz


@dataclass(frozen=True)
class SimilarityBreakdown:
    score: float
    ratio: float
    token_set: float
    char_ngram: float
    structure: float


def similarity(old_text: str, new_text: str, old_type: str = "", new_type: str = "") -> SimilarityBreakdown:
    if old_text == new_text:
        return SimilarityBreakdown(1.0, 1.0, 1.0, 1.0, 1.0)
    if not old_text or not new_text:
        return SimilarityBreakdown(0.0, 0.0, 0.0, 0.0, 0.0)
    ratio = fuzz.ratio(old_text, new_text) / 100
    token_set = fuzz.token_set_ratio(old_text, new_text) / 100
    ngram = _char_ngram_cosine(old_text, new_text)
    structure = 1.0 if old_type == new_type and old_type else 0.5
    score = 0.45 * ratio + 0.30 * token_set + 0.15 * ngram + 0.10 * structure
    return SimilarityBreakdown(score, ratio, token_set, ngram, structure)


def _char_ngram_cosine(left: str, right: str, n: int = 3) -> float:
    def grams(value: str) -> Counter:
        compact = value.replace(" ", "")
        if len(compact) <= n:
            return Counter([compact]) if compact else Counter()
        return Counter(compact[index : index + n] for index in range(len(compact) - n + 1))

    a = grams(left)
    b = grams(right)
    if not a or not b:
        return 0.0
    dot = sum(a[key] * b.get(key, 0) for key in a)
    norm_a = sqrt(sum(value * value for value in a.values()))
    norm_b = sqrt(sum(value * value for value in b.values()))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0

