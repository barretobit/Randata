from contextlib import contextmanager

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import DATABASE_URL

engine = None
SessionLocal = None

if DATABASE_URL:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """FastAPI dependency: one database session per request."""
    if SessionLocal is None:
        raise HTTPException(status_code=500, detail="DATABASE_URL is not configured.")
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope(session=None):
    """Use the caller's session when one is given, otherwise open and close a new one."""
    if session is not None:
        yield session
        return
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured.")
    new_session = SessionLocal()
    try:
        yield new_session
    finally:
        new_session.close()
