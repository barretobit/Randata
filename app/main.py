import atexit

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

from .db import SessionLocal
from .ingestion import ingest_daily_all
from .routers.finance import router as finance_router

app = FastAPI(
    title="Randata Finance API",
    description="Daily financial data (FX pairs, indexes, and precious metals) sourced from Yahoo Finance and stored in MySQL.",
    version="1.0",
)

@app.get("/")
async def root():
    return {"message": "Randata Finance API"}


@app.get("/health")
async def health():
    return {"status": "ok"}

app.include_router(finance_router, prefix="/finance", tags=["Finance"])

if SessionLocal is not None:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(ingest_daily_all, "cron", day_of_week="mon-fri", hour=23, minute=0)
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())