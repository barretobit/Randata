"""In-memory cache for historical price data.

Loads all daily_prices rows on startup and refreshes after each ingestion.
Serves data without hitting the database on read-heavy public endpoints.
"""

import threading
from datetime import datetime, timezone

from sqlalchemy import text

from .db import SessionLocal
from .logging_config import get_logger

logger = get_logger("cache")

_lock = threading.Lock()
_cache: dict[str, list[dict]] = {}
_loaded_at: datetime | None = None


def _row_to_dict(row) -> dict:
    return {
        "date":   str(row.date),
        "open":   row.open,
        "high":   row.high,
        "low":    row.low,
        "close":  row.close,
        "volume": row.volume,
    }


def load() -> None:
    """Load all historical data from the database into memory."""
    global _loaded_at
    if SessionLocal is None:
        logger.warning("No database connection — cache not loaded.")
        return
    db = None
    try:
        db = SessionLocal()
        rows = db.execute(
            text(
                "SELECT symbol, date, open, high, low, close, volume "
                "FROM daily_prices ORDER BY symbol, date ASC"
            )
        ).fetchall()
        new_cache: dict[str, list[dict]] = {}
        for r in rows:
            new_cache.setdefault(r.symbol, []).append(_row_to_dict(r))
        with _lock:
            _cache.clear()
            _cache.update(new_cache)
            _loaded_at = datetime.now(timezone.utc)
        total_rows = sum(len(v) for v in new_cache.values())
        logger.info(
            "Cache loaded: %d symbols, %d rows, refreshed at %s",
            len(new_cache), total_rows, _loaded_at.isoformat(),
        )
    except Exception as e:
        logger.error("Failed to load cache: %s", e)
    finally:
        if db is not None:
            db.close()


def refresh() -> None:
    """Alias for load(). Call after ingestion to update the cache."""
    load()


def invalidate() -> None:
    """Discard the entire cache so no stale data is served.

    Call at the start of a fetch cycle: the cache is emptied immediately and
    rebuilt from the database once the fetch has finished.
    """
    global _loaded_at
    with _lock:
        _cache.clear()
        _loaded_at = None
    logger.info("Cache invalidated — awaiting rebuild after fetch cycle.")


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
        for sym, history in sorted(_cache.items()):
            rows = len(history)
            total_rows += rows
            per_symbol.append({
                "symbol":     sym,
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
