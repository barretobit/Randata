"""Public endpoints across all assets: bulk history, any stored symbol, catalogue, freshness and logs."""

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ... import cache, catalog, db, price_repository
from ...config import HISTORY_YEARS
from ...db import get_db
from ...logging_config import LOG_RETENTION_DAYS, get_logger, get_recent_logs
from ...price_repository import price_bar_to_dict
from . import examples
from .responses import cached_json_response, compressed_document

router = APIRouter()
logger = get_logger("history")

HISTORY_RANGE_MAX_ROWS = 50000
# One calendar year holds ~47k bars today; this only guards memory against a runaway catalogue.
HISTORY_YEAR_MAX_ROWS = 500000
_STREAM_CHUNK_ROWS = 2000
_BAR_FIELDS = ("date", "open", "high", "low", "close", "volume")


def _too_many_rows() -> HTTPException:
    return HTTPException(
        status_code=413,
        detail=f"Date range exceeds the {HISTORY_RANGE_MAX_ROWS:,}-row limit.",
    )


@router.get(
    "/history/all",
    summary="Dump: all history for all assets",
    description=(
        "Returns **every stored daily bar** for every asset in one response, "
        "sorted by symbol then date (oldest first). Each entry contains the `symbol` plus "
        "`date, open, high, low, close, volume`.\n\n"
        "This is the big export endpoint — the default cap is 50,000 rows, so raise "
        "`limit` to pull the entire stored history (the full 10-year dataset is ~460,000 rows). "
        "The `from` and `to` fields report the earliest and latest dates in the returned rows.\n\n"
        "The response is streamed, so `count`, `from` and `to` come after `data` in the document."
    ),
    responses=examples.GET_HISTORY_ALL,
)
def get_history_all(
    limit: int = Query(50000, ge=1, le=500000, description="Maximum number of rows to return."),
):
    if db.SessionLocal is None:
        raise HTTPException(status_code=500, detail="DATABASE_URL is not configured.")
    return StreamingResponse(_stream_history_all(limit), media_type="application/json")


def _stream_history_all(limit: int):
    """Yield the /history/all JSON document piece by piece.

    `count`, `from` and `to` are only known at the end, so they follow `data`.
    """
    yield b'{"data":['
    count = 0
    earliest = latest = None
    for rows in price_repository.iterate_all_bars(limit, _STREAM_CHUNK_ROWS):
        pieces = []
        for row in rows:
            bar = {"symbol": row.symbol, **price_bar_to_dict(row)}
            if earliest is None or bar["date"] < earliest:
                earliest = bar["date"]
            if latest is None or bar["date"] > latest:
                latest = bar["date"]
            pieces.append(json.dumps(bar, separators=(",", ":")))
        yield (("," if count else "") + ",".join(pieces)).encode("utf-8")
        count += len(pieces)
    summary = json.dumps({"count": count, "from": earliest, "to": latest}, separators=(",", ":"))
    yield ("]," + summary[1:]).encode("utf-8")


def _range_from_cache(from_date: date, to_date: date) -> dict | None:
    """A date range served from the in-memory cache, or None if the cache is empty.

    Only for ranges that start within the cache window.
    """
    cached = cache.get_all()
    if not cached:
        return None
    first_day, last_day = str(from_date), str(to_date)
    data = []
    for symbol, history in cached.items():
        for bar in history:
            if first_day <= bar["date"] <= last_day:
                data.append({"symbol": symbol, **bar})
                if len(data) > HISTORY_RANGE_MAX_ROWS:
                    raise _too_many_rows()
    return {"count": len(data), "from": first_day, "to": last_day, "data": data}


@router.get(
    "/history/range",
    summary="History between two dates (all assets)",
    description=(
        "Returns every stored daily bar **between two inclusive dates** for every asset, "
        "sorted by symbol then date. Both query parameters are required, format `YYYY-MM-DD`.\n\n"
        f"Responses are limited to {HISTORY_RANGE_MAX_ROWS:,} rows. Requests matching more rows "
        "return HTTP 413 instead of a partial result.\n\n"
        "If `from` falls inside the in-memory cache window (the last `CACHE_HISTORY_YEARS` "
        "years, default 1) the response is served straight from memory with no database "
        "round-trip; otherwise (e.g. the initial 10-year load) it is served from the database. "
        "The `source` field reports which path was used.\n\n"
        "Example: `?from=2024-01-01&to=2024-12-31` gives all assets for the 2024 calendar year."
    ),
    responses=examples.GET_HISTORY_RANGE,
)
def get_history_range(
    request: Request,
    from_date: date = Query(..., alias="from", description="Start date, inclusive. Format `YYYY-MM-DD`.", examples=["2024-01-01"]),
    to_date: date = Query(..., alias="to", description="End date, inclusive. Format `YYYY-MM-DD`.", examples=["2024-12-31"]),
    session: Session = Depends(get_db),
):
    if from_date > to_date:
        raise HTTPException(status_code=400, detail="'from' must be less than or equal to 'to'.")
    within_cache = from_date >= cache.window_start()

    def produce():
        if within_cache:
            cached = _range_from_cache(from_date, to_date)
            if cached is not None:
                return {**cached, "source": "cache"}
        rows = price_repository.get_bars_between(from_date, to_date, HISTORY_RANGE_MAX_ROWS + 1, session)
        if len(rows) > HISTORY_RANGE_MAX_ROWS:
            raise _too_many_rows()
        data = [{"symbol": row.symbol, **price_bar_to_dict(row)} for row in rows]
        return {"count": len(data), "from": str(from_date), "to": str(to_date),
                "data": data, "source": "database"}

    return cached_json_response(request, f"history_range:{from_date}:{to_date}", produce)


def _history_year_key(year: int) -> str:
    return f"history_year:{year}"


def _history_year_document(year: int) -> dict:
    """Every stored bar of one calendar year, per symbol, as parallel date-ascending columns."""
    rows = price_repository.get_bars_between(
        date(year, 1, 1), date(year, 12, 31), HISTORY_YEAR_MAX_ROWS + 1
    )
    if len(rows) > HISTORY_YEAR_MAX_ROWS:
        raise HTTPException(status_code=413, detail=f"Year {year} exceeds the {HISTORY_YEAR_MAX_ROWS:,}-row limit.")
    symbols = {}
    for row in rows:
        columns = symbols.get(row.symbol)
        if columns is None:
            columns = symbols[row.symbol] = {field: [] for field in _BAR_FIELDS}
        for field, value in price_bar_to_dict(row).items():
            columns[field].append(value)
    return {"year": year, "count": len(rows), "symbols": symbols}


def warm_history_years() -> None:
    """Build the calendar-year documents of the stored history window ahead of any request.

    Run in the background after each cache load: reading a year from the
    database takes several seconds on the hosted instance, so clients doing a
    full load then download prepared documents instead of waiting on it.
    """
    if db.SessionLocal is None:
        return
    this_year = date.today().year
    for year in range(this_year, this_year - HISTORY_YEARS - 1, -1):
        try:
            compressed_document(_history_year_key(year), lambda: _history_year_document(year))
        except Exception as error:
            logger.warning("Could not prepare the %d history document: %s", year, error)
    logger.info("History year documents prepared (%d-%d).", this_year - HISTORY_YEARS, this_year)


cache.after_load_callbacks.append(warm_history_years)


@router.get(
    "/history/year/{year}",
    summary="One calendar year of history (all assets, column format)",
    description=(
        "Returns every stored daily bar of one calendar year for every asset, grouped per symbol "
        "as parallel arrays sorted by date (oldest first): "
        "`symbols[symbol] = {date: [...], open: [...], high: [...], low: [...], close: [...], volume: [...]}`. "
        "A year without data returns an empty `symbols` object.\n\n"
        "This is the fast path for loading the full history: the years of the stored window are "
        "prepared in memory after every cache reload, so requests (also in parallel) do not wait "
        "on the database. The column format is about half the size of the row format of "
        "`/finance/history/range`."
    ),
)
def get_history_year(
    request: Request,
    year: int = Path(..., ge=1970, le=2200, description="Calendar year.", examples=[2024]),
):
    return cached_json_response(request, _history_year_key(year), lambda: _history_year_document(year))


@router.get(
    "/last-updated",
    summary="Most recent stored date per asset",
    description="Returns the latest date available in the database for each symbol — a quick way to verify the daily fetch ran.",
    responses=examples.GET_LAST_UPDATED,
)
def get_last_updated(session: Session = Depends(get_db)):
    return [
        {"symbol": row.symbol, "last_date": str(row.last_date)}
        for row in price_repository.get_last_updated(session)
    ]


@router.get(
    "/assets",
    summary="List all tracked assets",
    description="Returns the full catalogue of tracked symbols grouped by asset class, with metadata (display code, region, unit).",
    responses=examples.LIST_ASSETS,
)
def list_assets():
    return catalog.get_catalog()


@router.get(
    "/logs/all",
    summary="All stored ingestion logs",
    description=(
        f"Returns every structured log event in the `api_logs` table (the last {LOG_RETENTION_DAYS} days; "
        "older rows are deleted nightly), sorted most-recent-first. Public: useful for checking that the "
        "nightly ingestion ran and which bars were skipped or repaired."
    ),
    responses=examples.GET_LOGS,
)
def get_all_logs(session: Session = Depends(get_db)):
    logs = get_recent_logs(session, days=None)
    return {"count": len(logs), "logs": logs}


def _with_catalogue_details(result: dict, symbol: str) -> dict:
    """Add name, display, region and unit from the catalogue when the symbol is tracked."""
    entry = catalog.get_symbol(symbol)
    if entry:
        result["name"] = entry.get("name")
        for field in ("display", "region", "unit"):
            if field in entry:
                result[field] = entry[field]
    return result


@router.get(
    "/symbol/{symbol}",
    summary="Latest bar for any stored symbol",
    description=(
        "Most recent daily bar for **any** symbol present in the database — works for the "
        "catalogue instruments as well as ad-hoc symbols added via `/finance/admin/backfill-symbol`.\n\n"
        "Returns 404 if the symbol has no stored data."
    ),
    responses=examples.GET_SYMBOL,
)
def get_symbol(
    symbol: str = Path(..., description="Exact Yahoo Finance symbol stored in the database.", examples=["^VIX", "LTC-USD"]),
    session: Session = Depends(get_db),
):
    row = price_repository.get_latest_bar(symbol, session)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No data for symbol '{symbol}'.")
    return _with_catalogue_details({"symbol": symbol, "latest": price_bar_to_dict(row)}, symbol)


@router.get(
    "/symbol/{symbol}/history",
    summary="Full history for any stored symbol",
    description=(
        "All stored daily bars (oldest first) for **any** symbol present in the database — "
        "catalogue instruments or ad-hoc symbols added via `/finance/admin/backfill-symbol`.\n\n"
        "Returns 404 if the symbol has no stored data."
    ),
    responses=examples.GET_SYMBOL_HISTORY,
)
def get_symbol_history(
    symbol: str = Path(..., description="Exact Yahoo Finance symbol stored in the database.", examples=["^VIX", "GC=F"]),
    session: Session = Depends(get_db),
):
    rows = price_repository.get_history(symbol, session)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No data for symbol '{symbol}'.")
    result = {"symbol": symbol, "count": len(rows), "history": [price_bar_to_dict(row) for row in rows]}
    return _with_catalogue_details(result, symbol)
