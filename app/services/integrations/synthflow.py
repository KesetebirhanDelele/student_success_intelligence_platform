"""Synthflow call integration — shadow-safe."""
from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def build_call_payload(student: dict, attempt: int) -> dict:
    return {
        "to": student.get("PhoneNumber"),
        "from": settings.SYNTHFLOW_PHONE_NUMBER,
        "executionMode": settings.EXECUTION_MODE,
        "metadata": {
            "user_id": student.get("UserID"),
            "attempt": attempt,
            "checkpoint": student.get("PathName"),
            "hws_behind": student.get("HWsBehind"),
            "avg_eff_rating": student.get("AvgEffRating"),
        },
    }


async def place_call(payload: dict) -> dict:
    """
    SHADOW: log payload, return simulated response.
    LIVE: POST to Synthflow API.
    """
    user_id = payload["metadata"]["user_id"]

    if settings.is_shadow:
        logger.info(
            "[SHADOW] Synthflow call | user_id=%s phone=%s attempt=%s",
            user_id,
            payload["to"],
            payload["metadata"]["attempt"],
        )
        return {
            "status": "simulated",
            "execution_mode": "SHADOW",
            "call_id": None,
        }

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.post(
                "https://api.synthflow.ai/v1/calls",
                headers={
                    "Authorization": f"Bearer {settings.SYNTHFLOW_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            logger.error("Synthflow API error for user %s: %s", user_id, exc)
            raise
