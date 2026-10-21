from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


CLAUSE_RE = re.compile(
    r"(?=(?:第[一二三四五六七八九十百零〇0-9]+[章节条款部分]|"
    r"\d+(?:\.\d+)+[、.)）]?|"
    r"\d+[、.)）]|"
    r"[（(][一二三四五六七八九十百零〇0-9]+[）)]|"
    r"[①②③④⑤⑥⑦⑧⑨⑩]))"
)
HARD_END = set("。！？；.!?;")
SOFT_SPLIT_RE = re.compile(r"(但是|同时|其中|因此|并且|另外|此外|以及|包括)")


@dataclass(frozen=True)
class NormalizedText:
    text: str
    index_map: list[int]


@dataclass(frozen=True)
class Sentence:
    id: str
    text: str
    normalized_text: str
    index: int
    original_start: int
    original_end: int
    number: str | None = None
    title: str | None = None
    body: str = ""
    normalized_title: str = ""
    normalized_body: str = ""


def normalize_with_map(text: str, ignore_case: bool = False) -> NormalizedText:
    chars: list[str] = []
    index_map: list[int] = []
    for index, char in enumerate(text or ""):
        normalized = unicodedata.normalize("NFKC", char)
        normalized = normalized.replace("\u00a0", " ").replace("\u3000", " ")
        for out_char in normalized:
            if out_char.isspace():
                continue
            chars.append(out_char.casefold() if ignore_case else out_char)
            index_map.append(index)
    return NormalizedText("".join(chars).strip(), index_map)


def split_sentences(text: str, prefix: str = "s", ignore_case: bool = False) -> list[Sentence]:
    ranges = _initial_ranges(text or "")
    ranges = _split_long_ranges(text or "", ranges)
    sentences: list[Sentence] = []
    for start, end in ranges:
        raw = (text or "")[start:end]
        stripped = raw.strip()
        if not stripped:
            continue
        leading = len(raw) - len(raw.lstrip())
        trailing = len(raw.rstrip())
        actual_start = start + leading
        actual_end = start + trailing
        normalized = normalize_with_map(text[actual_start:actual_end], ignore_case).text
        if not normalized:
            continue
        fields = parse_clause_fields(text[actual_start:actual_end], ignore_case)
        sentences.append(
            Sentence(
                id=f"{prefix}{len(sentences)}",
                text=text[actual_start:actual_end],
                normalized_text=normalized,
                index=len(sentences),
                original_start=actual_start,
                original_end=actual_end,
                number=fields["number"],
                title=fields["title"],
                body=fields["body"],
                normalized_title=fields["normalized_title"],
                normalized_body=fields["normalized_body"],
            )
        )
    return sentences


def parse_clause_fields(text: str, ignore_case: bool = False) -> dict[str, str | None]:
    raw = text.strip()
    number = None
    title = None
    body = raw
    match = re.match(
        r"^\s*(?P<number>(?:\d+(?:\.\d+)+|第[一二三四五六七八九十百千万零〇\d]+条|[（(]\d+[）)]|\d+[）)]|[①②③④⑤⑥⑦⑧⑨⑩]))\s*",
        raw,
    )
    if match:
        number = match.group("number")
        body = raw[match.end() :].strip()
    title_match = re.match(r"^[“\"《]?([^”：:，,。；;]{1,40})[”\"》]?\s*[：:]", body)
    if title_match:
        title = title_match.group(1).strip()
        body = body[title_match.end() :].strip()
    elif number and len(body) <= 60 and not any(char in body for char in "，,。；;"):
        title = body.strip()
        body = ""
    return {
        "number": number,
        "title": title,
        "body": body,
        "normalized_title": normalize_with_map(title or "", ignore_case).text,
        "normalized_body": normalize_with_map(body or "", ignore_case).text,
    }


def _initial_ranges(text: str) -> list[tuple[int, int]]:
    boundaries = {0, len(text)}
    for match in CLAUSE_RE.finditer(text):
        if match.start() > 0:
            boundaries.add(match.start())
    for index, char in enumerate(text):
        if char == "." and index > 0 and index + 1 < len(text) and text[index - 1].isdigit() and text[index + 1].isdigit():
            continue
        if char in HARD_END or char == "\n":
            boundaries.add(index + 1)
    ordered = sorted(boundaries)
    return [(ordered[i], ordered[i + 1]) for i in range(len(ordered) - 1) if ordered[i] < ordered[i + 1]]


def _split_long_ranges(text: str, ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for start, end in ranges:
        segment = text[start:end]
        if len(segment.strip()) <= 120:
            result.append((start, end))
            continue
        split_points = [match.end() for match in re.finditer(r"[；;]", segment)]
        if not split_points:
            split_points = [match.start() for match in SOFT_SPLIT_RE.finditer(segment) if match.start() >= 40]
        if not split_points:
            result.append((start, end))
            continue
        cursor = 0
        for point in split_points:
            if point - cursor >= 20:
                result.append((start + cursor, start + point))
                cursor = point
        if end - (start + cursor) > 0:
            result.append((start + cursor, end))
    return result
