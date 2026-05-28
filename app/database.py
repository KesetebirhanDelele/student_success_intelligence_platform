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


# ── Migration-lite column additions (safe to run repeatedly) ──────────────────
# Phase 4/5 trigger data columns
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

# Phase 48 — governance attribution columns per table
# Format: (table_name, column_name, column_type, default_expression_or_None)
_GOVERNANCE_COLS = [
    # student_outreach_tracking (mutable operational state — only correlation_id + mode)
    ("student_outreach_tracking", "correlation_id", "VARCHAR(36)", None),

    # outreach_history (append-only lineage — full attribution)
    ("outreach_history", "correlation_id", "VARCHAR(36)", None),
    ("outreach_history", "causation_id", "VARCHAR(36)", None),
    ("outreach_history", "config_version_id", "VARCHAR(100)", None),
    ("outreach_history", "execution_type", "VARCHAR(30)", "'original'"),
    ("outreach_history", "governance_scope", "VARCHAR(30)", "'SHADOW_ONLY'"),
    ("outreach_history", "orchestration_cycle_id", "VARCHAR(36)", None),
    ("outreach_history", "origin_source", "VARCHAR(100)", None),
    ("outreach_history", "origin_authority", "VARCHAR(100)", None),
    ("outreach_history", "is_replay", "BOOLEAN", "FALSE"),
    ("outreach_history", "attribution_complete", "BOOLEAN", "FALSE"),
    ("outreach_history", "idempotency_key", "VARCHAR(200)", None),
    ("outreach_history", "replay_context", "JSONB", None),

    # state_transition_log (append-only audit — full attribution)
    ("state_transition_log", "correlation_id", "VARCHAR(36)", None),
    ("state_transition_log", "causation_id", "VARCHAR(36)", None),
    ("state_transition_log", "config_version_id", "VARCHAR(100)", None),
    ("state_transition_log", "execution_mode", "VARCHAR(20)", "'SHADOW'"),
    ("state_transition_log", "execution_type", "VARCHAR(30)", "'original'"),
    ("state_transition_log", "governance_scope", "VARCHAR(30)", "'SHADOW_ONLY'"),
    ("state_transition_log", "origin_source", "VARCHAR(100)", None),
    ("state_transition_log", "origin_authority", "VARCHAR(100)", None),
    ("state_transition_log", "is_replay", "BOOLEAN", "FALSE"),
    ("state_transition_log", "attribution_complete", "BOOLEAN", "FALSE"),

    # processed_events (idempotency store — attribution for lineage tracing)
    ("processed_events", "correlation_id", "VARCHAR(36)", None),
    ("processed_events", "execution_mode", "VARCHAR(20)", "'SHADOW'"),
    ("processed_events", "execution_type", "VARCHAR(30)", "'original'"),
    ("processed_events", "governance_scope", "VARCHAR(30)", "'SHADOW_ONLY'"),

    # ai_insights (FINALIZED protection + full attribution)
    ("ai_insights", "is_finalized", "BOOLEAN", "FALSE"),
    ("ai_insights", "finalized_at", "TIMESTAMPTZ", None),
    ("ai_insights", "correlation_id", "VARCHAR(36)", None),
    ("ai_insights", "causation_id", "VARCHAR(36)", None),
    ("ai_insights", "config_version_id", "VARCHAR(100)", None),
    ("ai_insights", "execution_mode", "VARCHAR(20)", "'SHADOW'"),
    ("ai_insights", "execution_type", "VARCHAR(30)", "'original'"),
    ("ai_insights", "governance_scope", "VARCHAR(30)", "'SHADOW_ONLY'"),
    ("ai_insights", "origin_source", "VARCHAR(100)", None),
    ("ai_insights", "origin_authority", "VARCHAR(100)", None),
    ("ai_insights", "is_replay", "BOOLEAN", "FALSE"),

    # student_campaign_activity (append-only operational log — governance attribution)
    ("student_campaign_activity", "correlation_id", "VARCHAR(36)", None),
    ("student_campaign_activity", "causation_id", "VARCHAR(36)", None),
    ("student_campaign_activity", "config_version_id", "VARCHAR(100)", None),
    ("student_campaign_activity", "execution_type", "VARCHAR(30)", "'original'"),
    ("student_campaign_activity", "governance_scope", "VARCHAR(30)", "'SHADOW_ONLY'"),
    ("student_campaign_activity", "is_replay", "BOOLEAN", "FALSE"),
    ("student_campaign_activity", "attribution_complete", "BOOLEAN", "FALSE"),

    # student_quick_action_log (append-only operational log — governance attribution)
    ("student_quick_action_log", "correlation_id", "VARCHAR(36)", None),
    ("student_quick_action_log", "causation_id", "VARCHAR(36)", None),
    ("student_quick_action_log", "config_version_id", "VARCHAR(100)", None),
    ("student_quick_action_log", "execution_type", "VARCHAR(30)", "'original'"),
    ("student_quick_action_log", "governance_scope", "VARCHAR(30)", "'SHADOW_ONLY'"),
    ("student_quick_action_log", "is_replay", "BOOLEAN", "FALSE"),
    ("student_quick_action_log", "attribution_complete", "BOOLEAN", "FALSE"),
]


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Phase 4/5 trigger data columns (safe repeated)
        for col_name, col_type in _NEW_TRIGGER_COLS:
            await conn.execute(
                text(
                    f'ALTER TABLE ai_chatbot_triggerdata '
                    f'ADD COLUMN IF NOT EXISTS "{col_name}" {col_type}'
                )
            )

        # student_notes legacy columns
        await conn.execute(text(
            "ALTER TABLE student_notes ADD COLUMN IF NOT EXISTS note_type VARCHAR(50)"
        ))
        await conn.execute(text(
            "ALTER TABLE student_notes ADD COLUMN IF NOT EXISTS visibility VARCHAR(50)"
        ))

        # Phase 48 — governance attribution columns (safe repeated; ADD IF NOT EXISTS)
        for table, col, col_type, default in _GOVERNANCE_COLS:
            if default is not None:
                ddl = (
                    f'ALTER TABLE {table} '
                    f'ADD COLUMN IF NOT EXISTS {col} {col_type} NOT NULL DEFAULT {default}'
                )
            else:
                ddl = f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_type}'
            await conn.execute(text(ddl))

        # Warehouse-preparation indexes (safe repeated)
        for idx_ddl in [
            "CREATE INDEX IF NOT EXISTS ix_stl_created_at ON state_transition_log(created_at)",
            "CREATE INDEX IF NOT EXISTS ix_sot_updated_at ON student_outreach_tracking(updated_at)",
            "CREATE INDEX IF NOT EXISTS ix_oh_checkpoint  ON outreach_history(checkpoint_type)",
            "CREATE INDEX IF NOT EXISTS ix_sca_created_at ON student_campaign_activity(created_at)",
            # Phase 48 — governance queryability indexes
            "CREATE INDEX IF NOT EXISTS ix_oh_is_replay ON outreach_history(is_replay)",
            "CREATE INDEX IF NOT EXISTS ix_oh_correlation_id ON outreach_history(correlation_id)",
            "CREATE INDEX IF NOT EXISTS ix_stl_is_replay ON state_transition_log(is_replay)",
            "CREATE INDEX IF NOT EXISTS ix_stl_correlation_id ON state_transition_log(correlation_id)",
            "CREATE INDEX IF NOT EXISTS ix_ai_is_finalized ON ai_insights(is_finalized)",
            "CREATE INDEX IF NOT EXISTS ix_ai_is_replay ON ai_insights(is_replay)",
            "CREATE INDEX IF NOT EXISTS ix_ai_correlation_id ON ai_insights(correlation_id)",
            "CREATE INDEX IF NOT EXISTS ix_sca_is_replay ON student_campaign_activity(is_replay)",
            "CREATE INDEX IF NOT EXISTS ix_sqal_is_replay ON student_quick_action_log(is_replay)",
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
