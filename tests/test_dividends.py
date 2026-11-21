from collections import OrderedDict
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import db, dividend_repository, ingestion
from app.db import get_db
from app.main import app
from conftest import FakeSession, make_frame, random_walk


@pytest.fixture
def client():
    # No `with`: startup (catalog/cache load, scheduler) does not run.
    app.dependency_overrides[get_db] = lambda: FakeSession()
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def empty_response_store(monkeypatch):
    from app.routers.finance import responses

    monkeypatch.setattr(responses, "_compressed_responses", OrderedDict())


def frame_with_dividends(paid):
    """A 30-day frame whose "Dividends" column holds `paid` ({row index: amount}), zero elsewhere."""
    frame = make_frame(random_walk(30, 0.01))
    frame["Dividends"] = 0.0
    for index, amount in paid.items():
        frame.iloc[index, frame.columns.get_loc("Dividends")] = amount
    return frame


def test_store_frame_stores_the_dividends_next_to_the_bars(fake_session):
    frame = frame_with_dividends({10: 0.25, 20: 0.3})

    assert ingestion._store_frame("TEST", frame) == 30

    dividends = [write for write in fake_session.writes if "amount" in write]
    assert dividends == [
        {"symbol": "TEST", "date": frame.index[10].date(), "amount": 0.25},
        {"symbol": "TEST", "date": frame.index[20].date(), "amount": 0.3},
    ]


def test_a_dividend_failure_never_stops_the_bars(fake_session, monkeypatch):
    def broken_upsert(dividends):
        raise RuntimeError("Table 'dividends' doesn't exist")

    monkeypatch.setattr(dividend_repository, "upsert_dividends", broken_upsert)

    assert ingestion._store_frame("TEST", frame_with_dividends({5: 1.0})) == 30
    assert len(fake_session.writes) == 30


def test_frames_without_a_dividends_column_store_none(fake_session):
    ingestion._store_frame("TEST", make_frame(random_walk(30, 0.01)))
    assert not [write for write in fake_session.writes if "amount" in write]


def test_dividends_endpoint_returns_date_ascending_columns_per_symbol(client, monkeypatch, empty_response_store):
    rows = [
        SimpleNamespace(symbol="AAA", date=date(2024, 3, 1), amount=0.5),
        SimpleNamespace(symbol="AAA", date=date(2024, 9, 1), amount=0.55),
        SimpleNamespace(symbol="BBB", date=date(2025, 4, 22), amount=3.05),
    ]
    monkeypatch.setattr(db, "SessionLocal", lambda: FakeSession(reads=[rows]))

    body = client.get("/finance/dividends").json()

    assert body == {
        "count": 3,
        "symbols": {
            "AAA": {"date": ["2024-03-01", "2024-09-01"], "amount": [0.5, 0.55]},
            "BBB": {"date": ["2025-04-22"], "amount": [3.05]},
        },
    }


def test_dividends_endpoint_answers_503_when_the_table_is_missing(client, monkeypatch, empty_response_store):
    def missing_table(start_date):
        raise RuntimeError("Table 'dividends' doesn't exist")

    monkeypatch.setattr(dividend_repository, "get_dividends_since", missing_table)

    assert client.get("/finance/dividends").status_code == 503
