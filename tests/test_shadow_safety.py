"""Tests that SHADOW mode prevents all real outbound communication."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── GHL integration ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ghl_shadow_returns_simulated_no_http():
    with patch("app.services.integrations.ghl.settings") as ms:
        ms.is_shadow = True
        ms.GHL_API_KEY = "fake-key"
        ms.GHL_BASE_URL = "https://rest.gohighlevel.com"
        ms.GHL_LOCATION_ID = "fake-loc"
        ms.EXECUTION_MODE = "SHADOW"

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            from app.services.integrations.ghl import trigger_ghl_workflow, build_ghl_payload
            student = {"UserID": 1001, "FirstName": "Test", "LastName": "User",
                       "Email": "t@example.com", "PhoneNumber": "+15550001001",
                       "PathName": "SQL", "HWsBehind": 3, "AvgEffRating": 0.7, "LastActivityDays": 5}
            payload = build_ghl_payload(student, "CALL", 1)
            result = await trigger_ghl_workflow(payload)

            mock_post.assert_not_called()
            assert result.get("execution_mode") == "SHADOW"


# ── Synthflow integration ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_synthflow_shadow_returns_simulated_no_http():
    with patch("app.services.integrations.synthflow.settings") as ms:
        ms.is_shadow = True
        ms.SYNTHFLOW_API_KEY = "fake-key"
        ms.SYNTHFLOW_PHONE_NUMBER = "+15550000000"
        ms.EXECUTION_MODE = "SHADOW"

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            from app.services.integrations.synthflow import place_call, build_call_payload
            student = {"UserID": 1001, "PhoneNumber": "+15550001001",
                       "PathName": "SQL", "HWsBehind": 3, "AvgEffRating": 0.7}
            payload = build_call_payload(student, 1)
            result = await place_call(payload)

            mock_post.assert_not_called()
            assert result.get("execution_mode") == "SHADOW" or result.get("status") == "simulated"


# ── SMS integration ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sms_shadow_returns_simulated_no_http():
    with patch("app.services.integrations.sms.settings") as ms:
        ms.is_shadow = True
        ms.GHL_API_KEY = "fake-key"
        ms.GHL_BASE_URL = "https://rest.gohighlevel.com"
        ms.EXECUTION_MODE = "SHADOW"

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            from app.services.integrations.sms import send_sms, build_sms_payload
            student = {"UserID": 1001, "FirstName": "Test",
                       "PhoneNumber": "+15550001001", "PathName": "SQL", "HWsBehind": 3}
            payload = build_sms_payload(student, 1)
            result = await send_sms(payload)

            mock_post.assert_not_called()


# ── Email integration ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_email_shadow_returns_simulated_no_http():
    with patch("app.services.integrations.email.settings") as ms:
        ms.is_shadow = True
        ms.GHL_API_KEY = "fake-key"
        ms.GHL_BASE_URL = "https://rest.gohighlevel.com"
        ms.EXECUTION_MODE = "SHADOW"

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            from app.services.integrations.email import send_email, build_email_payload
            student = {"UserID": 1001, "FirstName": "Test",
                       "Email": "test@example.com", "PathName": "SQL", "HWsBehind": 3}
            payload = build_email_payload(student, 1)
            result = await send_email(payload)

            mock_post.assert_not_called()


# ── OutreachHistory model invariant ──────────────────────────────────────────

def test_outreach_history_shadow_fields():
    """OutreachHistory instantiation with SHADOW fields should have correct attributes."""
    from app.models import OutreachHistory

    entry = OutreachHistory(
        tracking_id=1,
        user_id=1001,
        checkpoint_type="SQL",
        attempt_number=1,
        channel="CALL",
        action="CALL_SIMULATED",
        execution_mode="SHADOW",
        simulated_status="NOT_SENT",
    )

    assert entry.execution_mode == "SHADOW"
    assert entry.simulated_status == "NOT_SENT"
    assert entry.action == "CALL_SIMULATED"


# ── State machine — no outreach after CLOSED ─────────────────────────────────

def test_no_transition_out_of_closed():
    from app.state_machine import can_transition, TRANSITIONS

    assert TRANSITIONS["CLOSED"] == set()
    for state in TRANSITIONS:
        if state != "CLOSED":
            assert not can_transition("CLOSED", state), (
                f"CLOSED → {state} should be forbidden"
            )
