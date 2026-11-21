"""Ingestion jobs: backfills, the nightly update and the stored-history audit.

Price checks live in `price_validation`, Yahoo calls in `yahoo`, and all SQL
in `asset_repository` / `price_repository`.
"""

import random
import statistics
import threading
import time
import zlib
from contextlib import contextmanager
from datetime import date, timedelta

import pandas as pd

from . import dividend_repository, price_repository, yahoo
from .asset_repository import get_all_assets, get_assets_missing_inception, set_inception_date
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
    SLOW_BACKFILL_DELAY_SECONDS,
    SLOW_BACKFILL_JITTER_SECONDS,
    SLOW_YAHOO_RETRY_BASE_SECONDS,
    YAHOO_RETRY_BASE_SECONDS,
)
from .logging_config import LOG_RETENTION_DAYS, delete_old_logs, get_logger, log_event
from .price_validation import (
    RECENT_MOVES_WINDOW,
    find_price_spikes,
    find_suspicious_bars,
    finite_number,
    frame_to_bars,
)

logger = get_logger("ingestion")

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


def _log_warning(symbol: str, message: str) -> None:
    logger.warning(message)
    log_event("WARNING", message, logger_name="ingestion", symbol=symbol, success=False)


def _log_info(symbol: str, message: str) -> None:
    logger.info(message)
    log_event("INFO", message, logger_name="ingestion", symbol=symbol, success=True)


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


def _throttle(delay: float, jitter: float) -> None:
    if delay <= 0 and jitter <= 0:
        return
    time.sleep(delay + random.uniform(0, jitter))


def _is_rotation_night(key: str, today: date) -> bool:
    """Spread work over HISTORY_AUDIT_CYCLE_DAYS nights: each key gets one fixed night per cycle."""
    cycle_days = max(1, HISTORY_AUDIT_CYCLE_DAYS)
    return zlib.crc32(key.encode("utf-8")) % cycle_days == today.toordinal() % cycle_days


# ---------------------------------------------------------------------------
# Fetch and store one symbol
# ---------------------------------------------------------------------------

def _store_frame(symbol: str, frame: pd.DataFrame) -> int:
    """Validate a Yahoo frame against its stored neighbours, upsert the good bars, drop spikes.

    The newest bar is stored before its next bar exists, so a glitch can only be
    confirmed a night later, when the overlap window fetches it again. Any bar
    confirmed as a spike is then also deleted if it was stored earlier.
    """
    bars, invalid_dates = frame_to_bars(symbol, frame)
    for invalid_date in invalid_dates:
        _log_warning(symbol, f"Skipped invalid OHLC bar for {symbol} on {invalid_date}.")
    if not bars:
        return 0
    prior_closes = price_repository.get_recent_closes_before(
        symbol, bars[0]["date"], RECENT_MOVES_WINDOW + 1
    )
    # When filling a gap, the stored bar right after it confirms or rejects the last fetched bar.
    next_close = price_repository.get_next_close_after(symbol, bars[-1]["date"])
    closes = prior_closes + [(bar["date"], bar["close"]) for bar in bars]
    spikes = find_price_spikes(closes + ([next_close] if next_close else []))
    bars_to_store = []
    spike_dates = []
    for offset, bar in enumerate(bars):
        if len(prior_closes) + offset in spikes:
            spike_dates.append(bar["date"])
            _log_warning(
                symbol,
                f"Skipped price spike for {symbol} on {bar['date']}: close {bar['close']} "
                "jumps away from its neighbours and straight back.",
            )
            continue
        bars_to_store.append(bar)
    price_repository.upsert_bars(bars_to_store)
    _store_dividends(symbol, frame)
    removed = price_repository.delete_bars(symbol, spike_dates)
    if removed:
        _log_warning(
            symbol,
            f"Removed {removed} previously stored price spike(s) for {symbol} "
            f"(checked dates: {', '.join(map(str, spike_dates))}).",
        )
    return len(bars_to_store)


def _store_dividends(symbol: str, frame: pd.DataFrame) -> int:
    """Upsert the frame's cash dividends (Yahoo's "Dividends" column, keyed by ex-date).

    Never raises: a missing `dividends` table or a database hiccup is logged,
    so it can never stop the price bars from being stored.
    """
    if "Dividends" not in frame.columns:
        return 0
    dividends = []
    for timestamp, value in frame["Dividends"].items():
        amount = finite_number(value)
        if amount is not None and amount > 0:
            dividends.append({"symbol": symbol, "date": timestamp.date(), "amount": amount})
    try:
        dividend_repository.upsert_dividends(dividends)
    except Exception as error:
        _log_warning(symbol, f"Could not store {len(dividends)} dividend(s) for {symbol}: {error}")
        return 0
    return len(dividends)


def _fetch_and_store(
    symbol: str,
    retry_base: float = YAHOO_RETRY_BASE_SECONDS,
    period: str = None,
    start_date: date = None,
    end_date: date = None,
) -> int:
    label = f"period={period}" if period else f"{start_date}..{end_date}"
    with _logged_failure(symbol, label):
        frame = yahoo.download(symbol, retry_base, period=period, start=start_date, end=end_date)
        if frame.empty:
            logger.info("No data returned for %s (%s)", symbol, label)
            return 0
        rows_written = _store_frame(symbol, frame)
    logger.info("Stored %d rows for %s (%s)", rows_written, symbol, label)
    return rows_written


def backfill(symbol: str, retry_base: float = YAHOO_RETRY_BASE_SECONDS) -> int:
    """Fetch and store the full HISTORY_YEARS window for one symbol."""
    return _fetch_and_store(symbol, retry_base, period=f"{HISTORY_YEARS}y")


def _history_was_readjusted(symbol: str, frame: pd.DataFrame) -> bool:
    """True when Yahoo's closes for already stored days all moved by the same ratio.

    With auto_adjust, a split or dividend rescales every earlier close. The
    stored rows then sit on the old scale, so the whole window must be
    re-fetched instead of appended to. The newest stored day is ignored: it may
    still have been an open trading day when it was stored.
    """
    fetched_closes = {
        timestamp.date(): finite_number(close) for timestamp, close in frame["Close"].items()
    }
    stored_closes = price_repository.get_closes_from(symbol, min(fetched_closes))
    ratios = [
        fetched_closes[stored_date] / stored_close - 1
        for stored_date, stored_close in stored_closes[:-1]
        if stored_close and fetched_closes.get(stored_date)
    ]
    return len(ratios) >= 2 and abs(statistics.median(ratios)) > READJUSTMENT_TOLERANCE


def ingest_daily(symbol: str) -> int:
    """Fetch new bars, re-fetching the last INGEST_OVERLAP_DAYS stored days for late corrections."""
    latest = price_repository.get_latest_date(symbol)
    if latest is None:
        return backfill(symbol)

    start_date = latest - timedelta(days=INGEST_OVERLAP_DAYS)
    end_date = date.today() + timedelta(days=1)
    label = f"{start_date}..{end_date}"
    with _logged_failure(symbol, label):
        frame = yahoo.download(symbol, start=start_date, end=end_date)
        if frame.empty:
            logger.info("No data returned for %s (%s)", symbol, label)
            return 0
        readjusted = _history_was_readjusted(symbol, frame)
        if not readjusted:
            rows_written = _store_frame(symbol, frame)
    if readjusted:
        _log_info(
            symbol,
            f"Yahoo re-adjusted the stored history of {symbol} (split or dividend); "
            "re-fetching the full window.",
        )
        return backfill(symbol)
    logger.info("Stored %d rows for %s (%s)", rows_written, symbol, label)
    return rows_written


# ---------------------------------------------------------------------------
# History coverage
# ---------------------------------------------------------------------------

def _window_start(today: date = None) -> date:
    """Start of the rolling fetch window (today minus HISTORY_YEARS)."""
    today = today or date.today()
    return today - timedelta(days=365 * HISTORY_YEARS)


def _expected_start(asset: dict, window_start: date) -> date:
    """Earliest date we can reasonably expect history for.

    Assets that started trading after the window began only need history since
    their inception, so we look no further back than that. Without a known
    inception we fall back to the full window.
    """
    inception = asset.get("inception_date")
    if inception is not None and inception > window_start:
        return inception
    return window_start


def _has_full_history(asset: dict, coverage: dict, window_start: date) -> bool:
    coverage_entry = coverage.get(asset["symbol"])
    if coverage_entry is None or coverage_entry["count"] == 0 or coverage_entry["first_date"] is None:
        return False
    expected = _expected_start(asset, window_start)
    return coverage_entry["first_date"] <= expected + timedelta(days=HISTORY_GRACE_DAYS)


def assets_missing_history() -> list[dict]:
    """Tracked assets whose stored history does not reach their expected start.

    The expected start is the rolling HISTORY_YEARS window, unless the asset's
    inception date is later — in which case only history since inception is
    required. This keeps genuinely young instruments out of the re-fetch loop.
    """
    assets = get_all_assets()
    coverage = price_repository.get_history_coverage()
    window_start = _window_start()
    missing = [
        asset for asset in assets
        if not _has_full_history(asset, coverage, window_start)
    ]
    logger.info("%d of %d tracked assets lack history back to their expected start (~%dy window).",
                len(missing), len(assets), HISTORY_YEARS)
    return missing


# ---------------------------------------------------------------------------
# Nightly history audit
# ---------------------------------------------------------------------------

def _date_clusters(dates: list, max_gap_days: int = 60) -> list[list]:
    """Group sorted dates so that dates less than `max_gap_days` apart share one Yahoo request."""
    clusters = []
    for item in dates:
        if not clusters or (item - clusters[-1][-1]).days > max_gap_days:
            clusters.append([item])
        else:
            clusters[-1].append(item)
    return clusters


def _repair_cluster(symbol: str, target_dates: list, retry_base: float) -> tuple[int, int]:
    """Replace suspicious stored bars with Yahoo's current values when those pass validation."""
    frame = yahoo.download(
        symbol,
        retry_base,
        start=target_dates[0] - timedelta(days=90),
        end=target_dates[-1] + timedelta(days=4),
    )
    if frame.empty:
        raise ValueError(f"Yahoo returned no history for {symbol} audit range.")

    yahoo_bars, _invalid_dates = frame_to_bars(symbol, frame)
    yahoo_closes = [(bar["date"], bar["close"]) for bar in yahoo_bars]
    yahoo_spike_dates = {yahoo_closes[index][0] for index in find_price_spikes(yahoo_closes)}
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
        _log_warning(
            symbol,
            f"History audit could not repair {symbol} on {target_date}: {reason}; "
            "stored data was left unchanged.",
        )

    price_repository.upsert_bars(repairs)
    for bar in repairs:
        _log_info(symbol, f"History audit repaired {symbol} on {bar['date']} from validated Yahoo history.")
    return len(repairs), unresolved


def audit_and_repair_history(
    delay: float = INGEST_DELAY_SECONDS,
    jitter: float = INGEST_JITTER_SECONDS,
    retry_base: float = YAHOO_RETRY_BASE_SECONDS,
) -> dict:
    """Scan stored bars and repair anomalies when Yahoo confirms valid context."""
    today = date.today()
    stored_symbols = price_repository.get_stored_symbols()
    suspicious_by_symbol = {}
    for symbol in stored_symbols:
        suspicious_dates = find_suspicious_bars(price_repository.get_price_bars(symbol))
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
# Bulk jobs (one at a time)
# ---------------------------------------------------------------------------

def _backfill_symbols(symbols: list[str], delay: float, jitter: float, retry_base: float) -> dict:
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
    retry_base: float = SLOW_YAHOO_RETRY_BASE_SECONDS,
) -> dict:
    """Slow, extra-gentle backfill of only the assets missing their expected history."""
    with _exclusive_bulk_job("missing-history backfill"):
        symbols = [asset["symbol"] for asset in assets_missing_history()]
        logger.info("backfill_missing (slow mode) covering %d assets...", len(symbols))
        return _backfill_symbols(symbols, delay, jitter, retry_base)


def backfill_all(
    delay: float = BACKFILL_DELAY_SECONDS,
    jitter: float = BACKFILL_JITTER_SECONDS,
    retry_base: float = YAHOO_RETRY_BASE_SECONDS,
) -> dict:
    """Backfill every tracked asset with the normal (milder) throttle."""
    with _exclusive_bulk_job("full backfill"):
        symbols = [asset["symbol"] for asset in get_all_assets()]
        return _backfill_symbols(symbols, delay, jitter, retry_base)


def backfill_inception_dates(
    delay: float = SLOW_BACKFILL_DELAY_SECONDS,
    jitter: float = SLOW_BACKFILL_JITTER_SECONDS,
    retry_base: float = SLOW_YAHOO_RETRY_BASE_SECONDS,
) -> dict:
    """Capture the inception date for every asset that does not have one yet."""
    with _exclusive_bulk_job("inception date backfill"):
        assets = get_assets_missing_inception()
        results = {}
        for index, asset in enumerate(assets):
            symbol = asset["symbol"]
            try:
                inception = yahoo.fetch_inception_date(symbol, retry_base=retry_base)
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


def ingest_daily_all() -> dict:
    """Nightly job: fill missing history, repair gaps, fetch new bars, then audit stored history."""
    with _exclusive_bulk_job("daily ingestion"):
        assets = get_all_assets()
        coverage = price_repository.get_history_coverage()
        gaps_by_symbol = {}
        for gap in price_repository.get_history_gaps():
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
        try:
            removed = delete_old_logs()
            logger.info("Deleted %d api_logs rows older than %d days.", removed, LOG_RETENTION_DAYS)
        except Exception as error:
            logger.error("Could not delete old api_logs rows: %s", error)
        return results
