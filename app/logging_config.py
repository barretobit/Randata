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

from .db import SessionLocal

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

    Never raises: if the database is not available (or SOCKS unconfigured),
    the event is dropped gracefully so logging never breaks the app.
    """
    if SessionLocal is None:
        return
    db = None
    try:
        db = SessionLocal()
        db.execute(
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
        db.commit()
    except Exception as e:  # pragma: no cover - logging must never crash the app
        logging.getLogger("randata").warning(
            "Failed to write API log event to database: %s", e
        )
    finally:
        if db is not None:
            db.close()
