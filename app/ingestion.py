import math
import random
import statistics
import time
import zlib
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import yfinance as yf
from sqlalchemy import text

from .asset_repo import (
    get_all_assets,
    get_all_price_bars,
    get_assets_missing_inception,
    get_history_coverage,
    get_history_gaps,
    set_inception_date,
)
from .config import (
    BACKFILL_DELAY_SECONDS,
    BACKFILL_JITTER_SECONDS,
    HISTORY_AUDIT_CYCLE_DAYS,
    HISTORY_REPAIR_MAX_RANGES_PER_NIGHT,
    HISTORY_GRACE_DAYS,
    HISTORY_YEARS,
    INGEST_OVERLAP_DAYS,
    INGEST_DELAY_SECONDS,
    INGEST_JITTER_SECONDS,
    PRICE_OUTLIER_MIN_RETURN,
    PRICE_OUTLIER_MIN_SAMPLES,
    PRICE_OUTLIER_SIGMA,
    PRICE_HARD_MAX_RETURN,
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


def _download_history_range(
    symbol: str, start: date, end: date, retry_base: float = YF_RETRY_BASE_SECONDS
):
    """Fetch daily bars for [start, end), retrying with exponential backoff."""
    attempt = 1
    while True:
        try:
            ticker = yf.Ticker(symbol)
            return ticker.history(
                start=start.isoformat(),
                end=end.isoformat(),
                interval="1d",
                auto_adjust=True,
            )
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

    Yahoo exposes the first trade as epoch seconds (`firstTradeDateEpochUtc`) or
    milliseconds (`firstTradeDateMilliseconds`), depending on the payload/version.
    Returns a `date` or None when unavailable. This is only a hint — for
    fx/crypto/index the value can be the data provider's start rather than a true
    listing date.
    """
    if not isinstance(info, dict):
        return None
    epoch = info.get("firstTradeDateEpochUtc")
    if epoch is None:
        millis = info.get("firstTradeDateMilliseconds")
        if millis is None:
            return None
        epoch = float(millis) / 1000.0
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


def _finite_number(value):
    if pd.isna(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _valid_ohlc(values):
    try:
        open_price, high, low, close = (float(value) for value in values)
    except (TypeError, ValueError, OverflowError):
        return False
    tolerance = 0.005
    return (
        all(math.isfinite(value) and value > 0 for value in (open_price, high, low, close))
        and low <= high
        and low * (1 - tolerance) <= open_price <= high * (1 + tolerance)
        and low * (1 - tolerance) <= close <= high * (1 + tolerance)
    )


def _return_threshold(returns, elapsed_days=1):
    if len(returns) < PRICE_OUTLIER_MIN_SAMPLES:
        return None
    center = statistics.median(returns)
    mad = statistics.median(abs(value - center) for value in returns)
    gap_scale = math.sqrt(max(1, elapsed_days - 2))
    return max(
        PRICE_OUTLIER_SIGMA * 1.4826 * mad * gap_scale,
        PRICE_OUTLIER_MIN_RETURN * gap_scale,
    ), center


def _is_suspicious_return(value, returns, elapsed_days=1):
    if abs(value) > PRICE_HARD_MAX_RETURN:
        return True
    threshold = _return_threshold(returns, elapsed_days)
    return threshold is not None and abs(value - threshold[1]) > threshold[0]


def _bar_values(row):
    return tuple(
        _finite_number(row[name]) for name in ("Open", "High", "Low", "Close")
    )


def _fetch_and_store(
    symbol: str,
    period: str = None,
    retry_base: float = YF_RETRY_BASE_SECONDS,
    start_date: date = None,
    end_date: date = None,
) -> int:
    start = time.perf_counter()
    count = 0
    period_label = period or f"{start_date}..{end_date}"
    try:
        if start_date is not None and end_date is not None:
            df = _download_history_range(symbol, start_date, end_date, retry_base)
        elif period is not None:
            df = _download_history(symbol, period, retry_base)
        else:
            raise ValueError("Provide either a history period or a start/end date range.")
        if df is None or df.empty:
            logger.info("No data returned for %s (period=%s)", symbol, period_label)
            return 0
        db = SessionLocal()
        try:
            first_date = df.index.min().date()
            prior_rows = db.execute(
                text(
                    "SELECT date, close FROM daily_prices "
                    "WHERE symbol = :symbol AND date < :before "
                    "ORDER BY date DESC LIMIT 61"
                ),
                {"symbol": symbol, "before": first_date},
            ).fetchall()
            closes = [
                (row.date, float(row.close))
                for row in reversed(prior_rows)
                if row.close is not None and _finite_number(row.close) is not None
            ]
            returns = [
                current / previous - 1
                for (previous_date, previous), (current_date, current) in zip(closes, closes[1:])
                if previous > 0 and current > 0
                and (current_date - previous_date).days <= 4
            ][-60:]

            for ts, row in df.sort_index().iterrows():
                open_price, high, low, close = _bar_values(row)
                if not _valid_ohlc((open_price, high, low, close)):
                    message = f"Skipped invalid OHLC bar for {symbol} on {ts.date()}."
                    logger.warning(message)
                    log_event("WARNING", message, logger_name="ingestion", symbol=symbol, success=False)
                    continue

                previous_close = closes[-1][1] if closes else None
                if previous_close is not None and previous_close > 0 and close > 0:
                    daily_return = close / previous_close - 1
                    elapsed_days = (ts.date() - closes[-1][0]).days
                    if abs(daily_return) > PRICE_HARD_MAX_RETURN:
                        message = (
                            f"Skipped extreme price move for {symbol} on {ts.date()}: "
                            f"return {daily_return:.2%} exceeds the "
                            f"{PRICE_HARD_MAX_RETURN:.0%} hard limit."
                        )
                        logger.warning(message)
                        log_event(
                            "WARNING", message, logger_name="ingestion",
                            symbol=symbol, success=False,
                        )
                        continue
                    return_limits = _return_threshold(returns, elapsed_days)
                    if return_limits is not None:
                        threshold, center = return_limits
                        if abs(daily_return - center) > threshold:
                            message = (
                                f"Skipped suspicious price for {symbol} on {ts.date()}: "
                                f"return {daily_return:.2%}, recent median {center:.2%}, "
                                f"threshold {threshold:.2%}."
                            )
                            logger.warning(message)
                            log_event(
                                "WARNING", message, logger_name="ingestion",
                                symbol=symbol, success=False,
                            )
                            continue
                    if elapsed_days <= 4:
                        returns.append(daily_return)
                        returns = returns[-60:]

                closes.append((ts.date(), close))
                db.execute(UPSERT_SQL, {
                    "symbol": symbol,
                    "date":   ts.date(),
                    "open":   open_price,
                    "high":   high,
                    "low":    low,
                    "close":  close,
                    "volume": int(_finite_number(row["Volume"])) if _finite_number(row["Volume"]) is not None else None,
                })
                count += 1
            db.commit()
        finally:
            db.close()
        logger.info("Stored %d rows for %s (period=%s)", count, symbol, period_label)
        return count
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event(
            "ERROR",
            f"Failed to fetch/store {symbol} (period={period_label}, duration={duration_ms}ms): {type(e).__name__}: {e}",
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
    db = SessionLocal()
    try:
        latest = db.execute(
            text("SELECT MAX(date) AS latest_date FROM daily_prices WHERE symbol = :symbol"),
            {"symbol": symbol},
        ).scalar()
    finally:
        db.close()
    start = latest - timedelta(days=INGEST_OVERLAP_DAYS) if latest else _window_start()
    return _fetch_and_store(
        symbol,
        retry_base=YF_RETRY_BASE_SECONDS,
        start_date=start,
        end_date=date.today() + timedelta(days=1),
    )


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


def _history_audit_due(symbol: str, today: date) -> bool:
    cycle_days = max(1, HISTORY_AUDIT_CYCLE_DAYS)
    cycle_day = (today - date(2000, 1, 1)).days % cycle_days
    symbol_day = zlib.crc32(symbol.encode("utf-8")) % cycle_days
    return cycle_day == symbol_day


def _find_suspicious_bars(bars):
    suspicious = set()
    returns = []
    previous = None
    for bar in bars:
        values = (bar["open"], bar["high"], bar["low"], bar["close"])
        if not _valid_ohlc(values):
            suspicious.add(bar["date"])
            continue
        close = float(bar["close"])
        if previous is not None:
            previous_date, previous_close = previous
            elapsed_days = (bar["date"] - previous_date).days
            if previous_close > 0 and close > 0:
                daily_return = close / previous_close - 1
                if _is_suspicious_return(daily_return, returns, elapsed_days):
                    suspicious.add(bar["date"])
                elif elapsed_days <= 4:
                    returns.append(daily_return)
                    returns = returns[-60:]
        previous = (bar["date"], close)
    return sorted(suspicious)


def _date_clusters(dates, max_gap_days=60):
    clusters = []
    for item in dates:
        if not clusters or (item - clusters[-1][-1]).days > max_gap_days:
            clusters.append([item])
        else:
            clusters[-1].append(item)
    return clusters


def _repair_cluster(symbol, target_dates, retry_base):
    start_date = target_dates[0] - timedelta(days=90)
    end_date = target_dates[-1] + timedelta(days=4)
    frame = _download_history_range(symbol, start_date, end_date, retry_base)
    if frame is None or frame.empty:
        raise ValueError(f"Yahoo returned no history for {symbol} audit range.")

    frame = frame.sort_index()
    yahoo_bars = {}
    yahoo_returns = []
    previous = None
    for timestamp, row in frame.iterrows():
        bar_date = timestamp.date()
        values = _bar_values(row)
        if not _valid_ohlc(values):
            previous = None
            continue
        open_price, high, low, close = values
        yahoo_bars[bar_date] = {
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": _finite_number(row["Volume"]),
        }
        if previous is not None:
            previous_date, previous_close = previous
            elapsed_days = (bar_date - previous_date).days
            if previous_close > 0 and close > 0 and elapsed_days <= 4:
                yahoo_returns.append(close / previous_close - 1)
        previous = (bar_date, close)

    repaired = unresolved = 0
    frame_dates = [timestamp.date() for timestamp in frame.index]
    db = SessionLocal()
    try:
        for target_date in target_dates:
            candidate = yahoo_bars.get(target_date)
            if candidate is None:
                unresolved += 1
                message = (
                    f"History audit could not repair {symbol} on {target_date}: "
                    "Yahoo returned no valid bar for that date."
                )
                logger.warning(message)
                log_event("WARNING", message, logger_name="ingestion", symbol=symbol, success=False)
                continue

            position = frame_dates.index(target_date)
            candidate_is_suspicious = False
            adjacent_returns = []
            if position > 0:
                previous_row = frame.iloc[position - 1]
                previous_close = _finite_number(previous_row["Close"])
                previous_date = frame_dates[position - 1]
                if previous_close and previous_close > 0:
                    elapsed = (target_date - previous_date).days
                    if elapsed <= 4:
                        adjacent_returns.append((candidate["close"] / previous_close - 1, elapsed))
            if position + 1 < len(frame_dates):
                next_row = frame.iloc[position + 1]
                next_close = _finite_number(next_row["Close"])
                next_date = frame_dates[position + 1]
                if next_close and next_close > 0:
                    elapsed = (next_date - target_date).days
                    if elapsed <= 4:
                        adjacent_returns.append((next_close / candidate["close"] - 1, elapsed))

            for candidate_return, elapsed in adjacent_returns:
                comparison_returns = yahoo_returns.copy()
                if candidate_return in comparison_returns:
                    comparison_returns.remove(candidate_return)
                if _is_suspicious_return(candidate_return, comparison_returns, elapsed):
                    candidate_is_suspicious = True
                    break

            if candidate_is_suspicious:
                unresolved += 1
                message = (
                    f"History audit found a suspicious bar for {symbol} on {target_date}; "
                    "Yahoo context also contains an abnormal move, so stored data was left unchanged."
                )
                logger.warning(message)
                log_event("WARNING", message, logger_name="ingestion", symbol=symbol, success=False)
                continue

            db.execute(
                UPSERT_SQL,
                {
                    "symbol": symbol,
                    "date": target_date,
                    **candidate,
                    "volume": int(candidate["volume"]) if candidate["volume"] is not None else None,
                },
            )
            repaired += 1
            message = f"History audit repaired {symbol} on {target_date} from validated Yahoo history."
            logger.info(message)
            log_event("INFO", message, logger_name="ingestion", symbol=symbol, success=True)
        db.commit()
    finally:
        db.close()
    return repaired, unresolved


def audit_and_repair_history(
    delay: float = INGEST_DELAY_SECONDS,
    jitter: float = INGEST_JITTER_SECONDS,
    retry_base: float = YF_RETRY_BASE_SECONDS,
):
    """Scan stored bars nightly and repair anomalies when Yahoo confirms valid context."""
    bars_by_symbol = {}
    for bar in get_all_price_bars():
        bars_by_symbol.setdefault(bar["symbol"], []).append(bar)

    candidates = {
        symbol: _find_suspicious_bars(bars)
        for symbol, bars in bars_by_symbol.items()
    }
    candidates = {symbol: dates for symbol, dates in candidates.items() if dates}
    cycle_days = max(1, HISTORY_AUDIT_CYCLE_DAYS)
    cycle_slot = date.today().toordinal() % cycle_days
    clusters = [
        (symbol, cluster)
        for symbol, dates in candidates.items()
        for cluster in _date_clusters(dates)
        if zlib.crc32(f"{symbol}:{cluster[0]}".encode("utf-8")) % cycle_days == cycle_slot
    ]
    max_ranges = max(1, HISTORY_REPAIR_MAX_RANGES_PER_NIGHT)
    if len(clusters) > max_ranges:
        clusters.sort(
            key=lambda item: zlib.crc32(
                f"{date.today()}:{item[0]}:{item[1][0]}".encode("utf-8")
            )
        )
    scheduled = clusters[:max_ranges]
    repaired = unresolved = 0
    for index, (symbol, cluster) in enumerate(scheduled):
        try:
            cluster_repaired, cluster_unresolved = _repair_cluster(symbol, cluster, retry_base)
            repaired += cluster_repaired
            unresolved += cluster_unresolved
        except Exception as e:
            unresolved += len(cluster)
            logger.error("History audit failed for %s: %s", symbol, e)
            log_event(
                "ERROR", f"History audit failed for {symbol}: {type(e).__name__}: {e}",
                logger_name="ingestion", symbol=symbol, success=False,
                exception=f"{type(e).__name__}: {e}",
            )
        if index < len(scheduled) - 1:
            _throttle(delay, jitter)
    deferred = len(clusters) - len(scheduled)
    logger.info(
        "History audit finished: checked %d assets, found %d suspicious bars, repaired %d; "
        "%d candidates require review, %d audit ranges deferred by the nightly limit.",
        len(bars_by_symbol), sum(map(len, candidates.values())), repaired, unresolved, deferred,
    )
    return {"repaired": repaired, "unresolved": unresolved, "deferred": deferred}


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
    assets = get_all_assets() or []
    coverage = get_history_coverage()
    gaps_by_symbol = {}
    for gap in get_history_gaps():
        gaps_by_symbol.setdefault(gap["symbol"], []).append(gap)

    today = date.today()
    window_start = _window_start(today)
    results = {}
    for i, asset in enumerate(assets):
        symbol = asset["symbol"]
        try:
            history = coverage.get(symbol)
            needs_initial_backfill = history is None or history["count"] == 0
            audit_due = _history_audit_due(symbol, today)
            has_full_history = _has_full_history(asset, coverage, window_start)
            if needs_initial_backfill or audit_due:
                n = backfill(symbol)
            else:
                if not has_full_history:
                    logger.info(
                        "%s starts later than expected; full-history audit remains scheduled "
                        "on its rotation.",
                        symbol,
                    )
                n = 0
                for gap in gaps_by_symbol.get(symbol, []):
                    n += _fetch_and_store(
                        symbol,
                        retry_base=YF_RETRY_BASE_SECONDS,
                        start_date=gap["start"],
                        end_date=gap["end"],
                    )
                n += ingest_daily(symbol)
            results[symbol] = n
        except Exception as e:
            results[symbol] = f"ERROR: {e}"
            logger.error("ingest_daily failed for %s: %s", symbol, e)
        if i < len(assets) - 1:
            _throttle(INGEST_DELAY_SECONDS, INGEST_JITTER_SECONDS)
    logger.info("ingest_daily_all finished: %d assets", len(assets))
    audit_and_repair_history()
    return results