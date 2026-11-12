from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from . import cache, catalog
from .db import SessionLocal
from .ingestion import IngestionAlreadyRunning, ingest_daily_all
from .logging_config import get_logger
from .routers.finance import router as finance_router
from .routers.homes import router as homes_router
from .routers.storage import router as storage_router

logger = get_logger("main")


def _scheduled_ingest():
    try:
        ingest_daily_all()
    except IngestionAlreadyRunning:
        logger.warning("Scheduled ingestion skipped: another ingestion job is still running.")
        return
    catalog.load()
    cache.load()
    logger.info("Cache refreshed after scheduled ingestion.")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    catalog.load()
    cache.load()
    scheduler = None
    if SessionLocal is not None:
        scheduler = BackgroundScheduler(timezone="UTC")
        scheduler.add_job(_scheduled_ingest, "cron", hour=23, minute=0)
        scheduler.start()
        logger.info("Daily ingestion scheduler started (daily at 23:00 UTC).")
    else:
        logger.warning("DATABASE_URL not set — scheduler disabled.")
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="Randata Finance API",
    description="Daily financial data (FX pairs, indexes, precious metals, stocks, ETFs, and crypto) sourced from Yahoo Finance and stored in MySQL.",
    version="1.2",
    lifespan=lifespan,
)

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
