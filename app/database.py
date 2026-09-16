from collections.abc import Generator
import os
import shutil
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base

_engine = None
_SessionLocal = None

VERCEL_SEED_SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "vercel-seed.sqlite"
VERCEL_RUNTIME_DB = Path("/tmp/dcu-bank.db")


def resolve_database_url(database_url: str) -> str:
    """On Vercel, copy the build-time seed snapshot to /tmp so SQLite can write."""
    if os.environ.get("VERCEL") != "1" or not VERCEL_SEED_SNAPSHOT.exists():
        return database_url
    if not VERCEL_RUNTIME_DB.exists():
        shutil.copy2(VERCEL_SEED_SNAPSHOT, VERCEL_RUNTIME_DB)
    return f"sqlite:///{VERCEL_RUNTIME_DB.as_posix()}"


def init_engine(database_url: str) -> None:
    global _engine, _SessionLocal
    database_url = resolve_database_url(database_url)
    if _engine is not None:
        _engine.dispose()
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    _engine = create_engine(
        database_url,
        connect_args=connect_args,
        echo=False,
    )
    _SessionLocal = sessionmaker(
        bind=_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(_engine)


def get_engine():
    if _engine is None:
        raise RuntimeError("Database engine is not initialized")
    return _engine


def SessionLocal() -> Session:
    if _SessionLocal is None:
        raise RuntimeError("Database engine is not initialized")
    return _SessionLocal()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def drop_all() -> None:
    Base.metadata.drop_all(get_engine())
    Base.metadata.create_all(get_engine())
