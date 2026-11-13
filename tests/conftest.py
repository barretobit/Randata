"""Offline test setup: no database, no Yahoo calls, no scheduler.

The environment is set before any `app` module is imported, because
`app.config` reads it at import time (load_dotenv never overrides it).
"""

import os

os.environ["DATABASE_URL"] = ""
os.environ["ADMIN_KEY"] = "test-admin-key"

from datetime import date  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

ADMIN_HEADERS = {"X-Admin-Key": "test-admin-key"}


class FakeResult:
    def __init__(self, rows, rowcount=0):
        self.rows = list(rows)
        self.rowcount = rowcount

    def fetchall(self):
        return list(self.rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def scalar(self):
        return self.rows[0][0] if self.rows else None

    def partitions(self, size):
        for start in range(0, len(self.rows), size):
            yield self.rows[start:start + size]


class FakeSession:
    """Stands in for a SQLAlchemy session.

    Reads are answered in order from `reads` (one list of rows per query).
    Bulk writes (a list of parameter dicts) are recorded in `writes`, and
    DELETE parameters in `deletes` (each reports one removed row per date).
    """

    def __init__(self, reads=()):
        self.reads = list(reads)
        self.writes = []
        self.deletes = []
        self.commits = 0

    def execute(self, statement, params=None, **options):
        if isinstance(params, list):
            self.writes.extend(params)
            return FakeResult([])
        if str(statement).lstrip().upper().startswith("DELETE"):
            self.deletes.append(params)
            return FakeResult([], rowcount=len(params.get("dates", [])))
        return FakeResult(self.reads.pop(0) if self.reads else [])

    def commit(self):
        self.commits += 1

    def close(self):
        pass


def price_row(day, close, symbol="TEST"):
    return SimpleNamespace(
        symbol=symbol, date=day, open=close, high=close, low=close, close=close, volume=100,
    )


def make_frame(closes, start="2024-01-01"):
    """A Yahoo-shaped daily frame (business days, exchange time zone) around the given closes."""
    closes = np.asarray(closes, dtype=float)
    index = pd.bdate_range(start, periods=len(closes), tz="America/New_York")
    return pd.DataFrame(
        {
            "Open": closes,
            "High": closes * 1.005,
            "Low": closes * 0.995,
            "Close": closes,
            "Volume": 1000,
        },
        index=index,
    )


def random_walk(length, daily_volatility, seed=7):
    moves = np.random.default_rng(seed).normal(0, daily_volatility, length)
    return 100 * np.cumprod(1 + moves)


def frame_dates(frame):
    return [timestamp.date() for timestamp in frame.index]


@pytest.fixture
def fake_session(monkeypatch):
    """One shared FakeSession for every database session; api_logs writes are dropped."""
    from app import db, ingestion

    session = FakeSession()
    monkeypatch.setattr(db, "SessionLocal", lambda: session)
    monkeypatch.setattr(ingestion, "log_event", lambda *arguments, **keywords: None)
    return session


@pytest.fixture
def first_day():
    return date(2024, 1, 1)
