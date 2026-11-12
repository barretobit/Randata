"""Database access for the tracked-assets catalogue (`assets`) and stored price bars (`daily_prices`)."""

import json
from contextlib import contextmanager
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .config import INGEST_MARKET_GAP_DAYS
from .db import SessionLocal

VALID_TYPES = ("fx", "index", "metal", "stock", "etf", "crypto")

_ASSET_COLUMNS = "symbol, name, asset_type, properties, inception_date"


@contextmanager
def _session(db=None):
    """Use the caller's session when one is given, otherwise open and close a new one."""
    if db is not None:
        yield db
        return
    own_session = SessionLocal()
    try:
        yield own_session
    finally:
        own_session.close()


def _row_to_asset(row):
    properties = row.properties
    if isinstance(properties, str):
        properties = json.loads(properties) if properties else {}
    return {
        "symbol":         row.symbol,
        "name":           row.name,
        "asset_type":     row.asset_type,
        "properties":     properties or {},
        "inception_date": row.inception_date,
    }


def _to_float(value):
    return float(value) if value is not None else None


def price_bar_to_dict(row):
    """One stored daily bar as a JSON-ready dict, or None. DECIMAL prices become floats."""
    if row is None:
        return None
    return {
        "date":   str(row.date),
        "open":   _to_float(row.open),
        "high":   _to_float(row.high),
        "low":    _to_float(row.low),
        "close":  _to_float(row.close),
        "volume": row.volume,
    }


def get_all_assets(db=None):
    """Return every tracked asset ordered by insertion. Raises if the table is missing."""
    with _session(db) as session:
        rows = session.execute(
            text(f"SELECT {_ASSET_COLUMNS} FROM assets ORDER BY id")
        ).fetchall()
    return [_row_to_asset(row) for row in rows]


def get_asset(symbol, db=None):
    """Return a single tracked asset by exact symbol, or None."""
    with _session(db) as session:
        row = session.execute(
            text(f"SELECT {_ASSET_COLUMNS} FROM assets WHERE symbol = :symbol"),
            {"symbol": symbol},
        ).fetchone()
    return _row_to_asset(row) if row else None


def asset_exists(symbol, db=None):
    return get_asset(symbol, db) is not None


def get_history_coverage(db=None):
    """Per-symbol stored coverage summary from daily_prices.

    Returns {symbol: {"count": int, "first_date": date or None, "last_date": date or None}}.
    """
    with _session(db) as session:
        rows = session.execute(
            text(
                "SELECT symbol, COUNT(*) AS bar_count, MIN(date) AS first_date, "
                "MAX(date) AS last_date FROM daily_prices GROUP BY symbol"
            )
        ).fetchall()
    return {
        row.symbol: {
            "count":      row.bar_count,
            "first_date": row.first_date,
            "last_date":  row.last_date,
        }
        for row in rows
    }


def get_stored_symbols(db=None):
    """Every symbol that has at least one stored bar."""
    with _session(db) as session:
        rows = session.execute(
            text("SELECT DISTINCT symbol FROM daily_prices ORDER BY symbol")
        ).fetchall()
    return [row.symbol for row in rows]


def get_price_bars(symbol, db=None):
    """One symbol's stored OHLCV bars in chronological order, with float prices.

    Read one symbol at a time: the whole table is ~460k rows (10 years), far
    too much to hold in memory at once on a small instance.
    """
    with _session(db) as session:
        rows = session.execute(
            text(
                "SELECT date, open, high, low, close, volume FROM daily_prices "
                "WHERE symbol = :symbol ORDER BY date"
            ),
            {"symbol": symbol},
        ).fetchall()
    return [
        {
            "date":   row.date,
            "open":   _to_float(row.open),
            "high":   _to_float(row.high),
            "low":    _to_float(row.low),
            "close":  _to_float(row.close),
            "volume": row.volume,
        }
        for row in rows
    ]


def get_history_gaps(db=None):
    """Find long gaps between stored bars, allowing for weekends and holidays."""
    with _session(db) as session:
        rows = session.execute(
            text(
                "SELECT gaps.symbol, gaps.previous_date, gaps.next_date FROM ("
                "  SELECT p.symbol, p.date AS previous_date, "
                "         LEAD(p.date) OVER (PARTITION BY p.symbol ORDER BY p.date) AS next_date "
                "  FROM daily_prices p"
                ") gaps "
                "LEFT JOIN assets a ON a.symbol = gaps.symbol "
                "WHERE gaps.next_date IS NOT NULL "
                "AND DATEDIFF(gaps.next_date, gaps.previous_date) > "
                "    CASE WHEN a.asset_type = 'crypto' THEN 1 ELSE :gap_days END "
                "ORDER BY gaps.symbol, gaps.previous_date"
            ),
            {"gap_days": INGEST_MARKET_GAP_DAYS},
        ).fetchall()
    return [
        {
            "symbol": row.symbol,
            "start": row.previous_date + timedelta(days=1),
            "end": row.next_date,
        }
        for row in rows
    ]


def add_asset(symbol, name, asset_type, properties=None, inception_date=None, db=None):
    """Insert a new tracked asset. Raises ValueError on duplicate or invalid type."""
    if asset_type not in VALID_TYPES:
        raise ValueError(
            f"Invalid asset_type '{asset_type}'. Must be one of {', '.join(VALID_TYPES)}."
        )
    with _session(db) as session:
        try:
            session.execute(
                text(
                    "INSERT INTO assets (symbol, name, asset_type, properties, inception_date) "
                    "VALUES (:symbol, :name, :asset_type, :properties, :inception_date)"
                ),
                {
                    "symbol":         symbol,
                    "name":           name,
                    "asset_type":     asset_type,
                    "properties":     json.dumps(properties or {}),
                    "inception_date": inception_date,
                },
            )
            session.commit()
        except IntegrityError:
            session.rollback()
            raise ValueError(f"Symbol '{symbol}' is already tracked.")
    return get_asset(symbol)


def set_inception_date(symbol, inception_date, db=None):
    """Persist an asset's inception/first-trade date. No-op if it is already set."""
    with _session(db) as session:
        session.execute(
            text(
                "UPDATE assets SET inception_date = :inception_date "
                "WHERE symbol = :symbol AND inception_date IS NULL"
            ),
            {"symbol": symbol, "inception_date": inception_date},
        )
        session.commit()


def get_assets_missing_inception(db=None):
    """Tracked assets whose inception_date has not been captured yet."""
    with _session(db) as session:
        rows = session.execute(
            text(
                f"SELECT {_ASSET_COLUMNS} FROM assets "
                "WHERE inception_date IS NULL ORDER BY id"
            )
        ).fetchall()
    return [_row_to_asset(row) for row in rows]
