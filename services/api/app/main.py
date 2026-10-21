from __future__ import annotations

import base64
import csv
import difflib
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

import fitz
import httpx
import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from starlette.concurrency import run_in_threadpool
from .case_database import list_database_cases
from .case_sync import sync_case_items
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from .comparison.adapter import compare_files_with_engine

API_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
# Shell and system environment variables keep precedence over either local file.
load_dotenv(API_ROOT / ".env", encoding="utf-8-sig")
load_dotenv(PROJECT_ROOT / ".env", encoding="utf-8-sig")

DATA_ROOT = Path(os.getenv("CONTRACT_REVIEW_DATA_DIR", PROJECT_ROOT / ".data"))
STORE = DATA_ROOT / "compare"
STORE.mkdir(parents=True, exist_ok=True)
REVIEW_STORE = DATA_ROOT / "review"
REVIEW_STORE.mkdir(parents=True, exist_ok=True)
CASE_STORE = DATA_ROOT / "cases"
CASE_STORE.mkdir(parents=True, exist_ok=True)
CASE_CATALOG_PATH = CASE_STORE / "catalog.json"
ALLOWED = {".doc", ".docx", ".pdf", ".jpg", ".jpeg", ".png"}
CASE_ALLOWED = {".doc", ".docx", ".pdf", ".txt", ".csv"}
WS = re.compile(r"\s+")
PAGE_NUMBER_LINE = re.compile(r"^\s*\d+\s*/\s*\d+\s*$")
CHINESE_CLAUSE_NUMBER = r"第[一二三四五六七八九十百千万零〇0-9]+[章节条款项]"
DECIMAL_CLAUSE_NUMBER = r"[0-9]+(?:\.[0-9]+)+"
LIST_CLAUSE_NUMBER = r"(?:[（(]\d+[）)]|\d+[）)])"
CLAUSE_NUMBER = (
    rf"(?:{CHINESE_CLAUSE_NUMBER}|{DECIMAL_CLAUSE_NUMBER}(?![\d.])|{LIST_CLAUSE_NUMBER})"
)
CLAUSE_HEADING = re.compile(
    rf"^\s*{CLAUSE_NUMBER}"
)
CLAUSE_BOUNDARY = re.compile(
    rf"(?<![A-Za-z0-9])(?={CLAUSE_NUMBER})"
)
logger = logging.getLogger("contract-review")
DIFF_LINES_PER_BLOCK = 6
DIFF_CHARS_PER_BLOCK = 480
ATOMIC_REPLACE_CHARS = 160
BLOCK_MATCH_THRESHOLD = 0.62


@dataclass(frozen=True)
class TextBlock:
    raw_text: str
    match_text: str
    start: int
    end: int
    order: int
    anchor: str = ""


def office_command() -> str | None:
    candidates: list[Path] = []
    configured = os.getenv("LIBREOFFICE_PATH", "").strip()
    if configured:
        candidates.append(Path(configured))
    executable_dir = Path(sys.executable).resolve().parent
    candidates.extend(
        [
            executable_dir / "libreoffice",
            executable_dir,
            Path(r"C:\Program Files\LibreOffice"),
            Path(r"C:\Program Files (x86)\LibreOffice"),
        ]
    )
    for command in (shutil.which("soffice.com"), shutil.which("soffice"), shutil.which("libreoffice")):
        if command:
            candidates.append(Path(command))
    seen: set[str] = set()
    for candidate in candidates:
        path = candidate
        if path.is_dir():
            path = path / "program" / "soffice.com"
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        if path.is_file():
            return str(path)
    return None


def office_process_env(soffice: str) -> dict[str, str]:
    """Keep LibreOffice's sibling DLLs ahead of any system installation."""
    program_dir = str(Path(soffice).resolve().parent)
    path = os.environ.get("PATH", "")
    return {**os.environ, "PATH": f"{program_dir}{os.pathsep}{path}", "SAL_USE_VCLPLUGIN": "svp"}


def office_process_kwargs() -> dict:
    """Run the console wrapper without showing a terminal window on Windows."""
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": startupinfo}

app = FastAPI(title="Contract Review API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DIFY_BASE_URL = os.getenv("DIFY_BASE_URL", "http://ciduai.daneng.cc/v1").rstrip("/")
DIFY_CONTRACT_TYPE_APP_ID = os.getenv("DIFY_CONTRACT_TYPE_APP_ID", "app-kn9ZmLFlmfnTyQ45ZsaEg6YC")
DIFY_CONTRACT_REVIEW_APP_ID = os.getenv("DIFY_CONTRACT_REVIEW_APP_ID", "app-UIqpM0VXmoZVkfdKsN9BE0Dl")
# Dify app API keys use the app-... value supplied for each agent by default.
DIFY_CONTRACT_TYPE_API_KEY = os.getenv("DIFY_CONTRACT_TYPE_API_KEY", DIFY_CONTRACT_TYPE_APP_ID)
DIFY_CONTRACT_REVIEW_API_KEY = os.getenv("DIFY_CONTRACT_REVIEW_API_KEY", DIFY_CONTRACT_REVIEW_APP_ID)
# Case import/synchronization uses a Dify dataset API key (dataset-...).
CASE_DB_HOST = os.getenv("CASE_DB_HOST", "127.0.0.1")
CASE_DB_PORT = int(os.getenv("CASE_DB_PORT", "5432"))
CASE_DB_NAME = os.getenv("CASE_DB_NAME", "dev_local_4_all")
CASE_DB_USER = os.getenv("CASE_DB_USER", "postgres")
CASE_DB_PASSWORD = os.getenv("CASE_DB_PASSWORD", "")
CASE_DB_SCHEMA = os.getenv("CASE_DB_SCHEMA", "public")
CASE_DB_TABLE = os.getenv("CASE_DB_TABLE", "tk_r8p0_case")
CASE_KB_API_KEY = os.getenv("CASE_KB_API_KEY", "")
CASE_KB_NAME = os.getenv("CASE_KB_NAME", "法律案例知识库")
CASE_KB_DATASET_ID = os.getenv("CASE_KB_DATASET_ID", "")
# Full URL of the Kingdee custom API that persists a case file in AttachmentFileService.
KINGDEE_CASE_STORAGE_URL = os.getenv("KINGDEE_CASE_STORAGE_URL", "").strip()
# Optional Authorization header value, for example "Bearer <access-token>".
KINGDEE_CASE_STORAGE_AUTHORIZATION = os.getenv("KINGDEE_CASE_STORAGE_AUTHORIZATION", "").strip()
# OAuth credentials are preferred over a static token because Kingdee tokens expire.
KINGDEE_CASE_STORAGE_TOKEN_URL = os.getenv("KINGDEE_CASE_STORAGE_TOKEN_URL", "").strip()
KINGDEE_CASE_STORAGE_CLIENT_ID = os.getenv("KINGDEE_CASE_STORAGE_CLIENT_ID", "").strip()
KINGDEE_CASE_STORAGE_CLIENT_SECRET = os.getenv("KINGDEE_CASE_STORAGE_CLIENT_SECRET", "").strip()
KINGDEE_CASE_STORAGE_USERNAME = os.getenv("KINGDEE_CASE_STORAGE_USERNAME", "").strip()
KINGDEE_CASE_STORAGE_ACCOUNT_ID = os.getenv("KINGDEE_CASE_STORAGE_ACCOUNT_ID", "").strip()


def _dify_text(payload: dict) -> str:
    """Read text from Dify chat or workflow response formats."""
    answer = payload.get("answer")
    if isinstance(answer, str) and answer.strip():
        return answer.strip()
    data = payload.get("data")
    if isinstance(data, dict):
        outputs = data.get("outputs")
        if isinstance(outputs, dict):
            for value in outputs.values():
                if isinstance(value, str) and value.strip():
                    return value.strip()
                if isinstance(value, (dict, list)):
                    return json.dumps(value, ensure_ascii=False)
    outputs = payload.get("outputs")
    if isinstance(outputs, dict):
        return json.dumps(outputs, ensure_ascii=False)
    return json.dumps(payload, ensure_ascii=False)


def _contract_type(answer: str) -> str:
    """Extract a concise type label while preserving non-JSON agent replies."""
    candidate = answer.strip().removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            for key in ("contract_type", "contractType", "type", "合同类型"):
                value = parsed.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    except json.JSONDecodeError:
        pass
    for pattern in (r"合同类型\s*[:：]\s*([^\n，,。]+)", r"类型\s*[:：]\s*([^\n，,。]+)"):
        match = re.search(pattern, answer, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return answer.splitlines()[0].strip()[:80] or "未识别"


async def _dify_chat_streaming(file_name: str, file_bytes: bytes, content_type: str, api_key: str, query: str, inputs: dict | None = None) -> str:
    """使用流式模式调用 Dify，避免 504 超时问题"""
    if not api_key:
        raise RuntimeError("未配置 DIFY API Key，请设置 DIFY_CONTRACT_TYPE_API_KEY 或 DIFY_CONTRACT_REVIEW_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"}
    # 流式模式下超时配置：连接30秒，读取600秒（等待流数据），写入60秒
    timeout = httpx.Timeout(600.0, connect=30.0, read=600.0, write=60.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        # 1. 上传文件
        upload = await client.post(
            f"{DIFY_BASE_URL}/files/upload",
            headers=headers,
            data={"user": "contract-review-web"},
            files={"file": (file_name, file_bytes, content_type or "application/octet-stream")},
        )
        upload.raise_for_status()
        upload_payload = upload.json()
        upload_id = upload_payload.get("id")
        if not upload_id:
            raise RuntimeError(f"Dify 文件上传未返回 id: {upload_payload}")

        # 2. 使用流式模式调用
        full_answer = ""
        conversation_id = None

        async with client.stream(
            "POST",
            f"{DIFY_BASE_URL}/chat-messages",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "inputs": inputs or {},
                "query": query,
                "response_mode": "streaming",  # 使用流式模式
                "user": "contract-review-web",
                "files": [{"type": "image" if (content_type or "").startswith("image/") else "document", "transfer_method": "local_file", "upload_file_id": upload_id}],
            },
        ) as response:
            response.raise_for_status()
            logger.info("Dify streaming started app=%s status=%s", api_key[:12], response.status_code)

            # 3. 逐行读取 SSE 流
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue

                try:
                    data = json.loads(line[6:])  # 去掉 "data: " 前缀
                    event = data.get("event")

                    if event == "message":
                        # 累积答案片段
                        answer_chunk = data.get("answer", "")
                        full_answer += answer_chunk
                        conversation_id = data.get("conversation_id")
                    elif event == "agent_message" or event == "message_replace":
                        # 某些 Dify 版本使用这些事件
                        answer_chunk = data.get("answer", "")
                        full_answer += answer_chunk
                    elif event == "message_end":
                        # 流结束
                        logger.info("Dify streaming completed conversation_id=%s answer_length=%d", conversation_id, len(full_answer))
                        break
                    elif event == "error":
                        # 处理错误
                        error_msg = data.get("message", "Unknown error")
                        raise RuntimeError(f"Dify streaming error: {error_msg}")
                except json.JSONDecodeError as e:
                    logger.warning("Failed to parse SSE line: %s, error: %s", line, e)
                    continue

        if not full_answer:
            raise RuntimeError("Dify 流式响应未返回任何内容")

        return full_answer.strip()


async def _dify_chat(file_name: str, file_bytes: bytes, content_type: str, api_key: str, query: str, inputs: dict | None = None) -> str:
    """调用 Dify API（支持流式和阻塞模式）"""
    # 优先使用流式模式，避免 504 超时
    try:
        return await _dify_chat_streaming(file_name, file_bytes, content_type, api_key, query, inputs)
    except Exception as e:
        logger.warning("Dify 流式调用失败，回退到阻塞模式: %s", e)
        # 回退到阻塞模式
        return await _dify_chat_blocking(file_name, file_bytes, content_type, api_key, query, inputs)


async def _dify_chat_blocking(file_name: str, file_bytes: bytes, content_type: str, api_key: str, query: str, inputs: dict | None = None) -> str:
    """使用阻塞模式调用 Dify（备用方案）"""
    if not api_key:
        raise RuntimeError("未配置 DIFY API Key，请设置 DIFY_CONTRACT_TYPE_API_KEY 或 DIFY_CONTRACT_REVIEW_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"}
    # 增加超时时间：合同智审可能需要较长处理时间
    # 连接超时 30 秒，读取超时 600 秒（10 分钟），写入超时 60 秒
    timeout = httpx.Timeout(600.0, connect=30.0, read=600.0, write=60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        upload = await client.post(
            f"{DIFY_BASE_URL}/files/upload",
            headers=headers,
            data={"user": "contract-review-web"},
            files={"file": (file_name, file_bytes, content_type or "application/octet-stream")},
        )
        upload.raise_for_status()
        upload_payload = upload.json()
        upload_id = upload_payload.get("id")
        if not upload_id:
            raise RuntimeError(f"Dify 文件上传未返回 id: {upload_payload}")
        response = await client.post(
            f"{DIFY_BASE_URL}/chat-messages",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "inputs": inputs or {},
                "query": query,
                "response_mode": "blocking",
                "user": "contract-review-web",
                "files": [{"type": "image" if (content_type or "").startswith("image/") else "document", "transfer_method": "local_file", "upload_file_id": upload_id}],
            },
        )
        logger.info("Dify response app=%s status=%s content_type=%s body_bytes=%s", api_key[:12], response.status_code, response.headers.get("content-type", ""), len(response.content))
        response.raise_for_status()
        return _dify_text(response.json())


async def _kingdee_case_headers(client: httpx.AsyncClient) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if KINGDEE_CASE_STORAGE_AUTHORIZATION:
        headers["Authorization"] = KINGDEE_CASE_STORAGE_AUTHORIZATION
        static_token = KINGDEE_CASE_STORAGE_AUTHORIZATION
        if static_token.lower().startswith("bearer "):
            static_token = static_token[7:].strip()
        if static_token:
            headers["accessToken"] = static_token
        headers["Idempotency-Key"] = str(uuid.uuid4())
        return headers

    required = {
        "KINGDEE_CASE_STORAGE_TOKEN_URL": KINGDEE_CASE_STORAGE_TOKEN_URL,
        "KINGDEE_CASE_STORAGE_CLIENT_ID": KINGDEE_CASE_STORAGE_CLIENT_ID,
        "KINGDEE_CASE_STORAGE_CLIENT_SECRET": KINGDEE_CASE_STORAGE_CLIENT_SECRET,
        "KINGDEE_CASE_STORAGE_USERNAME": KINGDEE_CASE_STORAGE_USERNAME,
        "KINGDEE_CASE_STORAGE_ACCOUNT_ID": KINGDEE_CASE_STORAGE_ACCOUNT_ID,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise HTTPException(
            503,
            "金蝶案例存储未配置鉴权：请设置 KINGDEE_CASE_STORAGE_AUTHORIZATION，"
            f"或配置 OAuth 参数：{', '.join(missing)}",
        )

    try:
        token_response = await client.post(
            KINGDEE_CASE_STORAGE_TOKEN_URL,
            json={
                "client_id": KINGDEE_CASE_STORAGE_CLIENT_ID,
                "client_secret": KINGDEE_CASE_STORAGE_CLIENT_SECRET,
                "username": KINGDEE_CASE_STORAGE_USERNAME,
                "accountId": KINGDEE_CASE_STORAGE_ACCOUNT_ID,
                "nonce": str(uuid.uuid4()),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "language": "zh_CN",
            },
        )
        token_response.raise_for_status()
        token_payload = token_response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"无法获取金蝶访问令牌: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(502, "无法获取金蝶访问令牌: 响应不是 JSON") from exc

    token_data = token_payload.get("data") if isinstance(token_payload, dict) else None
    access_token = token_data.get("access_token") if isinstance(token_data, dict) else None
    if token_payload.get("status") is False or not isinstance(access_token, str) or not access_token.strip():
        message = token_payload.get("message") if isinstance(token_payload, dict) else None
        raise HTTPException(502, f"无法获取金蝶访问令牌: {message or '响应缺少 access_token'}")
    access_token = access_token.strip()
    headers["Authorization"] = f"Bearer {access_token}"
    headers["accessToken"] = access_token
    headers["Idempotency-Key"] = str(uuid.uuid4())
    return headers


async def _store_case_in_kingdee(
    case_id: str,
    filename: str,
    content_type: str,
    file_bytes: bytes,
) -> tuple[str, str]:
    """Persist the original case file through the published Kingdee Custom API."""
    if not KINGDEE_CASE_STORAGE_URL:
        raise HTTPException(503, "金蝶案例存储未配置：请设置 KINGDEE_CASE_STORAGE_URL")

    payload = {
        "caseId": case_id,
        "fileName": filename,
        "contentType": content_type or "application/octet-stream",
        "contentBase64": base64.b64encode(file_bytes).decode("ascii"),
    }
    try:
        # 增加超时时间以处理大文件上传
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=30.0, read=300.0, write=120.0)) as client:
            response = await client.post(
                KINGDEE_CASE_STORAGE_URL,
                headers=await _kingdee_case_headers(client),
                json=payload,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] or "empty response body"
        raise HTTPException(
            502,
            f"金蝶案例文件存储失败: HTTP {exc.response.status_code}: {detail}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"无法连接金蝶案例存储服务: {exc}") from exc

    try:
        response_payload = response.json()
    except ValueError as exc:
        raise HTTPException(502, "金蝶案例文件存储失败: 响应不是 JSON") from exc

    if response_payload.get("status") is False or response_payload.get("success") is False:
        message = response_payload.get("message") or response_payload.get("msg") or "金蝶案例文件存储失败"
        raise HTTPException(502, str(message))

    data = response_payload.get("data", response_payload)
    if not isinstance(data, dict):
        raise HTTPException(502, "金蝶案例文件存储失败: 响应数据格式无效")
    storage_path = str(data.get("storagePath") or data.get("filePath") or "").strip()
    download_url = str(data.get("downloadUrl") or data.get("fileUrl") or "").strip()
    if not storage_path or not download_url:
        raise HTTPException(502, "金蝶案例文件存储失败: 响应缺少 storagePath 或 downloadUrl")
    return storage_path, download_url


def normalize(value: str, ignore_whitespace: bool, ignore_case: bool) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\u3000", " ")
    if ignore_whitespace:
        value = WS.sub("", value)
    return value.casefold() if ignore_case else value


def normalize_with_map(value: str, ignore_whitespace: bool, ignore_case: bool) -> tuple[str, list[int]]:
    """Normalize content while retaining each normalized character's source offset."""
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\u3000", " ")
    normalized: list[str] = []
    source_offsets: list[int] = []
    for offset, char in enumerate(value):
        if ignore_whitespace and WS.fullmatch(char):
            continue
        expanded = char.casefold() if ignore_case else char
        normalized.extend(expanded)
        source_offsets.extend([offset] * len(expanded))
    return "".join(normalized), source_offsets


def normalize_for_match(value: str, ignore_case: bool = False) -> str:
    """Build text used only for content matching, ignoring layout-only differences."""
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\u00a0", " ").replace("\u3000", " ")
    value = value.replace("\n", "")
    value = re.sub(r"[ \t]+", "", value)
    value = value.casefold() if ignore_case else value
    return value.strip()


def convert_to_pdf(source: Path, out: Path) -> Path:
    if source.suffix.lower() == ".pdf":
        return source
    if source.suffix.lower() in {".jpg", ".jpeg", ".png"}:
        image_doc = fitz.open(str(source))
        try:
            out.write_bytes(image_doc.convert_to_pdf())
        finally:
            image_doc.close()
        return out
    target_dir = out.parent
    soffice = office_command()
    if not soffice:
        raise RuntimeError("未找到 LibreOffice，无法生成 DOC/DOCX 预览")
    profile = target_dir / ".libreoffice-profile"
    profile.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [soffice, "--headless", f"-env:UserInstallation={profile.as_uri()}", "--convert-to", "pdf", "--outdir", str(target_dir), str(source)],
        check=True,
        capture_output=True,
        timeout=180,
        cwd=str(Path(soffice).resolve().parent),
        env=office_process_env(soffice),
        **office_process_kwargs(),
    )
    converted = target_dir / f"{source.stem}.pdf"
    if not converted.exists():
        raise RuntimeError("Office 文档转换 PDF 失败")
    return converted


def _word_to_pdf(source: Path, out: Path) -> Path:
    import win32com.client

    word = win32com.client.DispatchEx("Word.Application")
    try:
        word.Visible = False
        word.DisplayAlerts = 0
        document = word.Documents.Open(str(source.resolve()), ReadOnly=True)
        try:
            document.SaveAs2(str(out.resolve()), FileFormat=17)
        finally:
            document.Close(False)
    finally:
        word.Quit()
    if not out.exists():
        raise RuntimeError("Microsoft Word 未生成 PDF")
    return out


def _docx_preview_pdf(source: Path, out: Path) -> Path:
    """Build a dependable text preview when local LibreOffice is unavailable."""
    from PIL import Image, ImageDraw, ImageFont

    configured_font = os.getenv("CONTRACT_REVIEW_FONT")
    font_path = next(
        (
            Path(path)
            for path in (
                configured_font,
                r"C:\Windows\Fonts\msyh.ttc",
                r"C:\Windows\Fonts\simhei.ttf",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                "/usr/share/fonts/truetype/arphic/uming.ttc",
            )
            if path and Path(path).exists()
        ),
        None,
    )
    font = ImageFont.truetype(str(font_path), 25) if font_path else ImageFont.load_default()
    lines: list[str] = []
    for value in office_text(source).splitlines() or [""]:
        lines.extend(value[i : i + 35] for i in range(0, len(value), 35))
        if not value:
            lines.append("")
    images: list[Path] = []
    for page_index, start in enumerate(range(0, max(1, len(lines)), 42), 1):
        image = Image.new("RGB", (1240, 1754), "white")
        draw = ImageDraw.Draw(image)
        y = 75
        for line in lines[start : start + 42]:
            draw.text((80, y), line, fill="#172033", font=font)
            y += 38
        image_path = out.parent / f"{out.stem}_source_{page_index}.png"
        image.save(image_path)
        images.append(image_path)
    pdf = fitz.open()
    try:
        for image_path in images:
            image_doc = fitz.open(str(image_path))
            try:
                converted = fitz.open("pdf", image_doc.convert_to_pdf())
                pdf.insert_pdf(converted)
                converted.close()
            finally:
                image_doc.close()
        pdf.save(str(out))
    finally:
        pdf.close()
    return out


def office_text(path: Path) -> str:
    from docx import Document
    docx_path = path
    if path.suffix.lower() == ".doc":
        temp_dir = Path(tempfile.mkdtemp(prefix="doc-extract-", dir=str(STORE)))
        soffice = office_command()
        if not soffice:
            return ""
        profile = temp_dir / ".libreoffice-profile"
        profile.mkdir(parents=True, exist_ok=True)
        subprocess.run([soffice, "--headless", f"-env:UserInstallation={profile.as_uri()}", "--convert-to", "docx", "--outdir", str(temp_dir), str(path)], check=True, capture_output=True, timeout=180, cwd=str(Path(soffice).resolve().parent), env=office_process_env(soffice), **office_process_kwargs())
        docx_path = temp_dir / f"{path.stem}.docx"
    document = Document(str(docx_path))
    result: list[str] = []
    for para in document.paragraphs:
        result.append(para.text or "")
    for table in document.tables:
        for row in table.rows:
            result.append(" | ".join(cell.text.replace("\n", " ") for cell in row.cells))
    return "\n".join(result)


def pdf_text(path: Path) -> tuple[str, fitz.Document]:
    doc = fitz.open(str(path))
    pages: list[str] = []
    for page in doc:
        text = page.get_text("text") or ""
        pages.append(text.strip())
    return "\n\n".join(pages), doc


def pdf_page_texts(pdf: fitz.Document) -> list[str]:
    return [clean_extracted_text((page.get_text("text") or "").strip()) for page in pdf]


def page_offsets(page_texts: list[str]) -> list[tuple[int, int]]:
    offsets: list[tuple[int, int]] = []
    cursor = 0
    for index, page_text in enumerate(page_texts):
        start = cursor
        cursor += len(page_text)
        offsets.append((start, cursor))
        if index < len(page_texts) - 1:
            cursor += 2
    return offsets


def clean_extracted_text(value: str) -> str:
    lines = [
        line
        for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if not PAGE_NUMBER_LINE.fullmatch(line)
    ]
    return "\n".join(lines)


def ocr_text(path: Path) -> str:
    """OCR image/PDF pages when the source has no text layer."""
    try:
        import pytesseract
        import cv2
        import numpy as np
        from PIL import Image
        tesseract_command = os.getenv("TESSERACT_CMD")
        if tesseract_command:
            pytesseract.pytesseract.tesseract_cmd = tesseract_command
    except ImportError:
        return ""
    try:
        doc = fitz.open(str(path))
        pages: list[str] = []
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            grayscale = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
            image = Image.fromarray(cv2.threshold(grayscale, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1])
            pages.append(pytesseract.image_to_string(image, lang="chi_sim+eng"))
        doc.close()
        return "\n\n".join(pages)
    except Exception:
        return ""


def source_text(path: Path, rendered_pdf: Path) -> str:
    extension = path.suffix.lower()
    if extension in {".doc", ".docx"}:
        # Compare Word documents from their paragraphs/tables.  The PDF
        # rendering is only a visual preview and introduces layout-only
        # line breaks, headers and page numbers that can collapse a diff.
        text = office_text(path)
        if text.strip():
            return text
    text, _ = pdf_text(rendered_pdf)
    if text.strip():
        return clean_extracted_text(text)
    return clean_extracted_text(ocr_text(rendered_pdf))


def parse_case_records(text: str) -> list[dict[str, str]]:
    """Parse the LegalNewsAlerts case.txt block format into display records."""
    records: list[dict[str, str]] = []
    for block in re.split(r"\n\s*\n+", text.replace("\r\n", "\n")):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        joined = "\n".join(lines)
        source_match = re.search(r"^来源[：:]\s*(.*?)(?:[｜|]\s*日期[：:]|$)", joined, re.MULTILINE)
        date_match = re.search(r"(?:^|[｜|]\s*)日期[：:]\s*([^\n｜|]+)", joined, re.MULTILINE)
        link_match = re.search(r"^链接[：:]\s*(https?://\S+)", joined, re.MULTILINE | re.IGNORECASE)
        summary_match = re.search(r"^摘要[：:]\s*(.+)", joined, re.MULTILINE)
        body = [line for line in lines[1:] if not re.match(r"^(来源|日期|链接|摘要)[：:]", line)]
        records.append({
            "title": lines[0],
            "source": source_match.group(1).strip() if source_match else "",
            "date": date_match.group(1).strip() if date_match else "",
            "link": link_match.group(1).rstrip("。）]}") if link_match else "",
            "summary": summary_match.group(1).strip() if summary_match else "",
            "raw": " ".join(body),
        })
    return records


def parse_case_csv(data: bytes) -> list[dict[str, str]]:
    """Parse Law-Push UTF-8 CSV files using the five exported columns."""
    try:
        decoded = data.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(decoded, newline=""), strict=True)
        required = {"标题", "来源", "日期", "链接"}
        if not required.issubset(reader.fieldnames or set()):
            raise ValueError("CSV必须包含：标题、来源、日期、链接")
        records = []
        for row in reader:
            title = (row.get("标题") or "").strip()
            if not title:
                continue
            records.append({"title": title, "source": (row.get("来源") or "").strip(),
                            "date": (row.get("日期") or "").strip(),
                            "link": (row.get("链接") or "").strip(),
                            "file_date": (row.get("文件日期") or "").strip(),
                            "summary": (row.get("摘要") or "").strip(), "raw": ""})
        return records
    except (UnicodeDecodeError, csv.Error, ValueError) as exc:
        raise ValueError(f"CSV解析失败: {exc}") from exc


def _load_case_catalog() -> list[dict[str, Any]]:
    if not CASE_CATALOG_PATH.is_file():
        return []
    try:
        payload = json.loads(CASE_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(500, "案例库索引文件无法读取") from exc
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise HTTPException(500, "案例库索引文件格式无效")
    return payload


def _write_case_catalog(records: list[dict[str, Any]]) -> None:
    CASE_STORE.mkdir(parents=True, exist_ok=True)
    temporary_path = CASE_CATALOG_PATH.with_name(f".{CASE_CATALOG_PATH.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary_path.replace(CASE_CATALOG_PATH)
    finally:
        temporary_path.unlink(missing_ok=True)


def _upsert_case_record(record: dict[str, Any]) -> None:
    records = _load_case_catalog()
    for index, current in enumerate(records):
        if current.get("id") == record["id"]:
            records[index] = record
            break
    else:
        records.insert(0, record)
    _write_case_catalog(records)


def _case_response(record: dict[str, Any]) -> dict[str, Any]:
    storage_status = record.get("storage_status")
    if not storage_status:
        storage_status = "stored" if record.get("kingdee_download_url") else "failed"
    return {
        "id": record["id"],
        "name": record["name"],
        "extension": record.get("extension", ""),
        "items": record.get("items", []),
        "uploaded_at": record["uploaded_at"],
        "storage_status": storage_status,
        "storage_error": record.get("storage_error") or record.get("sync_error", ""),
        "kingdee_storage_path": record.get("kingdee_storage_path", ""),
        "kingdee_download_url": record.get("kingdee_download_url", ""),
        "database_count": record.get("database_count", 0),
        "knowledge_base_count": record.get("knowledge_base_count", 0),
        "pending_count": record.get("pending_count", 0),
        "failed_count": record.get("failed_count", 0),
        "sync_error": record.get("sync_error", ""),
    }


def _find_case_record(case_id: str) -> dict[str, Any]:
    for record in _load_case_catalog():
        if record.get("id") == case_id:
            return record
    raise HTTPException(404, "案例文件不存在")


def _case_source_path(record: dict[str, Any]) -> Path:
    extension = str(record.get("extension", "")).lower()
    if extension not in CASE_ALLOWED:
        raise HTTPException(500, "案例文件扩展名无效")
    return CASE_STORE / str(record["id"]) / f"source{extension}"


def _extract_case_text(source: Path, extension: str, file_bytes: bytes | None = None) -> str:
    if extension == ".txt":
        contents = file_bytes if file_bytes is not None else source.read_bytes()
        return contents.decode("utf-8-sig", errors="replace")
    if extension in {".doc", ".docx"}:
        return office_text(source)
    text, pdf = pdf_text(source)
    pdf.close()
    return text


def _case_content_type(extension: str) -> str:
    return {
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".csv": "text/csv",
    }.get(extension, "application/octet-stream")


async def _store_case_record_in_kingdee(
    record: dict[str, Any], file_bytes: bytes, content_type: str
) -> dict[str, Any]:
    storage_path, download_url = await _store_case_in_kingdee(
        str(record["id"]),
        str(record["name"]),
        content_type,
        file_bytes,
    )
    record["storage_status"] = "stored"
    record["storage_error"] = ""
    record["kingdee_storage_path"] = storage_path
    record["kingdee_download_url"] = download_url
    _upsert_case_record(record)
    return record


def diff_opcodes(old_text: str, new_text: str) -> list[tuple[str, int, int, int, int]]:
    """Prefer diff-match-patch when installed, with a robust stdlib fallback."""
    try:
        from diff_match_patch import diff_match_patch
    except ImportError:
        return difflib.SequenceMatcher(None, old_text, new_text, autojunk=False).get_opcodes()
    engine = diff_match_patch()
    diffs = engine.diff_main(old_text, new_text, checklines=False)
    engine.diff_cleanupSemantic(diffs)
    opcodes: list[tuple[str, int, int, int, int]] = []
    old_pos = new_pos = 0
    index = 0
    while index < len(diffs):
        operation, value = diffs[index]
        if operation == 0:
            opcodes.append(("equal", old_pos, old_pos + len(value), new_pos, new_pos + len(value)))
            old_pos += len(value); new_pos += len(value); index += 1; continue
        old_start, new_start = old_pos, new_pos
        if operation == -1:
            old_pos += len(value)
            index += 1
            if index < len(diffs) and diffs[index][0] == 1:
                new_pos += len(diffs[index][1]); index += 1
            opcodes.append(("replace" if new_pos > new_start else "delete", old_start, old_pos, new_start, new_pos))
        else:
            new_pos += len(value); index += 1
            opcodes.append(("insert", old_start, old_pos, new_start, new_pos))
    return opcodes


def _split_contract_line(content: str, start: int, end: int) -> list[tuple[str, int, int]]:
    """Split a physical extraction line into contract clauses when possible."""
    if PAGE_NUMBER_LINE.fullmatch(content):
        return []
    boundaries = [match.start() for match in CLAUSE_BOUNDARY.finditer(content)]
    boundaries = sorted(
        {boundary for boundary in boundaries if boundary == 0 or content[:boundary].strip()}
    )
    if not boundaries:
        return [(content, start, end)]
    if boundaries[0] != 0:
        boundaries.insert(0, 0)
    boundaries.append(len(content))
    segments: list[tuple[str, int, int]] = []
    for index in range(len(boundaries) - 1):
        segment_start, segment_end = boundaries[index], boundaries[index + 1]
        segment = content[segment_start:segment_end]
        if segment.strip():
            segments.append((segment, start + segment_start, start + segment_end))
    return segments


def block_anchor(value: str) -> str:
    match = CLAUSE_HEADING.match(value)
    if not match:
        return ""
    return normalize_for_match(match.group(0))


def text_blocks(value: str, ignore_case: bool = False) -> list[TextBlock]:
    """Return logical text blocks for content diff; Run/Span/Page never participate."""
    raw_blocks: list[tuple[str, int, int, bool, str]] = []
    cursor = 0
    for raw_line in value.splitlines(keepends=True):
        start, end = cursor, cursor + len(raw_line)
        cursor = end
        content = raw_line.rstrip("\r\n")
        for segment, segment_start, segment_end in _split_contract_line(content, start, end):
            match_text = normalize_for_match(segment, ignore_case)
            if not match_text:
                continue
            anchor = block_anchor(segment.lstrip())
            raw_blocks.append((segment, segment_start, segment_end, bool(anchor), anchor))
    if cursor < len(value):
        content = value[cursor:]
        for segment, segment_start, segment_end in _split_contract_line(content, cursor, len(value)):
            match_text = normalize_for_match(segment, ignore_case)
            if not match_text:
                continue
            anchor = block_anchor(segment.lstrip())
            raw_blocks.append((segment, segment_start, segment_end, bool(anchor), anchor))

    merged: list[tuple[str, int, int, str]] = []
    for raw_text, start, end, starts_clause, anchor in raw_blocks:
        previous_text = merged[-1][0].strip() if merged else ""
        should_merge_prefix = previous_text == "第" or bool(re.fullmatch(r"第?\d+", previous_text))
        if merged and not starts_clause and (merged[-1][3] or should_merge_prefix):
            previous_text, previous_start, _, previous_anchor = merged[-1]
            separator = "\n" if previous_text and raw_text else ""
            combined_text = f"{previous_text}{separator}{raw_text}"
            merged[-1] = (
                combined_text,
                previous_start,
                end,
                previous_anchor or block_anchor(combined_text.lstrip()),
            )
        else:
            merged.append((raw_text, start, end, anchor))

    blocks: list[TextBlock] = []
    for order, (raw_text, start, end, anchor) in enumerate(merged):
        match_text = normalize_for_match(raw_text, ignore_case)
        if match_text:
            blocks.append(TextBlock(raw_text, match_text, start, end, order, anchor))
    return blocks


def text_lines(value: str, ignore_whitespace: bool, ignore_case: bool) -> list[tuple[str, int, int]]:
    """Return comparable non-empty contract text blocks with their source offsets."""
    if ignore_whitespace:
        return [(block.match_text, block.start, block.end) for block in text_blocks(value, ignore_case)]
    raw_lines: list[tuple[str, int, int, bool]] = []
    cursor = 0
    for raw_line in value.splitlines(keepends=True):
        start, end = cursor, cursor + len(raw_line)
        cursor = end
        content = raw_line.rstrip("\r\n")
        for segment, segment_start, segment_end in _split_contract_line(content, start, end):
            normalized = normalize(segment, ignore_whitespace, ignore_case)
            if normalized:
                raw_lines.append(
                    (normalized, segment_start, segment_end, bool(CLAUSE_HEADING.match(segment)))
                )
    if cursor < len(value):
        content = value[cursor:]
        for segment, segment_start, segment_end in _split_contract_line(content, cursor, len(value)):
            normalized = normalize(segment, ignore_whitespace, ignore_case)
            if normalized:
                raw_lines.append(
                    (normalized, segment_start, segment_end, bool(CLAUSE_HEADING.match(segment)))
                )

    lines: list[tuple[str, int, int]] = []
    for normalized, start, end, starts_clause in raw_lines:
        previous_text = value[lines[-1][1] : lines[-1][2]].lstrip() if lines else ""
        if lines and not starts_clause and CLAUSE_HEADING.match(previous_text):
            previous_normalized, previous_start, _ = lines[-1]
            lines[-1] = (previous_normalized + normalized, previous_start, end)
        else:
            lines.append((normalized, start, end))
    return lines


def line_chunks(lines: list[tuple[str, int, int]], start: int, end: int) -> list[tuple[int, int]]:
    """Keep each displayed difference short enough to be useful in the UI."""
    chunks: list[tuple[int, int]] = []
    index = start
    while index < end:
        chunk_start, size = index, 0
        while index < end:
            line_size = lines[index][2] - lines[index][1]
            if index > chunk_start and (
                index - chunk_start >= DIFF_LINES_PER_BLOCK
                or size + line_size > DIFF_CHARS_PER_BLOCK
            ):
                break
            size += line_size
            index += 1
        chunks.append((lines[chunk_start][1], lines[index - 1][2]))
    return chunks


def source_range(
    source_map: list[int], start: int, end: int, source_length: int
) -> tuple[int, int]:
    """Map a normalized range back to the original extracted text."""
    source_start = source_map[start] if start < len(source_map) else source_length
    source_end = source_map[end - 1] + 1 if end > start else source_start
    return source_start, source_end


def character_diff_spans(
    old_text: str,
    new_text: str,
    old_base: int,
    new_base: int,
    ignore_whitespace: bool,
    ignore_case: bool,
) -> list[tuple[str, int, int, int, int]]:
    """Produce word/character-level differences inside an aligned text block."""
    old_normalized, old_map = normalize_with_map(old_text, ignore_whitespace, ignore_case)
    new_normalized, new_map = normalize_with_map(new_text, ignore_whitespace, ignore_case)
    spans: list[tuple[str, int, int, int, int]] = []
    for tag, old_start, old_end, new_start, new_end in diff_opcodes(old_normalized, new_normalized):
        if tag == "equal":
            continue
        if tag == "insert":
            while (
                new_end < len(new_normalized)
                and old_start < len(old_normalized)
                and new_normalized[new_start : new_start + 1]
                == old_normalized[old_start : old_start + 1]
            ):
                new_start += 1
                new_end += 1
        elif tag == "delete":
            while (
                old_end < len(old_normalized)
                and new_start < len(new_normalized)
                and old_normalized[old_start : old_start + 1]
                == new_normalized[new_start : new_start + 1]
            ):
                old_start += 1
                old_end += 1
        old_range = source_range(old_map, old_start, old_end, len(old_text))
        new_range = source_range(new_map, new_start, new_end, len(new_text))
        spans.append(
            (
                tag,
                old_base + old_range[0],
                old_base + old_range[1],
                new_base + new_range[0],
                new_base + new_range[1],
            )
        )
    return spans


def line_level_character_spans(
    old_text: str,
    new_text: str,
    old_base: int,
    new_base: int,
    ignore_whitespace: bool,
    ignore_case: bool,
) -> list[tuple[str, int, int, int, int]]:
    """Split a large unmatched block by line before applying a character diff."""
    old_lines = text_lines(old_text, ignore_whitespace, ignore_case)
    new_lines = text_lines(new_text, ignore_whitespace, ignore_case)
    spans: list[tuple[str, int, int, int, int]] = []
    for index in range(max(len(old_lines), len(new_lines))):
        old_line = old_lines[index] if index < len(old_lines) else None
        new_line = new_lines[index] if index < len(new_lines) else None
        if old_line and new_line:
            spans.extend(
                character_diff_spans(
                    old_text[old_line[1] : old_line[2]],
                    new_text[new_line[1] : new_line[2]],
                    old_base + old_line[1],
                    new_base + new_line[1],
                    ignore_whitespace,
                    ignore_case,
                )
            )
        elif old_line:
            spans.append(
                (
                    "delete",
                    old_base + old_line[1],
                    old_base + old_line[2],
                    new_base + len(new_text),
                    new_base + len(new_text),
                )
            )
        elif new_line:
            spans.append(
                (
                    "insert",
                    old_base + len(old_text),
                    old_base + len(old_text),
                    new_base + new_line[1],
                    new_base + new_line[2],
                )
            )
    return spans


def block_similarity(left: TextBlock, right: TextBlock) -> float:
    if left.match_text == right.match_text:
        return 1.0
    similarity = difflib.SequenceMatcher(None, left.match_text, right.match_text, autojunk=False).ratio()
    if left.anchor and left.anchor == right.anchor:
        return max(similarity, 0.72)
    if left.anchor and right.anchor and left.anchor != right.anchor:
        return min(similarity, 0.35)
    return similarity


def align_block_sequence(
    old_blocks: list[TextBlock], new_blocks: list[TextBlock]
) -> list[tuple[TextBlock | None, TextBlock | None]]:
    old_count, new_count = len(old_blocks), len(new_blocks)
    scores = [[0.0] * (new_count + 1) for _ in range(old_count + 1)]
    choices = [[""] * (new_count + 1) for _ in range(old_count + 1)]
    gap_penalty = 0.08

    for old_index in range(1, old_count + 1):
        scores[old_index][0] = scores[old_index - 1][0] - gap_penalty
        choices[old_index][0] = "delete"
    for new_index in range(1, new_count + 1):
        scores[0][new_index] = scores[0][new_index - 1] - gap_penalty
        choices[0][new_index] = "insert"

    for old_index, old_block in enumerate(old_blocks, 1):
        for new_index, new_block in enumerate(new_blocks, 1):
            similarity = block_similarity(old_block, new_block)
            if similarity >= BLOCK_MATCH_THRESHOLD:
                match_score = scores[old_index - 1][new_index - 1] + similarity
            else:
                match_score = float("-inf")
            delete_score = scores[old_index - 1][new_index] - gap_penalty
            insert_score = scores[old_index][new_index - 1] - gap_penalty
            best_score = max(match_score, delete_score, insert_score)
            scores[old_index][new_index] = best_score
            if best_score == match_score:
                choices[old_index][new_index] = "match"
            elif best_score == delete_score:
                choices[old_index][new_index] = "delete"
            else:
                choices[old_index][new_index] = "insert"

    aligned: list[tuple[TextBlock | None, TextBlock | None]] = []
    old_index, new_index = old_count, new_count
    while old_index or new_index:
        choice = choices[old_index][new_index]
        if choice == "match":
            aligned.append((old_blocks[old_index - 1], new_blocks[new_index - 1]))
            old_index -= 1
            new_index -= 1
        elif choice == "delete" or new_index == 0:
            aligned.append((old_blocks[old_index - 1], None))
            old_index -= 1
        else:
            aligned.append((None, new_blocks[new_index - 1]))
            new_index -= 1
    aligned.reverse()
    return aligned


def align_blocks(
    old_blocks: list[TextBlock], new_blocks: list[TextBlock]
) -> list[tuple[TextBlock | None, TextBlock | None]]:
    """Align logical blocks with DP; moved exact text is rescued when emitting diffs."""
    return align_block_sequence(old_blocks, new_blocks)


def line_diff_spans(
    old_text: str, new_text: str, ignore_whitespace: bool, ignore_case: bool
) -> list[tuple[str, int, int, int, int]]:
    """Compare logical text content only and return INSERT/DELETE/MODIFY spans."""
    old_blocks = text_blocks(old_text, ignore_case)
    new_blocks = text_blocks(new_text, ignore_case)
    aligned_blocks = align_blocks(old_blocks, new_blocks)
    deleted_exact = {
        old_block.match_text
        for old_block, new_block in aligned_blocks
        if old_block and not new_block
    }
    inserted_exact = {
        new_block.match_text
        for old_block, new_block in aligned_blocks
        if new_block and not old_block
    }
    moved_same = deleted_exact & inserted_exact
    spans: list[tuple[str, int, int, int, int]] = []
    for old_block, new_block in aligned_blocks:
        if old_block and new_block and old_block.match_text == new_block.match_text:
            continue
        if old_block and not new_block and old_block.match_text in moved_same:
            continue
        if new_block and not old_block and new_block.match_text in moved_same:
            continue
        if old_block and new_block:
            character_spans = character_diff_spans(
                old_block.raw_text,
                new_block.raw_text,
                old_block.start,
                new_block.start,
                ignore_whitespace,
                ignore_case,
            )
            if (
                len(character_spans) == 1
                and character_spans[0][0] == "replace"
                and max(
                    character_spans[0][2] - character_spans[0][1],
                    character_spans[0][4] - character_spans[0][3],
                )
                > ATOMIC_REPLACE_CHARS
            ):
                spans.extend(
                    line_level_character_spans(
                        old_block.raw_text,
                        new_block.raw_text,
                        old_block.start,
                        new_block.start,
                        ignore_whitespace,
                        ignore_case,
                    )
                )
            else:
                spans.extend(character_spans)
        elif old_block:
            spans.append(("delete", old_block.start, old_block.end, len(new_text), len(new_text)))
        elif new_block:
            spans.append(
                ("insert", len(old_text), len(old_text), new_block.start, new_block.end)
            )
    return spans


def line_similarity(old_text: str, new_text: str, ignore_whitespace: bool, ignore_case: bool) -> float:
    old_lines = [line[0] for line in text_lines(old_text, ignore_whitespace, ignore_case)]
    new_lines = [line[0] for line in text_lines(new_text, ignore_whitespace, ignore_case)]
    return difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False).ratio()


def is_format_artifact(old_text: str, new_text: str) -> bool:
    """Ignore private-use font glyphs emitted by Word/PDF symbol fonts."""
    combined = old_text + new_text
    return any("\ue000" <= char <= "\uf8ff" for char in combined)


def context_queries(source: str, start: int, end: int) -> list[str]:
    left, right = max(0, start - 36), min(len(source), max(end, start) + 36)
    exact = source[start:end].strip()
    context = source[left:right].strip()
    queries: list[str] = []
    if context and len(normalize_for_match(context)) >= 8:
        queries.append(context)
    if exact and len(normalize_for_match(exact)) >= 4:
        queries.append(exact)
    if exact and len(normalize_for_match(exact)) < 4 and not queries:
        wider_left, wider_right = max(0, start - 80), min(len(source), max(end, start) + 80)
        wider = source[wider_left:wider_right].strip()
        if wider:
            queries.append(wider)
    return queries


def fit_rects(rects: list[fitz.Rect]) -> dict[str, float] | None:
    if not rects:
        return None
    first = rects[0]
    same_line = [rect for rect in rects if abs(rect.y0 - first.y0) < 3]
    if same_line:
        return {
            "x0": min(rect.x0 for rect in same_line),
            "y0": min(rect.y0 for rect in same_line),
            "x1": max(rect.x1 for rect in same_line),
            "y1": max(rect.y1 for rect in same_line),
        }
    return {"x0": first.x0, "y0": first.y0, "x1": first.x1, "y1": first.y1}


def search_variants(query: str) -> list[str]:
    query = WS.sub(" ", query).strip()
    if not query:
        return []
    variants: list[str] = []
    if len(normalize_for_match(query)) >= 4:
        variants.append(query[:160])
    parts = [part.strip(" ，,。；;：:（）()") for part in re.split(r"[，,。；;：:\n]+", query)]
    variants.extend(part[:120] for part in parts if len(normalize_for_match(part)) >= 8)
    result: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        if variant and variant not in seen:
            seen.add(variant)
            result.append(variant)
    return result


def locate(
    pdf: fitz.Document, page_hint: int, queries: list[str], nearby_pages: int | None = None
) -> tuple[int, dict[str, float] | None]:
    page_hint = max(1, min(pdf.page_count, page_hint))
    nearby = [
        page
        for page in range(max(1, page_hint - (nearby_pages or 0)), min(pdf.page_count, page_hint + (nearby_pages or 0)) + 1)
    ]
    order = [page_hint] + [page for page in nearby if page != page_hint]
    if nearby_pages is None:
        order.extend(page for page in range(1, pdf.page_count + 1) if page not in order)
    for query in queries:
        variants = search_variants(query)
        for page_no in order:
            for variant in variants:
                rects = pdf[page_no - 1].search_for(variant)
                if rects:
                    return page_no, fit_rects(rects)
    if nearby_pages is not None:
        return locate(pdf, page_hint, queries, nearby_pages=None)
    return page_hint, None


def page_hint_for_offset(source: str, offset: int, page_count: int) -> int:
    """Estimate a preview page from a source-text offset when layouts differ."""
    if page_count <= 1 or not source:
        return 1
    ratio = max(0.0, min(1.0, offset / len(source)))
    return max(1, min(page_count, round(ratio * (page_count - 1)) + 1))


def page_hint_for_offsets(
    source: str, offset: int, page_count: int, offsets: list[tuple[int, int]] | None = None
) -> int:
    if offsets:
        for index, (start, end) in enumerate(offsets, 1):
            if start <= offset <= end:
                return index
    return page_hint_for_offset(source, offset, page_count)


def review_queries(report: str) -> list[str]:
    """Extract likely verbatim contract fragments from an AI report."""
    candidates: list[str] = []
    for pattern in (r"[\u201c\"]([^\u201d\"]{6,160})[\u201d\"]", r"第[一二三四五六七八九十百零〇0-9]+条(?:第[一二三四五六七八九十百零〇0-9]+款)?"):
        candidates.extend(match.group(1) if match.groups() else match.group(0) for match in re.finditer(pattern, report))
    for line in report.splitlines():
        plain = re.sub(r"[*`#>-]", "", line).strip()
        if any(label in plain for label in ("原条款内容", "原文引用", "原文", "条款内容")):
            value = re.split(r"[：:]", plain, maxsplit=1)[-1].strip()
            if len(value) >= 8:
                candidates.append(value[:160])
    result: list[str] = []
    seen: set[str] = set()
    for value in candidates:
        value = WS.sub(" ", value).strip(" 。；;:：,，")
        if len(value) < 3 or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def build_review_preview(source: Path, review_dir: Path, report: str) -> tuple[dict, list[dict]]:
    rendered = convert_to_pdf(source, review_dir / "document.pdf")
    doc = fitz.open(str(rendered))
    pages: list[dict] = []
    for index, page in enumerate(doc, 1):
        pix = page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)
        image = review_dir / f"p{index}.png"
        pix.save(str(image))
        pages.append({"page": index, "url": f"/api/v1/review/{review_dir.name}/files/p{index}.png", "width_px": pix.width, "height_px": pix.height})
    raw, _ = pdf_text(rendered)
    if not raw.strip():
        raw = source_text(source, rendered)
    annotations: list[dict] = []
    used: set[tuple[int, int, int, int]] = set()
    for query in review_queries(report):
        page, box = locate(doc, 1, context_queries(raw, raw.find(query), raw.find(query) + len(query)) if query in raw else [query])
        if not box:
            continue
        key = (page, round(box["x0"]), round(box["y0"]), round(box["x1"]))
        if key in used:
            continue
        used.add(key)
        annotations.append({"annotation_id": len(annotations) + 1, "text": query, "kind": "suggestion", "page": page, "box": box})
    rect = doc[0].rect if doc.page_count else fitz.Rect(0, 0, 595, 842)
    preview = {"filename": source.name, "ext": source.suffix.lower().lstrip("."), "display_format": "pdf", "page_count": len(pages), "page_width_pt": rect.width, "page_height_pt": rect.height, "pages": pages, "text_extracted": bool(raw.strip()), "text_error": "" if raw.strip() else "原文未提取到文本"}
    doc.close()
    return preview, annotations


def word_preview_box(source: str, offset: int, length: int) -> tuple[int, dict[str, float]]:
    """Coordinates matching the fallback DOCX text-preview renderer."""
    chars_per_line, lines_per_page = 35, 42
    positions: dict[int, tuple[int, int, int]] = {}
    source_cursor = 0
    line_index = 0
    for paragraph_index, paragraph in enumerate(source.split("\n")):
        chunks = [paragraph[i : i + chars_per_line] for i in range(0, len(paragraph), chars_per_line)] or [""]
        for chunk in chunks:
            for column in range(len(chunk)):
                positions[source_cursor + column] = (line_index // lines_per_page + 1, line_index % lines_per_page, column)
            source_cursor += len(chunk)
            line_index += 1
        if paragraph_index < source.count("\n"):
            positions[source_cursor] = (line_index // lines_per_page + 1, line_index % lines_per_page, 0)
            source_cursor += 1
    start = positions.get(offset) or positions.get(max(0, offset - 1)) or (1, 0, 0)
    end_offset = max(offset, offset + length - 1)
    end = positions.get(end_offset) or start
    page, row, column = start
    x0 = 60 + column * 14
    y0 = 56 + row * 28.5
    if end[0] == page and end[1] == row:
        width = max(10, (end[2] - column + 1) * 14)
    else:
        width = max(10, (chars_per_line - column) * 14)
    return page, {"x0": x0, "y0": y0, "x1": min(860, x0 + width), "y1": y0 + 27}


def compare_files(old: Path, new: Path, compare_dir: Path, ignore_whitespace: bool, ignore_case: bool) -> dict:
    old_pdf, new_pdf = convert_to_pdf(old, compare_dir / "old.pdf"), convert_to_pdf(new, compare_dir / "new.pdf")
    old_doc, new_doc = fitz.open(str(old_pdf)), fitz.open(str(new_pdf))
    old_pages, new_pages = [], []
    for side, doc, source in (("old", old_doc, old_pdf), ("new", new_doc, new_pdf)):
        for i, page in enumerate(doc, 1):
            pix = page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)
            image = compare_dir / f"{side}_p{i}.png"
            pix.save(str(image))
            (old_pages if side == "old" else new_pages).append({"page": i, "url": f"/api/v1/compare/{compare_dir.name}/files/{side}_p{i}.png", "width_px": pix.width, "height_px": pix.height})
    old_pdf_text, _ = pdf_text(old_pdf)
    new_pdf_text, _ = pdf_text(new_pdf)
    old_raw = source_text(old, old_pdf)
    new_raw = source_text(new, new_pdf)
    old_synthetic_preview = not old_pdf_text.strip() and old.suffix.lower() in {".doc", ".docx"}
    new_synthetic_preview = not new_pdf_text.strip() and new.suffix.lower() in {".doc", ".docx"}
    spans = line_diff_spans(old_raw, new_raw, ignore_whitespace, ignore_case)
    annotations = []
    old_pdf, new_pdf = fitz.open(str(old_pdf)), fitz.open(str(new_pdf))
    old_pdf_offsets = page_offsets(pdf_page_texts(old_pdf)) if old.suffix.lower() == ".pdf" else None
    new_pdf_offsets = page_offsets(pdf_page_texts(new_pdf)) if new.suffix.lower() == ".pdf" else None
    for diff_id, (tag, old_start, old_end, new_start, new_end) in enumerate(spans, 1):
        old_text, new_text = old_raw[old_start:old_end], new_raw[new_start:new_end]
        old_normalized = normalize(old_text, ignore_whitespace, ignore_case)
        new_normalized = normalize(new_text, ignore_whitespace, ignore_case)
        if is_format_artifact(old_normalized, new_normalized):
            continue
        kind = "added" if tag == "insert" else "removed" if tag == "delete" else "modified"
        marks = []
        if old_text:
            page, box = (
                word_preview_box(old_raw, old_start, max(1, old_end - old_start))
                if old_synthetic_preview
                else locate(
                    old_pdf,
                    page_hint_for_offsets(old_raw, old_start, old_pdf.page_count, old_pdf_offsets),
                    context_queries(old_raw, old_start, old_end),
                    nearby_pages=3,
                )
            )
            marks.append({"side":"old","page":page,"box":box})
        if new_text:
            page, box = (
                word_preview_box(new_raw, new_start, max(1, new_end - new_start))
                if new_synthetic_preview
                else locate(
                    new_pdf,
                    page_hint_for_offsets(new_raw, new_start, new_pdf.page_count, new_pdf_offsets),
                    context_queries(new_raw, new_start, new_end),
                    nearby_pages=3,
                )
            )
            marks.append({"side":"new","page":page,"box":box})
        annotations.append({"diff_id":diff_id,"kind":kind,"old_text":old_text if tag != "insert" else "","new_text":new_text if tag != "delete" else "","page_marks":marks,"similarity":round(difflib.SequenceMatcher(None, old_normalized, new_normalized).ratio(),4) if kind == "modified" else None})
    old_pdf.close(); new_pdf.close()
    def preview(path: Path, pages: list[dict], doc: fitz.Document) -> dict:
        rect = doc[0].rect if doc.page_count else fitz.Rect(0, 0, 595, 842)
        return {"filename":path.name,"ext":path.suffix.lower().lstrip("."),"display_format":"pdf","page_count":len(pages),"page_width_pt":rect.width,"page_height_pt":rect.height,"pages":pages,"text_extracted":True,"text_error":""}
    response = {"compare_id":compare_dir.name,"old":preview(old,old_pages,old_doc),"new":preview(new,new_pages,new_doc),"annotations":annotations,"added_count":sum(a["kind"]=="added" for a in annotations),"removed_count":sum(a["kind"]=="removed" for a in annotations),"modified_count":sum(a["kind"]=="modified" for a in annotations),"similarity":round(line_similarity(old_raw, new_raw, ignore_whitespace, ignore_case),4),"ignore_whitespace":ignore_whitespace,"ignore_case":ignore_case}
    old_doc.close(); new_doc.close()
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


@app.post("/api/v1/cases/parse")
async def case_parse_endpoint(file: Annotated[UploadFile, File(...)]) -> dict:
    filename = file.filename or "cases"
    extension = Path(filename).suffix.lower()
    if extension not in CASE_ALLOWED:
        raise HTTPException(400, "仅支持 DOC、DOCX、PDF、TXT、CSV 案例文件")
    file_bytes = await file.read()
    temp_dir = Path(tempfile.mkdtemp(prefix="case-parse-", dir=str(STORE)))
    source = temp_dir / f"source{extension}"
    try:
        source.write_bytes(file_bytes)
        if extension == ".csv":
            return {"filename": filename, "items": parse_case_csv(file_bytes), "text_extracted": True}
        if extension == ".txt":
            text = file_bytes.decode("utf-8-sig", errors="replace")
        elif extension in {".doc", ".docx"}:
            text = office_text(source)
        else:
            text, pdf = pdf_text(source)
            pdf.close()
        if not text.strip():
            raise HTTPException(422, "未能从案例文件提取文本")
        return {"filename": filename, "items": parse_case_records(text), "text_extracted": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"案例文件解析失败: {exc}") from exc
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.get("/api/v1/cases")
def list_cases_endpoint() -> dict[str, list[dict[str, Any]]]:
    return {"items": [_case_response(record) for record in _load_case_catalog()]}


@app.get("/api/v1/cases/database")
def list_database_cases_endpoint() -> dict[str, list[dict[str, Any]]]:
    """Return the case library directly from PostgreSQL."""
    try:
        items = list_database_cases({
            "host": CASE_DB_HOST,
            "port": CASE_DB_PORT,
            "dbname": CASE_DB_NAME,
            "user": CASE_DB_USER,
            "password": CASE_DB_PASSWORD,
            "schema": CASE_DB_SCHEMA,
            "table": CASE_DB_TABLE,
        })
    except (psycopg.Error, KeyError, ValueError) as exc:
        logger.error("Case database query failed: %s", type(exc).__name__)
        raise HTTPException(503, "案例数据库暂时不可用，请检查数据库配置和服务状态") from exc
    return {"items": items}


@app.post("/api/v1/cases")
async def create_case_endpoint(file: Annotated[UploadFile, File(...)], local_only: bool = Form(False)) -> dict[str, Any]:
    filename = Path(file.filename or "cases").name
    extension = Path(filename).suffix.lower()
    if extension not in CASE_ALLOWED:
        raise HTTPException(400, "仅支持 DOC、DOCX、PDF、TXT、CSV 案例文件")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(422, "案例文件不能为空")

    case_id = uuid.uuid4().hex
    record: dict[str, Any] = {
        "id": case_id,
        "name": filename,
        "extension": extension,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "items": [],
        "storage_status": "pending",
        "storage_error": "",
        "kingdee_storage_path": "",
        "kingdee_download_url": "",
    }
    CASE_STORE.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(
        tempfile.mkdtemp(prefix="contract-review-case-", dir=str(CASE_STORE))
    )
    source = temp_dir / f"source{extension}"
    try:
        source.write_bytes(file_bytes)
        try:
            if extension == ".csv":
                record["items"] = parse_case_csv(file_bytes)
                text = ""
            else:
                text = _extract_case_text(source, extension, file_bytes)
            if text.strip():
                record["items"] = parse_case_records(text)
            else:
                logger.warning("Case file has no extractable text: %s", filename)
        except Exception as exc:
            raise HTTPException(422, f"Case file parse failed: {exc}") from exc

        if not record["items"]:
            raise HTTPException(422, "未识别到可同步的案例条目")
        if local_only:
            destination = _case_source_path(record)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(file_bytes)
            record["storage_status"] = "local"
            _upsert_case_record(record)
            return _case_response(record)

        record = await _store_case_record_in_kingdee(
            record,
            file_bytes,
            file.content_type or _case_content_type(extension),
        )
        return _case_response(record)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"案例文件处理失败: {exc}") from exc
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/api/v1/cases/{case_id}/sync-database")
async def synchronize_case_database_endpoint(case_id: str) -> dict[str, Any]:
    """Import the displayed cases into PostgreSQL and then index them in Dify."""
    record = _find_case_record(case_id)
    items = record.get("items", [])
    if not items:
        raise HTTPException(422, "该文件没有可同步的案例")
    try:
        outcome = await run_in_threadpool(sync_case_items, items,
            {"host": CASE_DB_HOST, "port": CASE_DB_PORT, "dbname": CASE_DB_NAME,
             "user": CASE_DB_USER, "password": CASE_DB_PASSWORD,
             "schema": CASE_DB_SCHEMA, "table": CASE_DB_TABLE},
            {"base": DIFY_BASE_URL, "key": CASE_KB_API_KEY, "name": CASE_KB_NAME,
             "dataset_id": CASE_KB_DATASET_ID}, CASE_STORE / "sync-state")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        logger.error("Case database sync failed: %s", type(exc).__name__)
        raise HTTPException(502, "数据库同步失败，请检查连接、表名和字段长度约束；未进行知识库写入") from exc
    record.update(outcome)
    _upsert_case_record(record)
    return _case_response(record)


@app.post("/api/v1/cases/{case_id}/sync")
async def synchronize_case_endpoint(case_id: str) -> dict[str, Any]:
    """Retry storage for legacy case records that still have a local source file."""
    record = _find_case_record(case_id)
    if record.get("kingdee_download_url"):
        return _case_response(record)

    source = _case_source_path(record)
    if not source.is_file():
        raise HTTPException(409, "案例原始文件不存在，无法存储至金蝶，请重新上传")
    try:
        updated = await _store_case_record_in_kingdee(
            record,
            source.read_bytes(),
            _case_content_type(str(record["extension"])),
        )
        shutil.rmtree(CASE_STORE / case_id, ignore_errors=True)
        return _case_response(updated)
    except HTTPException as exc:
        record["storage_status"] = "failed"
        record["storage_error"] = str(exc.detail)
        _upsert_case_record(record)
        raise


@app.get("/api/v1/cases/{case_id}/file")
def download_case_file_endpoint(case_id: str) -> Response:
    record = _find_case_record(case_id)
    download_url = str(record.get("kingdee_download_url", "")).strip()
    if download_url:
        return RedirectResponse(download_url, status_code=307)

    source = _case_source_path(record)
    if not source.is_file():
        raise HTTPException(404, "案例原始文件不存在")
    return FileResponse(source, filename=str(record["name"]))


@app.delete("/api/v1/cases/{case_id}", status_code=204)
def delete_case_endpoint(case_id: str) -> Response:
    _find_case_record(case_id)
    records = [item for item in _load_case_catalog() if item.get("id") != case_id]
    _write_case_catalog(records)
    # Keep the Kingdee attachment intact; this only removes the local case index.
    shutil.rmtree(CASE_STORE / case_id, ignore_errors=True)
    return Response(status_code=204)


@app.post("/api/v1/contract/type")
async def contract_type_endpoint(file: Annotated[UploadFile, File(...)]) -> dict[str, str]:
    filename = file.filename or "contract"
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED:
        raise HTTPException(400, "仅支持 DOC、DOCX、PDF、JPG、JPEG、PNG 文件")
    try:
        answer = await _dify_chat(
            filename,
            await file.read(),
            file.content_type or "application/octet-stream",
            DIFY_CONTRACT_TYPE_API_KEY,
            "请识别上传文档的合同类型。只返回合同类型名称，必要时补充一句判断依据。",
        )
        return {"contract_type": _contract_type(answer), "detail": answer, "app_id": DIFY_CONTRACT_TYPE_APP_ID}
    except httpx.HTTPStatusError as exc:
        detail = f"HTTP {exc.response.status_code}: {exc.response.text[:500] or 'empty response body'}"
        raise HTTPException(502, f"合同类型识别 Dify 调用失败: {detail}") from exc
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/v1/contract/review")
async def contract_review_endpoint(file: Annotated[UploadFile, File(...)], contract_type: Annotated[str, Form(...)]) -> dict:
    filename = file.filename or "contract"
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED:
        raise HTTPException(400, "仅支持 DOC、DOCX、PDF、JPG、JPEG、PNG 文件")
    confirmed_type = contract_type.strip()
    if not confirmed_type:
        raise HTTPException(422, "请先确认合同类型")
    try:
        file_bytes = await file.read()
        review_query = f"请对上传的合同进行智能审查。用户已确认合同类型为：{confirmed_type}。请以该类型作为审查范围和适用规则，指出合同风险、不合理或缺失条款，并给出可执行的修改建议；每个问题附上合同中的原文引用。"
        answer = await _dify_chat(
            filename,
            file_bytes,
            file.content_type or "application/octet-stream",
            DIFY_CONTRACT_REVIEW_API_KEY,
            review_query,
            {"contract_type": confirmed_type},
        )
        review_dir = REVIEW_STORE / uuid.uuid4().hex[:16]
        review_dir.mkdir(parents=True, exist_ok=True)
        source = review_dir / f"source{extension}"
        source.write_bytes(file_bytes)
        try:
            preview, annotations = build_review_preview(source, review_dir, answer)
            preview_error = ""
        except Exception as preview_exc:
            shutil.rmtree(review_dir, ignore_errors=True)
            preview, annotations, preview_error = None, [], str(preview_exc)
        return {"filename": filename, "contract_type": confirmed_type, "review": answer, "app_id": DIFY_CONTRACT_REVIEW_APP_ID, "review_id": review_dir.name if preview else "", "preview": preview, "annotations": annotations, "preview_error": preview_error}
    except httpx.HTTPStatusError as exc:
        detail = f"HTTP {exc.response.status_code}: {exc.response.text[:500] or 'empty response body'}"
        raise HTTPException(502, f"合同智审 Dify 调用失败: {detail}") from exc
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/v1/compare")
async def compare_endpoint(old_file: Annotated[UploadFile, File(...)], new_file: Annotated[UploadFile, File(...)], ignore_whitespace: bool = Form(True), ignore_case: bool = Form(False)):
    old_ext, new_ext = Path(old_file.filename or "").suffix.lower(), Path(new_file.filename or "").suffix.lower()
    if old_ext not in ALLOWED or new_ext not in ALLOWED:
        raise HTTPException(400, "仅支持 DOC、DOCX、PDF、JPG、PNG 文件")
    compare_dir = STORE / uuid.uuid4().hex[:16]; compare_dir.mkdir(parents=True)
    old_path, new_path = compare_dir / f"old{old_ext}", compare_dir / f"new{new_ext}"
    old_path.write_bytes(await old_file.read()); new_path.write_bytes(await new_file.read())
    try:
        result = compare_files_with_engine(
            old_path,
            new_path,
            compare_dir,
            ignore_whitespace,
            ignore_case,
        )
        return {"compare_id":compare_dir.name,"status":"completed","result":result}
    except Exception as exc:
        shutil.rmtree(compare_dir, ignore_errors=True)
        raise HTTPException(500, str(exc)) from exc


@app.get("/api/v1/compare/{compare_id}/files/{filename}")
def compare_file(compare_id: str, filename: str):
    path = (STORE / compare_id / filename).resolve()
    if not path.is_file() or path.parent != (STORE / compare_id).resolve():
        raise HTTPException(404, "文件不存在")
    return FileResponse(path)


@app.get("/api/v1/review/{review_id}/files/{filename}")
def review_file(review_id: str, filename: str):
    path = (REVIEW_STORE / review_id / filename).resolve()
    if not path.is_file() or path.parent != (REVIEW_STORE / review_id).resolve():
        raise HTTPException(404, "文件不存在")
    return FileResponse(path)
