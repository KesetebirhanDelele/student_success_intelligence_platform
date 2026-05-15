from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

from sqlalchemy import text
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


_NEW_TRIGGER_COLS = [
    ('AttendancePercentage', 'DOUBLE PRECISION'),
    ('CurrentSection', 'VARCHAR(200)'),
    ('IPBCStartDate', 'TIMESTAMP'),
    ('Past10DaysLogon', 'INTEGER'),
    ('Total_Payments', 'DOUBLE PRECISION'),
    ('Total_Credits', 'DOUBLE PRECISION'),
    ('PaymentBalance', 'DOUBLE PRECISION'),
    ('ClassValue', 'DOUBLE PRECISION'),
    ('FeePaid', 'BOOLEAN'),
    ('ClassFeesPaid', 'DOUBLE PRECISION'),
]


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migration-lite: add new columns to existing table if absent
        for col_name, col_type in _NEW_TRIGGER_COLS:
            await conn.execute(
                text(
                    f'ALTER TABLE ai_chatbot_triggerdata '
                    f'ADD COLUMN IF NOT EXISTS "{col_name}" {col_type}'
                )
            )
    logger.info("Database tables and column migrations applied")


# ── SQL Server sync connections (read-only) ────────────────────────────────────

def _fetch_students_sync() -> tuple[list[dict], str | None]:
    if not settings.mssql_configured:
        logger.warning("SQL Server not configured — MSSQL_HOST/USER/DATABASE are empty")
        return [], "not_configured"
    try:
        import pyodbc
        conn = pyodbc.connect(settings.mssql_dsn, timeout=10)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM AI_ChatBot_TriggerData")
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        conn.close()
        return rows, None
    except Exception as exc:
        logger.error("SQL Server query failed: %s", exc)
        return [], str(exc)


def _fetch_interview_prep_sync() -> tuple[list[dict], str | None]:
    """Fetch all columns from InterviewPrep table; schema unknown so SELECT *."""
    if not settings.mssql_configured:
        return [], "not_configured"
    try:
        import pyodbc
        conn = pyodbc.connect(settings.mssql_dsn, timeout=10)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM AI_ChatBot_TriggerData_InterviewPrep")
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        conn.close()
        return rows, None
    except Exception as exc:
        logger.error("SQL Server InterviewPrep query failed: %s", exc)
        return [], str(exc)


async def fetch_students_from_mssql() -> tuple[list[dict], str | None]:
    return await asyncio.to_thread(_fetch_students_sync)


async def fetch_interview_prep_from_mssql() -> tuple[list[dict], str | None]:
    return await asyncio.to_thread(_fetch_interview_prep_sync)
