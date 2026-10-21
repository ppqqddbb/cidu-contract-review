from services.api.app.comparison.engine.models.document import AtomicElement, SourceSpan
from services.api.app.comparison.engine.preprocessing.non_content_filter import filter_non_content


def _element(index: int, text: str, page: int = 1) -> AtomicElement:
    return AtomicElement(
        element_id=f"e{index}",
        element_type="PARAGRAPH",
        text=text,
        normalized_text=text,
        order_index=index,
        page_no=page,
    )


def _positioned_element(index: int, text: str, y0: float, page: int = 1) -> AtomicElement:
    return _element(index, text, page).model_copy(
        update={
            "spans": [
                SourceSpan(
                    element_id=f"e{index}",
                    page_no=page,
                    bbox=(200.0, y0, 240.0, y0 + 12.0),
                    original_start=0,
                    original_end=len(text),
                )
            ]
        }
    )


def test_filter_non_content_removes_standalone_page_numbers() -> None:
    elements = [
        _element(1, "合同正文 100 元"),
        _element(2, "4 / 102"),
        _positioned_element(3, "5", 760),
    ]

    filtered = filter_non_content(elements)

    assert [item.text for item in filtered] == ["合同正文 100 元"]


def test_filter_non_content_keeps_bare_numbers_inside_body() -> None:
    elements = [
        _positioned_element(1, "1", 320),
        _element(2, "54,780,000.00"),
    ]

    filtered = filter_non_content(elements)

    assert [item.text for item in filtered] == ["1", "54,780,000.00"]


def test_filter_non_content_removes_toc_dotted_leaders() -> None:
    elements = [
        _element(1, "目录................................................................12"),
        _element(2, "第二部分 通用合同条款"),
    ]

    filtered = filter_non_content(elements)

    assert [item.text for item in filtered] == ["第二部分 通用合同条款"]


def test_filter_non_content_removes_compact_toc_blocks() -> None:
    elements = [
        _element(1, "目录 2 第一部分 合同协议书 4 第1章 合同范围 5 第二部分 通用合同条款 9"),
        _element(2, "第二部分 通用合同条款"),
    ]

    filtered = filter_non_content(elements)

    assert [item.text for item in filtered] == ["第二部分 通用合同条款"]


def test_filter_non_content_removes_split_docx_toc_region() -> None:
    elements = [
        _element(1, "目录"),
        _element(2, "目录 2"),
        _element(3, "第一部分 合同协议书 4"),
        _element(4, "第1条 合同标的与范围 4"),
        _element(5, "买方：江苏苏美达国际贸易有限公司"),
    ]

    filtered = filter_non_content(elements)

    assert [item.text for item in filtered] == ["买方：江苏苏美达国际贸易有限公司"]
