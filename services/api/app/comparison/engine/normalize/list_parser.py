import re
from dataclasses import dataclass


LIST_PATTERNS = [
    r"^\s*(\d+[、.．])",
    r"^\s*([（(]\d+[）)])",
    r"^\s*([一二三四五六七八九十]+[、.])",
    r"^\s*([（(][一二三四五六七八九十]+[）)])",
    r"^\s*([①②③④⑤⑥⑦⑧⑨⑩])",
    r"^\s*([-•·])",
]


@dataclass(frozen=True)
class ListParseResult:
    marker: str | None
    content: str


def parse_list_marker(text: str) -> ListParseResult:
    for pattern in LIST_PATTERNS:
        match = re.match(pattern, text or "")
        if match:
            marker = match.group(1)
            return ListParseResult(marker=marker, content=(text[match.end() :] or "").strip())
    return ListParseResult(marker=None, content=text)

