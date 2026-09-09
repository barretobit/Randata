import atexit

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .asset_repo import seed_assets
from .cache import load as load_cache
from .db import SessionLocal
from .ingestion import ingest_daily_all
from .logging_config import get_logger
from .routers.finance import router as finance_router

logger = get_logger("main")

app = FastAPI(
    title="Randata Finance API",
    description="Daily financial data (FX pairs, indexes, precious metals, stocks, ETFs, and crypto) sourced from Yahoo Finance and stored in MySQL.",
    version="1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Randata Finance API"}


@app.get("/health")
async def health():
    return {"status": "ok"}

app.include_router(finance_router, prefix="/finance", tags=["Finance"])


@app.on_event("startup")
def startup() -> None:
    if SessionLocal is not None:
        try:
            seed_assets()
        except Exception as e:
            logger.error("Could not seed the assets table: %s", e)
    load_cache()


def _scheduled_ingest():
    ingest_daily_all()
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