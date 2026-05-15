"""GHL message synchronization — read-only, always shadow-safe.

Lookup flow:
  1. Normalize student PhoneNumber → E.164
  2. GET /v1/contacts/?phone={phone}&locationId={loc}  →  contact_id
  3. GET /v1/conversations/search?contactId={id}       →  conversation_id
  4. GET /v1/conversations/{conv_id}/messages          →  message list
  5. Upsert new messages into ghl_messages (idempotent on ghl_message_id)

GHL reads are always permitted in SHADOW and LIVE modes (non-destructive).
Every outbound call is logged: start / end / duration_ms / status_code.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import func as sqlfunc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import GHLMessage, StudentTriggerData

logger = logging.getLogger(__name__)

_CHANNEL_TYPE_MAP = {
    "1": "SMS", "2": "EMAIL", "3": "CALL", "4": "WHATSAPP",
    "TYPE_SMS": "SMS", "TYPE_EMAIL": "EMAIL",
    "TYPE_CALL": "CALL", "TYPE_WHATSAPP": "WHATSAPP",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ghl_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.GHL_API_KEY}",
        "Version": "2021-04-15",
        "Content-Type": "application/json",
    }


def _normalize_phone(raw: str) -> str:
    """Strip non-digits and format as E.164 (+1XXXXXXXXXX for US numbers)."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        digits = "1" + digits
    return "+" + digits


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


async def _ghl_get(client: httpx.AsyncClient, url: str, params: dict, label: str, user_id: int) -> tuple[dict | None, str | None]:
    """Shared GET wrapper with timing + structured logging. Returns (data, error)."""
    t0 = time.monotonic()
    logger.info("[GHL_SYNC] %s START user_id=%s url=%s params=%s", label, user_id, url, params)
    try:
        r = await client.get(url, params=params)
        ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "[GHL_SYNC] %s END user_id=%s status=%s duration_ms=%d outcome=%s",
            label, user_id, r.status_code, ms,
            "success" if r.status_code < 400 else "failure",
        )
        r.raise_for_status()
        return r.json(), None
    except httpx.HTTPStatusError as exc:
        ms = int((time.monotonic() - t0) * 1000)
        logger.error(
            "[GHL_SYNC] %s HTTP error user_id=%s status=%s duration_ms=%d error_class=HTTPStatusError body=%s",
            label, user_id, exc.response.status_code, ms, exc.response.text[:300],
        )
        return None, f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
    except httpx.HTTPError as exc:
        ms = int((time.monotonic() - t0) * 1000)
        logger.error("[GHL_SYNC] %s network error user_id=%s duration_ms=%d msg=%s", label, user_id, ms, exc)
        return None, str(exc)


# ── Phone-based contact lookup ────────────────────────────────────────────────

async def _lookup_contact_by_phone(
    phone_e164: str,
    user_id: int,
) -> tuple[str | None, str | None]:
    """
    Look up GHL contact_id from E.164 phone number.
    Tries the primary contacts search endpoint; returns (contact_id, error).
    """
    async with httpx.AsyncClient(timeout=settings.GHL_TIMEOUT_SECONDS) as client:
        data, err = await _ghl_get(
            client,
            f"{settings.GHL_BASE_URL}/v1/contacts/",
            {"phone": phone_e164, "locationId": settings.GHL_LOCATION_ID},
            "contact_lookup",
            user_id,
        )

    if err:
        return None, err

    contacts = data.get("contacts", []) if data else []
    if not contacts:
        logger.info("[GHL_SYNC] No GHL contact found for phone=%s user_id=%s", phone_e164, user_id)
        return None, None

    contact_id = contacts[0].get("id")
    logger.info("[GHL_SYNC] Found contact_id=%s for phone=%s user_id=%s", contact_id, phone_e164, user_id)
    return contact_id, None


async def _get_conversation_id(
    contact_id: str,
    user_id: int,
) -> tuple[str | None, str | None]:
    """Find conversation_id for a GHL contact. Returns (conv_id, error)."""
    async with httpx.AsyncClient(timeout=settings.GHL_TIMEOUT_SECONDS) as client:
        data, err = await _ghl_get(
            client,
            f"{settings.GHL_BASE_URL}/v1/conversations/search",
            {"contactId": contact_id, "locationId": settings.GHL_LOCATION_ID},
            "conversation_search",
            user_id,
        )

    if err:
        return None, err

    conversations = (data or {}).get("conversations", [])
    if not conversations:
        return None, None

    return conversations[0].get("id"), None


async def _fetch_messages(
    conv_id: str,
    user_id: int,
) -> tuple[list[dict], str | None]:
    """Fetch all messages in a conversation. Returns (messages, error)."""
    async with httpx.AsyncClient(timeout=settings.GHL_TIMEOUT_SECONDS) as client:
        data, err = await _ghl_get(
            client,
            f"{settings.GHL_BASE_URL}/v1/conversations/{conv_id}/messages",
            {},
            "messages_fetch",
            user_id,
        )
    if err:
        return [], err
    return (data or {}).get("messages", []), None


# ── Persistence ───────────────────────────────────────────────────────────────

async def _upsert_messages(
    messages: list[dict],
    user_id: int,
    db: AsyncSession,
) -> int:
    """Insert new GHL messages; skip duplicates. Returns count inserted."""
    now_utc = datetime.now(tz=timezone.utc)
    synced = 0

    for msg in messages:
        ghl_id = msg.get("id") or msg.get("messageId")
        if not ghl_id:
            continue

        exists = await db.execute(
            select(GHLMessage.id).where(GHLMessage.ghl_message_id == str(ghl_id))
        )
        if exists.scalar_one_or_none():
            continue

        raw_dir = msg.get("direction", "")
        direction = "OUTBOUND" if str(raw_dir).lower() in ("outbound", "1") else "INBOUND"
        channel = _CHANNEL_TYPE_MAP.get(str(msg.get("type", "")), "UNKNOWN")
        ghl_ts = _parse_ts(msg.get("dateAdded") or msg.get("createdAt"))

        db.add(GHLMessage(
            ghl_message_id=str(ghl_id),
            user_id=user_id,
            direction=direction,
            channel=channel,
            body=(msg.get("body") or msg.get("message") or "")[:2000],
            status=str(msg.get("status") or "unknown"),
            ghl_created_at=ghl_ts,
            synced_at=now_utc,
        ))
        synced += 1

    if synced:
        await db.commit()

    return synced


# ── Public API ─────────────────────────────────────────────────────────────────

async def sync_by_phone(
    user_id: int,
    phone: str,
    db: AsyncSession,
) -> dict:
    """
    Full sync for one student using their phone number.
    Resolves phone → contact_id → conversation_id → messages → PostgreSQL.
    Idempotent: already-stored ghl_message_ids are skipped.
    """
    if not settings.GHL_API_KEY:
        logger.warning("[GHL_SYNC] Not configured — skipping user_id=%s", user_id)
        return {"status": "not_configured", "synced": 0, "total_ghl": 0, "phone": phone}

    if not phone or not phone.strip():
        return {"status": "no_phone", "synced": 0, "total_ghl": 0, "phone": None}

    phone_e164 = _normalize_phone(phone.strip())
    t_total = time.monotonic()
    logger.info("[GHL_SYNC] BEGIN phone_sync user_id=%s phone=%s", user_id, phone_e164)

    # Step 1: contact lookup
    contact_id, err = await _lookup_contact_by_phone(phone_e164, user_id)
    if err:
        return {"status": "error", "error": err, "step": "contact_lookup", "synced": 0, "total_ghl": 0}
    if not contact_id:
        return {"status": "not_found", "message": f"No GHL contact for phone {phone_e164}", "synced": 0, "total_ghl": 0}

    # Step 2: conversation lookup
    conv_id, err = await _get_conversation_id(contact_id, user_id)
    if err:
        return {"status": "error", "error": err, "step": "conversation_search", "synced": 0, "total_ghl": 0}
    if not conv_id:
        return {"status": "no_conversation", "contact_id": contact_id, "synced": 0, "total_ghl": 0}

    # Step 3: fetch messages
    messages, err = await _fetch_messages(conv_id, user_id)
    if err:
        return {"status": "error", "error": err, "step": "messages_fetch", "synced": 0, "total_ghl": 0}

    # Step 4: persist
    synced = await _upsert_messages(messages, user_id, db)
    total_ms = int((time.monotonic() - t_total) * 1000)

    logger.info(
        "[GHL_SYNC] COMPLETE user_id=%s phone=%s contact_id=%s synced=%d total_ghl=%d total_ms=%d",
        user_id, phone_e164, contact_id, synced, len(messages), total_ms,
    )
    return {
        "status": "success",
        "phone_e164": phone_e164,
        "contact_id": contact_id,
        "conversation_id": conv_id,
        "synced": synced,
        "total_ghl": len(messages),
        "already_stored": len(messages) - synced,
    }


async def sync_student_by_user_id(user_id: int, db: AsyncSession) -> dict:
    """
    Convenience wrapper: load student's phone from PostgreSQL then run sync.
    Used by the router so callers only need user_id.
    """
    student = await db.get(StudentTriggerData, user_id)
    if not student:
        return {"status": "error", "error": f"Student {user_id} not in local mirror. Run SQL Server sync first."}
    if not student.PhoneNumber:
        return {"status": "no_phone", "error": f"Student {user_id} has no PhoneNumber in the mirror."}
    return await sync_by_phone(user_id, student.PhoneNumber, db)


async def sync_all_students(db: AsyncSession, limit: int = 100) -> dict:
    """
    Batch sync: iterate all students with a phone number and sync their GHL messages.
    Runs sequentially to avoid GHL rate limits. Returns aggregate results.
    """
    if not settings.GHL_API_KEY:
        return {"status": "not_configured", "total_synced": 0, "students_processed": 0}

    result = await db.execute(
        select(StudentTriggerData)
        .where(StudentTriggerData.PhoneNumber.isnot(None))
        .limit(limit)
    )
    students = result.scalars().all()

    total_synced = 0
    results: list[dict] = []

    for s in students:
        r = await sync_by_phone(s.UserID, s.PhoneNumber, db)
        total_synced += r.get("synced", 0)
        results.append({"user_id": s.UserID, **r})

    logger.info("[GHL_SYNC] Batch complete: students=%d total_synced=%d", len(students), total_synced)
    return {
        "status": "success",
        "students_processed": len(students),
        "total_synced": total_synced,
        "results": results,
    }


async def get_sync_status(db: AsyncSession) -> dict:
    """Summary of GHL messages stored locally."""
    total_q = await db.execute(select(sqlfunc.count()).select_from(GHLMessage))
    total = total_q.scalar() or 0
    latest_q = await db.execute(
        select(GHLMessage.synced_at).order_by(GHLMessage.synced_at.desc()).limit(1)
    )
    latest = latest_q.scalar_one_or_none()
    return {
        "ghl_configured": bool(settings.GHL_API_KEY),
        "total_messages_stored": total,
        "latest_sync_at": latest.isoformat() if latest else None,
        "shadow_mode": settings.is_shadow,
        "note": "GHL reads always permitted (read-only). Writes gated by SHADOW mode.",
    }
