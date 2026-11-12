"""Yahoo Finance ingestion: backfills, nightly updates and history self-healing.

Every fetched bar passes two checks before it is stored:

1. Structure: open, high, low and close are positive, finite and consistent.
2. Spikes: a bar whose close jumps away and comes straight back (an isolated
   provider glitch) is skipped. Real moves such as earnings gaps, crashes or
   rallies persist on the following days and are kept.
"""

import math
import random
import statistics
import threading
import time
import zlib
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import yfinance as yf
from sqlalchemy import text

from .asset_repo import (
    get_all_assets,
    get_assets_missing_inception,
    get_history_coverage,
    get_history_gaps,
    get_price_bars,
    get_stored_symbols,
    set_inception_date,
)
from .config import (
    BACKFILL_DELAY_SECONDS,
    BACKFILL_JITTER_SECONDS,
    HISTORY_AUDIT_CYCLE_DAYS,
    HISTORY_GRACE_DAYS,
    HISTORY_REPAIR_MAX_RANGES_PER_NIGHT,
    HISTORY_YEARS,
    INGEST_DELAY_SECONDS,
    INGEST_JITTER_SECONDS,
    INGEST_OVERLAP_DAYS,
    PRICE_HARD_MAX_RETURN,
    PRICE_OUTLIER_MIN_RETURN,
    PRICE_OUTLIER_MIN_SAMPLES,
    PRICE_OUTLIER_SIGMA,
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

# How many recent close-to-close moves are used to judge whether a new move is abnormal.
RECENT_MOVES_WINDOW = 60
# Moves across a weekend plus a holiday still count as one daily move.
MAX_DAILY_MOVE_GAP_DAYS = 4
# Stored and freshly fetched closes for the same days differing by more than
# this ratio means Yahoo re-adjusted the history (split or dividend).
READJUSTMENT_TOLERANCE = 0.001


class IngestionAlreadyRunning(RuntimeError):
    """Raised when a bulk Yahoo job starts while another one is still running."""


# shortcut: guards one process only; with several workers, switch to a database lock (MySQL GET_LOCK).
_bulk_job_lock = threading.Lock()


@contextmanager
def _exclusive_bulk_job(job_name: str):
    """Run at most one bulk job (nightly ingestion, full backfills) at a time."""
    if not _bulk_job_lock.acquire(blocking=False):
        raise IngestionAlreadyRunning(
            f"Cannot start {job_name}: another ingestion or backfill job is still running."
        )
    try:
        yield
    finally:
        _bulk_job_lock.release()


def _tracked_symbols():
    """Symbols to fetch, from the `assets` table."""
    try:
        return [asset["symbol"] for asset in get_all_assets()]
    except Exception as error:
        logger.error("Could not read assets table (%s); nothing to fetch.", error)
        return []


def _with_rate_limit_retry(action, symbol: str, retry_base: float):
    """Run one Yahoo request, retrying with exponential backoff on rate limits."""
    attempt = 1
    while True:
        try:
            return action()
        except YFRateLimitError:
            if attempt > YF_MAX_RETRIES:
                raise
            wait_seconds = retry_base * (2 ** (attempt - 1))
            logger.warning(
                "Rate limit hit for %s (attempt %d/%d). Waiting %.1fs...",
                symbol, attempt, YF_MAX_RETRIES, wait_seconds,
            )
            time.sleep(wait_seconds)
            attempt += 1


def _download(
    symbol: str,
    retry_base: float = YF_RETRY_BASE_SECONDS,
    period: str = None,
    start: date = None,
    end: date = None,
):
    """Daily bars for a `period` (e.g. "10y") or for the range [start, end)."""
    if period is not None:
        history_range = {"period": period}
    elif start is not None and end is not None:
        history_range = {"start": start.isoformat(), "end": end.isoformat()}
    else:
        raise ValueError("Provide either a history period or a start/end date range.")
    return _with_rate_limit_retry(
        lambda: yf.Ticker(symbol).history(interval="1d", auto_adjust=True, **history_range),
        symbol,
        retry_base,
    )


# Keys that indicate a *real* info payload (Yahoo returns all-null dicts for bad symbols).
_INFO_MEANINGFUL_KEYS = (
    "longName", "shortName", "quoteType", "regularMarketPrice",
    "marketCap", "currency", "exchange", "fiftyTwoWeekHigh",
)


def _info_is_meaningful(info):
    if not isinstance(info, dict) or not info:
        return False
    return any(info.get(key) is not None for key in _INFO_MEANINGFUL_KEYS)


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
        milliseconds = info.get("firstTradeDateMilliseconds")
        if milliseconds is None:
            return None
        epoch = float(milliseconds) / 1000.0
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
        inception_date = _inception_from_info(info)

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


# ---------------------------------------------------------------------------
# Bar validation
# ---------------------------------------------------------------------------

def _finite_number(value):
    if value is None or pd.isna(value):
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


def _is_abnormal_move(move, recent_moves, elapsed_days=1):
    """Whether a close-to-close move is far outside the asset's recent behaviour.

    Uses a robust z-score: the median absolute deviation of recent moves, scaled
    to a standard deviation (x1.4826). The limit widens with the square root of
    the trading days elapsed, and never drops below PRICE_OUTLIER_MIN_RETURN.
    """
    if abs(move) > PRICE_HARD_MAX_RETURN:
        return True
    if len(recent_moves) < PRICE_OUTLIER_MIN_SAMPLES:
        return False
    typical_move = statistics.median(recent_moves)
    deviation = statistics.median(abs(value - typical_move) for value in recent_moves)
    gap_scale = math.sqrt(max(1, elapsed_days - 2))
    limit = max(
        PRICE_OUTLIER_SIGMA * 1.4826 * deviation * gap_scale,
        PRICE_OUTLIER_MIN_RETURN * gap_scale,
    )
    return abs(move - typical_move) > limit


def _find_price_spikes(closes):
    """Indexes of isolated spikes in a chronological list of (date, close) pairs.

    A spike jumps abnormally away from the previous kept close, then the next
    close comes back at least halfway with another abnormal move. A real move
    stays at its new level, so it is kept. The last bar has no next bar to
    confirm a reversal, so it is only rejected above the hard move limit; the
    nightly overlap window re-checks it once the next bar exists.
    """
    spikes = set()
    if not closes:
        return spikes
    recent_moves = []
    previous_date, previous_close = closes[0]
    for index in range(1, len(closes)):
        bar_date, close = closes[index]
        move_in = close / previous_close - 1
        elapsed_days = (bar_date - previous_date).days
        if index + 1 < len(closes):
            next_date, next_close = closes[index + 1]
            comes_back = abs(next_close / previous_close - 1) < abs(move_in) / 2
            is_spike = (
                comes_back
                and _is_abnormal_move(move_in, recent_moves, elapsed_days)
                and _is_abnormal_move(next_close / close - 1, recent_moves, (next_date - bar_date).days)
            )
        else:
            is_spike = abs(move_in) > PRICE_HARD_MAX_RETURN
        if is_spike:
            spikes.add(index)
            continue
        if elapsed_days <= MAX_DAILY_MOVE_GAP_DAYS:
            recent_moves.append(move_in)
            recent_moves = recent_moves[-RECENT_MOVES_WINDOW:]
        previous_date, previous_close = bar_date, close
    return spikes


def _bar_values(row):
    return tuple(
        _finite_number(row[name]) for name in ("Open", "High", "Low", "Close")
    )


def _log_skipped_bar(symbol, message):
    logger.warning(message)
    log_event("WARNING", message, logger_name="ingestion", symbol=symbol, success=False)


def _valid_frame_bars(symbol, frame, log_skipped=True):
    """Yahoo frame rows as upsert-ready bar dicts, without structurally invalid rows."""
    bars = []
    for timestamp, row in frame.sort_index().iterrows():
        values = _bar_values(row)
        if not _valid_ohlc(values):
            if log_skipped:
                _log_skipped_bar(symbol, f"Skipped invalid OHLC bar for {symbol} on {timestamp.date()}.")
            continue
        open_price, high, low, close = values
        volume = _finite_number(row["Volume"])
        bars.append({
            "symbol": symbol,
            "date":   timestamp.date(),
            "open":   open_price,
            "high":   high,
            "low":    low,
            "close":  close,
            "volume": int(volume) if volume is not None else None,
        })
    return bars


# ---------------------------------------------------------------------------
# Fetch and store
# ---------------------------------------------------------------------------

def _store_frame(symbol, frame) -> int:
    """Validate a Yahoo frame against the stored bars before it and upsert the good bars."""
    bars = _valid_frame_bars(symbol, frame)
    if not bars:
        return 0
    db = SessionLocal()
    try:
        prior_rows = db.execute(
            text(
                "SELECT date, close FROM daily_prices "
                "WHERE symbol = :symbol AND date < :before "
                "ORDER BY date DESC LIMIT :limit"
            ),
            {"symbol": symbol, "before": bars[0]["date"], "limit": RECENT_MOVES_WINDOW + 1},
        ).fetchall()
        prior_closes = [
            (row.date, float(row.close))
            for row in reversed(prior_rows)
            if row.close is not None and row.close > 0
        ]
        spikes = _find_price_spikes(prior_closes + [(bar["date"], bar["close"]) for bar in bars])
        bars_to_store = []
        for offset, bar in enumerate(bars):
            if len(prior_closes) + offset in spikes:
                _log_skipped_bar(
                    symbol,
                    f"Skipped price spike for {symbol} on {bar['date']}: close {bar['close']} "
                    "jumps away from its neighbours and straight back.",
                )
                continue
            bars_to_store.append(bar)
        if bars_to_store:
            db.execute(UPSERT_SQL, bars_to_store)
            db.commit()
    finally:
        db.close()
    return len(bars_to_store)


@contextmanager
def _logged_failure(symbol: str, label: str):
    """Record a failed fetch in api_logs (with its duration), then re-raise."""
    started = time.perf_counter()
    try:
        yield
    except Exception as error:
        duration_ms = int((time.perf_counter() - started) * 1000)
        error_text = f"{type(error).__name__}: {error}"
        log_event(
            "ERROR",
            f"Failed to fetch/store {symbol} ({label}, duration={duration_ms}ms): {error_text}",
            logger_name="ingestion",
            symbol=symbol,
            duration_ms=duration_ms,
            success=False,
            exception=error_text,
        )
        raise


def _fetch_and_store(
    symbol: str,
    retry_base: float = YF_RETRY_BASE_SECONDS,
    period: str = None,
    start_date: date = None,
    end_date: date = None,
) -> int:
    label = f"period={period}" if period else f"{start_date}..{end_date}"
    with _logged_failure(symbol, label):
        frame = _download(symbol, retry_base, period=period, start=start_date, end=end_date)
        if frame is None or frame.empty:
            logger.info("No data returned for %s (%s)", symbol, label)
            return 0
        rows_written = _store_frame(symbol, frame)
    logger.info("Stored %d rows for %s (%s)", rows_written, symbol, label)
    return rows_written


def backfill(symbol: str, retry_base: float = YF_RETRY_BASE_SECONDS) -> int:
    """Fetch and store the full HISTORY_YEARS window for one symbol."""
    return _fetch_and_store(symbol, retry_base, period=f"{HISTORY_YEARS}y")


def _history_was_readjusted(symbol, frame) -> bool:
    """True when Yahoo's closes for already stored days all moved by the same ratio.

    With auto_adjust, a split or dividend rescales every earlier close. The
    stored rows then sit on the old scale, so the whole window must be
    re-fetched instead of appended to. The newest stored day is ignored: it may
    still have been an open trading day when it was stored.
    """
    fetched_closes = {
        timestamp.date(): _finite_number(close) for timestamp, close in frame["Close"].items()
    }
    db = SessionLocal()
    try:
        stored_rows = db.execute(
            text(
                "SELECT date, close FROM daily_prices "
                "WHERE symbol = :symbol AND date >= :start ORDER BY date"
            ),
            {"symbol": symbol, "start": min(fetched_closes)},
        ).fetchall()
    finally:
        db.close()
    ratios = [
        fetched_closes[row.date] / float(row.close) - 1
        for row in stored_rows[:-1]
        if row.close and fetched_closes.get(row.date)
    ]
    return len(ratios) >= 2 and abs(statistics.median(ratios)) > READJUSTMENT_TOLERANCE


def ingest_daily(symbol: str) -> int:
    """Fetch new bars, re-fetching the last INGEST_OVERLAP_DAYS stored days for late corrections."""
    db = SessionLocal()
    try:
        latest = db.execute(
            text("SELECT MAX(date) FROM daily_prices WHERE symbol = :symbol"),
            {"symbol": symbol},
        ).scalar()
    finally:
        db.close()
    if latest is None:
        return backfill(symbol)

    start_date = latest - timedelta(days=INGEST_OVERLAP_DAYS)
    end_date = date.today() + timedelta(days=1)
    label = f"{start_date}..{end_date}"
    with _logged_failure(symbol, label):
        frame = _download(symbol, start=start_date, end=end_date)
        if frame is None or frame.empty:
            logger.info("No data returned for %s (%s)", symbol, label)
            return 0
        readjusted = _history_was_readjusted(symbol, frame)
        if not readjusted:
            rows_written = _store_frame(symbol, frame)
    if readjusted:
        message = (
            f"Yahoo re-adjusted the stored history of {symbol} (split or dividend); "
            "re-fetching the full window."
        )
        logger.info(message)
        log_event("INFO", message, logger_name="ingestion", symbol=symbol, success=True)
        return backfill(symbol)
    logger.info("Stored %d rows for %s (%s)", rows_written, symbol, label)
    return rows_written


# ---------------------------------------------------------------------------
# History coverage
# ---------------------------------------------------------------------------

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
    coverage_entry = coverage.get(asset["symbol"])
    if coverage_entry is None or coverage_entry["count"] == 0 or coverage_entry["first_date"] is None:
        return False
    expected = _expected_start(asset, window_start)
    return coverage_entry["first_date"] <= expected + timedelta(days=HISTORY_GRACE_DAYS)


def assets_missing_history(db=None):
    """Tracked assets whose stored history does not reach their expected start.

    The expected start is the rolling HISTORY_YEARS window, unless the asset's
    inception date is later — in which case only history since inception is
    required. This keeps genuinely young instruments out of the re-fetch loop.
    """
    assets = get_all_assets(db)
    coverage = get_history_coverage(db)
    window_start = _window_start()
    missing = [
        asset for asset in assets
        if not _has_full_history(asset, coverage, window_start)
    ]
    logger.info("%d of %d tracked assets lack history back to their expected start (~%dy window).",
                len(missing), len(assets), HISTORY_YEARS)
    return missing


def fetch_inception_date(symbol: str, retry_base: float = YF_RETRY_BASE_SECONDS):
    """Fetch a symbol's first-trade date from Yahoo, or None if unavailable."""
    try:
        info = _with_rate_limit_retry(lambda: yf.Ticker(symbol).info, symbol, retry_base)
    except YFRateLimitError:
        raise
    except Exception as error:
        logger.warning("Could not fetch inception date for %s: %s", symbol, error)
        return None
    return _inception_from_info(info)


def backfill_inception_dates(
    delay: float = SLOW_BACKFILL_DELAY_SECONDS,
    jitter: float = SLOW_BACKFILL_JITTER_SECONDS,
    retry_base: float = SLOW_YF_RETRY_BASE_SECONDS,
) -> dict:
    """Capture the inception date for every asset that does not have one yet."""
    with _exclusive_bulk_job("inception date backfill"):
        assets = get_assets_missing_inception()
        results = {}
        for index, asset in enumerate(assets):
            symbol = asset["symbol"]
            try:
                inception = fetch_inception_date(symbol, retry_base=retry_base)
                if inception is not None:
                    set_inception_date(symbol, inception)
                results[symbol] = str(inception) if inception is not None else None
            except Exception as error:
                results[symbol] = f"ERROR: {error}"
                logger.error("inception backfill failed for %s: %s", symbol, error)
            if index < len(assets) - 1:
                _throttle(delay, jitter)
        logger.info("inception backfill finished: %d assets", len(assets))
        return results


def _throttle(delay: float, jitter: float):
    if delay <= 0 and jitter <= 0:
        return
    time.sleep(delay + random.uniform(0, jitter))


def _is_rotation_night(key: str, today: date) -> bool:
    """Spread work over HISTORY_AUDIT_CYCLE_DAYS nights: each key gets one fixed night per cycle."""
    cycle_days = max(1, HISTORY_AUDIT_CYCLE_DAYS)
    return zlib.crc32(key.encode("utf-8")) % cycle_days == today.toordinal() % cycle_days


# ---------------------------------------------------------------------------
# Nightly history audit
# ---------------------------------------------------------------------------

def _find_suspicious_bars(bars):
    """Dates of stored bars that are structurally invalid or isolated price spikes."""
    suspicious = []
    closes = []
    for bar in bars:
        if _valid_ohlc((bar["open"], bar["high"], bar["low"], bar["close"])):
            closes.append((bar["date"], bar["close"]))
        else:
            suspicious.append(bar["date"])
    suspicious.extend(closes[index][0] for index in _find_price_spikes(closes))
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
    """Replace suspicious stored bars with Yahoo's current values when those pass validation."""
    frame = _download(
        symbol,
        retry_base,
        start=target_dates[0] - timedelta(days=90),
        end=target_dates[-1] + timedelta(days=4),
    )
    if frame is None or frame.empty:
        raise ValueError(f"Yahoo returned no history for {symbol} audit range.")

    yahoo_bars = _valid_frame_bars(symbol, frame, log_skipped=False)
    yahoo_closes = [(bar["date"], bar["close"]) for bar in yahoo_bars]
    yahoo_spike_dates = {yahoo_closes[index][0] for index in _find_price_spikes(yahoo_closes)}
    yahoo_bars_by_date = {bar["date"]: bar for bar in yahoo_bars}

    repairs = []
    unresolved = 0
    for target_date in target_dates:
        candidate = yahoo_bars_by_date.get(target_date)
        if candidate is None:
            reason = "Yahoo returned no valid bar for that date"
        elif target_date in yahoo_spike_dates:
            reason = "Yahoo history shows the same abnormal move"
        else:
            repairs.append(candidate)
            continue
        unresolved += 1
        message = (
            f"History audit could not repair {symbol} on {target_date}: {reason}; "
            "stored data was left unchanged."
        )
        logger.warning(message)
        log_event("WARNING", message, logger_name="ingestion", symbol=symbol, success=False)

    if repairs:
        db = SessionLocal()
        try:
            db.execute(UPSERT_SQL, repairs)
            db.commit()
        finally:
            db.close()
        for bar in repairs:
            message = f"History audit repaired {symbol} on {bar['date']} from validated Yahoo history."
            logger.info(message)
            log_event("INFO", message, logger_name="ingestion", symbol=symbol, success=True)
    return len(repairs), unresolved


def audit_and_repair_history(
    delay: float = INGEST_DELAY_SECONDS,
    jitter: float = INGEST_JITTER_SECONDS,
    retry_base: float = YF_RETRY_BASE_SECONDS,
):
    """Scan stored bars nightly and repair anomalies when Yahoo confirms valid context."""
    today = date.today()
    stored_symbols = get_stored_symbols()
    suspicious_by_symbol = {}
    for symbol in stored_symbols:
        suspicious_dates = _find_suspicious_bars(get_price_bars(symbol))
        if suspicious_dates:
            suspicious_by_symbol[symbol] = suspicious_dates

    clusters = [
        (symbol, cluster)
        for symbol, dates in suspicious_by_symbol.items()
        for cluster in _date_clusters(dates)
        if _is_rotation_night(f"{symbol}:{cluster[0]}", today)
    ]
    max_ranges = max(1, HISTORY_REPAIR_MAX_RANGES_PER_NIGHT)
    if len(clusters) > max_ranges:
        clusters.sort(
            key=lambda item: zlib.crc32(f"{today}:{item[0]}:{item[1][0]}".encode("utf-8"))
        )
    scheduled = clusters[:max_ranges]
    repaired = unresolved = 0
    for index, (symbol, cluster) in enumerate(scheduled):
        try:
            cluster_repaired, cluster_unresolved = _repair_cluster(symbol, cluster, retry_base)
            repaired += cluster_repaired
            unresolved += cluster_unresolved
        except Exception as error:
            unresolved += len(cluster)
            logger.error("History audit failed for %s: %s", symbol, error)
            log_event(
                "ERROR", f"History audit failed for {symbol}: {type(error).__name__}: {error}",
                logger_name="ingestion", symbol=symbol, success=False,
                exception=f"{type(error).__name__}: {error}",
            )
        if index < len(scheduled) - 1:
            _throttle(delay, jitter)
    deferred = len(clusters) - len(scheduled)
    logger.info(
        "History audit finished: checked %d assets, found %d suspicious bars, repaired %d; "
        "%d candidates require review, %d audit ranges deferred by the nightly limit.",
        len(stored_symbols), sum(map(len, suspicious_by_symbol.values())),
        repaired, unresolved, deferred,
    )
    return {"repaired": repaired, "unresolved": unresolved, "deferred": deferred}


# ---------------------------------------------------------------------------
# Bulk jobs
# ---------------------------------------------------------------------------

def _backfill_symbols(symbols, delay: float, jitter: float, retry_base: float) -> dict:
    results = {}
    for index, symbol in enumerate(symbols):
        try:
            results[symbol] = backfill(symbol, retry_base=retry_base)
        except Exception as error:
            results[symbol] = f"ERROR: {error}"
            logger.error("backfill failed for %s: %s", symbol, error)
        if index < len(symbols) - 1:
            _throttle(delay, jitter)
    logger.info("backfill run finished: %d assets", len(symbols))
    return results


def backfill_missing(
    delay: float = SLOW_BACKFILL_DELAY_SECONDS,
    jitter: float = SLOW_BACKFILL_JITTER_SECONDS,
    retry_base: float = SLOW_YF_RETRY_BASE_SECONDS,
):
    """Slow, extra-gentle backfill of only the assets missing their expected history."""
    with _exclusive_bulk_job("missing-history backfill"):
        symbols = [asset["symbol"] for asset in assets_missing_history()]
        logger.info("backfill_missing (slow mode) covering %d assets...", len(symbols))
        return _backfill_symbols(symbols, delay, jitter, retry_base)


def backfill_all(
    delay: float = BACKFILL_DELAY_SECONDS,
    jitter: float = BACKFILL_JITTER_SECONDS,
    retry_base: float = YF_RETRY_BASE_SECONDS,
):
    """Backfill every tracked asset with the normal (milder) throttle."""
    with _exclusive_bulk_job("full backfill"):
        return _backfill_symbols(_tracked_symbols(), delay, jitter, retry_base)


def ingest_daily_all():
    """Nightly job: fill missing history, repair gaps, fetch new bars, then audit stored history."""
    with _exclusive_bulk_job("daily ingestion"):
        assets = get_all_assets()
        coverage = get_history_coverage()
        gaps_by_symbol = {}
        for gap in get_history_gaps():
            gaps_by_symbol.setdefault(gap["symbol"], []).append(gap)

        today = date.today()
        window_start = _window_start(today)
        results = {}
        for index, asset in enumerate(assets):
            symbol = asset["symbol"]
            try:
                coverage_entry = coverage.get(symbol)
                needs_initial_backfill = coverage_entry is None or coverage_entry["count"] == 0
                if needs_initial_backfill or _is_rotation_night(symbol, today):
                    rows_written = backfill(symbol)
                else:
                    if not _has_full_history(asset, coverage, window_start):
                        logger.info(
                            "%s starts later than expected; full-history audit remains scheduled "
                            "on its rotation.",
                            symbol,
                        )
                    rows_written = 0
                    for gap in gaps_by_symbol.get(symbol, []):
                        rows_written += _fetch_and_store(
                            symbol, start_date=gap["start"], end_date=gap["end"],
                        )
                    rows_written += ingest_daily(symbol)
                results[symbol] = rows_written
            except Exception as error:
                results[symbol] = f"ERROR: {error}"
                logger.error("ingest_daily failed for %s: %s", symbol, error)
            if index < len(assets) - 1:
                _throttle(INGEST_DELAY_SECONDS, INGEST_JITTER_SECONDS)
        logger.info("ingest_daily_all finished: %d assets", len(assets))
        audit_and_repair_history()
        return results
