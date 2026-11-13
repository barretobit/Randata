import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import cache, db, ingestion
from app.db import get_db
from app.main import app
from app.routers.finance import history_endpoints, security
from conftest import ADMIN_HEADERS, FakeSession, price_row


@pytest.fixture
def client():
    # No `with`: startup (catalog/cache load, scheduler) does not run.
    app.dependency_overrides[get_db] = lambda: FakeSession()
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def cached_gold(monkeypatch):
    history = [{"date": "2026-09-08", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1}]
    monkeypatch.setitem(cache._cache, "GC=F", history)
    return history


def test_cache_symbol_endpoint_serves_cached_history(client, cached_gold):
    response = client.get("/finance/cache/GC=F")
    assert response.status_code == 200
    assert response.json() == {"symbol": "GC=F", "count": 1, "history": cached_gold}


def test_cache_symbol_endpoint_answers_404_for_unknown_symbol(client):
    assert client.get("/finance/cache/UNKNOWN").status_code == 404


@pytest.mark.parametrize("headers", [{}, {"X-Admin-Key": "wrong"}])
def test_admin_endpoints_reject_missing_or_wrong_key(client, headers):
    assert client.get("/finance/admin/cache/details", headers=headers).status_code == 403


def test_admin_endpoints_accept_right_key(client):
    assert client.get("/finance/admin/cache/details", headers=ADMIN_HEADERS).status_code == 200


def test_admin_endpoints_are_disabled_without_configured_key(client, monkeypatch):
    monkeypatch.setattr(security, "ADMIN_KEY", None)
    assert client.get("/finance/admin/cache/details", headers=ADMIN_HEADERS).status_code == 503


def test_logs_require_admin_key(client):
    assert client.get("/finance/logs").status_code == 403
    assert client.get("/finance/logs", headers=ADMIN_HEADERS).status_code == 200


def test_bulk_job_answers_409_while_another_runs(client):
    with ingestion._exclusive_bulk_job("test job"):
        response = client.post("/finance/admin/backfill", headers=ADMIN_HEADERS)
    assert response.status_code == 409


def test_admin_routes_document_the_key_in_openapi():
    schema = app.openapi()
    assert "X-Admin-Key" in schema["components"]["securitySchemes"]
    assert schema["paths"]["/finance/admin/backfill"]["post"]["security"] == [{"X-Admin-Key": []}]
    assert "security" not in schema["paths"]["/finance/stocks"]["get"]


def test_history_all_streams_every_row(client, monkeypatch):
    rows = [
        price_row(date(2024, 1, day), 10.0 + day, symbol=symbol)
        for symbol in ("AAA", "BBB")
        for day in range(1, 6)
    ]
    session = FakeSession(reads=[rows])
    monkeypatch.setattr(db, "SessionLocal", lambda: session)
    monkeypatch.setattr(history_endpoints, "_STREAM_CHUNK_ROWS", 3)  # force several chunks

    response = client.get("/finance/history/all?limit=100")

    body = json.loads(response.content)
    assert response.status_code == 200
    assert body["count"] == 10
    assert body["from"] == "2024-01-01"
    assert body["to"] == "2024-01-05"
    assert body["data"][0] == {
        "symbol": "AAA", "date": "2024-01-01", "open": 11.0, "high": 11.0,
        "low": 11.0, "close": 11.0, "volume": 100,
    }


def test_history_all_with_no_rows_is_valid_json(client, monkeypatch):
    monkeypatch.setattr(db, "SessionLocal", lambda: FakeSession(reads=[[]]))
    body = client.get("/finance/history/all").json()
    assert body == {"data": [], "count": 0, "from": None, "to": None}


def test_all_logs_are_public(monkeypatch):
    from types import SimpleNamespace

    row = SimpleNamespace(
        id=1, recorded_at="2026-11-12 23:00:01", logger="ingestion", level="WARNING",
        message="Skipped price spike", symbol="NVDA", duration_ms=None, rows_written=None,
        success=0, exception=None,
    )
    app.dependency_overrides[get_db] = lambda: FakeSession(reads=[[row, row]])
    try:
        response = TestClient(app).get("/finance/logs/all")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert response.json()["logs"][0]["message"] == "Skipped price spike"


def test_old_logs_are_deleted_after_90_days():
    from app.logging_config import delete_old_logs

    session = FakeSession()
    delete_old_logs(session=session)
    assert session.deletes == [{"days": 90}]
    assert session.commits == 1
