import gzip
import json

import pandas as pd
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app import catalog, config, yahoo
from app.db import get_db
from app.main import app
from app.routers.finance import responses
from conftest import ADMIN_HEADERS, FakeSession

# Every finance route that existed before the router split. None may disappear.
EXISTING_ROUTES = [
    ("GET", "/finance/admin/assets"),
    ("POST", "/finance/admin/assets"),
    ("POST", "/finance/admin/assets/backfill-inception-dates"),
    ("GET", "/finance/admin/assets/check"),
    ("POST", "/finance/admin/assets/onboard"),
    ("POST", "/finance/admin/assets/{symbol}/backfill"),
    ("POST", "/finance/admin/backfill"),
    ("POST", "/finance/admin/backfill-missing"),
    ("GET", "/finance/admin/backfill-symbol"),
    ("GET", "/finance/admin/cache/details"),
    ("POST", "/finance/admin/cache/refresh"),
    ("POST", "/finance/admin/ingest-daily"),
    ("GET", "/finance/assets"),
    ("GET", "/finance/cache/all"),
    ("GET", "/finance/cache/cryptos"),
    ("GET", "/finance/cache/etfs"),
    ("GET", "/finance/cache/indexes"),
    ("GET", "/finance/cache/metals"),
    ("GET", "/finance/cache/status"),
    ("GET", "/finance/cache/stocks"),
    ("GET", "/finance/cache/{symbol}"),
    ("GET", "/finance/crypto"),
    ("GET", "/finance/crypto/{symbol}"),
    ("GET", "/finance/crypto/{symbol}/history"),
    ("GET", "/finance/etfs"),
    ("GET", "/finance/etfs/{symbol}"),
    ("GET", "/finance/etfs/{symbol}/history"),
    ("GET", "/finance/fx/history/{pair}"),
    ("GET", "/finance/fx/rates"),
    ("GET", "/finance/fx/rates/{pair}"),
    ("GET", "/finance/history/all"),
    ("GET", "/finance/history/range"),
    ("GET", "/finance/indexes"),
    ("GET", "/finance/indexes/{symbol}"),
    ("GET", "/finance/indexes/{symbol}/history"),
    ("GET", "/finance/last-updated"),
    ("GET", "/finance/logs"),
    ("GET", "/finance/metals"),
    ("GET", "/finance/metals/{metal}"),
    ("GET", "/finance/metals/{metal}/history"),
    ("GET", "/finance/stocks"),
    ("GET", "/finance/stocks/{symbol}"),
    ("GET", "/finance/stocks/{symbol}/history"),
    ("GET", "/finance/symbol/{symbol}"),
    ("GET", "/finance/symbol/{symbol}/history"),
]


def registered_routes():
    schema = app.openapi()
    return {
        (method.upper(), path): operation
        for path, operations in schema["paths"].items()
        for method, operation in operations.items()
    }


def test_every_existing_route_is_still_registered():
    routes = registered_routes()
    assert [route for route in EXISTING_ROUTES if route not in routes] == []


def test_new_routes_exist_and_old_spellings_are_deprecated():
    routes = registered_routes()
    assert not routes[("GET", "/finance/fx/rates/{pair}/history")].get("deprecated")
    assert routes[("GET", "/finance/fx/history/{pair}")]["deprecated"] is True
    assert not routes[("POST", "/finance/admin/backfill-symbol")].get("deprecated")
    assert routes[("GET", "/finance/admin/backfill-symbol")]["deprecated"] is True


def test_every_admin_route_requires_the_key():
    for (method, path), operation in registered_routes().items():
        if "/finance/admin/" in path or path == "/finance/logs":
            assert operation.get("security") == [{"X-Admin-Key": []}], (method, path)


@pytest.fixture
def client_with_catalog(monkeypatch):
    catalog._build_from([
        {"symbol": "EURUSD=X", "name": "Euro / US Dollar", "asset_type": "fx",
         "properties": {"display": "EUR/USD"}, "inception_date": None},
    ])
    app.dependency_overrides[get_db] = lambda: FakeSession()
    yield TestClient(app)
    app.dependency_overrides.clear()
    catalog._build_from([])


def test_old_and_new_fx_history_paths_answer_the_same(client_with_catalog):
    new = client_with_catalog.get("/finance/fx/rates/eurusd/history")
    old = client_with_catalog.get("/finance/fx/history/eurusd")
    assert new.status_code == old.status_code == 200
    assert new.json() == old.json() == {
        "symbol": "EURUSD=X", "display": "EUR/USD", "name": "Euro / US Dollar", "count": 0, "history": [],
    }


def test_backfill_symbol_post_requires_admin_key(client_with_catalog):
    assert client_with_catalog.post("/finance/admin/backfill-symbol?symbol=X").status_code == 403


def test_renamed_setting_reads_new_name_then_old_name(monkeypatch):
    monkeypatch.delenv("YAHOO_TEST_SETTING", raising=False)
    monkeypatch.delenv("YF_TEST_SETTING", raising=False)
    assert config._renamed_setting("YAHOO_TEST_SETTING", "YF_TEST_SETTING", "1") == "1"
    monkeypatch.setenv("YF_TEST_SETTING", "2")
    assert config._renamed_setting("YAHOO_TEST_SETTING", "YF_TEST_SETTING", "1") == "2"
    monkeypatch.setenv("YAHOO_TEST_SETTING", "3")
    assert config._renamed_setting("YAHOO_TEST_SETTING", "YF_TEST_SETTING", "1") == "3"


class FakeTicker:
    def __init__(self, error):
        self.error = error

    def history(self, **arguments):
        raise self.error


def test_download_treats_missing_prices_as_empty(monkeypatch):
    monkeypatch.setattr(yahoo.yf, "Ticker", lambda symbol: FakeTicker(yahoo.YFPricesMissingError("TEST", "")))
    assert yahoo.download("TEST", period="10y").empty


def test_download_raises_real_failures(monkeypatch):
    monkeypatch.setattr(yahoo.yf, "Ticker", lambda symbol: FakeTicker(ConnectionError("network down")))
    with pytest.raises(ConnectionError):
        yahoo.download("TEST", period="10y")


def test_download_needs_a_period_or_a_range():
    with pytest.raises(ValueError):
        yahoo.download("TEST")


def make_request(accept_encoding):
    headers = [(b"accept-encoding", accept_encoding.encode())] if accept_encoding else []
    return Request({"type": "http", "headers": headers})


def test_cached_json_response_serves_gzip_and_plain_from_one_build():
    builds = []

    def produce():
        builds.append(1)
        return {"value": [1, 2, 3]}

    compressed = responses.cached_json_response(make_request("gzip, br"), "test:key", produce)
    plain = responses.cached_json_response(make_request(None), "test:key", produce)

    assert compressed.headers["content-encoding"] == "gzip"
    assert json.loads(gzip.decompress(compressed.body)) == {"value": [1, 2, 3]}
    assert json.loads(plain.body) == {"value": [1, 2, 3]}
    assert "content-encoding" not in plain.headers
    assert len(builds) == 1


def test_frame_to_bars_keeps_volume_none_when_missing():
    from app.price_validation import frame_to_bars

    frame = pd.DataFrame(
        {"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [float("nan")]},
        index=pd.DatetimeIndex(["2024-01-02"], tz="UTC"),
    )
    bars, invalid = frame_to_bars("TEST", frame)
    assert invalid == [] and bars[0]["volume"] is None
