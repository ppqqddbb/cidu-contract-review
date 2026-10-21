import base64
import json

import respx
from fastapi.testclient import TestClient

from services.api.app import main


def configure_case_store(tmp_path, monkeypatch) -> None:
    case_store = tmp_path / "cases"
    monkeypatch.setattr(main, "CASE_STORE", case_store)
    monkeypatch.setattr(main, "CASE_CATALOG_PATH", case_store / "catalog.json")


def test_case_upload_persists_original_in_kingdee(tmp_path, monkeypatch) -> None:
    configure_case_store(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "KINGDEE_CASE_STORAGE_URL", "https://kingdee.test/ierp/kapi/v2/r8p0/bos/contract-review/legal-cases/file/store")
    monkeypatch.setattr(main, "KINGDEE_CASE_STORAGE_AUTHORIZATION", "Bearer test-token")
    content = b"Case title\nSource: test\n"

    with respx.mock(assert_all_called=True) as mocked, TestClient(main.app) as client:
        route = mocked.post(main.KINGDEE_CASE_STORAGE_URL).respond(
            200,
            json={
                "data": {
                    "storagePath": "attachment/cases/case.txt",
                    "downloadUrl": "https://kingdee.test/files/case.txt",
                }
            },
        )
        response = client.post(
            "/api/v1/cases",
            files={"file": ("case.txt", content, "text/plain")},
        )

        assert response.status_code == 200
        created = response.json()
        assert created["storage_status"] == "stored"
        assert created["storage_error"] == ""
        assert created["kingdee_storage_path"] == "attachment/cases/case.txt"
        assert created["kingdee_download_url"] == "https://kingdee.test/files/case.txt"

        request = route.calls[0].request
        assert request.headers["authorization"] == "Bearer test-token"
        payload = json.loads(request.content)
        assert payload["caseId"] == created["id"]
        assert payload["fileName"] == "case.txt"
        assert payload["contentType"] == "text/plain"
        assert base64.b64decode(payload["contentBase64"]) == content

        case_store = main.CASE_STORE
        assert not (case_store / created["id"] / "source.txt").exists()
        catalog = json.loads((case_store / "catalog.json").read_text(encoding="utf-8"))
        assert catalog[0]["kingdee_storage_path"] == "attachment/cases/case.txt"

        listed = client.get("/api/v1/cases")
        assert listed.status_code == 200
        assert listed.json()["items"] == [created]

        downloaded = client.get(f"/api/v1/cases/{created['id']}/file", follow_redirects=False)
        assert downloaded.status_code == 307
        assert downloaded.headers["location"] == "https://kingdee.test/files/case.txt"

        deleted = client.delete(f"/api/v1/cases/{created['id']}")
        assert deleted.status_code == 204

    assert json.loads((main.CASE_CATALOG_PATH).read_text(encoding="utf-8")) == []


def test_case_upload_requires_kingdee_storage_configuration(tmp_path, monkeypatch) -> None:
    configure_case_store(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "KINGDEE_CASE_STORAGE_URL", "")

    with TestClient(main.app) as client:
        response = client.post(
            "/api/v1/cases",
            files={"file": ("case.txt", b"local only", "text/plain")},
        )

    assert response.status_code == 503
    assert "KINGDEE_CASE_STORAGE_URL" in response.json()["detail"]
    assert not main.CASE_CATALOG_PATH.exists()


def test_case_upload_obtains_a_kingdee_oauth_token(tmp_path, monkeypatch) -> None:
    configure_case_store(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "KINGDEE_CASE_STORAGE_URL", "https://kingdee.test/ierp/kapi/v2/r8p0/bos/contract-review/legal-cases/file/store")
    monkeypatch.setattr(main, "KINGDEE_CASE_STORAGE_AUTHORIZATION", "")
    monkeypatch.setattr(main, "KINGDEE_CASE_STORAGE_TOKEN_URL", "https://kingdee.test/ierp/kapi/oauth2/getToken")
    monkeypatch.setattr(main, "KINGDEE_CASE_STORAGE_CLIENT_ID", "case-library")
    monkeypatch.setattr(main, "KINGDEE_CASE_STORAGE_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(main, "KINGDEE_CASE_STORAGE_USERNAME", "api-user")
    monkeypatch.setattr(main, "KINGDEE_CASE_STORAGE_ACCOUNT_ID", "dev_local_4_all")

    with respx.mock(assert_all_called=True) as mocked, TestClient(main.app) as client:
        token_route = mocked.post(main.KINGDEE_CASE_STORAGE_TOKEN_URL).respond(
            200, json={"status": True, "data": {"access_token": "short-lived-token"}}
        )
        store_route = mocked.post(main.KINGDEE_CASE_STORAGE_URL).respond(
            200, json={"data": {"storagePath": "attachment/cases/case.txt", "downloadUrl": "https://kingdee.test/files/case.txt"}}
        )

        response = client.post("/api/v1/cases", files={"file": ("case.txt", b"case", "text/plain")})

    assert response.status_code == 200
    assert token_route.calls[0].request.content
    assert store_route.calls[0].request.headers["authorization"] == "Bearer short-lived-token"
    assert store_route.calls[0].request.headers["accessToken"] == "short-lived-token"
