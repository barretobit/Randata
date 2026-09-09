import random
import time
from datetime import date, timedelta

import pandas as pd
import yfinance as yf
from sqlalchemy import text

from .asset_repo import get_all_assets, get_history_coverage
from .assets import ALL_ASSETS
from .config import (
    BACKFILL_DELAY_SECONDS,
    BACKFILL_JITTER_SECONDS,
    INGEST_DELAY_SECONDS,
    INGEST_JITTER_SECONDS,
    SLOW_BACKFILL_DELAY_SECONDS,
    SLOW_BACKFILL_JITTER_SECONDS,
    SLOW_YF_RETRY_BASE_SECONDS,
    YF_MAX_RETRIES,
    YF_RETRY_BASE_SECONDS,
)
from .db import SessionLocal
from .logging_config import get_logger, log_event

logger = get_logger("ingestion")

try:
    from yfinance.exceptions import YFRateLimitError
except ImportError:  # pragma: no cover - defensive for older yfinance builds
    class YFRateLimitError(Exception):
        pass

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

# Yahoo quoteType -> our asset_type.
QUOTE_TYPE_TO_ASSET = {
    "EQUITY": "stock",
    "ETF": "etf",
    "CURRENCY": "fx",
    "INDEX": "index",
    "CRYPTOCURRENCY": "crypto",
    "FUTURE": "metal",
    "COMMODITY": "metal",
}


def _tracked_symbols():
    """Symbols to fetch, from the `assets` table (with static-list fallback)."""
    try:
        assets = get_all_assets()
        if assets:
            return [a["symbol"] for a in assets]
    except Exception as e:
        logger.error("Could not read assets table (%s); falling back to static catalogue.", e)
    return [a["symbol"] for a in ALL_ASSETS]


def _download_history(symbol: str, period: str, retry_base: float = YF_RETRY_BASE_SECONDS):
    """Fetch one symbol's history, retrying with exponential backoff on rate limits."""
    attempt = 1
    while True:
        try:
            ticker = yf.Ticker(symbol)
            return ticker.history(period=period, interval="1d", auto_adjust=True)
        except YFRateLimitError:
            if attempt > YF_MAX_RETRIES:
                raise
            wait = retry_base * (2 ** (attempt - 1))
            logger.warning(
                "Rate limit hit for %s (attempt %d/%d). Waiting %.1fs...",
                symbol, attempt, YF_MAX_RETRIES, wait,
            )
            time.sleep(wait)
            attempt += 1


# Keys that indicate a *real* info payload (Yahoo returns all-null dicts for bad symbols).
_INFO_MEANINGFUL_KEYS = (
    "longName", "shortName", "quoteType", "regularMarketPrice",
    "marketCap", "currency", "exchange", "fiftyTwoWeekHigh",
)


def _info_is_meaningful(info):
    if not isinstance(info, dict) or not info:
        return False
    return any(info.get(k) is not None for k in _INFO_MEANINGFUL_KEYS)


def check_symbol(symbol: str):
    """Verify a symbol exists on Yahoo Finance using both yf.Ticker and yf.download.

    An asset is considered valid if **either** source returns data — this avoids
    false negatives when one path is rate limited or superficially empty.
    """
    info = None
    info_error = None
    try:
        info = yf.Ticker(symbol).info
        if not _info_is_meaningful(info):
            info = None
    except Exception as e:
        info = None
        info_error = f"{type(e).__name__}: {e}"

    df = None
    download_error = None
    try:
        df = yf.download(symbol, period="5d", interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty:
            df = None
    except Exception as e:
        df = None
        download_error = f"{type(e).__name__}: {e}"

    sources = []
    if info:
        sources.append("yf.Ticker.info")
    if df is not None:
        sources.append("yf.download")
    exists = bool(sources)

    name = None
    quote_type = None
    if info:
        name = info.get("longName") or info.get("shortName")
        quote_type = info.get("quoteType")

    latest_close = None
    if df is not None:
        try:
            close = df.xs("Close", axis=1, level=0) if isinstance(df.columns, pd.MultiIndex) else df["Close"]
            close = close.squeeze().dropna()
            if not close.empty:
                latest_close = float(close.iloc[-1])
        except Exception:
            latest_close = None

    note = None
    if not exists and (info_error or download_error):
        note = "Both sources failed. Ticker: %s; download: %s" % (
            info_error or "no error",
            download_error or "no error",
        )
    return {
        "symbol":         symbol,
        "exists":         exists,
        "confirmed_by":   sources,
        "name":           name,
        "suggested_type": QUOTE_TYPE_TO_ASSET.get(quote_type) if quote_type else None,
        "latest_close":   latest_close,
        "note":           note,
    }


def _fetch_and_store(symbol: str, period: str, retry_base: float = YF_RETRY_BASE_SECONDS) -> int:
    start = time.perf_counter()
    count = 0
    try:
        df = _download_history(symbol, period, retry_base)
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
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event(
            "ERROR",
            f"Failed to fetch/store {symbol} (period={period}, duration={duration_ms}ms): {type(e).__name__}: {e}",
            logger_name="ingestion",
            symbol=symbol,
            duration_ms=duration_ms,
            rows_written=count if count > 0 else None,
            success=False,
            exception=f"{type(e).__name__}: {e}",
        )
        raise


def backfill(symbol: str, retry_base: float = YF_RETRY_BASE_SECONDS) -> int:
    return _fetch_and_store(symbol, period="5y", retry_base=retry_base)


def ingest_daily(symbol: str) -> int:
    return _fetch_and_store(symbol, period="5d")


# How far before the 5-year window the stored data may start/end and still
# count as "covered" (tolerates weekends/holidays and multi-day backfills).
FULL_HISTORY_YEARS = 5
FULL_HISTORY_GRACE_DAYS = 14


def _has_full_history(coverage, symbol, target_start):
    cov = coverage.get(symbol)
    if cov is None or cov["count"] == 0 or cov["first_date"] is None:
        return False
    return cov["first_date"] <= target_start + timedelta(days=FULL_HISTORY_GRACE_DAYS)


def assets_missing_history(db=None):
    """Tracked assets whose stored history does not span ~5 years."""
    assets = get_all_assets(db)
    if not assets:
        try:
            assets = [{"symbol": a["symbol"], "name": a["name"],
                       "asset_type": "unknown", "properties": {}} for a in ALL_ASSETS]
        except Exception:
            pass
    coverage = get_history_coverage(db)
    target_start = date.today() - timedelta(days=365 * FULL_HISTORY_YEARS)
    missing = [
        a for a in assets
        if not _has_full_history(coverage, a["symbol"], target_start)
    ]
    logger.info("%d of %d tracked assets lack ~%dy of history.",
                len(missing), len(assets), FULL_HISTORY_YEARS)
    return missing


def _throttle(delay: float, jitter: float):
    if delay <= 0 and jitter <= 0:
        return
    time.sleep(delay + random.uniform(0, jitter))


def _backfill_symbols(symbols, delay: float, jitter: float, retry_base: float) -> dict:
    results = {}
    for i, symbol in enumerate(symbols):
        try:
            n = backfill(symbol, retry_base=retry_base)
            results[symbol] = n
        except Exception as e:
            results[symbol] = f"ERROR: {e}"
            logger.error("backfill failed for %s: %s", symbol, e)
        if i < len(symbols) - 1:
            _throttle(delay, jitter)
    logger.info("backfill run finished: %d assets", len(symbols))
    return results


def backfill_missing(
    delay: float = SLOW_BACKFILL_DELAY_SECONDS,
    jitter: float = SLOW_BACKFILL_JITTER_SECONDS,
    retry_base: float = SLOW_YF_RETRY_BASE_SECONDS,
):
    """Slow, extra-gentle backfill of only the assets missing ~5 years of history."""
    assets = assets_missing_history()
    symbols = [a["symbol"] for a in assets]
    logger.info("backfill_missing (slow mode) covering %d assets...", len(symbols))
    return _backfill_symbols(symbols, delay, jitter, retry_base)


def backfill_all(
    delay: float = BACKFILL_DELAY_SECONDS,
    jitter: float = BACKFILL_JITTER_SECONDS,
    retry_base: float = YF_RETRY_BASE_SECONDS,
):
    """Backfill every tracked asset with the normal (milder) throttle."""
    return _backfill_symbols(_tracked_symbols(), delay, jitter, retry_base)


def ingest_daily_all():
    symbols = _tracked_symbols()
    results = {}
    for i, symbol in enumerate(symbols):
        try:
            n = ingest_daily(symbol)
            results[symbol] = n
        except Exception as e:
            results[symbol] = f"ERROR: {e}"
            logger.error("ingest_daily failed for %s: %s", symbol, e)
        if i < len(symbols) - 1:
            _throttle(INGEST_DELAY_SECONDS, INGEST_JITTER_SECONDS)
    logger.info("ingest_daily_all finished: %d assets", len(symbols))
    return results