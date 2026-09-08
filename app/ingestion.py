import time

import yfinance as yf
from sqlalchemy import text

from .assets import ALL_ASSETS
from .db import SessionLocal
from .logging_config import get_logger, log_event

logger = get_logger("ingestion")

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


def _fetch_and_store(symbol: str, period: str) -> int:
    start = time.perf_counter()
    count = 0
    error = None
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval="1d", auto_adjust=True)
        if df.empty:
            logger.info("No data returned for %s (period=%s)", symbol, period)
            return 0
        db = SessionLocal()
        try:
            for ts, row in df.iterrows():
                db.execute(UPSERT_SQL, {
                    "symbol": symbol,
                    "date":   ts.date(),
                    "open":   float(row["Open"])   if row["Open"]   == row["Open"] else None,
                    "high":   float(row["High"])   if row["High"]   == row["High"] else None,
                    "low":    float(row["Low"])    if row["Low"]    == row["Low"]  else None,
                    "close":  float(row["Close"])  if row["Close"]  == row["Close"]else None,
                    "volume": int(row["Volume"])   if row["Volume"] == row["Volume"]else None,
                })
                count += 1
            db.commit()
        finally:
            db.close()
        logger.info("Stored %d rows for %s (period=%s)", count, symbol, period)
        return count
    except Exception as e:
        error = str(e)
        raise
    finally:
        duration_ms = int((time.perf_counter() - start) * 1000)
        msg = f"Fetch failed for {symbol}" if error else f"Fetched {symbol} (period={period})"
        log_event(
            "ERROR" if error else "INFO",
            msg,
            logger_name="ingestion",
            symbol=symbol,
            duration_ms=duration_ms,
            rows_written=count if not error else None,
            success=error is None,
            exception=error,
        )


def backfill(symbol: str) -> int:
    return _fetch_and_store(symbol, period="5y")


def ingest_daily(symbol: str) -> int:
    return _fetch_and_store(symbol, period="5d")


def backfill_all():
    results = {}
    for asset in ALL_ASSETS:
        try:
            n = backfill(asset["symbol"])
            results[asset["symbol"]] = n
        except Exception as e:
            results[asset["symbol"]] = f"ERROR: {e}"
            logger.error("backfill failed for %s: %s", asset["symbol"], e)
    logger.info("backfill_all finished: %d assets", len(ALL_ASSETS))
    return results


def ingest_daily_all():
    results = {}
    for asset in ALL_ASSETS:
        try:
            n = ingest_daily(asset["symbol"])
            results[asset["symbol"]] = n
        except Exception as e:
            results[asset["symbol"]] = f"ERROR: {e}"
            logger.error("ingest_daily failed for %s: %s", asset["symbol"], e)
    logger.info("ingest_daily_all finished: %d assets", len(ALL_ASSETS))
    return results