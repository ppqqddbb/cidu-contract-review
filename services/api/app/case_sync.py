"""Import selected records, then synchronize the corresponding database rows."""
import hashlib
import json
import uuid
from contextlib import closing
from datetime import datetime

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .integrations.dify.case_dataset import CaseDataset


def connect(config):
    if not config.get("password"):
        raise ValueError("未配置 CASE_DB_PASSWORD，无法同步到数据库")
    return psycopg.connect(**{k: config[k] for k in ("host", "port", "dbname", "user", "password")},
                           connect_timeout=5, row_factory=dict_row)


def import_rows(db, table, items):
    # Existing Kingdee table has no fid default. Lock all writers during ID
    # allocation and de-duplication, then commit before contacting Dify.
    db.execute(sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(table))
    next_id = db.execute(sql.SQL("SELECT COALESCE(MAX(fid), 0) + 1 AS id FROM {}").format(table)).fetchone()["id"]
    rows, seen = [], set()
    for item in items:
        key = (item["title"].strip(), item.get("link", "").strip())
        if key in seen:
            continue
        seen.add(key)
        row = db.execute(sql.SQL("""SELECT fid, fk_r8p0_title AS title, fk_r8p0_source AS source,
            fk_r8p0_link AS link, fk_r8p0_date AS date, fk_r8p0_file_date AS file_date,
            fk_r8p0_summary AS summary, fk_r8p0_sync_kb AS sync_kb FROM {}
            WHERE fk_r8p0_title=%s AND fk_r8p0_link=%s ORDER BY fid LIMIT 1""").format(table), key).fetchone()
        if row is None:
            row = {**item, "fid": next_id, "title": key[0], "link": key[1], "sync_kb": "是"}
            db.execute(sql.SQL("""INSERT INTO {} (fid, fk_r8p0_title, fk_r8p0_source, fk_r8p0_link,
                fk_r8p0_date, fk_r8p0_file_date, fk_r8p0_summary, fk_r8p0_sync_kb)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'是')""").format(table),
                (next_id, key[0], row.get("source", ""), key[1], row.get("date") or None,
                 row.get("file_date") or None, row.get("summary", "")))
            next_id += 1
        rows.append(row)
    db.commit()
    return rows


def sync_case_items(items, db_config, kb_config, state_dir):
    for item in items:
        if not item.get("title", "").strip():
            raise ValueError("案例标题不能为空")
        for field in ("date", "file_date"):
            if item.get(field):
                datetime.fromisoformat(item[field])
    result = {"database_count": 0, "knowledge_base_count": 0, "pending_count": 0,
              "failed_count": 0, "sync_error": ""}
    scope = hashlib.sha256(json.dumps([db_config["host"], db_config["dbname"], db_config["schema"],
                                      db_config["table"], kb_config["base"], kb_config["name"],
                                      kb_config["dataset_id"]]).encode()).hexdigest()
    # Session advisory lock prevents concurrent synchronization through this API.
    with closing(connect(db_config)) as db:
        if not db.execute("SELECT pg_try_advisory_lock(%s) AS locked", (int(scope[:15], 16),)).fetchone()["locked"]:
            raise ValueError("已有同步正在执行，请稍后重试")
        table = sql.Identifier(db_config["schema"], db_config["table"])
        rows = import_rows(db, table, items)
        result["database_count"] = len(rows)
        result["knowledge_base_count"] = sum(row["sync_kb"].strip() == "否" for row in rows)
        pending = [row for row in rows if row["sync_kb"].strip() == "是"]
        if not pending:
            return result
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = state_dir / f"{scope}.json"
        states = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}

        def checkpoint(fid, value):
            states[str(fid)] = value
            temp = state_path.with_suffix(f".{uuid.uuid4().hex}.tmp")
            temp.write_text(json.dumps(states, ensure_ascii=False), encoding="utf-8")
            temp.replace(state_path)

        try:
            with closing(CaseDataset(**kb_config)) as client:
                dataset = client.resolve()
                for row in pending:
                    fid = row["fid"]
                    state = states.get(str(fid), {})
                    try:
                        if state.get("status") == "sending":
                            raise RuntimeError("上次写入结果待核实；请核对知识库后处理同步状态文件，未重复创建")
                        document_id = state.get("document_id")
                        if not document_id:
                            checkpoint(fid, {"status": "sending"})
                            document_id = client.create(dataset, row)
                            checkpoint(fid, {"status": "pending", "document_id": document_id})
                        status = client.status(dataset, document_id)
                        if status == "completed":
                            db.execute(sql.SQL("UPDATE {} SET fk_r8p0_sync_kb='否' WHERE fid=%s AND fk_r8p0_sync_kb='是'").format(table), (fid,))
                            db.commit()
                            result["knowledge_base_count"] += 1
                        elif status in ("error", "paused", "stopped"):
                            raise RuntimeError(f"知识库索引状态为 {status}，请在 Dify 处理后重试")
                        else:
                            result["pending_count"] += 1
                    except (RuntimeError, ValueError) as exc:
                        result["failed_count"] += 1
                        result["sync_error"] = f"案例 {fid}：{exc}"
        except (RuntimeError, ValueError) as exc:
            result["failed_count"] = len(pending)
            result["sync_error"] = str(exc)
    return result
