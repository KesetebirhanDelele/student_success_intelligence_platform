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
    # Phase 4
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
    # Phase 5 — additional SQL Server source columns
    ('ClassName', 'VARCHAR(200)'),
    ('ClassSignupsID', 'VARCHAR(100)'),
    ('ActiveStatus', 'VARCHAR(50)'),
    ('StatusI', 'VARCHAR(100)'),
    ('StatusII', 'VARCHAR(100)'),
    ('StudentStartDate', 'TIMESTAMP'),
    ('ClassStartDate', 'TIMESTAMP'),
    ('LastActivitySection', 'VARCHAR(300)'),
    ('LastLoginDays', 'INTEGER'),
    ('LastSubmitted', 'VARCHAR(200)'),
]


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migration-lite: add new columns if absent (safe to run repeatedly)
        for col_name, col_type in _NEW_TRIGGER_COLS:
            await conn.execute(
                text(
                    f'ALTER TABLE ai_chatbot_triggerdata '
                    f'ADD COLUMN IF NOT EXISTS "{col_name}" {col_type}'
                )
            )
        # Expand student_notes with note_type and visibility
        await conn.execute(text(
            "ALTER TABLE student_notes ADD COLUMN IF NOT EXISTS note_type VARCHAR(50)"
        ))
        await conn.execute(text(
            "ALTER TABLE student_notes ADD COLUMN IF NOT EXISTS visibility VARCHAR(50)"
        ))
        # Warehouse-preparation indexes — safe to run on existing tables
        # (CREATE TABLE IF NOT EXISTS only fires for new installs; these guards
        #  cover existing deployments where the tables already exist.)
        for idx_ddl in [
            "CREATE INDEX IF NOT EXISTS ix_stl_created_at ON state_transition_log(created_at)",
            "CREATE INDEX IF NOT EXISTS ix_sot_updated_at ON student_outreach_tracking(updated_at)",
            "CREATE INDEX IF NOT EXISTS ix_oh_checkpoint  ON outreach_history(checkpoint_type)",
            "CREATE INDEX IF NOT EXISTS ix_sca_created_at ON student_campaign_activity(created_at)",
        ]:
            await conn.execute(text(idx_ddl))
    logger.info("Database tables, column migrations, and indexes applied")


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
