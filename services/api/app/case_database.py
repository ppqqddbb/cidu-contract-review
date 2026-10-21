"""Read case-library records from the Kingdee PostgreSQL table."""

from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


def _date_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "").strip()[:10]


def _timestamp_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "").strip().replace("T", " ")


def group_cases(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group database rows by the CSV generation date for the sidebar."""
    groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for row in rows:
        file_date = _timestamp_text(row.get("file_date"))
        group_id = file_date[:10] if file_date else "undated"
        group = groups.setdefault(
            group_id,
            {
                "id": group_id,
                "name": f"文件日期 {group_id}" if file_date else "未标注文件日期",
                "items": [],
            },
        )
        group["items"].append(
            {
                "id": str(row.get("fid", "")),
                "title": str(row.get("title") or ""),
                "source": str(row.get("source") or ""),
                "date": _date_text(row.get("date")),
                "link": str(row.get("link") or ""),
                "file_date": file_date,
                "summary": str(row.get("summary") or ""),
                "sync_kb": str(row.get("sync_kb") or ""),
                "raw": "",
            }
        )
    return list(groups.values())


def list_database_cases(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Query all cases without consulting the legacy upload catalog."""
    table = sql.Identifier(str(config["schema"]), str(config["table"]))
    query = sql.SQL(
        """SELECT fid, fk_r8p0_title AS title, fk_r8p0_source AS source,
        fk_r8p0_link AS link, fk_r8p0_date AS date,
        fk_r8p0_file_date AS file_date, fk_r8p0_summary AS summary,
        fk_r8p0_sync_kb AS sync_kb FROM {}
        ORDER BY fk_r8p0_file_date DESC NULLS LAST,
        fk_r8p0_date DESC NULLS LAST, fid DESC"""
    ).format(table)
    connection = psycopg.connect(
        host=config["host"],
        port=config["port"],
        dbname=config["dbname"],
        user=config["user"],
        password=config.get("password", ""),
        connect_timeout=5,
        row_factory=dict_row,
    )
    with connection:
        rows = connection.execute(query).fetchall()
    return group_cases(rows)
