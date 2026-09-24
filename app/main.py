import atexit

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.utils import get_openapi

from .cache import load as load_cache
from .catalog import load as load_catalog, refresh as refresh_catalog
from .db import SessionLocal
from .ingestion import ingest_daily_all
from .logging_config import get_logger
from .routers.finance import router as finance_router
from .routers.homes import router as homes_router
from .routers.storage import router as storage_router

logger = get_logger("main")

app = FastAPI(
    title="Randata Finance API",
    description="Daily financial data (FX pairs, indexes, precious metals, stocks, ETFs, and crypto) sourced from Yahoo Finance and stored in MySQL.",
    version="1.2",
)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "X-Admin-Key": {
            "type": "apiKey",
            "in": "header",
            "name": "X-Admin-Key",
        }
    }
    for path_name, path in openapi_schema.get("paths", {}).items():
        if "/admin/" not in path_name:
            continue
        for operation in path.values():
            if not isinstance(operation, dict):
                continue
            operation["security"] = [{"X-Admin-Key": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=4096, compresslevel=5)

@app.get("/")
async def root():
    return {"message": "Randata Finance API"}


@app.get("/health")
async def health():
    return {"status": "ok", "version": app.version}

app.include_router(finance_router, prefix="/finance", tags=["Finance"])
app.include_router(storage_router, prefix="/storage", tags=["Storage"])
app.include_router(homes_router, prefix="/homes", tags=["Homes"])


@app.on_event("startup")
def startup() -> None:
    load_catalog()
    load_cache()


def _scheduled_ingest():
    ingest_daily_all()
    refresh_catalog()
    load_cache()
    logger.info("Cache refreshed after scheduled ingestion.")


if SessionLocal is not None:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        _scheduled_ingest, "cron", day_of_week="mon-fri", hour=23, minute=0
    )
    scheduler.start()
    logger.info("Daily ingestion scheduler started (Mon-Fri 23:00 UTC).")
    atexit.register(lambda: scheduler.shutdown(wait=False))
else:
    logger.warning("DATABASE_URL not set — scheduler disabled.")