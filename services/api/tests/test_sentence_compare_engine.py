from services.api.app.comparison.engine.diff.line_alignment import diff_lines
from services.api.app.comparison.engine.sentence.alignment import align_sentences
from services.api.app.comparison.engine.sentence.splitter import normalize_with_map, split_sentences


def changed(ops):
    return [(op.op, op.text) for op in ops if op.op != "EQUAL"]


def test_normalize_with_map_keeps_original_offsets() -> None:
    normalized = normalize_with_map("合同 金额： 100 元")

    assert normalized.text == "合同金额:100元"
    assert normalized.index_map[0] == 0
    assert normalized.index_map[-1] == len("合同 金额： 100 元") - 1


def test_splitter_handles_contract_clauses_and_long_sentences() -> None:
    text = "1.1 合同范围：卖方负责运输、安装；同时负责调试。1.2 付款方式：验收后付款。"

    sentences = split_sentences(text)

    assert [sentence.text for sentence in sentences] == [
        "1.1 合同范围：卖方负责运输、安装；",
        "同时负责调试。",
        "1.2 付款方式：验收后付款。",
    ]


def test_sentence_insert_does_not_shift_following_sentences() -> None:
    old = "A条款。B条款。C条款。D条款。"
    new = "A条款。X新增。B条款。C条款。D条款。"

    ops = diff_lines(old, new)

    assert changed(ops) == [("INSERT", "X新增。")]


def test_sentence_delete_reports_deleted_sentence_only() -> None:
    old = "A条款。B删除。C条款。"
    new = "A条款。C条款。"

    ops = diff_lines(old, new)

    assert changed(ops) == [("DELETE", "B删除。")]


def test_sentence_change_uses_character_diff_inside_matched_sentence() -> None:
    old = "设备质量保证期为2年。"
    new = "设备质量保证期为3年。"

    ops = diff_lines(old, new)

    assert changed(ops) == [("DELETE", "2"), ("INSERT", "3")]


def test_draftable_basic_equal_insert_delete_replace() -> None:
    assert changed(diff_lines("123", "123")) == []
    assert changed(diff_lines("123", "1234")) == [("INSERT", "4")]
    assert changed(diff_lines("1234", "123")) == [("DELETE", "4")]
    assert changed(diff_lines("123", "124")) == [("DELETE", "3"), ("INSERT", "4")]


def test_one_to_two_region_uses_clause_dp_not_merged_diff() -> None:
    old = "卖方负责设备运输和安装；卖方负责调试和技术服务。"
    new = "卖方负责设备运输和安装。卖方负责调试和技术服务。"

    ops = diff_lines(old, new)

    assert changed(ops) == []


def test_two_to_one_region_uses_clause_dp_not_merged_diff() -> None:
    old = "卖方负责设备运输和安装。卖方负责调试和技术服务。"
    new = "卖方负责设备运输和安装；卖方负责调试和技术服务。"

    ops = diff_lines(old, new)

    assert changed(ops) == []


def test_banded_dp_keeps_alignment_after_local_insert() -> None:
    old = "O100条款。O101条款。O102条款。O103条款。O104条款。"
    new = "O100条款。O101条款。N110新增。O102条款。O103条款。O104条款。"

    ops = diff_lines(old, new)

    assert changed(ops) == [("INSERT", "N110新增。")]


def test_clause_renumber_after_deleted_definition_does_not_cascade() -> None:
    old = "\n".join(
        [
            "1.32 生效日期",
            "1.33 法律",
            "1.34 INCOTERMS 2020",
            "1.35 人民币",
            "1.36 重大过失",
            "1.37 项目所在国",
            "1.38 书面形式",
            "1.39 潜在缺陷",
        ]
    )
    new = "\n".join(
        [
            "1.32 生效日期",
            "1.33 法律",
            "1.34 人民币",
            "1.35 重大过失",
            "1.36 项目所在国",
            "1.37 书面形式",
            "1.38 潜在缺陷",
        ]
    )

    ops = diff_lines(old, new)

    changes = changed(ops)
    assert ("DELETE", "1.34 INCOTERMS 2020") in changes
    assert ("DELETE", "1.35 人民币") not in changes
    assert ("INSERT", "1.34 人民币") not in changes
    assert ("DELETE", "人民币") not in changes
    assert ("INSERT", "人民币") not in changes


def test_pure_numbering_change_is_hidden_by_default() -> None:
    old = "1.35 “人民币”：指中华人民共和国法定货币。"
    new = "1.34 “人民币”：指中华人民共和国法定货币。"

    ops = diff_lines(old, new)

    assert changed(ops) == []


def test_exact_moved_sentence_is_not_reported_as_change() -> None:
    old = "A条款。B条款。C条款。"
    new = "A条款。C条款。B条款。"

    ops = diff_lines(old, new)

    assert changed(ops) == []


def test_exact_moved_renumbered_clause_is_not_reported_as_change() -> None:
    old = "第5条 保密\n第6条 质保期2年\n第7条 通知"
    new = "第5条 保密\n第7条 通知\n第12条 质保期2年"

    ops = diff_lines(old, new)

    assert changed(ops) == []


def test_moved_clause_with_content_change_reports_minimal_replace() -> None:
    old = "第5条 保密\n第6条 质保期2年\n第7条 通知"
    new = "第5条 保密\n第7条 通知\n第12条 质保期3年"

    ops = diff_lines(old, new)

    assert changed(ops) == [("DELETE", "2"), ("INSERT", "3")]


def test_exact_split_and_merge_are_hidden() -> None:
    assert changed(diff_lines("ABCDEFG", "ABC\nDEFG")) == []
    assert changed(diff_lines("ABC\nDEFG", "ABCDEFG")) == []


def test_pdf_auto_line_wrap_is_hidden() -> None:
    old = "卖方保证合同设备\n质量符合要求。"
    new = "卖方保证合同设备质量符合要求。"

    ops = diff_lines(old, new)

    assert changed(ops) == []
