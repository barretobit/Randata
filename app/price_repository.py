"""Database access for stored daily price bars (`daily_prices` table)."""

from datetime import date, timedelta
from typing import Iterator

from sqlalchemy import bindparam, text

from .config import INGEST_MARKET_GAP_DAYS
from .db import session_scope

_BAR_COLUMNS = "date, open, high, low, close, volume"

UPSERT_SQL = text(
    "INSERT INTO daily_prices (symbol, date, open, high, low, close, volume) "
    "VALUES (:symbol, :date, :open, :high, :low, :close, :volume) "
    "ON DUPLICATE KEY UPDATE "
    "open = VALUES(open), "
    "high = VALUES(high), "
    "low = VALUES(low), "
    "close = VALUES(close), "
    "volume = VALUES(volume)"
)


def _to_float(value):
    return float(value) if value is not None else None


def price_bar_to_dict(row) -> dict | None:
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


# ---------------------------------------------------------------------------
# Reads for the public endpoints
# ---------------------------------------------------------------------------

def get_latest_bar(symbol: str, session=None):
    """The newest stored bar of one symbol, or None."""
    with session_scope(session) as active_session:
        return active_session.execute(
            text(
                f"SELECT {_BAR_COLUMNS} "
                "FROM daily_prices WHERE symbol = :symbol ORDER BY date DESC LIMIT 1"
            ),
            {"symbol": symbol},
        ).fetchone()


def get_latest_bars(symbols: list[str], session=None) -> dict:
    """The newest stored bar of each symbol, in one query: {symbol: row}."""
    if not symbols:
        return {}
    placeholders = ", ".join(f":symbol{index}" for index in range(len(symbols)))
    parameters = {f"symbol{index}": symbol for index, symbol in enumerate(symbols)}
    with session_scope(session) as active_session:
        rows = active_session.execute(
            text(
                "SELECT p.symbol, p.date, p.open, p.high, p.low, p.close, p.volume "
                "FROM daily_prices p "
                "JOIN (SELECT symbol, MAX(date) AS max_date FROM daily_prices "
                f"WHERE symbol IN ({placeholders}) GROUP BY symbol) m "
                "ON p.symbol = m.symbol AND p.date = m.max_date"
            ),
            parameters,
        ).fetchall()
    return {row.symbol: row for row in rows}


def get_history(symbol: str, session=None) -> list:
    """Every stored bar of one symbol, oldest first."""
    with session_scope(session) as active_session:
        return active_session.execute(
            text(
                f"SELECT {_BAR_COLUMNS} "
                "FROM daily_prices WHERE symbol = :symbol ORDER BY date ASC"
            ),
            {"symbol": symbol},
        ).fetchall()


def get_bars_between(from_date: date, to_date: date, limit: int, session=None) -> list:
    """Bars of every symbol between two inclusive dates, sorted by symbol then date."""
    with session_scope(session) as active_session:
        return active_session.execute(
            text(
                "SELECT symbol, date, open, high, low, close, volume "
                "FROM daily_prices WHERE date BETWEEN :from AND :to "
                "ORDER BY symbol, date ASC LIMIT :limit"
            ),
            {"from": from_date, "to": to_date, "limit": limit},
        ).fetchall()


def iterate_all_bars(limit: int, chunk_rows: int) -> Iterator[list]:
    """Every stored bar (up to `limit`), sorted by symbol then date, in chunks of rows.

    Uses an unbuffered (server-side) cursor, so the full table never sits in
    memory at once. Opens its own session, because callers stream the chunks
    after the request's own session is closed.
    """
    with session_scope() as active_session:
        result = active_session.execute(
            text(
                "SELECT symbol, date, open, high, low, close, volume "
                "FROM daily_prices ORDER BY symbol, date ASC LIMIT :limit"
            ),
            {"limit": limit},
            execution_options={"stream_results": True},
        )
        yield from result.partitions(chunk_rows)


def get_last_updated(session=None) -> list:
    """(symbol, last_date) rows: the newest stored date of every symbol."""
    with session_scope(session) as active_session:
        return active_session.execute(
            text("SELECT symbol, MAX(date) AS last_date FROM daily_prices GROUP BY symbol ORDER BY symbol")
        ).fetchall()


def get_bars_since(start_date: date, session=None) -> list:
    """Bars of every symbol from `start_date` on, sorted by symbol then date (cache load)."""
    with session_scope(session) as active_session:
        return active_session.execute(
            text(
                "SELECT symbol, date, open, high, low, close, volume "
                "FROM daily_prices WHERE date >= :start_date "
                "ORDER BY symbol, date ASC"
            ),
            {"start_date": start_date},
        ).fetchall()


# ---------------------------------------------------------------------------
# Reads and writes for ingestion
# ---------------------------------------------------------------------------

def get_latest_date(symbol: str, session=None) -> date | None:
    with session_scope(session) as active_session:
        return active_session.execute(
            text("SELECT MAX(date) FROM daily_prices WHERE symbol = :symbol"),
            {"symbol": symbol},
        ).scalar()


def get_recent_closes_before(symbol: str, before: date, limit: int, session=None) -> list[tuple]:
    """Up to `limit` positive (date, close) pairs before a date, oldest first."""
    with session_scope(session) as active_session:
        rows = active_session.execute(
            text(
                "SELECT date, close FROM daily_prices "
                "WHERE symbol = :symbol AND date < :before "
                "ORDER BY date DESC LIMIT :limit"
            ),
            {"symbol": symbol, "before": before, "limit": limit},
        ).fetchall()
    return [
        (row.date, float(row.close))
        for row in reversed(rows)
        if row.close is not None and row.close > 0
    ]


def get_next_close_after(symbol: str, after: date, session=None) -> tuple | None:
    """The first positive (date, close) pair stored after a date, or None."""
    with session_scope(session) as active_session:
        row = active_session.execute(
            text(
                "SELECT date, close FROM daily_prices "
                "WHERE symbol = :symbol AND date > :after AND close > 0 "
                "ORDER BY date LIMIT 1"
            ),
            {"symbol": symbol, "after": after},
        ).fetchone()
    return (row.date, float(row.close)) if row else None


def delete_bars(symbol: str, dates: list[date], session=None) -> int:
    """Delete one symbol's bars on the given dates. Returns how many rows were removed."""
    if not dates:
        return 0
    with session_scope(session) as active_session:
        result = active_session.execute(
            text("DELETE FROM daily_prices WHERE symbol = :symbol AND date IN :dates").bindparams(
                bindparam("dates", expanding=True)
            ),
            {"symbol": symbol, "dates": list(dates)},
        )
        active_session.commit()
        return result.rowcount


def get_closes_from(symbol: str, start: date, session=None) -> list[tuple]:
    """(date, close) pairs from a date on, oldest first. Close may be None."""
    with session_scope(session) as active_session:
        rows = active_session.execute(
            text(
                "SELECT date, close FROM daily_prices "
                "WHERE symbol = :symbol AND date >= :start ORDER BY date"
            ),
            {"symbol": symbol, "start": start},
        ).fetchall()
    return [(row.date, _to_float(row.close)) for row in rows]


def upsert_bars(bars: list[dict], session=None) -> None:
    """Insert or update bars (dicts with symbol, date, open, high, low, close, volume) in one batch."""
    if not bars:
        return
    with session_scope(session) as active_session:
        active_session.execute(UPSERT_SQL, bars)
        active_session.commit()


def get_history_coverage(session=None) -> dict:
    """Per-symbol coverage: {symbol: {"count": int, "first_date": date, "last_date": date}}."""
    with session_scope(session) as active_session:
        rows = active_session.execute(
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


def get_stored_symbols(session=None) -> list[str]:
    """Every symbol that has at least one stored bar."""
    with session_scope(session) as active_session:
        rows = active_session.execute(
            text("SELECT DISTINCT symbol FROM daily_prices ORDER BY symbol")
        ).fetchall()
    return [row.symbol for row in rows]


def get_price_bars(symbol: str, session=None) -> list[dict]:
    """One symbol's stored bars, oldest first, with float prices and `date` objects.

    Read one symbol at a time: the whole table is ~460k rows (10 years), far
    too much to hold in memory at once on a small instance.
    """
    with session_scope(session) as active_session:
        rows = active_session.execute(
            text(
                f"SELECT {_BAR_COLUMNS} FROM daily_prices "
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


def get_history_gaps(session=None) -> list[dict]:
    """Long gaps between stored bars, allowing for weekends and holidays (crypto: any missing day)."""
    with session_scope(session) as active_session:
        rows = active_session.execute(
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
            "start":  row.previous_date + timedelta(days=1),
            "end":    row.next_date,
        }
        for row in rows
    ]
