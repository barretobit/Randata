"""In-memory catalogue of tracked assets, sourced from the `assets` table.

Loaded at startup and reloaded (`load()`) whenever an admin adds an asset or
reloads the price cache, so new instruments appear in the public endpoints
without a redeploy. Mirrors the price-cache pattern in cache.py.
"""

import threading

from .asset_repository import get_all_assets
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

_lock = threading.Lock()
_catalog: dict[str, list[dict]] = {}
_by_symbol: dict[str, dict] = {}
# Case-insensitive lookups per asset type: metals by name ("gold"), the rest by symbol ("nvda").
_lookups: dict[str, dict[str, dict]] = {}


def _flatten(asset: dict) -> dict:
    """Public catalogue entry: symbol and name plus the asset's properties (display, region, unit)."""
    entry = {"symbol": asset["symbol"], "name": asset["name"]}
    entry.update(asset["properties"] or {})
    return entry


def _build_from(assets: list[dict]) -> int:
    grouped = {group: [] for group in _GROUPS}
    by_symbol = {}
    lookups = {asset_type: {} for asset_type in _TYPE_TO_GROUP}
    total = 0
    for asset in assets:
        entry = _flatten(asset)
        by_symbol[entry["symbol"]] = entry
        asset_type = asset.get("asset_type")
        group = _TYPE_TO_GROUP.get(asset_type)
        if group is None:
            continue
        grouped[group].append(entry)
        total += 1
        lookup_key = entry["name"] if asset_type == "metal" else entry["symbol"]
        lookups[asset_type][lookup_key.lower()] = entry
    with _lock:
        _catalog.clear()
        _catalog.update(grouped)
        _by_symbol.clear()
        _by_symbol.update(by_symbol)
        _lookups.clear()
        _lookups.update(lookups)
    return total


def load() -> bool:
    """Reload the catalogue from the assets table. Returns False if the table cannot be read."""
    try:
        assets = get_all_assets()
    except Exception as error:
        logger.error("Could not read the assets table: %s", error)
        return False
    total = _build_from(assets)
    if total == 0:
        logger.warning("Catalogue loaded with 0 assets — add symbols via the admin API.")
    else:
        logger.info("Catalogue loaded: %d assets grouped by class.", total)
    return True


def get_catalog() -> dict[str, list[dict]]:
    """Every tracked asset, grouped by class (fx_pairs, indexes, ...)."""
    with _lock:
        return {group: list(_catalog.get(group, [])) for group in _GROUPS}


def get_group(asset_type: str) -> list[dict]:
    """Tracked assets of one type, in insertion order."""
    group = _TYPE_TO_GROUP.get(asset_type)
    if group is None:
        return []
    with _lock:
        return list(_catalog.get(group, []))


def get_symbol(symbol: str) -> dict | None:
    """Catalogue entry for an exact symbol (any type), or None."""
    with _lock:
        return _by_symbol.get(symbol)


def get_lookup(asset_type: str) -> dict[str, dict]:
    """Case-insensitive lookup for one type: lowercase name (metals) or symbol -> entry."""
    with _lock:
        return dict(_lookups.get(asset_type, {}))
