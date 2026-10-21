import csv
import io
from unittest.mock import Mock

from fastapi.testclient import TestClient

from services.api.app import main


def sample_csv():
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["标题", "来源", "日期", "链接", "文件日期", "摘要"])
    writer.writerow(['案例,"一"', "法院", "2026-09-09", "https://example.com/case",
                     "2026-09-10 09:20:31", "第一行\n第二行"])
    return stream.getvalue().encode("utf-8-sig")


def test_upload_then_explicit_sync(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "CASE_STORE", tmp_path / "cases")
    monkeypatch.setattr(main, "CASE_CATALOG_PATH", tmp_path / "cases/catalog.json")
    sync = Mock(return_value={"database_count": 1, "knowledge_base_count": 1,
                              "pending_count": 0, "failed_count": 0, "sync_error": ""})
    monkeypatch.setattr(main, "sync_case_items", sync)
    with TestClient(main.app) as client:
        uploaded = client.post("/api/v1/cases", data={"local_only": "true"}, files={"file": ("case.csv", sample_csv(), "text/csv")})
        assert uploaded.status_code == 200
        record = uploaded.json()
        assert record["items"][0]["file_date"] == "2026-09-10 09:20:31"
        assert record["items"][0]["summary"] == "第一行\n第二行"
        sync.assert_not_called()
        assert client.get(f"/api/v1/cases/{record['id']}/file").content == sample_csv()
        result = client.post(f"/api/v1/cases/{record['id']}/sync-database")
        assert result.status_code == 200
        assert result.json()["knowledge_base_count"] == 1
        assert client.get("/api/v1/cases").json()["items"][0]["database_count"] == 1


def test_csv_rejects_invalid_headers_without_saving(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "CASE_STORE", tmp_path / "cases")
    monkeypatch.setattr(main, "CASE_CATALOG_PATH", tmp_path / "cases/catalog.json")
    with TestClient(main.app) as client:
        response = client.post("/api/v1/cases", files={"file": ("bad.csv", b"bad,header\na,b", "text/csv")})
        assert response.status_code == 422
        assert client.get("/api/v1/cases").json()["items"] == []
