from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class NormalizedText:
    text: str
    norm_to_raw: list[int]


def normalize_with_map(raw: str, unicode_nfkc: bool = False) -> NormalizedText:
    text = unicodedata.normalize("NFKC" if unicode_nfkc else "NFC", raw or "")
    out: list[str] = []
    mapping: list[int] = []
    previous_space = False
    for index, char in enumerate(text):
        if char in {"\u200b", "\ufeff"}:
            continue
        if char in "\r\n\t\f\v\u3000" or char.isspace():
            if not previous_space:
                out.append(" ")
                mapping.append(index)
                previous_space = True
            continue
        out.append(char)
        mapping.append(index)
        previous_space = False
    normalized = "".join(out).strip()
    if normalized != "".join(out):
        left_trim = len("".join(out)) - len("".join(out).lstrip())
        right_len = len(normalized)
        mapping = mapping[left_trim : left_trim + right_len]
    return NormalizedText(normalized, mapping)


def normalize_for_match(raw: str) -> str:
    normalized = normalize_with_map(raw).text
    # Remove artificial spaces between CJK characters introduced by PDF extraction.
    return re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", normalized)

