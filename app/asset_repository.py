"""Database access for the tracked-assets catalogue (`assets` table)."""

import json

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .db import session_scope

VALID_TYPES = ("fx", "index", "metal", "stock", "etf", "crypto")

_ASSET_COLUMNS = "symbol, name, asset_type, properties, inception_date"


def _row_to_asset(row) -> dict:
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


def get_all_assets(session=None) -> list[dict]:
    """Every tracked asset, ordered by insertion. Raises if the table is missing."""
    with session_scope(session) as active_session:
        rows = active_session.execute(
            text(f"SELECT {_ASSET_COLUMNS} FROM assets ORDER BY id")
        ).fetchall()
    return [_row_to_asset(row) for row in rows]


def get_asset(symbol: str, session=None) -> dict | None:
    """One tracked asset by exact symbol, or None."""
    with session_scope(session) as active_session:
        row = active_session.execute(
            text(f"SELECT {_ASSET_COLUMNS} FROM assets WHERE symbol = :symbol"),
            {"symbol": symbol},
        ).fetchone()
    return _row_to_asset(row) if row else None


def asset_exists(symbol: str, session=None) -> bool:
    return get_asset(symbol, session) is not None


def get_assets_missing_inception(session=None) -> list[dict]:
    """Tracked assets whose inception_date has not been captured yet."""
    with session_scope(session) as active_session:
        rows = active_session.execute(
            text(
                f"SELECT {_ASSET_COLUMNS} FROM assets "
                "WHERE inception_date IS NULL ORDER BY id"
            )
        ).fetchall()
    return [_row_to_asset(row) for row in rows]


def add_asset(symbol, name, asset_type, properties=None, inception_date=None, session=None) -> dict:
    """Insert a new tracked asset. Raises ValueError on duplicate or invalid type."""
    if asset_type not in VALID_TYPES:
        raise ValueError(
            f"Invalid asset_type '{asset_type}'. Must be one of {', '.join(VALID_TYPES)}."
        )
    with session_scope(session) as active_session:
        try:
            active_session.execute(
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
            active_session.commit()
        except IntegrityError:
            active_session.rollback()
            raise ValueError(f"Symbol '{symbol}' is already tracked.")
    return get_asset(symbol)


def set_inception_date(symbol, inception_date, session=None) -> None:
    """Persist an asset's inception (first-trade) date. No-op if it is already set."""
    with session_scope(session) as active_session:
        active_session.execute(
            text(
                "UPDATE assets SET inception_date = :inception_date "
                "WHERE symbol = :symbol AND inception_date IS NULL"
            ),
            {"symbol": symbol, "inception_date": inception_date},
        )
        active_session.commit()
