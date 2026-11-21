"""Database access for dividend events (`dividends` table)."""

from datetime import date

from sqlalchemy import text

from .db import session_scope

UPSERT_SQL = text(
    "INSERT INTO dividends (symbol, date, amount) "
    "VALUES (:symbol, :date, :amount) "
    "ON DUPLICATE KEY UPDATE amount = VALUES(amount)"
)


def upsert_dividends(dividends: list[dict], session=None) -> None:
    """Insert or update dividends (dicts with symbol, date, amount) in one batch."""
    if not dividends:
        return
    with session_scope(session) as active_session:
        active_session.execute(UPSERT_SQL, dividends)
        active_session.commit()


def get_dividends_since(start_date: date, session=None) -> list:
    """Every stored dividend from `start_date` on, sorted by symbol then date."""
    with session_scope(session) as active_session:
        return active_session.execute(
            text(
                "SELECT symbol, date, amount FROM dividends "
                "WHERE date >= :start_date ORDER BY symbol, date"
            ),
            {"start_date": start_date},
        ).fetchall()
