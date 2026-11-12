"""Logging setup for Randata.

Sets up Python's standard `logging` with a console handler so that errors and
interesting events are visible in the server output, plus a lightweight
`log_event()` helper that persists structured events into the MySQL
`api_logs` table (non-fatal if the database write fails).

The API logs table is created separately, see `sql/create_api_logs.sql`.
"""

import logging
import sys
from datetime import datetime, timezone

from sqlalchemy import text

from . import db
from .db import session_scope

logger = logging.getLogger("randata")
logger.setLevel(logging.INFO)


def _configure_console() -> None:
    if logger.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)


_configure_console()


def get_logger(name: str = "randata") -> logging.Logger:
    return logging.getLogger(f"randata.{name}")


def log_event(
    level: str,
    message: str,
    *,
    logger_name: str = None,
    symbol: str = None,
    duration_ms: int = None,
    rows_written: int = None,
    success: bool = None,
    exception: str = None,
) -> None:
    """Persist one structured event into the `api_logs` table.

    Never raises: if the database is not available, the event is dropped
    gracefully so logging never breaks the app.
    """
    if db.SessionLocal is None:
        return
    try:
        with session_scope() as session:
            session.execute(
                text(
                    "INSERT INTO api_logs "
                    "(recorded_at, logger, level, message, symbol, duration_ms, "
                    " rows_written, success, exception) "
                    "VALUES (:recorded_at, :logger, :level, :message, :symbol, "
                    " :duration_ms, :rows_written, :success, :exception)"
                ),
                {
                    "recorded_at": datetime.now(timezone.utc),
                    "logger": logger_name,
                    "level": level,
                    "message": message,
                    "symbol": symbol,
                    "duration_ms": duration_ms,
                    "rows_written": rows_written,
                    "success": success,
                    "exception": exception,
                },
            )
            session.commit()
    except Exception as error:  # pragma: no cover - logging must never crash the app
        logging.getLogger("randata").warning(
            "Failed to write API log event to database: %s", error
        )


def get_recent_logs(session=None, days: int = 7) -> list[dict]:
    """Structured events from `api_logs` for the last `days` days, newest first."""
    with session_scope(session) as active_session:
        rows = active_session.execute(
            text(
                "SELECT id, recorded_at, logger, level, message, symbol, "
                "duration_ms, rows_written, success, exception "
                "FROM api_logs WHERE recorded_at >= UTC_TIMESTAMP() - INTERVAL :days DAY "
                "ORDER BY recorded_at DESC"
            ),
            {"days": days},
        ).fetchall()
    return [
        {
            "id":           row.id,
            "recorded_at":  str(row.recorded_at),
            "logger":       row.logger,
            "level":        row.level,
            "message":      row.message,
            "symbol":       row.symbol,
            "duration_ms":  row.duration_ms,
            "rows_written": row.rows_written,
            "success":      bool(row.success),
            "exception":    row.exception,
        }
        for row in rows
    ]
