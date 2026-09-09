"""Database access for the tracked-assets catalogue (`assets` table)."""

import json

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .assets import CRYPTO, ETFS, FX_PAIRS, INDEXES, PRECIOUS_METALS, STOCKS
from .db import SessionLocal
from .logging_config import get_logger

logger = get_logger("asset_repo")

VALID_TYPES = ("fx", "index", "metal", "stock", "etf", "crypto")

# (asset_type, list) seed groups from the static catalogue in app/assets.py.
_ASSET_GROUPS = [
    ("fx",    FX_PAIRS),
    ("index", INDEXES),
    ("metal", PRECIOUS_METALS),
    ("stock", STOCKS),
    ("etf",   ETFS),
    ("crypto", CRYPTO),
]


def _properties_of(item):
    return {k: v for k, v in item.items() if k not in ("symbol", "name")}


def _row_to_asset(row):
    props = row.properties
    if isinstance(props, str):
        props = json.loads(props) if props else {}
    return {
        "symbol":     row.symbol,
        "name":       row.name,
        "asset_type": row.asset_type,
        "properties": props or {},
    }


def _close(db, own):
    if own and db is not None:
        db.close()


def seed_assets(db=None):
    """Idempotently insert the static catalogue from app/assets.py into the DB."""
    own = db is None
    if own:
        db = SessionLocal()
    added = 0
    try:
        for asset_type, group in _ASSET_GROUPS:
            for item in group:
                result = db.execute(
                    text(
                        "INSERT IGNORE INTO assets (symbol, name, asset_type, properties) "
                        "VALUES (:symbol, :name, :asset_type, :properties)"
                    ),
                    {
                        "symbol": item["symbol"],
                        "name":   item["name"],
                        "asset_type": asset_type,
                        "properties": json.dumps(_properties_of(item)),
                    },
                )
                added += result.rowcount or 0
        db.commit()
    finally:
        _close(db, own)
    if added:
        logger.info("Seeded %d new rows into the assets table.", added)
    return added


def get_all_assets(db=None):
    """Return every tracked asset ordered by insertion. Raises if the table is missing."""
    own = db is None
    if own:
        db = SessionLocal()
    try:
        rows = db.execute(
            text("SELECT symbol, name, asset_type, properties FROM assets ORDER BY id")
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
                "SELECT symbol, name, asset_type, properties "
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


def add_asset(symbol, name, asset_type, properties=None, db=None):
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
                "INSERT INTO assets (symbol, name, asset_type, properties) "
                "VALUES (:symbol, :name, :asset_type, :properties)"
            ),
            {
                "symbol":     symbol,
                "name":       name,
                "asset_type": asset_type,
                "properties": json.dumps(properties or {}),
            },
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError(f"Symbol '{symbol}' is already tracked.")
    finally:
        _close(db, own)
    return get_asset(symbol)