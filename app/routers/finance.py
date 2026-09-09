from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..asset_repo import add_asset, asset_exists, get_all_assets as get_tracked_assets
from ..assets import ALL_ASSETS, CRYPTO, CRYPTO_MAP, ETFS, ETF_MAP, FX_PAIRS, INDEXES, METAL_MAP, PRECIOUS_METALS, STOCKS, STOCK_MAP, SYMBOL_MAP
from ..cache import details as cache_details, get_all, get_symbol, invalidate as invalidate_cache, refresh as refresh_cache, stats as cache_stats
from ..config import ADMIN_KEY
from ..db import engine, get_db
from ..ingestion import backfill, backfill_all, backfill_missing, check_symbol, ingest_daily_all

router = APIRouter()


class AddAssetRequest(BaseModel):
    symbol: str
    name: Optional[str] = None
    asset_type: Optional[str] = None
    properties: Optional[dict] = None


def _resp(example, description="Successful response"):
    return {200: {"description": description, "content": {"application/json": {"example": example}}}}


def _latest(symbol: str, db: Session):
    sql = text(
        "SELECT date, open, high, low, close, volume "
        "FROM daily_prices WHERE symbol = :symbol ORDER BY date DESC LIMIT 1"
    )
    return db.execute(sql, {"symbol": symbol}).fetchone()


def _history(symbol: str, db: Session, limit: int = None):
    sql = (
        "SELECT date, open, high, low, close, volume "
        "FROM daily_prices WHERE symbol = :symbol ORDER BY date ASC"
    )
    params = {"symbol": symbol}
    if limit:
        sql += " LIMIT :limit"
        params["limit"] = int(limit)
    return db.execute(text(sql), params).fetchall()


def _row_to_dict(row):
    if row is None:
        return None
    return {
        "date":   str(row.date),
        "open":   row.open,
        "high":   row.high,
        "low":    row.low,
        "close":  row.close,
        "volume": row.volume,
    }


def require_admin(request: Request):
    if ADMIN_KEY and request.headers.get("X-Admin-Key") != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key.")


@router.get(
    "/fx/rates",
    summary="Latest rate for all FX pairs",
    description="Returns the most recent daily bar for every tracked FX pair, in order.",
    responses=_resp([
        {"symbol": "EURUSD=X", "display": "EURUSD", "name": "Euro / US Dollar",
         "latest": {"date": "2026-09-08", "open": 1.162791, "high": 1.163873,
                    "low": 1.160000, "close": 1.161710, "volume": 0}},
        {"symbol": "GBPUSD=X", "display": "GBPUSD", "name": "British Pound / US Dollar",
         "latest": {"date": "2026-09-08", "open": 1.354224, "high": 1.355326,
                    "low": 1.352265, "close": 1.354536, "volume": 0}},
    ]),
)
def get_all_fx_rates(db: Session = Depends(get_db)):
    result = []
    for pair in FX_PAIRS:
        row = _latest(pair["symbol"], db)
        result.append({
            "symbol":  pair["symbol"],
            "display": pair["display"],
            "name":    pair["name"],
            "latest":  _row_to_dict(row),
        })
    return result


@router.get(
    "/fx/rates/{pair}",
    summary="Latest rate for one FX pair",
    description=(
        "Latest daily bar for a single pair. The pair code is given **without** the currency "
        "notation and is case-insensitive; `=X` is appended automatically."
    ),
    responses=_resp({
        "symbol": "EURUSD=X",
        "display": "EURUSD",
        "name": "Euro / US Dollar",
        "latest": {"date": "2026-09-08", "open": 1.162791, "high": 1.163873,
                   "low": 1.160000, "close": 1.161710, "volume": 0},
    }),
)
def get_fx_rate(
    pair: str = Path(..., description="Pair code without the `=X` suffix.", examples=["EURUSD", "JPYUSD"]),
    db: Session = Depends(get_db),
):
    symbol = f"{pair.upper()}=X"
    if symbol not in SYMBOL_MAP:
        raise HTTPException(status_code=404, detail=f"FX pair '{pair}' not tracked.")
    row = _latest(symbol, db)
    meta = SYMBOL_MAP[symbol]
    return {
        "symbol":  symbol,
        "display": meta["display"],
        "name":    meta["name"],
        "latest":  _row_to_dict(row),
    }


@router.get(
    "/fx/history/{pair}",
    summary="Full history for one FX pair",
    description=(
        "All stored daily bars (oldest first) for a single FX pair. "
        "With a fresh backfill this covers roughly 5 years."
    ),
    responses=_resp({
        "symbol": "EURUSD=X",
        "display": "EURUSD",
        "name": "Euro / US Dollar",
        "count": 1300,
        "history": [
            {"date": "2021-09-09", "open": 1.1810, "high": 1.1840, "low": 1.1800, "close": 1.1825, "volume": 0},
            {"date": "2026-09-08", "open": 1.1628, "high": 1.1639, "low": 1.1600, "close": 1.1617, "volume": 0},
        ],
    }),
)
def get_fx_history(
    pair: str = Path(..., description="Pair code without the `=X` suffix.", examples=["GBPUSD", "CHFUSD"]),
    db: Session = Depends(get_db),
):
    symbol = f"{pair.upper()}=X"
    if symbol not in SYMBOL_MAP:
        raise HTTPException(status_code=404, detail=f"FX pair '{pair}' not tracked.")
    rows = _history(symbol, db)
    meta = SYMBOL_MAP[symbol]
    return {
        "symbol":  symbol,
        "display": meta["display"],
        "name":    meta["name"],
        "count":   len(rows),
        "history": [_row_to_dict(r) for r in rows],
    }


@router.get(
    "/indexes",
    summary="Latest value for all indexes",
    description="Returns the most recent daily bar for every tracked stock index, in order.",
    responses=_resp([
        {"symbol": "^GSPC", "name": "S&P 500", "region": "US",
         "latest": {"date": "2026-09-04", "open": 7750.190, "high": 7750.190,
                    "low": 7706.120, "close": 7718.600, "volume": 4103570000}},
        {"symbol": "^N225", "name": "Nikkei 225", "region": "JP",
         "latest": {"date": "2026-09-08", "open": 65843.688, "high": 66791.844,
                    "low": 65269.328, "close": 65269.328, "volume": 0}},
    ]),
)
def get_all_indexes(db: Session = Depends(get_db)):
    result = []
    for idx in INDEXES:
        row = _latest(idx["symbol"], db)
        result.append({
            "symbol": idx["symbol"],
            "name":   idx["name"],
            "region": idx["region"],
            "latest": _row_to_dict(row),
        })
    return result


@router.get(
    "/indexes/{symbol}",
    summary="Latest value for one index",
    description=(
        "Latest daily bar for a single index. Provide the symbol **without** the `^` prefix "
        "(added automatically), case-insensitive."
    ),
    responses=_resp({
        "symbol": "^GSPC",
        "name": "S&P 500",
        "region": "US",
        "latest": {"date": "2026-09-04", "open": 7750.190, "high": 7750.190,
                   "low": 7706.120, "close": 7718.600, "volume": 4103570000},
    }),
)
def get_index(
    symbol: str = Path(..., description="Index code without the `^` prefix.", examples=["GSPC", "N225", "GDAXI"]),
    db: Session = Depends(get_db),
):
    full_symbol = f"^{symbol.upper()}"
    if full_symbol not in SYMBOL_MAP:
        raise HTTPException(status_code=404, detail=f"Index '{symbol}' not tracked.")
    row = _latest(full_symbol, db)
    meta = SYMBOL_MAP[full_symbol]
    return {
        "symbol": full_symbol,
        "name":   meta["name"],
        "region": meta["region"],
        "latest": _row_to_dict(row),
    }


@router.get(
    "/indexes/{symbol}/history",
    summary="Full history for one index",
    description=(
        "All stored daily bars (oldest first) for a single index. "
        "With a fresh backfill this covers roughly 5 years."
    ),
    responses=_resp({
        "symbol": "^GSPC",
        "name": "S&P 500",
        "region": "US",
        "count": 1255,
        "history": [
            {"date": "2021-09-09", "open": 4500.0, "high": 4520.0, "low": 4495.0, "close": 4512.5, "volume": 3900000000},
            {"date": "2026-09-04", "open": 7750.2, "high": 7750.2, "low": 7706.1, "close": 7718.6, "volume": 4103570000},
        ],
    }),
)
def get_index_history(
    symbol: str = Path(..., description="Index code without the `^` prefix.", examples=["IXIC", "HSI", "GDAXI"]),
    db: Session = Depends(get_db),
):
    full_symbol = f"^{symbol.upper()}"
    if full_symbol not in SYMBOL_MAP:
        raise HTTPException(status_code=404, detail=f"Index '{symbol}' not tracked.")
    rows = _history(full_symbol, db)
    meta = SYMBOL_MAP[full_symbol]
    return {
        "symbol":  full_symbol,
        "name":    meta["name"],
        "region":  meta["region"],
        "count":   len(rows),
        "history": [_row_to_dict(r) for r in rows],
    }


@router.get(
    "/metals",
    summary="Latest price for all precious metals",
    description="Returns the most recent daily bar for Gold, Silver, Platinum and Palladium.",
    responses=_resp([
        {"symbol": "GC=F", "display": "XAU", "name": "Gold", "unit": "USD per troy ounce",
         "latest": {"date": "2026-09-08", "open": 4466.5, "high": 4488.8,
                    "low": 4426.2, "close": 4443.5, "volume": 127903}},
        {"symbol": "SI=F", "display": "XAG", "name": "Silver", "unit": "USD per troy ounce",
         "latest": {"date": "2026-09-08", "open": 66.735, "high": 67.835,
                    "low": 66.025, "close": 66.735, "volume": 27451}},
    ]),
)
def get_all_metals(db: Session = Depends(get_db)):
    result = []
    for metal in PRECIOUS_METALS:
        row = _latest(metal["symbol"], db)
        result.append({
            "symbol":  metal["symbol"],
            "display": metal["display"],
            "name":    metal["name"],
            "unit":    metal["unit"],
            "latest":  _row_to_dict(row),
        })
    return result


@router.get(
    "/metals/{metal}",
    summary="Latest price for one precious metal",
    description=(
        "Latest daily bar for a single precious metal, addressed by short name "
        "(`gold`, `silver`, `platinum`, `palladium`), case-insensitive."
    ),
    responses=_resp({
        "symbol": "GC=F",
        "display": "XAU",
        "name": "Gold",
        "unit": "USD per troy ounce",
        "latest": {"date": "2026-09-08", "open": 4466.5, "high": 4488.8,
                   "low": 4426.2, "close": 4443.5, "volume": 127903},
    }),
)
def get_metal(
    metal: str = Path(..., description="Metal name: gold, silver, platinum or palladium.", examples=["gold", "silver"]),
    db: Session = Depends(get_db),
):
    asset = METAL_MAP.get(metal.lower())
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Precious metal '{metal}' not tracked.")
    row = _latest(asset["symbol"], db)
    return {
        "symbol":  asset["symbol"],
        "display": asset["display"],
        "name":    asset["name"],
        "unit":    asset["unit"],
        "latest":  _row_to_dict(row),
    }


@router.get(
    "/metals/{metal}/history",
    summary="Full history for one precious metal",
    description=(
        "All stored daily bars (oldest first) for a single precious metal. "
        "With a fresh backfill this covers roughly 5 years."
    ),
    responses=_resp({
        "symbol": "GC=F",
        "display": "XAU",
        "name": "Gold",
        "unit": "USD per troy ounce",
        "count": 1257,
        "history": [
            {"date": "2021-09-09", "open": 1790.0, "high": 1805.0, "low": 1785.5, "close": 1794.2, "volume": 120000},
            {"date": "2026-09-08", "open": 4466.5, "high": 4488.8, "low": 4426.2, "close": 4443.5, "volume": 127903},
        ],
    }),
)
def get_metal_history(
    metal: str = Path(..., description="Metal name: gold, silver, platinum or palladium.", examples=["platinum", "palladium"]),
    db: Session = Depends(get_db),
):
    asset = METAL_MAP.get(metal.lower())
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Precious metal '{metal}' not tracked.")
    rows = _history(asset["symbol"], db)
    return {
        "symbol":  asset["symbol"],
        "display": asset["display"],
        "name":    asset["name"],
        "unit":    asset["unit"],
        "count":   len(rows),
        "history": [_row_to_dict(r) for r in rows],
    }


@router.get(
    "/stocks",
    summary="Latest price for all stocks",
    description="Returns the most recent daily bar for every tracked stock.",
    responses=_resp([
        {"symbol": "NVDA", "name": "NVIDIA",
         "latest": {"date": "2026-09-08", "open": 220.0, "high": 225.0,
                    "low": 218.0, "close": 223.67, "volume": 50000000}},
        {"symbol": "AAPL", "name": "Apple",
         "latest": {"date": "2026-09-08", "open": 313.0, "high": 316.0,
                    "low": 312.0, "close": 315.34, "volume": 30000000}},
    ]),
)
def get_all_stocks(db: Session = Depends(get_db)):
    result = []
    for stock in STOCKS:
        row = _latest(stock["symbol"], db)
        result.append({
            "symbol": stock["symbol"],
            "name":   stock["name"],
            "latest": _row_to_dict(row),
        })
    return result


@router.get(
    "/stocks/{symbol}",
    summary="Latest price for one stock",
    description="Latest daily bar for a single stock, addressed by ticker symbol (e.g. `NVDA`, `AAPL`).",
    responses=_resp({
        "symbol": "NVDA",
        "name": "NVIDIA",
        "latest": {"date": "2026-09-08", "open": 220.0, "high": 225.0,
                   "low": 218.0, "close": 223.67, "volume": 50000000},
    }),
)
def get_stock(
    symbol: str = Path(..., description="Stock ticker symbol.", examples=["NVDA", "AAPL"]),
    db: Session = Depends(get_db),
):
    asset = STOCK_MAP.get(symbol.lower())
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol}' not tracked.")
    row = _latest(asset["symbol"], db)
    return {
        "symbol": asset["symbol"],
        "name":   asset["name"],
        "latest": _row_to_dict(row),
    }


@router.get(
    "/stocks/{symbol}/history",
    summary="Full history for one stock",
    description="All stored daily bars (oldest first) for a single stock.",
    responses=_resp({
        "symbol": "NVDA",
        "name": "NVIDIA",
        "count": 1257,
        "history": [
            {"date": "2021-09-09", "open": 220.0, "high": 225.0, "low": 218.0, "close": 222.5, "volume": 40000000},
            {"date": "2026-09-08", "open": 220.0, "high": 225.0, "low": 218.0, "close": 223.67, "volume": 50000000},
        ],
    }),
)
def get_stock_history(
    symbol: str = Path(..., description="Stock ticker symbol.", examples=["NVDA", "AAPL"]),
    db: Session = Depends(get_db),
):
    asset = STOCK_MAP.get(symbol.lower())
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol}' not tracked.")
    rows = _history(asset["symbol"], db)
    return {
        "symbol": asset["symbol"],
        "name":   asset["name"],
        "count":  len(rows),
        "history": [_row_to_dict(r) for r in rows],
    }


@router.get(
    "/etfs",
    summary="Latest price for all ETFs",
    description="Returns the most recent daily bar for every tracked ETF.",
    responses=_resp([
        {"symbol": "VOO", "name": "Vanguard S&P 500 ETF",
         "latest": {"date": "2026-09-08", "open": 585.0, "high": 590.0,
                    "low": 582.0, "close": 588.9, "volume": 4000000}},
        {"symbol": "QQQ", "name": "Invesco Nasdaq-100 ETF",
         "latest": {"date": "2026-09-08", "open": 560.0, "high": 565.0,
                    "low": 557.0, "close": 563.4, "volume": 40000000}},
    ]),
)
def get_all_etfs(db: Session = Depends(get_db)):
    result = []
    for etf in ETFS:
        row = _latest(etf["symbol"], db)
        result.append({
            "symbol": etf["symbol"],
            "name":   etf["name"],
            "latest": _row_to_dict(row),
        })
    return result


@router.get(
    "/etfs/{symbol}",
    summary="Latest price for one ETF",
    description="Latest daily bar for a single ETF, addressed by ticker symbol (e.g. `VOO`, `QQQ`).",
    responses=_resp({
        "symbol": "VOO",
        "name": "Vanguard S&P 500 ETF",
        "latest": {"date": "2026-09-08", "open": 585.0, "high": 590.0,
                   "low": 582.0, "close": 588.9, "volume": 4000000},
    }),
)
def get_etf(
    symbol: str = Path(..., description="ETF ticker symbol.", examples=["VOO", "QQQ"]),
    db: Session = Depends(get_db),
):
    asset = ETF_MAP.get(symbol.lower())
    if asset is None:
        raise HTTPException(status_code=404, detail=f"ETF '{symbol}' not tracked.")
    row = _latest(asset["symbol"], db)
    return {
        "symbol": asset["symbol"],
        "name":   asset["name"],
        "latest": _row_to_dict(row),
    }


@router.get(
    "/etfs/{symbol}/history",
    summary="Full history for one ETF",
    description="All stored daily bars (oldest first) for a single ETF.",
    responses=_resp({
        "symbol": "VOO",
        "name": "Vanguard S&P 500 ETF",
        "count": 1257,
        "history": [
            {"date": "2021-09-09", "open": 400.0, "high": 405.0, "low": 398.0, "close": 402.5, "volume": 3000000},
            {"date": "2026-09-08", "open": 585.0, "high": 590.0, "low": 582.0, "close": 588.9, "volume": 4000000},
        ],
    }),
)
def get_etf_history(
    symbol: str = Path(..., description="ETF ticker symbol.", examples=["VOO", "QQQ"]),
    db: Session = Depends(get_db),
):
    asset = ETF_MAP.get(symbol.lower())
    if asset is None:
        raise HTTPException(status_code=404, detail=f"ETF '{symbol}' not tracked.")
    rows = _history(asset["symbol"], db)
    return {
        "symbol": asset["symbol"],
        "name":   asset["name"],
        "count":  len(rows),
        "history": [_row_to_dict(r) for r in rows],
    }


@router.get(
    "/crypto",
    summary="Latest price for all cryptocurrencies",
    description="Returns the most recent daily bar for every tracked cryptocurrency.",
    responses=_resp([
        {"symbol": "BTC-USD", "display": "BTC", "name": "Bitcoin",
         "latest": {"date": "2026-09-08", "open": 110000.0, "high": 112000.0,
                    "low": 109000.0, "close": 111500.0, "volume": 30000000000}},
        {"symbol": "ETH-USD", "display": "ETH", "name": "Ethereum",
         "latest": {"date": "2026-09-08", "open": 4200.0, "high": 4300.0,
                    "low": 4150.0, "close": 4250.0, "volume": 15000000000}},
    ]),
)
def get_all_crypto(db: Session = Depends(get_db)):
    result = []
    for coin in CRYPTO:
        row = _latest(coin["symbol"], db)
        result.append({
            "symbol":  coin["symbol"],
            "display": coin["display"],
            "name":    coin["name"],
            "latest":  _row_to_dict(row),
        })
    return result


@router.get(
    "/crypto/{symbol}",
    summary="Latest price for one cryptocurrency",
    description="Latest daily bar for a single cryptocurrency, addressed by ticker (e.g. `BTC-USD`, `ETH-USD`).",
    responses=_resp({
        "symbol": "BTC-USD",
        "display": "BTC",
        "name": "Bitcoin",
        "latest": {"date": "2026-09-08", "open": 110000.0, "high": 112000.0,
                   "low": 109000.0, "close": 111500.0, "volume": 30000000000},
    }),
)
def get_crypto(
    symbol: str = Path(..., description="Crypto ticker symbol.", examples=["BTC-USD", "ETH-USD"]),
    db: Session = Depends(get_db),
):
    asset = CRYPTO_MAP.get(symbol.lower())
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Cryptocurrency '{symbol}' not tracked.")
    row = _latest(asset["symbol"], db)
    return {
        "symbol":  asset["symbol"],
        "display": asset["display"],
        "name":    asset["name"],
        "latest":  _row_to_dict(row),
    }


@router.get(
    "/crypto/{symbol}/history",
    summary="Full history for one cryptocurrency",
    description="All stored daily bars (oldest first) for a single cryptocurrency.",
    responses=_resp({
        "symbol": "BTC-USD",
        "display": "BTC",
        "name": "Bitcoin",
        "count": 1257,
        "history": [
            {"date": "2021-09-09", "open": 46000.0, "high": 47000.0, "low": 45500.0, "close": 46500.0, "volume": 25000000000},
            {"date": "2026-09-08", "open": 110000.0, "high": 112000.0, "low": 109000.0, "close": 111500.0, "volume": 30000000000},
        ],
    }),
)
def get_crypto_history(
    symbol: str = Path(..., description="Crypto ticker symbol.", examples=["BTC-USD", "ETH-USD"]),
    db: Session = Depends(get_db),
):
    asset = CRYPTO_MAP.get(symbol.lower())
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Cryptocurrency '{symbol}' not tracked.")
    rows = _history(asset["symbol"], db)
    return {
        "symbol":  asset["symbol"],
        "display": asset["display"],
        "name":    asset["name"],
        "count":   len(rows),
        "history": [_row_to_dict(r) for r in rows],
    }


@router.get(
    "/history/all",
    summary="Dump: all history for all assets",
    description=(
        "Returns **every stored daily bar** for every asset in one response, "
        "sorted by symbol then date (oldest first). Each entry contains the `symbol` plus "
        "`date, open, high, low, close, volume`.\n\n"
        "This is the big export endpoint — the default cap is 50,000 rows "
        "(the full 5-year dataset is ~31,000)."
    ),
    responses=_resp({
        "count": 2,
        "from": "2021-09-09",
        "to": "2026-09-08",
        "data": [
            {"symbol": "EURUSD=X", "date": "2021-09-09", "open": 1.1810, "high": 1.1840,
             "low": 1.1800, "close": 1.1825, "volume": 0},
            {"symbol": "EURUSD=X", "date": "2026-09-08", "open": 1.1628, "high": 1.1639,
             "low": 1.1600, "close": 1.1617, "volume": 0},
        ],
    }),
)
def get_history_all(
    limit: int = Query(50000, ge=1, le=500000, description="Maximum number of rows to return."),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text(
            "SELECT symbol, date, open, high, low, close, volume "
            "FROM daily_prices ORDER BY symbol, date ASC LIMIT :limit"
        ),
        {"limit": limit},
    ).fetchall()
    data = [{"symbol": r.symbol, **_row_to_dict(r)} for r in rows]
    first = data[0] if data else None
    last = data[-1] if data else None
    return {"count": len(data), "from": first["date"] if first else None,
            "to": last["date"] if last else None, "data": data}


@router.get(
    "/history/range",
    summary="History between two dates (all assets)",
    description=(
        "Returns every stored daily bar **between two inclusive dates** for every asset, "
        "sorted by symbol then date. Both query parameters are required, format `YYYY-MM-DD`.\n\n"
        "Example: `?from=2024-01-01&to=2024-12-31` gives all assets for the 2024 calendar year."
    ),
    responses=_resp({
        "count": 2,
        "from": "2024-01-02",
        "to": "2024-01-03",
        "data": [
            {"symbol": "EURUSD=X", "date": "2024-01-02", "open": 1.0940, "high": 1.0960,
             "low": 1.0920, "close": 1.0950, "volume": 0},
            {"symbol": "GC=F", "date": "2024-01-03", "open": 2045.0, "high": 2060.0,
             "low": 2040.0, "close": 2052.5, "volume": 150000},
        ],
    }),
)
def get_history_range(
    from_date: date = Query(..., alias="from", description="Start date, inclusive. Format `YYYY-MM-DD`.", examples=["2024-01-01"]),
    to_date: date = Query(..., alias="to", description="End date, inclusive. Format `YYYY-MM-DD`.", examples=["2024-12-31"]),
    db: Session = Depends(get_db),
):
    if from_date > to_date:
        raise HTTPException(status_code=400, detail="'from' must be less than or equal to 'to'.")
    rows = db.execute(
        text(
            "SELECT symbol, date, open, high, low, close, volume "
            "FROM daily_prices WHERE date BETWEEN :from AND :to ORDER BY symbol, date ASC"
        ),
        {"from": from_date, "to": to_date},
    ).fetchall()
    data = [{"symbol": r.symbol, **_row_to_dict(r)} for r in rows]
    return {"count": len(data), "from": str(from_date), "to": str(to_date), "data": data}


@router.get(
    "/last-updated",
    summary="Most recent stored date per asset",
    description="Returns the latest date available in the database for each symbol — a quick way to verify the daily fetch ran.",
    responses=_resp([
        {"symbol": "EURUSD=X", "last_date": "2026-09-08"},
        {"symbol": "GC=F", "last_date": "2026-09-08"},
    ]),
)
def get_last_updated(db: Session = Depends(get_db)):
    rows = db.execute(
        text("SELECT symbol, MAX(date) AS last_date FROM daily_prices GROUP BY symbol ORDER BY symbol")
    ).fetchall()
    return [{"symbol": r.symbol, "last_date": str(r.last_date)} for r in rows]


@router.get(
    "/assets",
    summary="List all tracked assets",
    description="Returns the full catalogue of tracked symbols grouped by asset class, with metadata (display code, region, unit).",
    responses=_resp({
        "fx_pairs": [{"symbol": "EURUSD=X", "display": "EURUSD", "name": "Euro / US Dollar"}],
        "indexes": [{"symbol": "^GSPC", "name": "S&P 500", "region": "US"}],
        "precious_metals": [{"symbol": "GC=F", "display": "XAU", "name": "Gold", "unit": "USD per troy ounce"}],
        "stocks": [{"symbol": "NVDA", "name": "NVIDIA"}],
        "etfs": [{"symbol": "VOO", "name": "Vanguard S&P 500 ETF"}],
        "crypto": [{"symbol": "BTC-USD", "display": "BTC", "name": "Bitcoin"}],
    }),
)
def list_assets():
    return {
        "fx_pairs":        FX_PAIRS,
        "indexes":         INDEXES,
        "precious_metals": PRECIOUS_METALS,
        "stocks":          STOCKS,
        "etfs":            ETFS,
        "crypto":          CRYPTO,
    }


@router.get(
    "/admin/backfill-symbol",
    summary="Backfill 5 years for a single symbol (admin, fast)",
    description=(
        "**Fast path:** downloads ~5 years of daily data for **one arbitrary Yahoo Finance symbol** "
        "in a single request — the way to add a new instrument without restarting or editing the "
        "asset list. Because it hits Yahoo once, no inter-request throttling is needed; it still "
        "retries with exponential backoff if rate limited.\n\n"
        "`symbol` is any valid Yahoo Finance ticker (e.g. `^VIX`, `LTC-USD`, `GC=F`). "
        "Upserts, so re-running just refreshes existing rows. Takes ~1 minute.\n\n"
        "For bulk/backfilling-many use the slow endpoint `POST /finance/admin/backfill-missing`."
    ),
    responses=_resp({
        "status": "done",
        "symbol": "^VIX",
        "rows_written": 1250,
        "latest": {"date": "2026-09-08", "open": 15.2, "high": 15.5,
                   "low": 14.8, "close": 15.1, "volume": 120000},
    }),
    dependencies=[Depends(require_admin)],
)
def run_backfill_symbol(
    symbol: str = Query(..., description="Yahoo Finance symbol to backfill.", examples=["^VIX", "LTC-USD"]),
    db: Session = Depends(get_db),
):
    rows = backfill(symbol)
    if rows > 0:
        invalidate_cache()
        refresh_cache()
    return {
        "status": "done" if rows > 0 else "no_data",
        "symbol": symbol,
        "rows_written": rows,
        "latest": _row_to_dict(_latest(symbol, db)),
    }


@router.get(
    "/admin/assets",
    summary="List all tracked assets from the database (admin)",
    description=(
        "Returns every asset stored in the `assets` table — the source of truth the "
        "backfill and daily ingestion now iterate over. Protected by the `X-Admin-Key` header."
    ),
    responses=_resp({
        "assets": [
            {"symbol": "EURUSD=X", "name": "Euro / US Dollar", "asset_type": "fx",
             "properties": {"display": "EUR/USD"}},
        ],
    }),
    dependencies=[Depends(require_admin)],
)
def list_tracked_assets(db: Session = Depends(get_db)):
    return {"assets": get_tracked_assets(db)}


@router.get(
    "/admin/assets/check",
    summary="Verify a symbol exists on Yahoo Finance (admin)",
    description=(
        "Combines `yf.Ticker().info` and `yf.download()`: the symbol is considered valid "
        "if **either** source returns data (avoids false negatives when one path is rate "
        "limited or empty). Also suggests a display name and an asset category."
    ),
    responses=_resp({
        "symbol": "LTC-USD",
        "exists": True,
        "confirmed_by": ["yf.Ticker.info", "yf.download"],
        "name": "Litecoin",
        "suggested_type": "crypto",
        "latest_close": 103.2,
        "note": None,
    }),
    dependencies=[Depends(require_admin)],
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
        "`POST /finance/admin/assets/{symbol}/backfill` to fetch its 5-year history."
    ),
    responses=_resp({
        "symbol": "LTC-USD",
        "name": "Litecoin",
        "asset_type": "crypto",
        "properties": {},
    }, description="The stored asset row"),
    dependencies=[Depends(require_admin)],
)
def add_tracked_asset(payload: AddAssetRequest):
    if asset_exists(payload.symbol):
        raise HTTPException(
            status_code=409, detail=f"Symbol '{payload.symbol}' is already tracked."
        )
    name, asset_type = payload.name, payload.asset_type
    if name is None or asset_type is None:
        chk = check_symbol(payload.symbol)
        if not chk["exists"]:
            raise HTTPException(
                status_code=422,
                detail=chk["note"] or f"Symbol '{payload.symbol}' was not found on Yahoo Finance.",
            )
        name = name or chk["name"] or payload.symbol
        asset_type = asset_type or chk["suggested_type"]
        if asset_type is None:
            raise HTTPException(
                status_code=422,
                detail="Could not infer an asset category. Provide an explicit asset_type.",
            )
    try:
        return add_asset(payload.symbol, name, asset_type, payload.properties)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post(
    "/admin/assets/{symbol}/backfill",
    summary="Backfill 5 years for a single tracked asset (admin, fast)",
    description=(
        "**Fast path:** downloads ~5 years of daily history for **one asset already present in the "
        "`assets` table** in a single request (no inter-request throttling needed; still retries "
        "with exponential backoff on rate limits). Upserts, so re-running just refreshes stored "
        "rows.\n\n"
        "For bulk/backfilling-many use the slow endpoint `POST /finance/admin/backfill-missing`."
    ),
    responses=_resp({
        "status": "done",
        "symbol": "LTC-USD",
        "rows_written": 1250,
        "latest": {"date": "2026-09-08", "open": 102.5, "high": 104.0,
                   "low": 101.8, "close": 103.2, "volume": 50000},
    }),
    dependencies=[Depends(require_admin)],
)
def backfill_tracked_asset(
    symbol: str = Path(..., description="Symbol present in the assets table.", examples=["LTC-USD", "NVDA"]),
    db: Session = Depends(get_db),
):
    if not asset_exists(symbol):
        raise HTTPException(
            status_code=404,
            detail=f"Symbol '{symbol}' is not in the assets table. Add it first via POST /finance/admin/assets.",
        )
    rows = backfill(symbol)
    if rows > 0:
        invalidate_cache()
        refresh_cache()
    return {
        "status": "done" if rows > 0 else "no_data",
        "symbol": symbol,
        "rows_written": rows,
        "latest": _row_to_dict(_latest(symbol, db)),
    }


@router.get(
    "/admin/cache/details",
    summary="Detailed cache report (admin)",
    description=(
        "Returns a full report of what is currently held in the in-memory cache: "
        "per-symbol row counts, coverage (first/last date), total rows, and an "
        "estimated memory footprint. Useful for confirming the cache is healthy "
        "after a deploy or an ingestion run."
    ),
    responses=_resp({
        "loaded_at": "2026-09-10T00:00:00+00:00",
        "symbols": 116,
        "total_rows": 153950,
        "est_memory_mb": 66.1,
        "per_symbol": [
            {"symbol": "EURUSD=X", "rows": 1300, "first_date": "2021-09-09", "last_date": "2026-09-10"},
        ],
    }),
    dependencies=[Depends(require_admin)],
)
def get_cache_details():
    return cache_details()


@router.get(
    "/symbol/{symbol}",
    summary="Latest bar for any stored symbol",
    description=(
        "Most recent daily bar for **any** symbol present in the database — works for the "
        "hardcoded instruments as well as ad-hoc symbols added via `/finance/admin/backfill-symbol`.\n\n"
        "6404 if the symbol has no stored data."
    ),
    responses=_resp({
        "symbol": "LTC-USD",
        "latest": {"date": "2026-09-08", "open": 102.5, "high": 104.0,
                   "low": 101.8, "close": 103.2, "volume": 50000},
    }),
)
def get_symbol(
    symbol: str = Path(..., description="Exact Yahoo Finance symbol stored in the database.", examples=["^VIX", "LTC-USD"]),
    db: Session = Depends(get_db),
):
    row = _latest(symbol, db)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No data for symbol '{symbol}'.")
    result = {"symbol": symbol, "latest": _row_to_dict(row)}
    meta = SYMBOL_MAP.get(symbol)
    if meta:
        result["name"] = meta.get("name")
        if "display" in meta:
            result["display"] = meta["display"]
        if "region" in meta:
            result["region"] = meta["region"]
        if "unit" in meta:
            result["unit"] = meta["unit"]
    return result


@router.get(
    "/symbol/{symbol}/history",
    summary="Full history for any stored symbol",
    description=(
        "All stored daily bars (oldest first) for **any** symbol present in the database — "
        "hardcoded instruments or ad-hoc symbols added via `/finance/admin/backfill-symbol`.\n\n"
        "Returns 404 if the symbol has no stored data."
    ),
    responses=_resp({
        "symbol": "LTC-USD",
        "count": 1200,
        "history": [
            {"date": "2021-09-09", "open": 195.0, "high": 198.5, "low": 194.0,
             "close": 196.2, "volume": 400000},
            {"date": "2026-09-08", "open": 102.5, "high": 104.0, "low": 101.8,
             "close": 103.2, "volume": 50000},
        ],
    }),
)
def get_symbol_history(
    symbol: str = Path(..., description="Exact Yahoo Finance symbol stored in the database.", examples=["^VIX", "GC=F"]),
    db: Session = Depends(get_db),
):
    rows = _history(symbol, db)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No data for symbol '{symbol}'.")
    result = {"symbol": symbol, "count": len(rows), "history": [_row_to_dict(r) for r in rows]}
    meta = SYMBOL_MAP.get(symbol)
    if meta:
        result["name"] = meta.get("name")
        if "display" in meta:
            result["display"] = meta["display"]
        if "region" in meta:
            result["region"] = meta["region"]
        if "unit" in meta:
            result["unit"] = meta["unit"]
    return result


def _ingestion_summary(db: Session, results):
    summary = []
    for asset in get_tracked_assets(db):
        row = _latest(asset["symbol"], db)
        summary.append({
            "symbol":       asset["symbol"],
            "name":         asset["name"],
            "asset_type":   asset["asset_type"],
            "rows_written": results.get(asset["symbol"]),
            "latest":       _row_to_dict(row),
        })
    return summary


@router.post(
    "/admin/backfill",
    summary="Backfill ALL assets (admin, medium speed)",
    description=(
        "Triggers the full 5-year backfill for **all tracked assets** (whether or not they "
        "already have history) and stores the data in the database. Throttled with the normal "
        "delay config (`BACKFILL_DELAY_SECONDS`, default ~2s between symbols). Protected by the "
        "`X-Admin-Key` header (send the value of the `ADMIN_KEY` environment variable). Takes "
        "several minutes.\n\n"
        "Usually `POST /finance/admin/backfill-missing` (slow, skips covered assets) is the safer "
        "choice. Returns the number of rows written per asset plus the latest stored value for each."
    ),
    responses=_resp({
        "status": "done",
        "fetched_at": "2026-09-08T12:00:00+00:00",
        "results": [
            {"symbol": "EURUSD=X", "name": "Euro / US Dollar", "rows_written": 1300,
             "latest": {"date": "2026-09-08", "open": 1.162791, "high": 1.163873,
                        "low": 1.160000, "close": 1.161710, "volume": 0}},
        ],
    }),
    dependencies=[Depends(require_admin)],
)
def run_backfill(db: Session = Depends(get_db)):
    invalidate_cache()
    results = backfill_all()
    refresh_cache()
    return {"status": "done", "fetched_at": datetime.now(timezone.utc).isoformat(),
            "results": _ingestion_summary(db, results)}


@router.post(
    "/admin/backfill-missing",
    summary="Backfill missing history (admin, slow & safe)",
    description=(
        "**Slow path, purpose-built to avoid Yahoo rate limits.** Downloads ~5 years of daily "
        "history **only for tracked assets whose stored data does not span ~5 years** (newly "
        "added assets, partially backfilled symbols, assets with only recent daily ingestion).\n\n"
        "It spaces every symbol out with a generous delay (default ~12s + jitter between "
        "symbols, configurable via `SLOW_BACKFILL_DELAY_SECONDS` / `SLOW_BACKFILL_JITTER_SECONDS`) "
        "and uses a gentler exponential backoff on rate limits "
        "(`SLOW_YF_RETRY_BASE_SECONDS`). Safe to re-run: covered assets are skipped.\n\n"
        "For a single asset (one quick request) use `POST /finance/admin/assets/{symbol}/backfill` "
        "instead. Protected by the `X-Admin-Key` header."
    ),
    responses=_resp({
        "status": "done",
        "fetched_at": "2026-09-08T12:00:00+00:00",
        "results": [
            {"symbol": "NVDA", "name": "NVIDIA", "asset_type": "stock", "rows_written": 1250,
             "latest": {"date": "2026-09-08", "open": 220.0, "high": 225.0,
                        "low": 218.0, "close": 223.67, "volume": 50000000}},
        ],
    }),
    dependencies=[Depends(require_admin)],
)
def run_backfill_missing(db: Session = Depends(get_db)):
    invalidate_cache()
    results = backfill_missing()
    refresh_cache()
    return {"status": "done", "fetched_at": datetime.now(timezone.utc).isoformat(),
            "results": _ingestion_summary(db, results)}


@router.get(
    "/cache/status",
    summary="Cache status",
    description=(
        "Returns metadata about the in-memory cache — number of symbols, total rows "
        "held in memory, and when it was last reloaded from the database."
    ),
)

def get_cache_status():
    return cache_stats()


@router.get(
    "/cache/all",
    summary="All data from memory (fast)",
    description=(
        "Returns every stored daily bar for every asset straight from the in-memory "
        "cache (no database hit). The cache is loaded at startup and refreshed after "
        "each scheduled ingestion."
    ),
    responses=_resp({
        "count": 31250,
        "symbols": 24,
        "data": [
            {"symbol": "EURUSD=X", "history": [
                {"date": "2021-09-09", "open": 1.1810, "high": 1.1840,
                 "low": 1.1800, "close": 1.1825, "volume": 0},
            ]},
        ],
    }),
)
def get_cache_all():
    cache = get_all()
    data = [{"symbol": sym, "history": history} for sym, history in cache.items()]
    total = sum(len(h) for h in cache.values())
    return {"count": total, "symbols": len(data), "data": data}


@router.get(
    "/cache/{symbol}",
    summary="History for one symbol from memory (fast)",
    description=(
        "Returns the full cached history for a single symbol straight from memory. "
        "Faster than the DB-backed endpoints — no database round-trip."
    ),
    responses=_resp({
        "symbol": "GC=F",
        "count": 1257,
        "history": [
            {"date": "2021-09-09", "open": 1790.0, "high": 1805.0, "low": 1785.5,
             "close": 1794.2, "volume": 120000},
        ],
    }),
)
def get_cache_symbol(
    symbol: str = Path(..., description="Exact Yahoo Finance symbol.", examples=["^VIX", "GC=F"]),
):
    history = get_symbol(symbol)
    if history is None:
        raise HTTPException(status_code=404, detail=f"No cached data for symbol '{symbol}'.")
    return {"symbol": symbol, "count": len(history), "history": history}


def _cache_by_type(symbols: list) -> dict:
    cache = get_all()
    wanted = {s["symbol"] for s in symbols}
    filtered = {sym: hist for sym, hist in cache.items() if sym in wanted}
    data = [{"symbol": sym, "history": hist} for sym, hist in filtered.items()]
    total = sum(len(h) for h in filtered.values())
    return {"count": total, "symbols": len(data), "data": data}


@router.get(
    "/cache/stocks",
    summary="All stock histories from memory (fast)",
    description="Returns the full cached 5-year history for every tracked stock straight from the in-memory cache.",
)
def get_cache_stocks():
    return _cache_by_type(STOCKS)


@router.get(
    "/cache/indexes",
    summary="All index histories from memory (fast)",
    description="Returns the full cached 5-year history for every tracked index straight from the in-memory cache.",
)
def get_cache_indexes():
    return _cache_by_type(INDEXES)


@router.get(
    "/cache/metals",
    summary="All metal histories from memory (fast)",
    description="Returns the full cached 5-year history for every tracked precious metal straight from the in-memory cache.",
)
def get_cache_metals():
    return _cache_by_type(PRECIOUS_METALS)


@router.get(
    "/cache/etfs",
    summary="All ETF histories from memory (fast)",
    description="Returns the full cached 5-year history for every tracked ETF straight from the in-memory cache.",
)
def get_cache_etfs():
    return _cache_by_type(ETFS)


@router.get(
    "/cache/cryptos",
    summary="All crypto histories from memory (fast)",
    description="Returns the full cached 5-year history for every tracked crypto asset straight from the in-memory cache.",
)
def get_cache_cryptos():
    return _cache_by_type(CRYPTO)


@router.get(
    "/logs",
    summary="Recent ingestion logs (last 7 days)",
    description=(
        "Returns all structured log events from the `api_logs` table for the past 7 days, "
        "sorted most-recent-first. Useful for diagnosing scheduler or fetch failures."
    ),
    responses=_resp({
        "count": 2,
        "logs": [
            {
                "id": 1,
                "recorded_at": "2026-09-08T23:00:12",
                "logger": "ingestion",
                "level": "INFO",
                "message": "Fetched ^GSPC (period=5d)",
                "symbol": "^GSPC",
                "duration_ms": 1234,
                "rows_written": 5,
                "success": True,
                "exception": None,
            },
        ],
    }),
)
def get_logs(db: Session = Depends(get_db)):
    rows = db.execute(
        text(
            "SELECT id, recorded_at, logger, level, message, symbol, "
            "duration_ms, rows_written, success, exception "
            "FROM api_logs WHERE recorded_at >= UTC_TIMESTAMP() - INTERVAL 7 DAY "
            "ORDER BY recorded_at DESC"
        )
    ).fetchall()
    logs = []
    for r in rows:
        logs.append({
            "id":           r.id,
            "recorded_at":  str(r.recorded_at),
            "logger":       r.logger,
            "level":        r.level,
            "message":      r.message,
            "symbol":       r.symbol,
            "duration_ms":  r.duration_ms,
            "rows_written": r.rows_written,
            "success":      bool(r.success),
            "exception":    r.exception,
        })
    return {"count": len(logs), "logs": logs}


@router.post(
    "/admin/ingest-daily",
    summary="Run daily ingestion now (admin)",
    description=(
        "Triggers the daily fetch for all assets immediately — the same work the automatic "
        "scheduler does at 23:00 UTC on weekdays. Protected by the `X-Admin-Key` header (send the "
        "value of the `ADMIN_KEY` environment variable).\n\n"
        "Returns the number of rows written per asset plus the latest stored value for each."
    ),
    responses=_resp({
        "status": "done",
        "fetched_at": "2026-09-08T12:00:00+00:00",
        "results": [
            {"symbol": "GC=F", "name": "Gold", "rows_written": 5,
             "latest": {"date": "2026-09-08", "open": 4466.5, "high": 4488.8,
                        "low": 4426.2, "close": 4443.5, "volume": 127903}},
        ],
    }),
    dependencies=[Depends(require_admin)],
)
def run_daily_ingest(db: Session = Depends(get_db)):
    invalidate_cache()
    results = ingest_daily_all()
    refresh_cache()
    return {"status": "done", "fetched_at": datetime.now(timezone.utc).isoformat(),
            "results": _ingestion_summary(db, results)}