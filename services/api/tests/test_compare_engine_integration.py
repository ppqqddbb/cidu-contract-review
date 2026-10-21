from pathlib import Path

from fastapi.testclient import TestClient

from services.api.app import main
from services.api.app.comparison.adapter import _annotations


def test_compare_endpoint_uses_structured_engine_and_keeps_frontend_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    main.STORE = tmp_path / "compare"
    main.STORE.mkdir()
    calls: list[tuple[str, str, bool, bool]] = []

    def fake_compare(
        old: Path,
        new: Path,
        compare_dir: Path,
        ignore_whitespace: bool,
        ignore_case: bool,
    ) -> dict:
        calls.append((old.suffix, new.suffix, ignore_whitespace, ignore_case))
        return {
            "compare_id": compare_dir.name,
            "old": {"filename": old.name, "pages": [], "page_count": 0},
            "new": {"filename": new.name, "pages": [], "page_count": 0},
            "annotations": [],
            "added_count": 0,
            "removed_count": 0,
            "modified_count": 0,
            "similarity": 1.0,
            "ignore_whitespace": ignore_whitespace,
            "ignore_case": ignore_case,
        }

    monkeypatch.setattr(main, "compare_files_with_engine", fake_compare)

    with TestClient(main.app) as client:
        response = client.post(
            "/api/v1/compare",
            files={
                "old_file": ("old.pdf", b"old", "application/pdf"),
                "new_file": ("new.pdf", b"new", "application/pdf"),
            },
            data={"ignore_whitespace": "true", "ignore_case": "false"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert set(payload["result"]) >= {
        "old",
        "new",
        "annotations",
        "added_count",
        "removed_count",
        "modified_count",
        "similarity",
    }
    assert calls == [(".pdf", ".pdf", True, False)]


def test_compare_endpoint_does_not_fall_back_to_legacy_engine(
    monkeypatch,
    tmp_path: Path,
) -> None:
    main.STORE = tmp_path / "compare"
    main.STORE.mkdir()

    def fail_structured(*_args, **_kwargs):
        raise RuntimeError("structured engine failed")

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("legacy compare must not run")

    monkeypatch.setattr(main, "compare_files_with_engine", fail_structured)
    monkeypatch.setattr(main, "compare_files", fail_if_called)

    with TestClient(main.app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/compare",
            files={
                "old_file": ("old.pdf", b"old", "application/pdf"),
                "new_file": ("new.pdf", b"new", "application/pdf"),
            },
        )

    assert response.status_code == 500
    assert not any(main.STORE.iterdir())


def test_docx_pdf_changes_keep_precise_text_and_convert_normalized_boxes(
    tmp_path: Path,
) -> None:
    import fitz

    old_pdf = tmp_path / "old.pdf"
    new_pdf = tmp_path / "new.pdf"
    for path in (old_pdf, new_pdf):
        document = fitz.open()
        document.new_page(width=600, height=800)
        document.save(path)
        document.close()

    changes = [
        {
            "type": "DELETE",
            "text": "10",
            "old": {"page_index": 0, "preview_bbox": [100, 200, 300, 250]},
            "new": {},
            "metadata": {"group_id": "modify:payment"},
        },
        {
            "type": "INSERT",
            "text": "12",
            "old": {},
            "new": {"page_index": 0, "preview_bbox": [400, 500, 500, 550]},
            "metadata": {"group_id": "modify:payment"},
        },
    ]

    annotations = _annotations(changes, old_pdf, new_pdf)

    assert annotations == [
        {
            "diff_id": 1,
            "kind": "modified",
            "old_text": "10",
            "new_text": "12",
            "page_marks": [
                {
                    "side": "old",
                    "page": 1,
                    "box": {"x0": 60.0, "y0": 160.0, "x1": 180.0, "y1": 200.0},
                },
                {
                    "side": "new",
                    "page": 1,
                    "box": {"x0": 240.0, "y0": 400.0, "x1": 300.0, "y1": 440.0},
                },
            ],
            "similarity": 0.5,
        }
    ]


def test_separate_changed_ranges_do_not_become_one_large_page_mark(tmp_path: Path) -> None:
    import fitz

    old_pdf = tmp_path / "old.pdf"
    new_pdf = tmp_path / "new.pdf"
    for path in (old_pdf, new_pdf):
        document = fitz.open()
        document.new_page(width=600, height=800)
        document.save(path)
        document.close()

    changes = [
        {
            "type": "DELETE",
            "text": "10",
            "old": {
                "page_index": 0,
                "preview_bbox": [100, 100, 150, 130],
                "preview_bboxes": [[100, 100, 150, 130]],
            },
            "new": {},
            "metadata": {"group_id": "same-group"},
        },
        {
            "type": "DELETE",
            "text": "20",
            "old": {
                "page_index": 0,
                "preview_bbox": [700, 700, 760, 730],
                "preview_bboxes": [[700, 700, 760, 730]],
            },
            "new": {},
            "metadata": {"group_id": "same-group"},
        },
    ]

    marks = _annotations(changes, old_pdf, new_pdf)[0]["page_marks"]

    assert len(marks) == 2
    assert marks[0]["box"] == {"x0": 60.0, "y0": 80.0, "x1": 90.0, "y1": 104.0}
    assert marks[1]["box"] == {"x0": 420.0, "y0": 560.0, "x1": 456.0, "y1": 584.0}
