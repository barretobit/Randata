"""Database access for the tracked-assets catalogue (`assets` table)."""

import json
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .config import INGEST_MARKET_GAP_DAYS
from .db import SessionLocal
from .logging_config import get_logger

logger = get_logger("asset_repo")

VALID_TYPES = ("fx", "index", "metal", "stock", "etf", "crypto")


def _row_to_asset(row):
    props = row.properties
    if isinstance(props, str):
        props = json.loads(props) if props else {}
    return {
        "symbol":         row.symbol,
        "name":           row.name,
        "asset_type":     row.asset_type,
        "properties":     props or {},
        "inception_date": row.inception_date,
    }


def _close(db, own):
    if own and db is not None:
        db.close()


def get_all_assets(db=None):
    """Return every tracked asset ordered by insertion. Raises if the table is missing."""
    own = db is None
    if own:
        db = SessionLocal()
    try:
        rows = db.execute(
            text(
                "SELECT symbol, name, asset_type, properties, inception_date "
                "FROM assets ORDER BY id"
            )
        ).fetchall()
    finally:
        _close(db, own)
    return [_row_to_asset(row) for row in rows]


def get_asset(symbol, db=None):
    """Return a single tracked asset by exact symbol, or None."""
    own = db is None
    if own:
        db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT symbol, name, asset_type, properties, inception_date "
                "FROM assets WHERE symbol = :symbol"
            ),
            {"symbol": symbol},
        ).fetchone()
    finally:
        _close(db, own)
    return _row_to_asset(row) if row else None


def asset_exists(symbol, db=None):
    return get_asset(symbol, db) is not None


def get_history_coverage(db=None):
    """Per-symbol stored coverage summary from daily_prices.

    Returns {symbol: {"count": int, "first_date": date or None, "last_date": date or None}}.
    """
    own = db is None
    if own:
        db = SessionLocal()
    try:
        rows = db.execute(
            text(
                "SELECT symbol, COUNT(*) AS n, MIN(date) AS min_d, MAX(date) AS max_d "
                "FROM daily_prices GROUP BY symbol"
            )
        ).fetchall()
    finally:
        _close(db, own)
    return {
        r.symbol: {
            "count":      r.n,
            "first_date": r.min_d,
            "last_date":  r.max_d,
        }
        for r in rows
    }


def get_all_price_bars(db=None):
    """Return stored OHLCV bars in chronological order for history audits."""
    own = db is None
    if own:
        db = SessionLocal()
    try:
        rows = db.execute(
            text(
                "SELECT symbol, date, open, high, low, close, volume "
                "FROM daily_prices ORDER BY symbol, date"
            )
        ).fetchall()
    finally:
        _close(db, own)
    return [
        {
            "symbol": row.symbol,
            "date": row.date,
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "close": row.close,
            "volume": row.volume,
        }
        for row in rows
    ]


def get_history_gaps(db=None):
    """Find long gaps between stored bars, allowing for weekends and holidays."""
    own = db is None
    if own:
        db = SessionLocal()
    try:
        rows = db.execute(
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
    finally:
        _close(db, own)
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
    own = db is None
    if own:
        db = SessionLocal()
    try:
        db.execute(
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
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError(f"Symbol '{symbol}' is already tracked.")
    finally:
        _close(db, own)
    return get_asset(symbol)


def set_inception_date(symbol, inception_date, db=None):
    """Persist an asset's inception/first-trade date. No-op if it is already set."""
    own = db is None
    if own:
        db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE assets SET inception_date = :inception_date "
                "WHERE symbol = :symbol AND inception_date IS NULL"
            ),
            {"symbol": symbol, "inception_date": inception_date},
        )
        db.commit()
    finally:
        _close(db, own)


def get_assets_missing_inception(db=None):
    """Tracked assets whose inception_date has not been captured yet."""
    own = db is None
    if own:
        db = SessionLocal()
    try:
        rows = db.execute(
            text(
                "SELECT symbol, name, asset_type, properties, inception_date "
                "FROM assets WHERE inception_date IS NULL ORDER BY id"
            )
        ).fetchall()
    finally:
        _close(db, own)
    return [_row_to_asset(row) for row in rows]