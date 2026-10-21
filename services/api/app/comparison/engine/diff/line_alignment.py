from ..diff.char_diff import char_diff
from ..models.config import ComparisonProfile
from ..models.diff import DiffOp
from ..sentence.alignment import align_sentences
from ..sentence.splitter import split_sentences


def logical_lines(text: str) -> list[str]:
    return [sentence.text for sentence in split_sentences(text)]


def diff_lines(old_text: str, new_text: str, profile: ComparisonProfile | None = None) -> list[DiffOp]:
    profile = profile or ComparisonProfile()
    ops: list[DiffOp] = []
    old_sentences = split_sentences(old_text, "old_s")
    new_sentences = split_sentences(new_text, "new_s")
    alignments = align_sentences(
        old_sentences,
        new_sentences,
        threshold=profile.sentence_match_threshold,
        max_merge=profile.sentence_max_merge,
    )
    for item in alignments:
        old_segment = _join_sentence_text(item.old_sentences)
        new_segment = _join_sentence_text(item.new_sentences)
        if item.type == "MATCH":
            if _same_normalized(item.old_sentences, item.new_sentences, profile):
                ops.append(DiffOp(op="EQUAL", text=new_segment or old_segment))
            else:
                ops.extend(_field_level_diff(item.old_sentences, item.new_sentences, old_segment, new_segment, profile))
            continue
        if item.type == "DELETE" and old_segment:
            ops.append(DiffOp(op="DELETE", text=old_segment))
            continue
        if item.type == "INSERT" and new_segment:
            ops.append(DiffOp(op="INSERT", text=new_segment))
    return _merge_adjacent(_drop_sentence_boundary_punctuation_changes([op for op in ops if op.text]))


def _join_sentence_text(sentences) -> str:
    return "\n".join(sentence.text for sentence in sentences if sentence.text)


def _same_normalized(old_sentences, new_sentences, profile: ComparisonProfile) -> bool:
    same_content = "".join(_content_key(sentence) for sentence in old_sentences) == "".join(
        _content_key(sentence) for sentence in new_sentences
    )
    if profile.ignore_pure_numbering_changes:
        return same_content
    same_number = "".join(sentence.number or "" for sentence in old_sentences) == "".join(
        sentence.number or "" for sentence in new_sentences
    )
    return same_content and same_number


def _field_level_diff(old_sentences, new_sentences, old_segment: str, new_segment: str, profile: ComparisonProfile) -> list[DiffOp]:
    if len(old_sentences) != 1 or len(new_sentences) != 1:
        return char_diff(old_segment, new_segment)
    old = old_sentences[0]
    new = new_sentences[0]
    if not (old.number or new.number or old.title or new.title):
        return char_diff(old_segment, new_segment)
    ops: list[DiffOp] = []
    if not profile.ignore_pure_numbering_changes and (old.number or "") != (new.number or ""):
        if old.number:
            ops.append(DiffOp(op="DELETE", text=old.number))
        if new.number:
            ops.append(DiffOp(op="INSERT", text=new.number))
    if old.normalized_title != new.normalized_title:
        ops.extend(char_diff(old.title or "", new.title or ""))
    if old.normalized_body != new.normalized_body:
        ops.extend(char_diff(old.body or "", new.body or ""))
    return ops or [DiffOp(op="EQUAL", text=new_segment or old_segment)]


def _content_key(sentence) -> str:
    return (sentence.normalized_title + sentence.normalized_body).strip() or _strip_leading_number(sentence.normalized_text)


def _strip_leading_number(text: str) -> str:
    import re

    return re.sub(r"^(第[一二三四五六七八九十百零〇0-9]+[章节条款部分]|\d+(?:\.\d+)*|[（(][一二三四五六七八九十百零〇0-9]+[）)]|\d+[）).、])", "", text or "")


def _merge_adjacent(ops: list[DiffOp]) -> list[DiffOp]:
    merged: list[DiffOp] = []
    for op in ops:
        if merged and merged[-1].op == op.op == "EQUAL":
            merged[-1].text += "\n" + op.text if "\n" not in {merged[-1].text[-1:], op.text[:1]} else op.text
        else:
            merged.append(op)
    return merged


def _drop_sentence_boundary_punctuation_changes(ops: list[DiffOp]) -> list[DiffOp]:
    kept: list[DiffOp] = []
    index = 0
    while index < len(ops):
        current = ops[index]
        next_op = ops[index + 1] if index + 1 < len(ops) else None
        if (
            current.op == "DELETE"
            and next_op
            and next_op.op == "INSERT"
            and _boundary_punctuation(current.text)
            and _boundary_punctuation(next_op.text)
        ):
            index += 2
            continue
        kept.append(current)
        index += 1
    return kept


def _boundary_punctuation(text: str) -> bool:
    return bool(text) and all(char in "。；;.!?\n\r\t " for char in text)

