"""Admin endpoints (X-Admin-Key): catalogue management, backfills, ingestion, cache and logs."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ... import cache, catalog, price_repository
from ...asset_repository import add_asset, asset_exists, get_all_assets
from ...config import SLOW_YAHOO_RETRY_BASE_SECONDS
from ...db import get_db
from ...ingestion import (
    IngestionAlreadyRunning,
    backfill,
    backfill_all,
    backfill_inception_dates,
    backfill_missing,
    ingest_daily_all,
)
from ...logging_config import get_recent_logs
from ...price_repository import price_bar_to_dict
from ...yahoo import check_symbol
from . import examples
from .security import require_admin

router = APIRouter(dependencies=[Depends(require_admin)])


class AddAssetRequest(BaseModel):
    symbol: str
    name: Optional[str] = None
    asset_type: Optional[str] = None
    properties: Optional[dict] = None


class OnboardAssetRequest(BaseModel):
    symbol: str
    name: Optional[str] = None
    asset_type: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_bulk_job(job):
    """Run a bulk ingestion job, answering 409 while another one is still running."""
    try:
        return job()
    except IngestionAlreadyRunning as error:
        raise HTTPException(status_code=409, detail=str(error))


def _reload_after_write(rows_written: int) -> None:
    """Serve freshly written history right away: reload the price cache and the catalogue."""
    if rows_written > 0:
        cache.load()
        catalog.load()


def _single_backfill_response(symbol: str, rows_written: int, session: Session) -> dict:
    return {
        "status":       "done" if rows_written > 0 else "no_data",
        "symbol":       symbol,
        "rows_written": rows_written,
        "latest":       price_bar_to_dict(price_repository.get_latest_bar(symbol, session)),
    }


def _bulk_job_response(results: dict, session: Session) -> dict:
    """Rows written per tracked asset plus each asset's latest stored bar."""
    assets = get_all_assets(session)
    latest = price_repository.get_latest_bars([asset["symbol"] for asset in assets], session)
    return {
        "status":     "done",
        "fetched_at": _now(),
        "results": [
            {
                "symbol":       asset["symbol"],
                "name":         asset["name"],
                "asset_type":   asset["asset_type"],
                "rows_written": results.get(asset["symbol"]),
                "latest":       price_bar_to_dict(latest.get(asset["symbol"])),
            }
            for asset in assets
        ],
    }


def _identify_new_asset(symbol: str, name: str | None, asset_type: str | None, always_verify: bool):
    """Name, asset type and inception date for a symbol about to be tracked.

    Missing values come from Yahoo Finance. Raises 409 if the symbol is already
    tracked and 422 if Yahoo does not know it or no asset type can be inferred.
    """
    if asset_exists(symbol):
        raise HTTPException(status_code=409, detail=f"Symbol '{symbol}' is already tracked.")
    if name is not None and asset_type is not None and not always_verify:
        return name, asset_type, None
    check = check_symbol(symbol)
    if not check["exists"]:
        raise HTTPException(
            status_code=422,
            detail=check["note"] or f"Symbol '{symbol}' was not found on Yahoo Finance.",
        )
    asset_type = asset_type or check["suggested_type"]
    if asset_type is None:
        raise HTTPException(
            status_code=422,
            detail=f"Could not infer an asset category for '{symbol}'. Provide an explicit asset_type.",
        )
    return name or check["name"] or symbol, asset_type, check.get("inception_date")


def _add_asset_or_409(symbol, name, asset_type, properties=None, inception_date=None) -> dict:
    try:
        return add_asset(symbol, name, asset_type, properties, inception_date=inception_date)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------

@router.get(
    "/admin/assets",
    summary="List all tracked assets from the database (admin)",
    description=(
        "Returns every asset stored in the `assets` table — the source of truth the "
        "backfill and daily ingestion now iterate over. Protected by the `X-Admin-Key` header."
    ),
    responses=examples.LIST_TRACKED_ASSETS,
)
def list_tracked_assets(session: Session = Depends(get_db)):
    return {"assets": get_all_assets(session)}


@router.get(
    "/admin/assets/check",
    summary="Verify a symbol exists on Yahoo Finance (admin)",
    description=(
        "Combines `yf.Ticker().info` and `yf.download()`: the symbol is considered valid "
        "if **either** source returns data (avoids false negatives when one path is rate "
        "limited or empty). Also suggests a display name and an asset category."
    ),
    responses=examples.CHECK_ASSET_SYMBOL,
)
def check_asset_symbol(
    symbol: str = Query(..., description="Yahoo Finance symbol to verify.", examples=["LTC-USD", "^VIX"]),
):
    result = check_symbol(symbol)
    result["already_tracked"] = asset_exists(symbol)
    return result


@router.post(
    "/admin/assets",
    summary="Add an asset to the tracked catalogue (admin)",
    description=(
        "Inserts a new symbol into the `assets` table. `name` and `asset_type` are optional: "
        "if omitted they are inferred from Yahoo Finance (`asset_type` must then be one of "
        "`fx`, `index`, `metal`, `stock`, `etf`, `crypto`). After adding, use "
        "`POST /finance/admin/assets/{symbol}/backfill` to fetch its history."
    ),
    responses=examples.ADD_TRACKED_ASSET,
)
def add_tracked_asset(payload: AddAssetRequest):
    name, asset_type, inception_date = _identify_new_asset(
        payload.symbol, payload.name, payload.asset_type, always_verify=False
    )
    asset = _add_asset_or_409(payload.symbol, name, asset_type, payload.properties, inception_date)
    catalog.load()
    return asset


@router.post(
    "/admin/assets/onboard",
    summary="Onboard a new asset from just its symbol (admin)",
    description=(
        "One-call onboarding. Given only a Yahoo Finance symbol this endpoint:\n\n"
        "1. Verifies the symbol and pulls its metadata (name + suggested asset type) from Yahoo Finance.\n"
        "2. Inserts the asset into the `assets` catalogue, so it appears in every public endpoint.\n"
        "3. Backfills the configured history window of daily data (gentle exponential backoff on rate limits).\n"
        "4. Rebuilds the in-memory catalogue and price cache so the new asset is served everywhere.\n\n"
        "Takes roughly a minute — the history download dominates the runtime.\n\n"
        "Errors: `409` if the symbol is already tracked, `422` if Yahoo cannot identify it or an "
        "asset type cannot be inferred (`name`/`asset_type` can be provided as overrides), `502` if "
        "the asset was added but the backfill failed (safe to retry via "
        "`POST /finance/admin/assets/{symbol}/backfill`).\n\n"
        "Protected by the `X-Admin-Key` header."
    ),
    responses=examples.ONBOARD_ASSET,
)
def onboard_asset(payload: OnboardAssetRequest, session: Session = Depends(get_db)):
    symbol = payload.symbol
    name, asset_type, inception_date = _identify_new_asset(
        symbol, payload.name, payload.asset_type, always_verify=True
    )
    asset = _add_asset_or_409(symbol, name, asset_type, inception_date=inception_date)
    try:
        rows_written = backfill(symbol, retry_base=SLOW_YAHOO_RETRY_BASE_SECONDS)
    except Exception as error:
        catalog.load()
        raise HTTPException(
            status_code=502,
            detail=f"Asset '{symbol}' was added, but the history backfill failed: {error}. "
                   f"Retry via POST /finance/admin/assets/{symbol}/backfill.",
        )
    catalog.load()
    if rows_written > 0:
        cache.load()
    return {
        "status":       "done",
        "asset":        asset,
        "rows_written": rows_written,
        "latest":       price_bar_to_dict(price_repository.get_latest_bar(symbol, session)),
    }


# ---------------------------------------------------------------------------
# Single-symbol backfills (fast)
# ---------------------------------------------------------------------------

_BACKFILL_SYMBOL_DESCRIPTION = (
    "**Fast path:** downloads the configured history window of daily data for **one arbitrary Yahoo Finance symbol** "
    "in a single request — the way to add a new instrument without restarting or editing the "
    "asset list. Because it hits Yahoo once, no inter-request throttling is needed; it still "
    "retries with exponential backoff if rate limited.\n\n"
    "`symbol` is any valid Yahoo Finance ticker (e.g. `^VIX`, `LTC-USD`, `GC=F`). "
    "Upserts, so re-running just refreshes existing rows. Takes ~1 minute.\n\n"
    "For bulk/backfilling-many use the slow endpoint `POST /finance/admin/backfill-missing`."
)


@router.post(
    "/admin/backfill-symbol",
    summary="Backfill history for a single symbol (admin, fast)",
    description=_BACKFILL_SYMBOL_DESCRIPTION,
    responses=examples.RUN_BACKFILL_SYMBOL,
)
@router.get(
    "/admin/backfill-symbol",
    summary="Backfill history for a single symbol (admin, fast, deprecated method)",
    description=(
        _BACKFILL_SYMBOL_DESCRIPTION
        + "\n\nDeprecated: this writes data, so use `POST /finance/admin/backfill-symbol` instead."
    ),
    responses=examples.RUN_BACKFILL_SYMBOL,
    deprecated=True,
)
def run_backfill_symbol(
    symbol: str = Query(..., description="Yahoo Finance symbol to backfill.", examples=["^VIX", "LTC-USD"]),
    session: Session = Depends(get_db),
):
    rows_written = backfill(symbol)
    _reload_after_write(rows_written)
    return _single_backfill_response(symbol, rows_written, session)


@router.post(
    "/admin/assets/{symbol}/backfill",
    summary="Backfill history for a single tracked asset (admin, fast)",
    description=(
        "**Fast path:** downloads the configured history window of daily data for **one asset already present in the "
        "`assets` table** in a single request (no inter-request throttling needed; still retries "
        "with exponential backoff on rate limits). Upserts, so re-running just refreshes stored "
        "rows.\n\n"
        "For bulk/backfilling-many use the slow endpoint `POST /finance/admin/backfill-missing`."
    ),
    responses=examples.BACKFILL_TRACKED_ASSET,
)
def backfill_tracked_asset(
    symbol: str = Path(..., description="Symbol present in the assets table.", examples=["LTC-USD", "NVDA"]),
    session: Session = Depends(get_db),
):
    if not asset_exists(symbol):
        raise HTTPException(
            status_code=404,
            detail=f"Symbol '{symbol}' is not in the assets table. Add it first via POST /finance/admin/assets.",
        )
    rows_written = backfill(symbol)
    _reload_after_write(rows_written)
    return _single_backfill_response(symbol, rows_written, session)


# ---------------------------------------------------------------------------
# Bulk jobs (one at a time, HTTP 409 while another runs)
# ---------------------------------------------------------------------------

@router.post(
    "/admin/backfill",
    summary="Backfill ALL assets (admin, medium speed)",
    description=(
        "Triggers the full history-window backfill for **all tracked assets** (whether or not they "
        "already have history) and stores the data in the database. Throttled with the normal "
        "delay config (`BACKFILL_DELAY_SECONDS`, default ~2s between symbols). Protected by the "
        "`X-Admin-Key` header (send the value of the `ADMIN_KEY` environment variable). Takes "
        "several minutes.\n\n"
        "Usually `POST /finance/admin/backfill-missing` (slow, skips covered assets) is the safer "
        "choice. Returns the number of rows written per asset plus the latest stored value for each."
    ),
    responses=examples.RUN_BACKFILL,
)
def run_backfill(session: Session = Depends(get_db)):
    catalog.load()
    results = _run_bulk_job(backfill_all)
    cache.load()
    return _bulk_job_response(results, session)


@router.post(
    "/admin/backfill-missing",
    summary="Backfill missing history (admin, slow & safe)",
    description=(
        "**Slow path, purpose-built to avoid Yahoo rate limits.** Downloads the configured history "
        "window of daily data **only for tracked assets whose stored data does not reach their "
        "expected start** (newly added assets, partially backfilled symbols, assets with only recent "
        "daily ingestion). Assets younger than the window are measured against their `inception_date`, "
        "so they are not re-fetched once their full available history is stored.\n\n"
        "It spaces every symbol out with a generous delay (default ~12s + jitter between "
        "symbols, configurable via `SLOW_BACKFILL_DELAY_SECONDS` / `SLOW_BACKFILL_JITTER_SECONDS`) "
        "and uses a gentler exponential backoff on rate limits "
        "(`SLOW_YAHOO_RETRY_BASE_SECONDS`). Safe to re-run: covered assets are skipped.\n\n"
        "For a single asset (one quick request) use `POST /finance/admin/assets/{symbol}/backfill` "
        "instead. Protected by the `X-Admin-Key` header."
    ),
    responses=examples.RUN_BACKFILL_MISSING,
)
def run_backfill_missing(session: Session = Depends(get_db)):
    catalog.load()
    results = _run_bulk_job(backfill_missing)
    cache.load()
    return _bulk_job_response(results, session)


@router.post(
    "/admin/assets/backfill-inception-dates",
    summary="Capture missing inception dates (admin, slow)",
    description=(
        "Fetches the first-trade date (`inception_date`) from Yahoo Finance for every tracked "
        "asset that does not have one yet. The inception date lets the backfill logic tell a "
        "genuinely young instrument (e.g. an IPO from 3 years ago) apart from one with an "
        "incomplete fetch, so young assets stop being re-fetched forever.\n\n"
        "Paced with the slow throttle (`SLOW_BACKFILL_DELAY_SECONDS`) because it issues one "
        "Yahoo request per asset. Safe to re-run: assets that already have a date are skipped. "
        "Protected by the `X-Admin-Key` header."
    ),
    responses=examples.RUN_BACKFILL_INCEPTION_DATES,
)
def run_backfill_inception_dates():
    results = _run_bulk_job(backfill_inception_dates)
    catalog.load()
    return {
        "status":     "done",
        "fetched_at": _now(),
        "results":    [
            {"symbol": symbol, "inception_date": value}
            for symbol, value in results.items()
        ],
    }


@router.post(
    "/admin/ingest-daily",
    summary="Run daily ingestion now (admin)",
    description=(
        "Checks stored history for every tracked asset, repairs detected gaps, and fetches an "
        "overlapping recent date range to capture delayed bars or corrections. Assets are "
        "periodically assigned a full-history audit. Suspicious or structurally invalid bars "
        "are skipped and logged. This is the same work the automatic scheduler does daily at "
        "23:00 UTC. Protected by the `X-Admin-Key` header (send the value of the "
        "`ADMIN_KEY` environment variable).\n\n"
        "Returns the number of rows written per asset plus the latest stored value for each."
    ),
    responses=examples.RUN_DAILY_INGEST,
)
def run_daily_ingest(session: Session = Depends(get_db)):
    catalog.load()
    results = _run_bulk_job(ingest_daily_all)
    cache.load()
    return _bulk_job_response(results, session)


# ---------------------------------------------------------------------------
# Cache and logs
# ---------------------------------------------------------------------------

@router.get(
    "/admin/cache/details",
    summary="Detailed cache report (admin)",
    description=(
        "Returns a full report of what is currently held in the in-memory cache: "
        "per-symbol row counts, coverage (first/last date), total rows, and an "
        "estimated memory footprint. Useful for confirming the cache is healthy "
        "after a deploy or an ingestion run."
    ),
    responses=examples.GET_CACHE_DETAILS,
)
def get_cache_details():
    return cache.details()


@router.post(
    "/admin/cache/refresh",
    summary="Refresh the in-memory cache (admin)",
    description=(
        "Reloads the in-memory cache from the database using the rolling history window "
        "of daily price data; the previous data keeps being served until the new data is "
        "ready. This does not fetch data from Yahoo Finance. Protected by the `X-Admin-Key` header."
    ),
    responses=examples.REFRESH_CACHE_FROM_DATABASE,
)
def refresh_cache_from_database():
    catalog.load()
    if not cache.load():
        raise HTTPException(status_code=503, detail="Cache refresh failed.")
    stats = cache.stats()
    return {
        "status":       "done",
        "refreshed_at": stats["loaded_at"],
        "symbols":      stats["symbols"],
        "total_rows":   stats["total_rows"],
    }


@router.get(
    "/logs",
    summary="Recent ingestion logs, last 7 days (admin)",
    description=(
        "Returns all structured log events from the `api_logs` table for the past 7 days, "
        "sorted most-recent-first. Useful for diagnosing scheduler or fetch failures."
    ),
    responses=examples.GET_LOGS,
)
def get_logs(session: Session = Depends(get_db)):
    logs = get_recent_logs(session)
    return {"count": len(logs), "logs": logs}
