from services.api.app.main import (
    DIFF_CHARS_PER_BLOCK,
    align_blocks,
    clean_extracted_text,
    line_diff_spans,
    normalize_for_match,
    page_hint_for_offsets,
    page_offsets,
    text_blocks,
    text_lines,
)


def test_line_diff_splits_a_large_replacement_into_readable_blocks() -> None:
    old_text = "\n".join(f"旧合同条款第 {index} 项" for index in range(18))
    new_text = "\n".join(f"新合同条款第 {index} 项" for index in range(18))

    spans = line_diff_spans(old_text, new_text, ignore_whitespace=True, ignore_case=False)

    assert len(spans) >= 3
    assert all(span[2] - span[1] <= DIFF_CHARS_PER_BLOCK for span in spans)
    assert all(span[4] - span[3] <= DIFF_CHARS_PER_BLOCK for span in spans)


def test_line_diff_keeps_word_level_changes_inside_aligned_lines() -> None:
    old_text = "共同条款\n工程名称：低压电缆\n合同金额：100 元"
    new_text = "共同条款\n工程名称：低压高压电缆\n合同金额：2000 元"

    spans = line_diff_spans(old_text, new_text, ignore_whitespace=True, ignore_case=False)
    changes = [
        (tag, old_text[start:end], new_text[new_start:new_end])
        for tag, start, end, new_start, new_end in spans
    ]

    assert ("insert", "", "高压") in changes
    assert any(old == "1" and new == "20" for _, old, new in changes)


def test_text_lines_merges_wrapped_numbered_clauses_and_splits_inline_clauses() -> None:
    text = (
        "1.11 技术资料：指卖方提供的设计、制造、检验、安装、调试、\n"
        "性能试验、运行维护有关的技术文件。\n"
        "10 / 102\n"
        "1.12 技术服务：指卖方提供的监督、检验。1.13 技术培训：指卖方培训。"
    )

    lines = text_lines(text, ignore_whitespace=True, ignore_case=False)

    assert [line[0][:4] for line in lines] == ["1.11", "1.12", "1.13"]
    assert "性能试验" in lines[0][0]
    assert all("10/102" not in line[0] for line in lines)


def test_clean_extracted_text_removes_pdf_page_number_lines() -> None:
    assert clean_extracted_text("正文\n10 / 102\n下一页") == "正文\n下一页"


def test_run_split_is_same() -> None:
    a = "第4条 卖方履约地点、履约方式、履约时间进度"
    b = "".join(["第", "4条 ", "卖方履约地点、履约方式、履约时间进度"])

    assert normalize_for_match(a) == normalize_for_match(b)


def test_line_break_is_same() -> None:
    a = "山东省青岛市胶州市胶北办事处工业园达能路3号"
    b = "山东省青岛市胶州市胶北办事处工\n业园达能路3号"

    assert normalize_for_match(a) == normalize_for_match(b)


def test_insert_does_not_shift_following_blocks() -> None:
    old_blocks = text_blocks("\n".join(["P1", "P2", "P3", "P4"]))
    new_blocks = text_blocks("\n".join(["P1", "NEW", "P2", "P3", "P4"]))

    aligned = [
        (left.raw_text if left else None, right.raw_text if right else None)
        for left, right in align_blocks(old_blocks, new_blocks)
    ]

    assert aligned == [
        ("P1", "P1"),
        (None, "NEW"),
        ("P2", "P2"),
        ("P3", "P3"),
        ("P4", "P4"),
    ]


def test_same_text_moved_should_not_modify() -> None:
    old_text = "\n".join(["A", "B", "C"])
    new_text = "\n".join(["A", "C", "B"])

    spans = line_diff_spans(old_text, new_text, ignore_whitespace=True, ignore_case=False)

    assert spans == []


def test_same_clause_with_different_wrapping_has_no_diff() -> None:
    old_text = "第4条 卖方履约地点、履约方式、履约时间进度\n4.1 山东省青岛市胶州市胶北办事处工\n业园达能路3号。"
    new_text = "第\n4条 卖方履约地点、履约方式、履约时间进度\n4.1 山东省青岛市胶州市胶北办事处工业园达能路3号。"

    spans = line_diff_spans(old_text, new_text, ignore_whitespace=True, ignore_case=False)

    assert spans == []


def test_context_queries_do_not_search_tiny_terms_alone() -> None:
    from services.api.app.main import context_queries

    source = "合同设备的合同价格为含13%税的总价格。"
    start = source.index("税")
    queries = context_queries(source, start, start + 1)

    assert queries
    assert "税" not in queries


def test_page_hint_uses_pdf_page_offsets() -> None:
    pages = ["第一页正文", "第二页合同价格", "第三页交货"]
    offsets = page_offsets(pages)
    source = "\n\n".join(pages)

    assert page_hint_for_offsets(source, source.index("合同价格"), 3, offsets) == 2
