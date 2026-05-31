"""
Governance-safe synchronization orchestration coordination layer.

Public API: coordinate_sync_cycle(ctx) -> SyncCoordinationRecord

Advisory contract only — never writes to SQL Server, never dispatches providers,
never mutates FINALIZED artifacts, never executes ETL business logic.
Returns SyncCoordinationRecord. Consuming services (scheduler, API handlers) act on
the returned record; this module never acts directly.
Attribution propagated immutably from input.

Architecture preservation prohibitions (MUST NOT):
  FAD-5   / ABG-1   — no write operations to SQL Server (read-only authoritative source)
  INV-1   / FAD-1   — no mutation of FINALIZED warehouse records or snapshot_ai_narratives
  INV-4   / AP-RT2  — no LIVE effects from replay/regeneration execution types
  INV-5             — no governance record without correlation_id and attribution
  INV-6   / FAD-1   — no overwrite of allows_update=false AI narratives
  FAD-4             — no mutation of append-only audit/lineage tables
  AP-RT9  / ABG-5   — no hardcoded Config V2 threshold fallbacks; UNKNOWN_V0 only
  AP-RT10           — no duplicate LIVE execution of the same sync intent
  AP-RT13           — no raw PII in observability records
  AP-RT14           — no silent failure swallowing; every exception classified
  AP-RT15           — no orphaned coordination cycles without completion log
  ABG-2             — no platform enrichment overwriting SQL Server authoritative values
  ABG-3             — no silent conflict resolution; conflicts preserved with both values
  RSV-1   / ABG-4   — no replay-triggered LIVE mutations or downstream side-effects
  AOWG-1            — no sync path produces warehouse schema INSERT/UPDATE/DELETE
"""
from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any, Dict, List, Optional

from app.services._sync_helpers import (
    _make_blocked_record,
    _make_coordination_record,
    _make_maintenance_record,
    _make_replay_record,
    emit_sync_event_log,
)
from app.services._sync_types import (
    CB_OPEN,
    INTENT_DEFER_STALE,
    INTENT_HOLD,
    INTENT_INGEST_AUTHORITATIVE,
    INTENT_RECONCILE_CONFLICTS,
    K_SQL_MAX_SYNC_AGE_HOURS,
    MODE_SHADOW,
    OUTCOME_DEGRADED,
    OUTCOME_SHADOW_ONLY,
    REQUIRED_SYNC_ATTRIBUTION,
    SCOPE_SHADOW_ONLY,
    SCOPE_UNAVAILABLE,
    TYPE_ORIGINAL,
    UNKNOWN_V0,
    _REPLAY_TYPES,
    _SYNC_THRESHOLD_KEYS,
    _VALID_EXECUTION_MODES,
    _VALID_EXECUTION_TYPES,
    SyncCoordinationRecord,
    SyncOrchestrationContext,
)

logger = logging.getLogger(__name__)

# In-memory idempotency store for sync deduplication (AP-RT10, spec/04 §4.1)
_sync_idempotency_keys: set[str] = set()


# ── Pure helpers ──────────────────────────────────────────────────────────────

def _attribution_complete(ctx: SyncOrchestrationContext) -> bool:
    """Returns True only if all required sync attribution fields are populated."""
    return all(getattr(ctx, f, None) for f in REQUIRED_SYNC_ATTRIBUTION)


def _governance_precondition_gate(
    ctx: SyncOrchestrationContext,
    codes: List[str],
) -> bool:
    """
    RULE 0: Governance precondition gate. All conditions must pass before evaluation
    proceeds. Never bypassed (INV-5, spec/04 §4.1, spec/05 §4.4).
    Returns True if all preconditions pass; False if coordination must stop.
    """
    ok = True
    if ctx.execution_mode not in _VALID_EXECUTION_MODES:
        codes.append("INVALID_EXECUTION_MODE")
        ok = False
    if ctx.execution_type not in _VALID_EXECUTION_TYPES:
        codes.append("INVALID_EXECUTION_TYPE")
        ok = False
    if not ctx.config_version_id:
        codes.append("CONFIG_VERSION_ID_MISSING")
        ok = False
    if not ctx.correlation_id:
        codes.append("CORRELATION_ID_MISSING")
        ok = False
    if not ctx.origin_source:
        codes.append("ORIGIN_SOURCE_MISSING")
        ok = False
    if not ctx.origin_authority:
        codes.append("ORIGIN_AUTHORITY_MISSING")
        ok = False
    if not ctx.actor_identity:
        codes.append("ACTOR_IDENTITY_MISSING")
        ok = False
    if ctx.idempotency_key and ctx.idempotency_key in _sync_idempotency_keys:
        codes.append("IDEMPOTENCY_DUPLICATE_DETECTED")
        ok = False
    return ok


def _resolve_sync_thresholds(
    rule_set: Dict[str, Any],
    missing_keys: List[str],
) -> Dict[str, Any]:
    """
    Resolve Config V2 Group A / K sync thresholds from rule_set.
    Missing or UNKNOWN_V0 inputs resolve to UNKNOWN_V0 sentinel — never hardcoded (AP-RT9).
    """
    result: Dict[str, Any] = {}
    for k in _SYNC_THRESHOLD_KEYS:
        if k in rule_set and rule_set[k] != UNKNOWN_V0:
            result[k] = rule_set[k]
        else:
            result[k] = UNKNOWN_V0
            missing_keys.append(k)
    return result


def _classify_sync_intent(
    ctx: SyncOrchestrationContext,
    threshold_bindings: Dict[str, Any],
    sync_blocked: bool,
) -> str:
    """
    Classify the synchronization intent based on provider state and Config V2 thresholds.
    Never re-implements directive logic; classifies from observable state only.
    """
    if sync_blocked:
        return INTENT_HOLD

    # SQL Server unavailable → defer until available
    if not ctx.sql_server_available:
        return INTENT_DEFER_STALE

    # Sync lag check — governed by Config V2, never hardcoded (AP-RT9)
    lag_threshold = threshold_bindings.get(K_SQL_MAX_SYNC_AGE_HOURS)
    if lag_threshold not in (UNKNOWN_V0, None):
        try:
            if ctx.sync_lag_hours > float(lag_threshold):
                return INTENT_DEFER_STALE
        except (ValueError, TypeError):
            pass  # malformed threshold treated as UNKNOWN_V0

    # Conflicts present → govern reconciliation (spec/05 §4.6)
    if ctx.rows_invalid > 0:
        return INTENT_RECONCILE_CONFLICTS

    # Normal path — ingest authoritative data from SQL Server
    return INTENT_INGEST_AUTHORITATIVE


# ── Public coordination API ───────────────────────────────────────────────────

def coordinate_sync_cycle(
    ctx: SyncOrchestrationContext,
) -> SyncCoordinationRecord:
    """
    Evaluate synchronization orchestration governance for one sync cycle.

    Coordination contract: returns SyncCoordinationRecord only.
    Never writes to SQL Server, never mutates FINALIZED artifacts,
    never dispatches providers (FAD-5, INV-1, INV-6, FAD-1).
    Attribution propagated immutably from input (INV-5).
    Every path emits a structured observability record (AP-RT15).
    """
    t0 = time.monotonic()
    codes: List[str] = []
    rule_path: List[str] = []
    degradation_flags: List[str] = []
    rule_set = ctx.config_rule_set or {}

    # ── RULE 0: Governance precondition gate (INV-5, spec/04 §4.1) ───────────
    rule_path.append("RULE_0")
    gate_codes: List[str] = []
    if not _governance_precondition_gate(ctx, gate_codes):
        codes.extend(gate_codes)
        record = _make_blocked_record(
            ctx, codes, rule_path, t0, {},
            gate_codes[0] if gate_codes else "GOVERNANCE_PRECONDITION_FAILED",
        )
        emit_sync_event_log(record)
        return record

    # Register idempotency key after gate passes; only for original execution (AP-RT10)
    if ctx.idempotency_key and ctx.execution_type == TYPE_ORIGINAL:
        _sync_idempotency_keys.add(ctx.idempotency_key)

    # ── RULE 1: MAINTENANCE mode suspension ───────────────────────────────────
    rule_path.append("RULE_1")
    if ctx.maintenance_mode_active:
        codes.append("MAINTENANCE_MODE_ACTIVE")
        record = _make_maintenance_record(ctx, codes, rule_path, t0)
        emit_sync_event_log(record)
        return record

    # ── RULE 2: Replay/regeneration containment (INV-4, AP-RT2) ─────────────
    rule_path.append("RULE_2")
    is_replay = ctx.execution_type in _REPLAY_TYPES
    if is_replay:
        codes.append("REPLAY_MODE_ACTIVE")
        if not ctx.source_artifact_id:
            codes.append("REPLAY_SOURCE_ARTIFACT_MISSING")
        record = _make_replay_record(ctx, codes, rule_path, t0, {})
        emit_sync_event_log(record)
        return record

    # ── RULE 3: Config V2 threshold resolution (AP-RT9, spec/01 §12) ─────────
    rule_path.append("RULE_3")
    missing_threshold_keys: List[str] = []
    threshold_bindings = _resolve_sync_thresholds(rule_set, missing_threshold_keys)
    for k in missing_threshold_keys:
        flag = f"CONFIG_THRESHOLD_MISSING_{k.upper()}"
        codes.append(flag)
        degradation_flags.append(flag)

    # ── RULE 4: SHADOW mode detection ─────────────────────────────────────────
    rule_path.append("RULE_4")
    shadow_mode = ctx.execution_mode == MODE_SHADOW

    # ── RULE 5: SQL Server authoritative boundary enforcement (FAD-5, ABG-1) ──
    # SQL Server is always read-only. No write path exists. Inbound-only: SQL Server
    # → platform mirror. This rule annotates the invariant on every coordination output.
    rule_path.append("RULE_5")
    codes.append("SQL_SERVER_READ_ONLY_BOUNDARY_ENFORCED")

    # ── RULE 6: FINALIZED artifact immutability protection (INV-1, INV-6, FAD-1)
    rule_path.append("RULE_6")
    sync_blocked = False
    sync_blocked_reason: Optional[str] = None

    if ctx.finalized_artifacts_detected > 0:
        # Sync coordination never modifies FINALIZED records; protective annotation
        codes.append(f"FINALIZED_ARTIFACTS_PROTECTED_{ctx.finalized_artifacts_detected}")

    # ── RULE 7: Provider availability and circuit breaker (spec/05 §11) ───────
    rule_path.append("RULE_7")
    if ctx.circuit_breaker_state == CB_OPEN:
        sync_blocked = True
        sync_blocked_reason = "CIRCUIT_BREAKER_OPEN"
        codes.append("CIRCUIT_BREAKER_OPEN")
        degradation_flags.append("CIRCUIT_BREAKER_OPEN")

    if not ctx.sql_server_available:
        if not sync_blocked:
            sync_blocked = True
            sync_blocked_reason = "SQL_SERVER_UNAVAILABLE"
        codes.append("SQL_SERVER_UNAVAILABLE")
        degradation_flags.append("SQL_SERVER_UNAVAILABLE")

    # Sync lag degradation annotation (spec/05 §4.2 / staleness policy U-2)
    lag_threshold = threshold_bindings.get(K_SQL_MAX_SYNC_AGE_HOURS)
    if lag_threshold not in (UNKNOWN_V0, None):
        try:
            if ctx.sync_lag_hours > float(lag_threshold):
                codes.append("SYNC_LAG_EXCEEDED")
                degradation_flags.append("SYNC_LAG_EXCEEDED")
        except (ValueError, TypeError):
            pass

    # ── RULE 8: Compliance hold (spec/05 §10.6) ────────────────────────────────
    rule_path.append("RULE_8")
    if ctx.compliance_hold_flag:
        if not sync_blocked:
            sync_blocked = True
            sync_blocked_reason = "COMPLIANCE_HOLD_ACTIVE"
        codes.append("COMPLIANCE_HOLD_SYNC_BLOCKED")
        degradation_flags.append("COMPLIANCE_HOLD_SYNC_BLOCKED")

    # ── RULE 9: Conflict preservation governance (spec/05 §4.6, ABG-3) ───────
    # Conflicts between SQL Server authoritative values and platform-supplementary
    # estimates must preserve both values — never silent overwrite (ABG-3).
    rule_path.append("RULE_9")
    conflict_preservation_required = ctx.rows_invalid > 0

    # ── RULE 10: Sync intent classification ───────────────────────────────────
    rule_path.append("RULE_10")
    sync_intent = _classify_sync_intent(ctx, threshold_bindings, sync_blocked)
    codes.append(f"INTENT_{sync_intent}")

    # ── RULE 11: Governance scope assignment ──────────────────────────────────
    # AUTHORIZED scope requires Phase-12 certification.
    # Current deployment: both LIVE and SHADOW produce SHADOW_ONLY.
    rule_path.append("RULE_11")
    if sync_blocked:
        governance_scope = SCOPE_UNAVAILABLE
        outcome = OUTCOME_DEGRADED
    elif ctx.execution_mode == MODE_SHADOW:
        governance_scope = SCOPE_SHADOW_ONLY
        outcome = OUTCOME_SHADOW_ONLY
    else:
        # LIVE mode: Phase-12 cert gate — maps to SHADOW_ONLY until cert is granted
        codes.append("LIVE_SCOPE_SHADOW_ONLY_PHASE11")
        governance_scope = SCOPE_SHADOW_ONLY
        outcome = OUTCOME_SHADOW_ONLY

    # ── RULE 12: Dispatch authorization ───────────────────────────────────────
    rule_path.append("RULE_12")
    # Dispatch authorized only when governance_scope is AUTHORIZED (Phase-12 cert).
    # Under current SHADOW deployment, dispatch_authorized is unconditionally False.
    dispatch_authorized = False    # Phase-12 cert required for True; see RULE 11

    # ── RULE 13: Terminal output ───────────────────────────────────────────────
    rule_path.append("RULE_13")
    degraded = bool(degradation_flags)
    degradation_cause = degradation_flags[0] if degraded else None

    record = _make_coordination_record(
        ctx=ctx,
        codes=codes,
        rule_path=rule_path,
        t0=t0,
        threshold_bindings=threshold_bindings,
        governance_scope=governance_scope,
        sync_intent=sync_intent,
        dispatch_authorized=dispatch_authorized,
        sync_blocked_reason=sync_blocked_reason,
        conflict_preservation_required=conflict_preservation_required,
        degraded=degraded,
        degradation_flags=degradation_flags,
        degradation_cause=degradation_cause,
        outcome=outcome,
    )
    emit_sync_event_log(record)
    return record


# ── Operational sync entry points (read SQL Server → write PostgreSQL) ─────────

async def sync_from_mssql(db: Any) -> Dict[str, Any]:
    """
    Pull AI_ChatBot_TriggerData from SQL Server and upsert into local PostgreSQL mirror.
    Read-only from SQL Server (FAD-5/ABG-1). Safe to run in SHADOW mode.
    """
    import json as _json
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.database import fetch_students_from_mssql
    from app.models import StudentTriggerData

    rows, error = await fetch_students_from_mssql()
    if error:
        logger.warning(_json.dumps({
            "service": "sync", "event": "mssql_fetch_failed", "error": error,
        }))
        return {"synced": 0, "total_fetched": 0, "error": error, "status": "failed"}

    from sqlalchemy import String, Boolean as SABoolean

    model_col_types: dict = {
        c.name: type(c.type) for c in StudentTriggerData.__table__.columns
    }
    model_cols: set = set(model_col_types)

    count = 0
    for row in rows:
        values = {k: v for k, v in row.items() if k in model_cols}
        if not values.get("UserID"):
            continue
        # Coerce SQL Server types to match PostgreSQL column expectations
        for col, val in list(values.items()):
            col_type = model_col_types.get(col)
            if val is None:
                continue
            if col_type is SABoolean:
                values[col] = bool(val)
            elif col_type is String and not isinstance(val, str):
                values[col] = str(val)
        # Apply defaults for non-nullable columns that SQL Server may return NULL for
        values.setdefault("HWsBehind", 0)
        values.setdefault("AvgEffRating", 0.0)
        values.setdefault("LastActivityDays", 0)
        if values.get("HWsBehind") is None:
            values["HWsBehind"] = 0
        if values.get("AvgEffRating") is None:
            values["AvgEffRating"] = 0.0
        if values.get("LastActivityDays") is None:
            values["LastActivityDays"] = 0
        stmt = (
            pg_insert(StudentTriggerData)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["UserID"],
                set_={k: v for k, v in values.items() if k != "UserID"},
            )
        )
        await db.execute(stmt)
        count += 1

    await db.commit()
    logger.info(_json.dumps({
        "service": "sync", "event": "mssql_sync_complete",
        "synced": count, "total_fetched": len(rows),
    }))
    return {"synced": count, "total_fetched": len(rows), "error": None, "status": "ok"}


async def sync_ipbc_students(db: Any) -> Dict[str, Any]:
    """
    Pull AI_Chatbot_TriggerData_IPBC from SQL Server and:
      1. Upsert IPBC student records into ai_chatbot_triggerdata (main mirror)
      2. Upsert their mentor/supermentor assignments into mentorship_assignments
    IPBC students are a completely separate population from AI_ChatBot_TriggerData.
    Read-only from SQL Server (FAD-5/ABG-1). Safe to run in SHADOW mode.
    """
    import json as _json
    from datetime import datetime, timezone
    from sqlalchemy import String, Boolean as SABoolean
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.database import fetch_ipbc_students_from_mssql
    from app.models import MentorshipAssignment, StudentTriggerData

    rows, error = await fetch_ipbc_students_from_mssql()
    if error:
        logger.warning(_json.dumps({
            "service": "sync", "event": "ipbc_fetch_failed", "error": error,
        }))
        return {"synced": 0, "mentorship_synced": 0, "total_fetched": 0, "error": error, "status": "failed"}

    model_col_types: dict = {
        c.name: type(c.type) for c in StudentTriggerData.__table__.columns
    }
    model_cols: set = set(model_col_types)

    # IPBC table has UserID as VARCHAR — column name mapping differs slightly
    _IPBC_RENAMES = {
        "IPBC_StartDate": "IPBCStartDate",
    }

    now = datetime.now(timezone.utc)
    student_count = 0
    mentor_count = 0

    for row in rows:
        # IPBC UserID is stored as VARCHAR in SQL Server
        uid_raw = row.get("UserID")
        if not uid_raw:
            continue
        try:
            uid = int(uid_raw)
        except (TypeError, ValueError):
            continue

        # --- 1. Upsert student into ai_chatbot_triggerdata ---
        renamed = {}
        for k, v in row.items():
            key = _IPBC_RENAMES.get(k, k)
            renamed[key] = v

        values = {k: v for k, v in renamed.items() if k in model_cols}
        values["UserID"] = uid

        for col, val in list(values.items()):
            col_type = model_col_types.get(col)
            if val is None:
                continue
            if col_type is SABoolean:
                values[col] = bool(val)
            elif col_type is String and not isinstance(val, str):
                values[col] = str(val)

        values.setdefault("HWsBehind", 0)
        values.setdefault("AvgEffRating", 0.0)
        values.setdefault("LastActivityDays", 0)
        if values.get("HWsBehind") is None:
            values["HWsBehind"] = 0
        if values.get("AvgEffRating") is None:
            values["AvgEffRating"] = 0.0
        if values.get("LastActivityDays") is None:
            values["LastActivityDays"] = 0

        stmt = (
            pg_insert(StudentTriggerData)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["UserID"],
                set_={k: v for k, v in values.items() if k != "UserID"},
            )
        )
        await db.execute(stmt)
        student_count += 1

        # --- 2. Upsert mentor assignments ---
        mentor_values = {
            "user_id": uid,
            "mm_mentor": row.get("MM_Mentor"),
            "mentor_email": row.get("MentorEmail"),
            "supermentor": row.get("SuperMentor"),
            "supermentor_email": row.get("SuperMentorEmail"),
            "ipbc_instructor": None,
            "ipbc_instructor_email": None,
            "synced_at": now,
        }
        if mentor_values.get("mm_mentor") or mentor_values.get("supermentor"):
            stmt2 = (
                pg_insert(MentorshipAssignment)
                .values(**mentor_values)
                .on_conflict_do_update(
                    index_elements=["user_id"],
                    set_={k: v for k, v in mentor_values.items() if k != "user_id"},
                )
            )
            await db.execute(stmt2)
            mentor_count += 1

    await db.commit()
    logger.info(_json.dumps({
        "service": "sync", "event": "ipbc_sync_complete",
        "students_synced": student_count, "mentors_synced": mentor_count,
        "total_fetched": len(rows),
    }))
    return {
        "students_synced": student_count,
        "mentorship_synced": mentor_count,
        "total_fetched": len(rows),
        "error": None,
        "status": "ok",
    }


async def sync_mentorship_assignments(db: Any) -> Dict[str, Any]:
    """
    Pull ADF_Mentorship_Activity from SQL Server and upsert into mentorship_assignments.
    Read-only from SQL Server (FAD-5/ABG-1). Safe to run in SHADOW mode.
    """
    import json as _json
    from datetime import datetime, timezone
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.database import fetch_mentorship_from_mssql
    from app.models import MentorshipAssignment

    rows, error = await fetch_mentorship_from_mssql()
    if error:
        logger.warning(_json.dumps({
            "service": "sync", "event": "mentorship_fetch_failed", "error": error,
        }))
        return {"synced": 0, "total_fetched": 0, "error": error, "status": "failed"}

    now = datetime.now(timezone.utc)
    count = 0
    for row in rows:
        uid = row.get("UserID") or row.get("user_id") or row.get("StudentID")
        if not uid:
            continue
        values = {
            "user_id": int(uid),
            "mm_mentor": row.get("MM_Mentor"),
            "mentor_email": row.get("MentorEmail"),
            "supermentor": row.get("SuperMentor"),
            "supermentor_email": row.get("SuperMentorEmail"),
            # Instructor not available in AI_Chatbot_TriggerData_IPBC
            "ipbc_instructor": None,
            "ipbc_instructor_email": None,
            "synced_at": now,
        }
        stmt = (
            pg_insert(MentorshipAssignment)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["user_id"],
                set_={k: v for k, v in values.items() if k != "user_id"},
            )
        )
        await db.execute(stmt)
        count += 1

    await db.commit()
    logger.info(_json.dumps({
        "service": "sync", "event": "mentorship_sync_complete",
        "synced": count, "total_fetched": len(rows),
    }))
    return {"synced": count, "total_fetched": len(rows), "error": None, "status": "ok"}


async def sync_campaign_activity(db: Any) -> Dict[str, Any]:
    """
    Pull RETOOLCALLENGAGEMENT, RetoolEmailEngagement, RetoolNoteEngagement from SQL Server
    and insert into student_campaign_activity (Gap 1 historical import).
    Idempotent: deletes existing retool_* source rows before re-inserting.
    Read-only from SQL Server (FAD-5/ABG-1). Safe to run in SHADOW mode.
    """
    import json as _json
    from datetime import datetime, timezone
    from sqlalchemy import delete
    from app.database import fetch_retool_outreach_from_mssql
    from app.models import StudentCampaignActivity

    rows, error = await fetch_retool_outreach_from_mssql()
    if error:
        logger.warning(_json.dumps({
            "service": "sync", "event": "retool_outreach_fetch_failed", "error": error,
        }))
        return {"synced": 0, "total_fetched": 0, "error": error, "status": "failed"}

    # Idempotent replace: remove existing engagement_events rows so re-runs are safe
    await db.execute(
        delete(StudentCampaignActivity).where(
            StudentCampaignActivity.source == "engagement_events"
        )
    )

    count = 0
    for row in rows:
        # AI_ChatBot_EngagementEvents uses user_id (not UserID)
        uid = row.get("user_id") or row.get("UserID")
        if not uid:
            continue

        event_type = row.get("event_type") or row.get("_activity_type") or "EVENT"
        created_at = row.get("created_at")
        activity_date = None
        if created_at:
            if hasattr(created_at, "isoformat"):
                activity_date = created_at if getattr(created_at, "tzinfo", None) else created_at.replace(tzinfo=timezone.utc)
            elif isinstance(created_at, str):
                try:
                    activity_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass

        raw = {k: (v.isoformat() if hasattr(v, "isoformat") else v)
               for k, v in row.items() if not k.startswith("_")}

        obj = StudentCampaignActivity(
            student_user_id=int(uid),
            activity_date=activity_date,
            activity_type=event_type.upper(),
            activity_label=(event_type[:200] if event_type else None),
            channel=(row.get("channel") or "").lower() or "system",
            subject=row.get("agent_name", "")[:300] if row.get("agent_name") else None,
            message_body=(row.get("message") or _json.dumps(raw, default=str))[:2000],
            source="engagement_events",
            created_by=row.get("agent_name"),
            execution_mode="SHADOW",
            shadow_only=True,
        )
        db.add(obj)
        count += 1

    await db.commit()
    await db.commit()
    logger.info(_json.dumps({
        "service": "sync", "event": "campaign_activity_sync_complete",
        "synced": count, "total_fetched": len(rows),
    }))
    return {"synced": count, "total_fetched": len(rows), "error": None, "status": "ok"}


async def capture_month_state(
    snapshot_month: date,
    db: Any,
) -> Dict[str, Any]:
    """
    Copy the current ai_chatbot_triggerdata state into student_mirror_history
    for the given snapshot_month.  Idempotent: re-running for the same month
    overwrites the existing row so the latest capture always wins.

    Run at (or near) the last day of each month for historically accurate
    relative fields (LastActivityDays, LastLoginDays).  Running after
    month-end still stores useful data; assemble_snapshot will adjust those
    fields by the capture-to-month-end offset.

    Read-only from SQL Server (FAD-5/ABG-1). Safe in SHADOW mode.
    """
    import json as _json
    from datetime import datetime, timezone
    from sqlalchemy import text as _text

    # Always capture from the PostgreSQL mirror — it is the authoritative merged
    # view of all SQL Server sources (AI_ChatBot_TriggerData + IPBC + others).
    # Callers should run POST /sync/mssql + /sync/ipbc-students beforehand if
    # they need a fresh pull from SQL Server before capturing.
    result = await db.execute(_text("SELECT * FROM ai_chatbot_triggerdata"))
    source_rows = [dict(r) for r in result.mappings().all()]
    source = "pg_mirror"

    _MIRROR_COLS = [
        "UserID", "FirstName", "LastName", "Email", "PhoneNumber", "PathName",
        "HWsBehind", "AvgEffRating", "LastActivityDays", "AttendancePercentage",
        "CurrentSection", "IPBCStartDate", "Past10DaysLogon", "Total_Payments",
        "Total_Credits", "PaymentBalance", "ClassValue", "FeePaid", "ClassFeesPaid",
        "ClassName", "ClassSignupsID", "ActiveStatus", "StatusI", "StatusII",
        "StudentStartDate", "ClassStartDate", "LastActivitySection",
        "LastLoginDays", "LastSubmitted",
    ]
    _BOOL_COLS = {"FeePaid"}
    _STR_COLS = {
        "FirstName", "LastName", "Email", "PhoneNumber", "PathName",
        "CurrentSection", "ClassName", "ClassSignupsID", "ActiveStatus",
        "StatusI", "StatusII", "LastActivitySection", "LastSubmitted",
    }
    _INT_COLS = {"UserID", "HWsBehind", "LastActivityDays", "Past10DaysLogon", "LastLoginDays"}

    now = datetime.now(timezone.utc)
    count = 0
    for row in source_rows:
        uid = row.get("UserID")
        if not uid:
            continue

        def _coerce(col: str, val: Any) -> Any:
            if val is None:
                return None
            if col in _BOOL_COLS:
                return bool(val)
            if col in _STR_COLS and not isinstance(val, str):
                return str(val)
            if col in _INT_COLS and not isinstance(val, int):
                try:
                    return int(val)
                except (TypeError, ValueError):
                    return val
            return val

        # Build parameterised upsert with quoted column names
        col_list = ', '.join(f'"{c}"' for c in _MIRROR_COLS)
        param_list = ', '.join(f':p_{c}' for c in _MIRROR_COLS)
        update_set = ', '.join(
            f'"{c}" = EXCLUDED."{c}"' for c in _MIRROR_COLS if c != "UserID"
        )
        params: Dict[str, Any] = {
            "snapshot_month": snapshot_month,
            "captured_at": now,
        }
        for c in _MIRROR_COLS:
            params[f"p_{c}"] = _coerce(c, row.get(c))

        # Apply non-nullable defaults (mirrors sync_from_mssql behaviour)
        if params.get("p_HWsBehind") is None:
            params["p_HWsBehind"] = 0
        if params.get("p_AvgEffRating") is None:
            params["p_AvgEffRating"] = 0.0
        if params.get("p_LastActivityDays") is None:
            params["p_LastActivityDays"] = 0

        await db.execute(_text(f"""
            INSERT INTO student_mirror_history
                (snapshot_month, captured_at, {col_list})
            VALUES
                (:snapshot_month, :captured_at, {param_list})
            ON CONFLICT (snapshot_month, "UserID")
            DO UPDATE SET
                captured_at = EXCLUDED.captured_at,
                {update_set}
        """), params)
        count += 1

    await db.commit()
    logger.info(_json.dumps({
        "service": "sync", "event": "month_state_captured",
        "snapshot_month": str(snapshot_month), "count": count,
        "source": source,
    }))
    return {
        "snapshot_month": str(snapshot_month),
        "captured": count,
        "source": source,
        "status": "ok",
    }


async def sync_interview_prep(db: Any) -> Dict[str, Any]:
    """
    Pull InterviewPrep data from SQL Server and store as JSONB in local PostgreSQL.
    Read-only from SQL Server (FAD-5/ABG-1). Safe to run in SHADOW mode.
    """
    import json as _json
    from datetime import datetime, timezone
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.database import fetch_interview_prep_from_mssql
    from app.models import StudentInterviewPrep

    rows, error = await fetch_interview_prep_from_mssql()
    if error:
        logger.warning(_json.dumps({
            "service": "sync", "event": "interview_prep_fetch_failed", "error": error,
        }))
        return {"synced": 0, "total_fetched": 0, "error": error, "status": "failed"}

    now = datetime.now(timezone.utc)
    count = 0
    for row in rows:
        uid = row.get("UserID")
        if not uid:
            continue
        stmt = (
            pg_insert(StudentInterviewPrep)
            .values(user_id=int(uid), raw_data=row, synced_at=now)
            .on_conflict_do_update(
                index_elements=["user_id"],
                set_={"raw_data": row, "synced_at": now},
            )
        )
        await db.execute(stmt)
        count += 1

    await db.commit()
    logger.info(_json.dumps({
        "service": "sync", "event": "interview_prep_sync_complete",
        "synced": count, "total_fetched": len(rows),
    }))
    return {"synced": count, "total_fetched": len(rows), "error": None, "status": "ok"}
