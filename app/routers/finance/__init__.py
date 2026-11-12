"""Finance API, mounted at /finance.

- market_endpoints:  latest bar and history per asset class (fx, indexes, metals, stocks, etfs, crypto)
- history_endpoints: bulk history, any stored symbol, catalogue and freshness
- cache_endpoints:   data served straight from the in-memory cache
- admin_endpoints:   catalogue management, backfills, ingestion, cache and logs (X-Admin-Key)
"""

from fastapi import APIRouter

from . import admin_endpoints, cache_endpoints, history_endpoints, market_endpoints

router = APIRouter()
router.include_router(market_endpoints.router)
router.include_router(history_endpoints.router)
router.include_router(cache_endpoints.router)
router.include_router(admin_endpoints.router)
