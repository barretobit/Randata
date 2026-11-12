"""Yahoo Finance client: daily history downloads, symbol checks and inception dates.

yfinance hides most errors by default and returns an empty table instead, so a
network failure looked exactly like "no data". Errors are switched on here;
only "no prices in this range" (holidays, weekends, a quiet gap) still counts
as an empty result.
"""

import time
from datetime import date, datetime, timezone

import pandas as pd
import yfinance as yf

from .config import YAHOO_MAX_RETRIES, YAHOO_RETRY_BASE_SECONDS
from .logging_config import get_logger

logger = get_logger("yahoo")

try:
    from yfinance.exceptions import YFPricesMissingError, YFRateLimitError
except ImportError:  # pragma: no cover - defensive for older yfinance builds
    class YFRateLimitError(Exception):
        pass

    class YFPricesMissingError(Exception):
        pass

yf.config.debug.hide_exceptions = False

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

# Keys that indicate a *real* info payload (Yahoo returns all-null dicts for bad symbols).
_INFO_MEANINGFUL_KEYS = (
    "longName", "shortName", "quoteType", "regularMarketPrice",
    "marketCap", "currency", "exchange", "fiftyTwoWeekHigh",
)


def with_rate_limit_retry(action, symbol: str, retry_base: float = YAHOO_RETRY_BASE_SECONDS):
    """Run one Yahoo request, retrying with exponential backoff on rate limits."""
    attempt = 1
    while True:
        try:
            return action()
        except YFRateLimitError:
            if attempt > YAHOO_MAX_RETRIES:
                raise
            wait_seconds = retry_base * (2 ** (attempt - 1))
            logger.warning(
                "Rate limit hit for %s (attempt %d/%d). Waiting %.1fs...",
                symbol, attempt, YAHOO_MAX_RETRIES, wait_seconds,
            )
            time.sleep(wait_seconds)
            attempt += 1


def download(
    symbol: str,
    retry_base: float = YAHOO_RETRY_BASE_SECONDS,
    period: str = None,
    start: date = None,
    end: date = None,
) -> pd.DataFrame:
    """Daily split- and dividend-adjusted bars for a `period` (e.g. "10y") or for [start, end).

    Returns an empty frame when Yahoo has no prices for the request. Any other
    failure (network, unknown symbol, adjustment error) raises.
    """
    if period is not None:
        history_range = {"period": period}
    elif start is not None and end is not None:
        history_range = {"start": start.isoformat(), "end": end.isoformat()}
    else:
        raise ValueError("Provide either a history period or a start/end date range.")

    def request():
        try:
            return yf.Ticker(symbol).history(interval="1d", auto_adjust=True, **history_range)
        except YFPricesMissingError:
            return pd.DataFrame()

    return with_rate_limit_retry(request, symbol, retry_base)


def _info_is_meaningful(info) -> bool:
    if not isinstance(info, dict) or not info:
        return False
    return any(info.get(key) is not None for key in _INFO_MEANINGFUL_KEYS)


def inception_from_info(info) -> date | None:
    """An asset's first-trade date from a Yahoo `info` payload, or None.

    Yahoo exposes the first trade as epoch seconds (`firstTradeDateEpochUtc`) or
    milliseconds (`firstTradeDateMilliseconds`), depending on the payload/version.
    This is only a hint: for fx/crypto/index the value can be the data
    provider's start rather than a true listing date.
    """
    if not isinstance(info, dict):
        return None
    epoch = info.get("firstTradeDateEpochUtc")
    if epoch is None:
        milliseconds = info.get("firstTradeDateMilliseconds")
        if milliseconds is None:
            return None
        epoch = float(milliseconds) / 1000.0
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).date()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def fetch_inception_date(symbol: str, retry_base: float = YAHOO_RETRY_BASE_SECONDS) -> date | None:
    """A symbol's first-trade date from Yahoo, or None if unavailable."""
    try:
        info = with_rate_limit_retry(lambda: yf.Ticker(symbol).info, symbol, retry_base)
    except YFRateLimitError:
        raise
    except Exception as error:
        logger.warning("Could not fetch inception date for %s: %s", symbol, error)
        return None
    return inception_from_info(info)


def check_symbol(symbol: str) -> dict:
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
    except Exception as error:
        info = None
        info_error = f"{type(error).__name__}: {error}"

    frame = None
    download_error = None
    try:
        frame = yf.download(symbol, period="5d", interval="1d", progress=False, auto_adjust=True)
        if frame is None or frame.empty:
            frame = None
    except Exception as error:
        frame = None
        download_error = f"{type(error).__name__}: {error}"

    sources = []
    if info:
        sources.append("yf.Ticker.info")
    if frame is not None:
        sources.append("yf.download")
    exists = bool(sources)

    name = None
    quote_type = None
    inception_date = None
    if info:
        name = info.get("longName") or info.get("shortName")
        quote_type = info.get("quoteType")
        inception_date = inception_from_info(info)

    latest_close = None
    if frame is not None:
        try:
            if isinstance(frame.columns, pd.MultiIndex):
                close = frame.xs("Close", axis=1, level=0)
            else:
                close = frame["Close"]
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
