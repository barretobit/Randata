"""In-memory catalogue of tracked assets, sourced from the `assets` table.

The public catalogue is loaded from the database at startup and refreshed
(`load()`) whenever an admin adds an asset or reloads the price cache, so new
instruments appear in the public endpoints without a redeploy. Mirrors the
price-cache pattern in cache.py.
"""

import threading
from datetime import datetime, timezone

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


def _build_from(assets) -> int:
    grouped = {group: [] for group in _GROUPS}
    symbol_map = {}
    lower_maps = {asset_type: {} for asset_type in _MAP_TYPES}
    total = 0
    for item in assets:
        row = _merged(item)
        symbol_map[row["symbol"]] = row
        asset_type = item.get("asset_type")
        group = _TYPE_TO_GROUP.get(asset_type)
        if group:
            grouped[group].append(row)
            total += 1
        if asset_type == "metal":
            lower_maps["metal"][row["name"].lower()] = row
        elif asset_type in lower_maps:
            lower_maps[asset_type][row["symbol"].lower()] = row
    with _lock:
        _catalog.clear()
        _catalog.update(grouped)
        _symbol_map.clear()
        _symbol_map.update(symbol_map)
        _lower_maps.clear()
        _lower_maps.update(lower_maps)
    return total


def load() -> bool:
    global _loaded_at
    try:
        assets = get_all_assets()
    except Exception as error:
        logger.error("Could not read the assets table: %s", error)
        return False
    total = _build_from(assets)
    with _lock:
        _loaded_at = datetime.now(timezone.utc)
    if total == 0:
        logger.warning("Catalogue loaded with 0 assets — add symbols via the admin API.")
    else:
        logger.info("Catalogue loaded: %d assets grouped by class.", total)
    return True


def get_catalog() -> dict:
    with _lock:
        return {group: list(_catalog.get(group, [])) for group in _GROUPS}


def get_group(asset_type: str) -> list:
    group = _TYPE_TO_GROUP.get(asset_type)
    if group is None:
        return []
    with _lock:
        return list(_catalog.get(group, []))


def get_symbol(symbol: str):
    with _lock:
        return _symbol_map.get(symbol)


def get_map(kind: str) -> dict:
    with _lock:
        return dict(_lower_maps.get(kind, {}))