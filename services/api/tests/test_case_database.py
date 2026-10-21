from datetime import datetime
from unittest.mock import Mock

import psycopg
from fastapi.testclient import TestClient

from services.api.app import main
from services.api.app.case_database import group_cases


def test_groups_preserve_bigint_and_full_file_timestamp():
    rows = [dict(fid=2564731451543126016, title='案例', source='法院', link='https://example.com',
                 date=datetime(2026, 9, 9), file_date=datetime(2026, 9, 10, 9, 20, 31),
                 summary='摘要', sync_kb='是'),
            dict(fid=2, title='历史案例', date=None, file_date=None)]
    groups = group_cases(rows)
    assert groups[0]['items'][0]['id'] == '2564731451543126016'
    assert groups[0]['items'][0]['file_date'] == '2026-09-10 09:20:31'
    assert groups[0]['items'][0]['date'] == '2026-09-09'
    assert groups[1]['items'][0]['title'] == '历史案例'


def test_database_listing_does_not_depend_on_uploaded_catalog(monkeypatch):
    query = Mock(side_effect=[[{'id': '2026-09-10', 'name': '文件日期 2026-09-10', 'items': [{'title': '数据库案例'}]}], []])
    monkeypatch.setattr(main, 'list_database_cases', query)
    monkeypatch.setattr(main, '_load_case_catalog', Mock(side_effect=AssertionError('must not use uploads')))
    with TestClient(main.app) as client:
        assert client.get('/api/v1/cases/database').json()['items'][0]['items'][0]['title'] == '数据库案例'
        assert client.get('/api/v1/cases/database').json()['items'] == []
    assert query.call_count == 2


def test_database_error_is_not_reported_as_empty_success(monkeypatch):
    monkeypatch.setattr(main, 'list_database_cases', Mock(side_effect=psycopg.OperationalError('offline')))
    with TestClient(main.app) as client:
        response = client.get('/api/v1/cases/database')
    assert response.status_code == 503
    assert '数据库' in response.json()['detail']
