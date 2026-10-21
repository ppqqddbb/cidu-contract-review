"""Dataset HTTP calls for the explicit case synchronization action."""
import httpx


class CaseDataset:
    def __init__(self, base, key, name, dataset_id=""):
        if not key:
            raise ValueError("未配置 CASE_KB_API_KEY，案例已入库，配置后可再次同步")
        self.base, self.name, self.dataset_id = base.rstrip("/"), name, dataset_id
        self.client = httpx.Client(timeout=30, follow_redirects=False,
                                   headers={"Authorization": "Bearer " + key})

    def close(self):
        self.client.close()

    def request(self, method, path, **kwargs):
        try:
            response = self.client.request(method, self.base + path, **kwargs)
        except httpx.HTTPError:
            raise RuntimeError("知识库连接失败或超时，请检查服务后重试") from None
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"知识库返回 HTTP {response.status_code}，请检查权限和服务配置")
        try:
            body = response.json()
        except ValueError:
            raise RuntimeError("知识库响应不是 JSON") from None
        if not isinstance(body, dict):
            raise RuntimeError("知识库返回格式异常")
        return body

    def resolve(self):
        if self.dataset_id:
            return self.request("GET", f"/datasets/{self.dataset_id}")
        matches, page = [], 1
        while True:
            body = self.request("GET", "/datasets", params={"page": page, "limit": 100})
            matches.extend(row for row in body.get("data", []) if row.get("name") == self.name)
            if not body.get("has_more"):
                break
            page += 1
        if len(matches) != 1:
            raise ValueError("未找到唯一的法律案例知识库，请配置 CASE_KB_DATASET_ID")
        return matches[0]

    def create(self, dataset, row):
        text = "\n".join(f"{label}：{row.get(key) or ''}" for label, key in (
            ("标题", "title"), ("来源", "source"), ("日期", "date"),
            ("链接", "link"), ("文件日期", "file_date"), ("摘要", "summary")))
        body = self.request("POST", f"/datasets/{dataset['id']}/document/create-by-text", json={
            "name": f"case-{row['fid']} {row['title']}"[:200], "text": text,
            "indexing_technique": dataset.get("indexing_technique") or "high_quality",
            "process_rule": {"mode": "automatic"},
        })
        if not isinstance(body.get("document"), dict) or not body["document"].get("id"):
            raise RuntimeError("知识库未返回 document.id，请核对写入结果")
        return body["document"]["id"]

    def status(self, dataset, document_id):
        body = self.request("GET", f"/datasets/{dataset['id']}/documents/{document_id}")
        return body.get("indexing_status", "unknown")
