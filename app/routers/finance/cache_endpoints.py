"""Public endpoints served straight from the in-memory price cache (no database round-trip)."""

from fastapi import APIRouter, HTTPException, Path, Request
from fastapi.responses import Response

from ... import cache, catalog
from . import examples
from .responses import cached_json_response

router = APIRouter()


@router.get(
    "/cache/status",
    summary="Cache status",
    description=(
        "Returns metadata about the in-memory cache — number of symbols, total rows "
        "held in memory, and when it was last reloaded from the database."
    ),
)
def get_cache_status():
    return cache.stats()


def _cached_histories(request: Request, key: str, asset_type: str | None = None) -> Response:
    """Every cached history (or only those of one asset type) as one document."""

    def produce():
        cached = cache.get_all()
        if asset_type is not None:
            wanted = {asset["symbol"] for asset in catalog.get_group(asset_type)}
            cached = {symbol: history for symbol, history in cached.items() if symbol in wanted}
        data = [{"symbol": symbol, "history": history} for symbol, history in cached.items()]
        total = sum(len(history) for history in cached.values())
        return {"count": total, "symbols": len(data), "data": data}

    return cached_json_response(request, key, produce)


@router.get(
    "/cache/all",
    summary="All data from memory (fast)",
    description=(
        "Returns every stored daily bar for every asset straight from the in-memory "
        "cache (no database hit). The cache is loaded at startup and refreshed after "
        "each scheduled ingestion."
    ),
    responses=examples.GET_CACHE_ALL,
)
def get_cache_all(request: Request):
    return _cached_histories(request, "cache:all")


@router.get(
    "/cache/stocks",
    summary="All stock histories from memory (fast)",
    description="Returns the full cached history window for every tracked stock straight from the in-memory cache.",
)
def get_cache_stocks(request: Request):
    return _cached_histories(request, "cache:stocks", "stock")


@router.get(
    "/cache/indexes",
    summary="All index histories from memory (fast)",
    description="Returns the full cached history window for every tracked index straight from the in-memory cache.",
)
def get_cache_indexes(request: Request):
    return _cached_histories(request, "cache:indexes", "index")


@router.get(
    "/cache/metals",
    summary="All metal histories from memory (fast)",
    description="Returns the full cached history window for every tracked precious metal straight from the in-memory cache.",
)
def get_cache_metals(request: Request):
    return _cached_histories(request, "cache:metals", "metal")


@router.get(
    "/cache/etfs",
    summary="All ETF histories from memory (fast)",
    description="Returns the full cached history window for every tracked ETF straight from the in-memory cache.",
)
def get_cache_etfs(request: Request):
    return _cached_histories(request, "cache:etfs", "etf")


@router.get(
    "/cache/cryptos",
    summary="All crypto histories from memory (fast)",
    description="Returns the full cached history window for every tracked crypto asset straight from the in-memory cache.",
)
def get_cache_cryptos(request: Request):
    return _cached_histories(request, "cache:cryptos", "crypto")


@router.get(
    "/cache/{symbol}",
    summary="History for one symbol from memory (fast)",
    description=(
        "Returns the full cached history for a single symbol straight from memory. "
        "Faster than the database-backed endpoints — no database round-trip."
    ),
    responses=examples.GET_CACHE_SYMBOL,
)
def get_cache_symbol(
    symbol: str = Path(..., description="Exact Yahoo Finance symbol.", examples=["^VIX", "GC=F"]),
):
    history = cache.get_symbol(symbol)
    if history is None:
        raise HTTPException(status_code=404, detail=f"No cached data for symbol '{symbol}'.")
    return {"symbol": symbol, "count": len(history), "history": history}
