"""In-memory cache for historical price data.

Loads the configured rolling window (CACHE_HISTORY_YEARS) of daily_prices rows
on startup and reloads after each ingestion. A reload builds the new data first
and swaps it in one step, so readers never see an empty or half-built cache.
Serves data without hitting the database on read-heavy public endpoints.
"""

import threading
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text

from .asset_repo import price_bar_to_dict
from .config import CACHE_HISTORY_YEARS
from .db import SessionLocal
from .logging_config import get_logger

logger = get_logger("cache")

_lock = threading.Lock()
_cache: dict[str, list[dict]] = {}
_loaded_at: datetime | None = None
_CACHE_HISTORY_DAYS = 365 * CACHE_HISTORY_YEARS


def load() -> bool:
    """Load the configured rolling window of historical data from the database into memory."""
    global _loaded_at
    if SessionLocal is None:
        logger.warning("No database connection — cache not loaded.")
        return False
    db = None
    try:
        db = SessionLocal()
        rows = db.execute(
            text(
                "SELECT symbol, date, open, high, low, close, volume "
                "FROM daily_prices WHERE date >= :start_date "
                "ORDER BY symbol, date ASC"
            ),
            {"start_date": date.today() - timedelta(days=_CACHE_HISTORY_DAYS)},
        ).fetchall()
        new_cache: dict[str, list[dict]] = {}
        for row in rows:
            new_cache.setdefault(row.symbol, []).append(price_bar_to_dict(row))
        with _lock:
            _cache.clear()
            _cache.update(new_cache)
            _loaded_at = datetime.now(timezone.utc)
        total_rows = sum(len(history) for history in new_cache.values())
        logger.info(
            "Cache loaded: %d symbols, %d rows, refreshed at %s",
            len(new_cache), total_rows, _loaded_at.isoformat(),
        )
        return True
    except Exception as error:
        logger.error("Failed to load cache: %s", error)
        return False
    finally:
        if db is not None:
            db.close()


def get_symbol(symbol: str) -> list[dict] | None:
    """Return cached history for a symbol, or None if not in cache."""
    with _lock:
        return _cache.get(symbol)


def get_all() -> dict[str, list[dict]]:
    """Return the entire cache (shallow copy of keys)."""
    with _lock:
        return dict(_cache)


def stats() -> dict:
    """Return cache metadata for diagnostics."""
    with _lock:
        symbols = list(_cache.keys())
        total_rows = sum(len(v) for v in _cache.values())
        return {
            "symbols":    len(symbols),
            "total_rows": total_rows,
            "loaded_at":  _loaded_at.isoformat() if _loaded_at else None,
        }


def details() -> dict:
    """Return a detailed cache report: per-symbol coverage and memory estimate.

    Estimated size is a rough memory footprint of the Python dict/list structure,
    useful for monitoring whether the cache is healthy or unexpectedly large.
    """
    with _lock:
        per_symbol = []
        total_rows = 0
        total_bytes = 0
        for symbol, history in sorted(_cache.items()):
            rows = len(history)
            total_rows += rows
            per_symbol.append({
                "symbol":     symbol,
                "rows":       rows,
                "first_date": history[0]["date"] if rows else None,
                "last_date":  history[-1]["date"] if rows else None,
            })
            # rough Python overhead: dict + strings + floats
            total_bytes += rows * 450
        return {
            "loaded_at":  _loaded_at.isoformat() if _loaded_at else None,
            "symbols":    len(per_symbol),
            "total_rows": total_rows,
            "est_memory_mb": round(total_bytes / (1024 * 1024), 2),
            "per_symbol": per_symbol,
        }
