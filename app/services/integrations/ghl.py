"""GHL (GoHighLevel) integration — shadow-safe."""
from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def build_ghl_payload(student: dict, channel: str, attempt: int) -> dict:
    return {
        "locationId": settings.GHL_LOCATION_ID,
        "executionMode": settings.EXECUTION_MODE,
        "user": {
            "id": student.get("UserID"),
            "firstName": student.get("FirstName"),
            "lastName": student.get("LastName"),
            "email": student.get("Email"),
            "phone": student.get("PhoneNumber"),
        },
        "workflow": {
            "channel": channel,
            "attempt": attempt,
            "checkpoint": student.get("PathName"),
        },
        "risk": {
            "hwsBehind": student.get("HWsBehind"),
            "avgEffRating": student.get("AvgEffRating"),
            "lastActivityDays": student.get("LastActivityDays"),
        },
    }


async def trigger_ghl_workflow(payload: dict) -> dict:
    """
    SHADOW: log payload, return simulated success.
    LIVE: POST to GHL workflow trigger endpoint.
    """
    user_id = payload["user"]["id"]

    if settings.is_shadow:
        logger.info(
            "[SHADOW] GHL workflow | user_id=%s channel=%s attempt=%s",
            user_id,
            payload["workflow"]["channel"],
            payload["workflow"]["attempt"],
        )
        return {
            "status": "simulated",
            "execution_mode": "SHADOW",
            "ghl_workflow_id": None,
        }

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.post(
                f"{settings.GHL_BASE_URL}/v1/workflows/trigger",
                headers={
                    "Authorization": f"Bearer {settings.GHL_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            logger.error("GHL API error for user %s: %s", user_id, exc)
            raise
