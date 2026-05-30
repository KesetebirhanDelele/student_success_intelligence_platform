"""
Historical Retool outreach import — Gap 1.

Reads RETOOLCALLENGAGEMENT, RetoolEmailEngagement, RetoolNoteEngagement from
SQL Server (read-only CCPP) and inserts rows into PostgreSQL
student_campaign_activity with source='retool_import'.

Idempotent: each row is hashed to an import_key stored in source_import_keys;
rows already present are skipped via ON CONFLICT DO NOTHING.

Usage:
    python -m app.scripts.import_retool_outreach
    python -m app.scripts.import_retool_outreach --dry-run
    python -m app.scripts.import_retool_outreach --table RETOOLCALLENGAGEMENT
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Optional

import pyodbc

from app.config import settings
from app.database import AsyncSessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("import_retool_outreach")

# ── Source table definitions ──────────────────────────────────────────────────

# Each definition maps CCPP column names to student_campaign_activity fields.
# UserID / CandidateID is the FK to ai_chatbot_triggerdata.UserID.

_CALL_QUERY = """
SELECT
    UserID,
    CreateDate,
    CallType,
    CallOutcome,
    CallDuration,
    Notes,
    CreatedBy
FROM RETOOLCALLENGAGEMENT
"""

_EMAIL_QUERY = """
SELECT
    UserID,
    CreateDate,
    Subject,
    EmailBody,
    EmailOutcome,
    CreatedBy
FROM RetoolEmailEngagement
"""

_NOTE_QUERY = """
SELECT
    UserID,
    CreateDate,
    NoteText,
    NoteType,
    CreatedBy
FROM RetoolNoteEngagement
"""

_TABLE_SPECS: dict[str, dict[str, Any]] = {
    "RETOOLCALLENGAGEMENT": {
        "query": _CALL_QUERY,
        "channel": "CALL",
        "activity_type": "call",
        "label_col": "CallType",
        "subject_col": None,
        "body_col": "Notes",
    },
    "RetoolEmailEngagement": {
        "query": _EMAIL_QUERY,
        "channel": "EMAIL",
        "activity_type": "email",
        "label_col": "EmailOutcome",
        "subject_col": "Subject",
        "body_col": "EmailBody",
    },
    "RetoolNoteEngagement": {
        "query": _NOTE_QUERY,
        "channel": "NOTE",
        "activity_type": "note",
        "label_col": "NoteType",
        "subject_col": None,
        "body_col": "NoteText",
    },
}


# ── MSSQL fetch ───────────────────────────────────────────────────────────────

def _fetch_from_mssql(query: str) -> tuple[list[dict], Optional[str]]:
    if not settings.mssql_configured:
        return [], "SQL Server not configured"
    try:
        conn = pyodbc.connect(settings.mssql_dsn, timeout=30)
        cursor = conn.cursor()
        cursor.execute(query)
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        conn.close()
        return rows, None
    except Exception as exc:
        logger.error("MSSQL fetch failed: %s", exc)
        return [], str(exc)


# ── Row-level import key (dedup) ──────────────────────────────────────────────

def _import_key(table: str, row: dict) -> str:
    """SHA-256 of table + UserID + CreateDate to deduplicate on re-run."""
    raw = f"{table}|{row.get('UserID')}|{row.get('CreateDate')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:48]


# ── PostgreSQL upsert ─────────────────────────────────────────────────────────

_INSERT_SQL = """
INSERT INTO student_campaign_activity (
    student_user_id, activity_date, activity_type, activity_label,
    channel, subject, message_body, source, created_by,
    execution_mode, shadow_only, correlation_id,
    governance_scope, is_replay, attribution_complete
) VALUES (
    :uid, :activity_date, :activity_type, :label,
    :channel, :subject, :body, 'retool_import', :created_by,
    'SHADOW', true, :correlation_id,
    'SHADOW_ONLY', false, true
)
ON CONFLICT DO NOTHING
"""

# import_key stored in a lightweight dedup table
_DEDUP_DDL = """
CREATE TABLE IF NOT EXISTS retool_import_keys (
    import_key CHAR(48) PRIMARY KEY,
    imported_at TIMESTAMPTZ DEFAULT NOW()
)
"""

_DEDUP_CHECK = "SELECT 1 FROM retool_import_keys WHERE import_key = :k"
_DEDUP_INSERT = "INSERT INTO retool_import_keys (import_key) VALUES (:k) ON CONFLICT DO NOTHING"


# ── Core import logic ─────────────────────────────────────────────────────────

async def _import_table(
    table_name: str,
    spec: dict[str, Any],
    dry_run: bool,
    correlation_id: str,
) -> dict[str, int]:
    rows, err = await asyncio.to_thread(_fetch_from_mssql, spec["query"])
    if err:
        logger.error(json.dumps({
            "event": "mssql_fetch_failed", "table": table_name, "error": err
        }))
        return {"fetched": 0, "inserted": 0, "skipped": 0, "errors": 1}

    logger.info(json.dumps({
        "event": "mssql_fetch_ok", "table": table_name, "row_count": len(rows)
    }))

    inserted = skipped = errors = 0

    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        await db.execute(text(_DEDUP_DDL))
        await db.commit()

        for row in rows:
            ikey = _import_key(table_name, row)

            existing = (await db.execute(text(_DEDUP_CHECK), {"k": ikey})).fetchone()
            if existing:
                skipped += 1
                continue

            if dry_run:
                inserted += 1
                continue

            try:
                uid = row.get("UserID")
                if not uid:
                    skipped += 1
                    continue

                created_date = row.get("CreateDate")
                if isinstance(created_date, datetime):
                    activity_date = created_date.replace(tzinfo=timezone.utc) if created_date.tzinfo is None else created_date
                else:
                    activity_date = None

                await db.execute(text(_INSERT_SQL), {
                    "uid": int(uid),
                    "activity_date": activity_date,
                    "activity_type": spec["activity_type"],
                    "label": row.get(spec["label_col"]) if spec["label_col"] else None,
                    "channel": spec["channel"],
                    "subject": row.get(spec["subject_col"]) if spec["subject_col"] else None,
                    "body": row.get(spec["body_col"]) if spec["body_col"] else None,
                    "created_by": str(row.get("CreatedBy") or "retool"),
                    "correlation_id": correlation_id,
                })
                await db.execute(text(_DEDUP_INSERT), {"k": ikey})
                await db.commit()
                inserted += 1

            except Exception as exc:
                await db.rollback()
                logger.error(json.dumps({
                    "event": "row_insert_failed", "table": table_name,
                    "error_class": type(exc).__name__, "error": str(exc),
                    "user_id": str(row.get("UserID")),
                }))
                errors += 1

    return {"fetched": len(rows), "inserted": inserted, "skipped": skipped, "errors": errors}


async def run_import(tables: Optional[list[str]], dry_run: bool) -> None:
    import uuid
    correlation_id = str(uuid.uuid4())
    target_tables = tables or list(_TABLE_SPECS.keys())

    logger.info(json.dumps({
        "event": "import_started", "tables": target_tables,
        "dry_run": dry_run, "correlation_id": correlation_id,
    }))

    totals: dict[str, int] = {"fetched": 0, "inserted": 0, "skipped": 0, "errors": 0}

    for table_name in target_tables:
        spec = _TABLE_SPECS.get(table_name)
        if not spec:
            logger.error(json.dumps({"event": "unknown_table", "table": table_name}))
            continue
        result = await _import_table(table_name, spec, dry_run, correlation_id)
        for k in totals:
            totals[k] += result.get(k, 0)
        logger.info(json.dumps({
            "event": "table_import_complete", "table": table_name,
            "dry_run": dry_run, **result,
        }))

    logger.info(json.dumps({
        "event": "import_finished", "dry_run": dry_run,
        "correlation_id": correlation_id, **totals,
    }))


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Import historical Retool outreach into student_campaign_activity")
    parser.add_argument("--dry-run", action="store_true", help="Count rows without inserting")
    parser.add_argument("--table", choices=list(_TABLE_SPECS.keys()), help="Import a single table only")
    args = parser.parse_args()

    tables = [args.table] if args.table else None
    asyncio.run(run_import(tables=tables, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
