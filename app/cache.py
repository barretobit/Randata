"""In-memory cache for historical price data.

Loads the configured rolling window (CACHE_HISTORY_YEARS) of daily_prices rows
on startup and reloads after each ingestion. A reload builds the new data first
and swaps it in one step, so readers never see an empty or half-built cache.
Serves data without hitting the database on read-heavy public endpoints.
"""

import threading
from datetime import date, datetime, timedelta, timezone

from . import price_repository
from .config import CACHE_HISTORY_YEARS
from .logging_config import get_logger

logger = get_logger("cache")

# Measured footprint of one cached bar (a dict with a date string, 4 floats and an int).
_ESTIMATED_BYTES_PER_ROW = 470
_CACHE_HISTORY_DAYS = 365 * CACHE_HISTORY_YEARS

_lock = threading.Lock()
_cache: dict[str, list[dict]] = {}
_loaded_at: datetime | None = None


def window_start() -> date:
    """Earliest date held by the cache (today minus the cache window)."""
    return date.today() - timedelta(days=_CACHE_HISTORY_DAYS)


def load() -> bool:
    """Load the configured rolling window of historical data from the database into memory."""
    global _loaded_at
    try:
        rows = price_repository.get_bars_since(window_start())
    except Exception as error:
        logger.error("Failed to load cache: %s", error)
        return False
    new_cache: dict[str, list[dict]] = {}
    for row in rows:
        new_cache.setdefault(row.symbol, []).append(price_repository.price_bar_to_dict(row))
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


def get_symbol(symbol: str) -> list[dict] | None:
    """Cached history for one symbol, or None if it is not in the cache."""
    with _lock:
        return _cache.get(symbol)


def get_all() -> dict[str, list[dict]]:
    """The entire cache (a shallow copy, safe to iterate while a reload happens)."""
    with _lock:
        return dict(_cache)


def loaded_at() -> str | None:
    """When the cache was last loaded (ISO 8601), or None if it never was."""
    with _lock:
        return _loaded_at.isoformat() if _loaded_at else None


def stats() -> dict:
    """Cache metadata for diagnostics."""
    with _lock:
        return {
            "symbols":    len(_cache),
            "total_rows": sum(len(history) for history in _cache.values()),
            "loaded_at":  _loaded_at.isoformat() if _loaded_at else None,
        }


def details() -> dict:
    """Detailed cache report: per-symbol coverage and an estimated memory footprint."""
    with _lock:
        per_symbol = []
        total_rows = 0
        for symbol, history in sorted(_cache.items()):
            rows = len(history)
            total_rows += rows
            per_symbol.append({
                "symbol":     symbol,
                "rows":       rows,
                "first_date": history[0]["date"] if rows else None,
                "last_date":  history[-1]["date"] if rows else None,
            })
        return {
            "loaded_at":  _loaded_at.isoformat() if _loaded_at else None,
            "symbols":    len(per_symbol),
            "total_rows": total_rows,
            "est_memory_mb": round(total_rows * _ESTIMATED_BYTES_PER_ROW / (1024 * 1024), 2),
            "per_symbol": per_symbol,
        }
