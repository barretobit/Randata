from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from ..assets import ALL_ASSETS, FX_PAIRS, INDEXES, METAL_MAP, PRECIOUS_METALS, SYMBOL_MAP
from ..config import ADMIN_KEY, DATABASE_URL
from ..db import get_db
from ..ingestion import backfill_all, ingest_daily_all

router = APIRouter()


def _latest(symbol: str, db: Session):
    sql = text(
        "SELECT date, open, high, low, close, volume "
        "FROM daily_prices WHERE symbol = :symbol ORDER BY date DESC LIMIT 1"
    )
    return db.execute(sql, {"symbol": symbol}).fetchone()


def _history(symbol: str, db: Session, limit: int = None):
    base = (
        "SELECT date, open, high, low, close, volume "
        "FROM daily_prices WHERE symbol = :symbol ORDER BY date ASC"
    )
    if limit:
        base += f" LIMIT {int(limit)}"
    return db.execute(text(base), {"symbol": symbol}).fetchall()


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


@router.get("/backfill")
def fetch_backfill_all(db: Session = Depends(get_db)):
    """Backfills ~5 years of history for ALL assets and returns the stored results."""
    results = backfill_all()
    summary = []
    for asset in ALL_ASSETS:
        row = _latest(asset["symbol"], db)
        summary.append({
            "symbol":       asset["symbol"],
            "name":         asset["name"],
            "rows_written": results.get(asset["symbol"]),
            "latest":       _row_to_dict(row),
        })
    return {"status": "done", "fetched_at": datetime.now(timezone.utc).isoformat(), "results": summary}


@router.get("/ingest-daily")
def fetch_daily_all(db: Session = Depends(get_db)):
    """Runs the daily fetch now for ALL tracked assets and returns the stored values."""
    results = ingest_daily_all()
    summary = []
    for asset in ALL_ASSETS:
        row = _latest(asset["symbol"], db)
        summary.append({
            "symbol":      asset["symbol"],
            "name":        asset["name"],
            "rows_written": results.get(asset["symbol"]),
            "latest":      _row_to_dict(row),
        })
    return {"status": "done", "fetched_at": datetime.now(timezone.utc).isoformat(), "results": summary}


@router.get("/db-check")
def db_check():
    """Diagnostic - opens a fresh connection to the database and reports the result."""
    if not DATABASE_URL:
        return {"configured": False, "detail": "DATABASE_URL is not configured."}
    parsed = urlparse(DATABASE_URL)
    result = {
        "configured": True,
        "host": parsed.hostname,
        "port": parsed.port,
        "database": parsed.path.lstrip("/"),
        "username": parsed.username,
    }
    try:
        engine = create_engine(DATABASE_URL, connect_args={"connect_timeout": 15})
        with engine.connect() as conn:
            db_row = conn.execute(text("SELECT DATABASE(), VERSION()")).fetchone()
            user_row = conn.execute(
                text("SELECT CURRENT_USER(), @@hostname, @@version_comment")
            ).fetchone()
            tables = [r[0] for r in conn.execute(text("SHOW TABLES")).fetchall()]
            src = conn.execute(
                text("SELECT HOST FROM information_schema.PROCESSLIST WHERE ID = CONNECTION_ID()")
            ).fetchone()
        result["connected"] = True
        result["database"] = db_row[0]
        result["server_version"] = db_row[1]
        result["current_user"] = user_row[0]
        result["server_hostname"] = user_row[1]
        result["version_comment"] = user_row[2]
        result["source_address"] = src[0] if src else None
        result["tables"] = tables
    except Exception as e:
        result["connected"] = False
        result["error_type"] = type(e).__name__
        result["error_message"] = str(e)
    return result


@router.get("/fx/rates")
def get_all_fx_rates(db: Session = Depends(get_db)):
    """Latest rate for all tracked FX pairs."""
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


@router.get("/fx/rates/{pair}")
def get_fx_rate(pair: str, db: Session = Depends(get_db)):
    """Latest rate for a specific FX pair. Example: EURUSD"""
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


@router.get("/fx/history/{pair}")
def get_fx_history(pair: str, db: Session = Depends(get_db)):
    """5-year daily history for a specific FX pair. Example: EURUSD"""
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


@router.get("/indexes")
def get_all_indexes(db: Session = Depends(get_db)):
    """Latest value for all tracked indexes."""
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


@router.get("/indexes/{symbol}")
def get_index(symbol: str, db: Session = Depends(get_db)):
    """
    Latest value for a specific index.
    Symbol examples: GSPC (S&P 500), IXIC (NASDAQ), FTSE, GDAXI, N225
    The ^ prefix is added automatically.
    """
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


@router.get("/indexes/{symbol}/history")
def get_index_history(symbol: str, db: Session = Depends(get_db)):
    """5-year daily history for a specific index."""
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


@router.get("/metals")
def get_all_metals(db: Session = Depends(get_db)):
    """Latest price for all tracked precious metals."""
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


@router.get("/metals/{metal}")
def get_metal(metal: str, db: Session = Depends(get_db)):
    """
    Latest price for a specific precious metal.
    Example: gold, silver, platinum, palladium
    """
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


@router.get("/metals/{metal}/history")
def get_metal_history(metal: str, db: Session = Depends(get_db)):
    """5-year daily history for a specific precious metal."""
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


@router.get("/last-updated")
def get_last_updated(db: Session = Depends(get_db)):
    """Returns the most recent date present in the database for each symbol."""
    rows = db.execute(
        text("SELECT symbol, MAX(date) AS last_date FROM daily_prices GROUP BY symbol ORDER BY symbol")
    ).fetchall()
    return [{"symbol": r.symbol, "last_date": str(r.last_date)} for r in rows]


@router.get("/assets")
def list_assets():
    """Returns the full list of tracked symbols and their metadata."""
    return {
        "fx_pairs":        FX_PAIRS,
        "indexes":         INDEXES,
        "precious_metals": PRECIOUS_METALS,
    }


@router.post("/admin/backfill", dependencies=[Depends(require_admin)])
def run_backfill():
    """Backfills 5 years of history for all tracked assets. Slow - run once."""
    results = backfill_all()
    return {"status": "done", "rows_inserted": results}


@router.post("/admin/ingest-daily", dependencies=[Depends(require_admin)])
def run_daily_ingest():
    """Manually triggers the daily ingestion job."""
    results = ingest_daily_all()
    return {"status": "done", "rows_inserted": results}