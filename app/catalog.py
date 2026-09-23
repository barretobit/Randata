"""In-memory catalogue of tracked assets, sourced from the `assets` table.

The public catalogue is loaded from the database at startup and refreshed
whenever an admin adds an asset or recomputes the price cache, so new
instruments appear in the public endpoints without a redeploy. Mirrors the
price-cache pattern in cache.py; the static lists in assets.py are only a
bootstrap seed and a fallback when the table is unavailable.
"""

import threading
from datetime import datetime, timezone

from .assets import CRYPTO, ETFS, FX_PAIRS, INDEXES, PRECIOUS_METALS, STOCKS
from .asset_repo import get_all_assets
from .logging_config import get_logger

logger = get_logger("catalog")

_TYPE_TO_GROUP = {
    "fx":     "fx_pairs",
    "index":  "indexes",
    "metal":  "precious_metals",
    "stock":  "stocks",
    "etf":    "etfs",
    "crypto": "crypto",
}
_GROUPS = list(_TYPE_TO_GROUP.values())

_STATIC_GROUPS = [
    ("fx",     FX_PAIRS),
    ("index",  INDEXES),
    ("metal",  PRECIOUS_METALS),
    ("stock",  STOCKS),
    ("etf",    ETFS),
    ("crypto", CRYPTO),
]

_MAP_TYPES = ("fx", "index", "stock", "etf", "crypto", "metal")

_lock = threading.Lock()
_catalog: dict = {}
_symbol_map: dict = {}
_lower_maps: dict = {}
_loaded_at: datetime | None = None


def _merged(item) -> dict:
    asset = {"symbol": item["symbol"], "name": item["name"]}
    asset.update(item["properties"] or {})
    return asset


def _static_items():
    out = []
    for asset_type, items in _STATIC_GROUPS:
        for item in items:
            out.append({
                "symbol":     item["symbol"],
                "name":       item["name"],
                "asset_type": asset_type,
                "properties": {k: v for k, v in item.items() if k not in ("symbol", "name")},
            })
    return out


def _build_from(assets) -> None:
    grouped = {g: [] for g in _GROUPS}
    symbol_map = {}
    lower_maps = {t: {} for t in _MAP_TYPES}
    total = 0
    for item in assets:
        row = _merged(item)
        symbol_map[row["symbol"]] = row
        group = _TYPE_TO_GROUP.get(item.get("asset_type"))
        if group:
            grouped[group].append(row)
            total += 1
        atype = item.get("asset_type")
        if atype == "metal":
            lower_maps["metal"][row["name"].lower()] = row
        elif atype in lower_maps:
            lower_maps[atype][row["symbol"].lower()] = row
    with _lock:
        _catalog.clear()
        _catalog.update(grouped)
        _symbol_map.clear()
        _symbol_map.update(symbol_map)
        _lower_maps.clear()
        _lower_maps.update(lower_maps)
    return total


def _finish_load(assets) -> bool:
    global _loaded_at
    total = _build_from(assets)
    with _lock:
        _loaded_at = datetime.now(timezone.utc)
    logger.info("Catalogue loaded: %d assets grouped by class.", total)
    return True


def load() -> bool:
    try:
        assets = get_all_assets()
    except Exception as e:
        logger.error("Could not read assets table (%s); falling back to static catalogue.", e)
        return _finish_load(_static_items())
    if not assets:
        logger.warning("Assets table is empty; falling back to static catalogue.")
        return _finish_load(_static_items())
    return _finish_load(assets)


def invalidate() -> None:
    global _loaded_at
    with _lock:
        _catalog.clear()
        _symbol_map.clear()
        _lower_maps.clear()
        _loaded_at = None
    logger.info("Catalogue invalidated — awaiting rebuild.")


def refresh() -> bool:
    """Reload the catalogue from the assets table. Call after admin mutations."""
    return load()


def get_catalog() -> dict:
    with _lock:
        return {g: list(_catalog.get(g, [])) for g in _GROUPS}


def get_group(asset_type: str) -> list:
    group = _TYPE_TO_GROUP.get(asset_type)
    if group is None:
        return []
    with _lock:
        return list(_catalog.get(group, []))


def get_symbol_map() -> dict:
    with _lock:
        return dict(_symbol_map)


def get_map(kind: str) -> dict:
    with _lock:
        return dict(_lower_maps.get(kind, {}))