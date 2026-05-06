from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)

# ── PostgreSQL async engine ────────────────────────────────────────────────────

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")


# ── SQL Server sync connection (read-only) ─────────────────────────────────────

def _fetch_students_sync() -> tuple[list[dict], str | None]:
    if not settings.mssql_configured:
        logger.warning("SQL Server not configured — MSSQL_HOST/USER/DATABASE are empty")
        return [], "not_configured"
    try:
        import pyodbc
        conn = pyodbc.connect(settings.mssql_dsn, timeout=10)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT UserID, FirstName, LastName, Email, PhoneNumber, PathName, "
            "HWsBehind, AvgEffRating, LastActivityDays "
            "FROM AI_ChatBot_TriggerData"
        )
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        conn.close()
        return rows, None
    except Exception as exc:
        logger.error("SQL Server query failed: %s", exc)
        return [], str(exc)


async def fetch_students_from_mssql() -> tuple[list[dict], str | None]:
    return await asyncio.to_thread(_fetch_students_sync)
