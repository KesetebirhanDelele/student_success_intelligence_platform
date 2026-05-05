import logging
from typing import Any, Dict, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GHL_TRIGGER_ENDPOINT = "/contacts/"


def _build_payload(
    user_id: int,
    first_name: str,
    last_name: str,
    email: Optional[str],
    phone_number: Optional[str],
    checkpoint_type: str,
    hws_behind: int,
    avg_eff_rating: float,
    last_activity_days: int,
    contact_attempt: int,
    priority: str = "MEDIUM",
    reason_codes: Optional[list] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "user_id": user_id,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone_number": phone_number,
        "checkpoint_type": checkpoint_type,
        "hws_behind": hws_behind,
        "avg_eff_rating": avg_eff_rating,
        "last_activity_days": last_activity_days,
        "contact_attempt": contact_attempt,
        "priority": priority,
    }
    if reason_codes:
        payload["reason_codes"] = reason_codes
    return payload


def trigger_outreach(
    *,
    user_id: int,
    first_name: str,
    last_name: str,
    email: Optional[str],
    phone_number: Optional[str],
    checkpoint_type: str,
    hws_behind: int,
    avg_eff_rating: float,
    last_activity_days: int,
    contact_attempt: int,
    priority: str = "MEDIUM",
    reason_codes: Optional[list] = None,
) -> bool:
    """
    Send outreach trigger to GHL. Returns True on success.
    In mock mode, logs the payload and returns True without an HTTP call.
    """
    payload = _build_payload(
        user_id=user_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone_number=phone_number,
        checkpoint_type=checkpoint_type,
        hws_behind=hws_behind,
        avg_eff_rating=avg_eff_rating,
        last_activity_days=last_activity_days,
        contact_attempt=contact_attempt,
        priority=priority,
        reason_codes=reason_codes,
    )

    if settings.GHL_MOCK_MODE:
        logger.info(
            "[GHL MOCK] Trigger for student %d | checkpoint=%s | attempt=%d | payload=%s",
            user_id, checkpoint_type, contact_attempt, payload,
        )
        return True

    url = f"{settings.GHL_API_URL.rstrip('/')}{GHL_TRIGGER_ENDPOINT}"
    headers = {
        "Authorization": f"Bearer {settings.GHL_API_KEY}",
        "Content-Type": "application/json",
        "Version": "2021-07-28",
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        logger.info("GHL trigger success for student %d: %s", user_id, response.status_code)
        return True
    except httpx.HTTPStatusError as exc:
        logger.error(
            "GHL HTTP error for student %d: %s — %s",
            user_id, exc.response.status_code, exc.response.text,
        )
    except httpx.RequestError as exc:
        logger.error("GHL request error for student %d: %s", user_id, exc)

    # Retry once immediately per GHL integration contract
    logger.warning("GHL: retrying once for student %d", user_id)
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        logger.info("GHL retry success for student %d", user_id)
        return True
    except Exception as exc:
        logger.error("GHL retry failed for student %d: %s", user_id, exc)
        return False
