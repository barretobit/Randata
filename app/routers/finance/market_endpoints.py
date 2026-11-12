"""Public endpoints per asset class: latest bar for all, latest bar for one, full history for one.

Every class (FX, indexes, metals, stocks, ETFs, crypto) behaves the same way;
only the URL code, the lookup and a few descriptive fields differ. Those
differences live in one `AssetClass` entry per class, and every route is a
one-line call into the shared functions below.
"""

from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from ... import catalog, price_repository
from ...db import get_db
from ...price_repository import price_bar_to_dict
from . import examples

router = APIRouter()


@dataclass(frozen=True)
class AssetClass:
    asset_type: str
    # Used in 404 messages: "<label> '<code>' not tracked."
    label: str
    # Catalogue entry for the code given in the URL, or None.
    find: Callable[[str], dict | None]
    # Descriptive fields shown before `latest` / `history`, in response order.
    fields: tuple[str, ...]


def _find_by_lowercase(asset_type: str) -> Callable[[str], dict | None]:
    return lambda code: catalog.get_lookup(asset_type).get(code.lower())


FX = AssetClass(
    "fx", "FX pair", lambda pair: catalog.get_symbol(f"{pair.upper()}=X"), ("symbol", "display", "name"),
)
INDEXES = AssetClass(
    "index", "Index", lambda code: catalog.get_symbol(f"^{code.upper()}"), ("symbol", "name", "region"),
)
METALS = AssetClass(
    "metal", "Precious metal", _find_by_lowercase("metal"), ("symbol", "display", "name", "unit"),
)
STOCKS = AssetClass("stock", "Stock", _find_by_lowercase("stock"), ("symbol", "name"))
ETFS = AssetClass("etf", "ETF", _find_by_lowercase("etf"), ("symbol", "name"))
CRYPTO = AssetClass("crypto", "Cryptocurrency", _find_by_lowercase("crypto"), ("symbol", "display", "name"))


def _describe(asset_class: AssetClass, asset: dict) -> dict:
    values = {
        "symbol":  asset["symbol"],
        "display": asset.get("display", asset["symbol"]),
        "name":    asset["name"],
        "region":  asset.get("region"),
        "unit":    asset.get("unit"),
    }
    return {field: values[field] for field in asset_class.fields}


def _find_or_404(asset_class: AssetClass, code: str) -> dict:
    asset = asset_class.find(code)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"{asset_class.label} '{code}' not tracked.")
    return asset


def list_latest(asset_class: AssetClass, session: Session) -> list[dict]:
    """Latest bar of every tracked asset of one class, in catalogue order."""
    assets = catalog.get_group(asset_class.asset_type)
    latest = price_repository.get_latest_bars([asset["symbol"] for asset in assets], session)
    return [
        {**_describe(asset_class, asset), "latest": price_bar_to_dict(latest.get(asset["symbol"]))}
        for asset in assets
    ]


def latest_one(asset_class: AssetClass, code: str, session: Session) -> dict:
    """Latest bar of one asset, addressed by its URL code."""
    asset = _find_or_404(asset_class, code)
    row = price_repository.get_latest_bar(asset["symbol"], session)
    return {**_describe(asset_class, asset), "latest": price_bar_to_dict(row)}


def history_one(asset_class: AssetClass, code: str, session: Session) -> dict:
    """Every stored bar of one asset, oldest first."""
    asset = _find_or_404(asset_class, code)
    rows = price_repository.get_history(asset["symbol"], session)
    return {
        **_describe(asset_class, asset),
        "count":   len(rows),
        "history": [price_bar_to_dict(row) for row in rows],
    }


_HISTORY_DESCRIPTION = (
    "All stored daily bars (oldest first) for a single {}. "
    "With a fresh backfill this covers roughly the configured history window."
)


# ---------------------------------------------------------------------------
# FX pairs
# ---------------------------------------------------------------------------

@router.get(
    "/fx/rates",
    summary="Latest rate for all FX pairs",
    description="Returns the most recent daily bar for every tracked FX pair, in order.",
    responses=examples.GET_ALL_FX_RATES,
)
def get_all_fx_rates(session: Session = Depends(get_db)):
    return list_latest(FX, session)


@router.get(
    "/fx/rates/{pair}",
    summary="Latest rate for one FX pair",
    description=(
        "Latest daily bar for a single pair. The pair code is given **without** the currency "
        "notation and is case-insensitive; `=X` is appended automatically."
    ),
    responses=examples.GET_FX_RATE,
)
def get_fx_rate(
    pair: str = Path(..., description="Pair code without the `=X` suffix.", examples=["EURUSD", "JPYUSD"]),
    session: Session = Depends(get_db),
):
    return latest_one(FX, pair, session)


@router.get(
    "/fx/rates/{pair}/history",
    summary="Full history for one FX pair",
    description=_HISTORY_DESCRIPTION.format("FX pair"),
    responses=examples.GET_FX_HISTORY,
)
@router.get(
    "/fx/history/{pair}",
    summary="Full history for one FX pair (deprecated path)",
    description=(
        _HISTORY_DESCRIPTION.format("FX pair")
        + "\n\nDeprecated: use `/finance/fx/rates/{pair}/history`, which matches the other asset classes."
    ),
    responses=examples.GET_FX_HISTORY,
    deprecated=True,
)
def get_fx_history(
    pair: str = Path(..., description="Pair code without the `=X` suffix.", examples=["GBPUSD", "CHFUSD"]),
    session: Session = Depends(get_db),
):
    return history_one(FX, pair, session)


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------

@router.get(
    "/indexes",
    summary="Latest value for all indexes",
    description="Returns the most recent daily bar for every tracked stock index, in order.",
    responses=examples.GET_ALL_INDEXES,
)
def get_all_indexes(session: Session = Depends(get_db)):
    return list_latest(INDEXES, session)


@router.get(
    "/indexes/{symbol}",
    summary="Latest value for one index",
    description=(
        "Latest daily bar for a single index. Provide the symbol **without** the `^` prefix "
        "(added automatically), case-insensitive."
    ),
    responses=examples.GET_INDEX,
)
def get_index(
    symbol: str = Path(..., description="Index code without the `^` prefix.", examples=["GSPC", "N225", "GDAXI"]),
    session: Session = Depends(get_db),
):
    return latest_one(INDEXES, symbol, session)


@router.get(
    "/indexes/{symbol}/history",
    summary="Full history for one index",
    description=_HISTORY_DESCRIPTION.format("index"),
    responses=examples.GET_INDEX_HISTORY,
)
def get_index_history(
    symbol: str = Path(..., description="Index code without the `^` prefix.", examples=["IXIC", "HSI", "GDAXI"]),
    session: Session = Depends(get_db),
):
    return history_one(INDEXES, symbol, session)


# ---------------------------------------------------------------------------
# Metals
# ---------------------------------------------------------------------------

_METAL_NAME = "Metal name: gold, silver, copper, platinum or palladium."


@router.get(
    "/metals",
    summary="Latest price for all precious metals",
    description="Returns the most recent daily bar for every tracked metal (gold, silver, copper, platinum, palladium).",
    responses=examples.GET_ALL_METALS,
)
def get_all_metals(session: Session = Depends(get_db)):
    return list_latest(METALS, session)


@router.get(
    "/metals/{metal}",
    summary="Latest price for one precious metal",
    description=(
        "Latest daily bar for a single precious metal, addressed by short name "
        "(`gold`, `silver`, `copper`, `platinum`, `palladium`), case-insensitive."
    ),
    responses=examples.GET_METAL,
)
def get_metal(
    metal: str = Path(..., description=_METAL_NAME, examples=["gold", "silver"]),
    session: Session = Depends(get_db),
):
    return latest_one(METALS, metal, session)


@router.get(
    "/metals/{metal}/history",
    summary="Full history for one precious metal",
    description=_HISTORY_DESCRIPTION.format("precious metal"),
    responses=examples.GET_METAL_HISTORY,
)
def get_metal_history(
    metal: str = Path(..., description=_METAL_NAME, examples=["platinum", "palladium"]),
    session: Session = Depends(get_db),
):
    return history_one(METALS, metal, session)


# ---------------------------------------------------------------------------
# Stocks
# ---------------------------------------------------------------------------

@router.get(
    "/stocks",
    summary="Latest price for all stocks",
    description="Returns the most recent daily bar for every tracked stock.",
    responses=examples.GET_ALL_STOCKS,
)
def get_all_stocks(session: Session = Depends(get_db)):
    return list_latest(STOCKS, session)


@router.get(
    "/stocks/{symbol}",
    summary="Latest price for one stock",
    description="Latest daily bar for a single stock, addressed by ticker symbol (e.g. `NVDA`, `AAPL`).",
    responses=examples.GET_STOCK,
)
def get_stock(
    symbol: str = Path(..., description="Stock ticker symbol.", examples=["NVDA", "AAPL"]),
    session: Session = Depends(get_db),
):
    return latest_one(STOCKS, symbol, session)


@router.get(
    "/stocks/{symbol}/history",
    summary="Full history for one stock",
    description="All stored daily bars (oldest first) for a single stock.",
    responses=examples.GET_STOCK_HISTORY,
)
def get_stock_history(
    symbol: str = Path(..., description="Stock ticker symbol.", examples=["NVDA", "AAPL"]),
    session: Session = Depends(get_db),
):
    return history_one(STOCKS, symbol, session)


# ---------------------------------------------------------------------------
# ETFs
# ---------------------------------------------------------------------------

@router.get(
    "/etfs",
    summary="Latest price for all ETFs",
    description="Returns the most recent daily bar for every tracked ETF.",
    responses=examples.GET_ALL_ETFS,
)
def get_all_etfs(session: Session = Depends(get_db)):
    return list_latest(ETFS, session)


@router.get(
    "/etfs/{symbol}",
    summary="Latest price for one ETF",
    description="Latest daily bar for a single ETF, addressed by ticker symbol (e.g. `VOO`, `QQQ`).",
    responses=examples.GET_ETF,
)
def get_etf(
    symbol: str = Path(..., description="ETF ticker symbol.", examples=["VOO", "QQQ"]),
    session: Session = Depends(get_db),
):
    return latest_one(ETFS, symbol, session)


@router.get(
    "/etfs/{symbol}/history",
    summary="Full history for one ETF",
    description="All stored daily bars (oldest first) for a single ETF.",
    responses=examples.GET_ETF_HISTORY,
)
def get_etf_history(
    symbol: str = Path(..., description="ETF ticker symbol.", examples=["VOO", "QQQ"]),
    session: Session = Depends(get_db),
):
    return history_one(ETFS, symbol, session)


# ---------------------------------------------------------------------------
# Crypto
# ---------------------------------------------------------------------------

@router.get(
    "/crypto",
    summary="Latest price for all cryptocurrencies",
    description="Returns the most recent daily bar for every tracked cryptocurrency.",
    responses=examples.GET_ALL_CRYPTO,
)
def get_all_crypto(session: Session = Depends(get_db)):
    return list_latest(CRYPTO, session)


@router.get(
    "/crypto/{symbol}",
    summary="Latest price for one cryptocurrency",
    description="Latest daily bar for a single cryptocurrency, addressed by ticker (e.g. `BTC-USD`, `ETH-USD`).",
    responses=examples.GET_CRYPTO,
)
def get_crypto(
    symbol: str = Path(..., description="Crypto ticker symbol.", examples=["BTC-USD", "ETH-USD"]),
    session: Session = Depends(get_db),
):
    return latest_one(CRYPTO, symbol, session)


@router.get(
    "/crypto/{symbol}/history",
    summary="Full history for one cryptocurrency",
    description="All stored daily bars (oldest first) for a single cryptocurrency.",
    responses=examples.GET_CRYPTO_HISTORY,
)
def get_crypto_history(
    symbol: str = Path(..., description="Crypto ticker symbol.", examples=["BTC-USD", "ETH-USD"]),
    session: Session = Depends(get_db),
):
    return history_one(CRYPTO, symbol, session)
