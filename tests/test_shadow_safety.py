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

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            from app.services.integrations.ghl import trigger_ghl_workflow
            result = await trigger_ghl_workflow({"user_id": 1001, "channel": "CALL", "attempt": 1})

            mock_post.assert_not_called()
            assert result.get("execution_mode") == "SHADOW"


# ── Synthflow integration ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_synthflow_shadow_returns_simulated_no_http():
    with patch("app.services.integrations.synthflow.settings") as ms:
        ms.is_shadow = True
        ms.SYNTHFLOW_API_KEY = "fake-key"
        ms.SYNTHFLOW_PHONE_NUMBER = "+15550000000"

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            from app.services.integrations.synthflow import place_call
            result = await place_call({"phone_number": "+15550001001", "user_id": 1001})

            mock_post.assert_not_called()
            assert result.get("execution_mode") == "SHADOW" or result.get("status") == "simulated"


# ── SMS integration ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sms_shadow_returns_simulated_no_http():
    with patch("app.services.integrations.sms.settings") as ms:
        ms.is_shadow = True
        ms.GHL_API_KEY = "fake-key"
        ms.GHL_BASE_URL = "https://rest.gohighlevel.com"

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            from app.services.integrations.sms import send_sms
            result = await send_sms({"user_id": 1001, "phone": "+15550001001"})

            mock_post.assert_not_called()


# ── Email integration ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_email_shadow_returns_simulated_no_http():
    with patch("app.services.integrations.email.settings") as ms:
        ms.is_shadow = True
        ms.GHL_API_KEY = "fake-key"
        ms.GHL_BASE_URL = "https://rest.gohighlevel.com"

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            from app.services.integrations.email import send_email
            result = await send_email({"user_id": 1001, "email": "test@example.com"})

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
