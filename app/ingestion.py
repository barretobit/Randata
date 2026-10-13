import random
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import yfinance as yf
from sqlalchemy import text

from .asset_repo import (
    get_all_assets,
    get_assets_missing_inception,
    get_history_coverage,
    set_inception_date,
)
from .config import (
    BACKFILL_DELAY_SECONDS,
    BACKFILL_JITTER_SECONDS,
    HISTORY_GRACE_DAYS,
    HISTORY_YEARS,
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
    """Symbols to fetch, from the `assets` table."""
    try:
        assets = get_all_assets()
        return [a["symbol"] for a in assets] if assets else []
    except Exception as e:
        logger.error("Could not read assets table (%s); nothing to fetch.", e)
        return []


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


def _inception_from_info(info):
    """Extract an asset's first-trade date from a Yahoo `info` payload.

    Yahoo exposes `firstTradeDateEpochUtc` (epoch seconds). Returns a `date` or
    None when unavailable. This is only a hint — for fx/crypto/index the value
    can be the data provider's start rather than a true listing date.
    """
    if not isinstance(info, dict):
        return None
    epoch = info.get("firstTradeDateEpochUtc")
    if epoch is None:
        return None
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).date()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


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
    inception_date = None
    if info:
        name = info.get("longName") or info.get("shortName")
        quote_type = info.get("quoteType")
        inception_date = _inception_from_info(info)

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
        "inception_date": inception_date,
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
    return _fetch_and_store(symbol, period=f"{HISTORY_YEARS}y", retry_base=retry_base)


def ingest_daily(symbol: str) -> int:
    return _fetch_and_store(symbol, period="5d")


def _window_start(today=None):
    """Start of the rolling fetch window (today minus HISTORY_YEARS)."""
    today = today or date.today()
    return today - timedelta(days=365 * HISTORY_YEARS)


def _expected_start(asset, window_start):
    """Earliest date we can reasonably expect history for.

    Assets that started trading after the window began only need history since
    their inception, so we look no further back than that. Without a known
    inception we fall back to the full window.
    """
    inception = asset.get("inception_date")
    if inception is not None and inception > window_start:
        return inception
    return window_start


def _has_full_history(asset, coverage, window_start):
    cov = coverage.get(asset["symbol"])
    if cov is None or cov["count"] == 0 or cov["first_date"] is None:
        return False
    expected = _expected_start(asset, window_start)
    return cov["first_date"] <= expected + timedelta(days=HISTORY_GRACE_DAYS)


def assets_missing_history(db=None):
    """Tracked assets whose stored history does not reach their expected start.

    The expected start is the rolling HISTORY_YEARS window, unless the asset's
    inception date is later — in which case only history since inception is
    required. This keeps genuinely young instruments out of the re-fetch loop.
    """
    assets = get_all_assets(db) or []
    coverage = get_history_coverage(db)
    window_start = _window_start()
    missing = [
        a for a in assets
        if not _has_full_history(a, coverage, window_start)
    ]
    logger.info("%d of %d tracked assets lack history back to their expected start (~%dy window).",
                len(missing), len(assets), HISTORY_YEARS)
    return missing


def fetch_inception_date(symbol: str, retry_base: float = YF_RETRY_BASE_SECONDS):
    """Fetch a symbol's first-trade date from Yahoo, or None if unavailable."""
    attempt = 1
    while True:
        try:
            info = yf.Ticker(symbol).info
            return _inception_from_info(info)
        except YFRateLimitError:
            if attempt > YF_MAX_RETRIES:
                raise
            wait = retry_base * (2 ** (attempt - 1))
            logger.warning(
                "Rate limit hit fetching inception for %s (attempt %d/%d). Waiting %.1fs...",
                symbol, attempt, YF_MAX_RETRIES, wait,
            )
            time.sleep(wait)
            attempt += 1
        except Exception as e:
            logger.warning("Could not fetch inception date for %s: %s", symbol, e)
            return None


def backfill_inception_dates(
    delay: float = SLOW_BACKFILL_DELAY_SECONDS,
    jitter: float = SLOW_BACKFILL_JITTER_SECONDS,
    retry_base: float = SLOW_YF_RETRY_BASE_SECONDS,
) -> dict:
    """Capture the inception date for every asset that does not have one yet."""
    assets = get_assets_missing_inception() or []
    results = {}
    for i, asset in enumerate(assets):
        symbol = asset["symbol"]
        try:
            inception = fetch_inception_date(symbol, retry_base=retry_base)
            if inception is not None:
                set_inception_date(symbol, inception)
            results[symbol] = str(inception) if inception is not None else None
        except Exception as e:
            results[symbol] = f"ERROR: {e}"
            logger.error("inception backfill failed for %s: %s", symbol, e)
        if i < len(assets) - 1:
            _throttle(delay, jitter)
    logger.info("inception backfill finished: %d assets", len(assets))
    return results


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
    """Slow, extra-gentle backfill of only the assets missing their expected history."""
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