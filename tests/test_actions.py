"""Tests for manual action validation guards."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.outreach import execute_manual_action


def _make_tracking(state: str, attempt: int = 0, checkpoint: str = "SQL"):
    t = MagicMock()
    t.state = state
    t.current_attempt = attempt
    t.checkpoint_type = checkpoint
    t.id = 1
    return t


def _make_db(tracking):
    result = MagicMock()
    result.scalar_one_or_none.return_value = tracking
    db = AsyncMock()
    db.execute.return_value = result
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


# ── FORCE_RETRY guards ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_force_retry_blocked_at_max_attempts():
    tracking = _make_tracking("NO_RESPONSE", attempt=3)
    db = _make_db(tracking)

    with patch("app.services.outreach.settings") as ms:
        ms.MAX_ATTEMPTS = 3
        ms.EXECUTION_MODE = "SHADOW"
        ms.is_shadow = True
        result = await execute_manual_action(db, 1001, "FORCE_RETRY", None)

    assert result["status"] == "max_attempts_reached"
    assert result["max"] == 3
    assert result["current_attempt"] == 3


@pytest.mark.asyncio
async def test_force_retry_allowed_below_max():
    tracking = _make_tracking("NO_RESPONSE", attempt=1)
    db = _make_db(tracking)

    with patch("app.services.outreach.settings") as ms:
        ms.MAX_ATTEMPTS = 3
        ms.EXECUTION_MODE = "SHADOW"
        ms.is_shadow = True
        result = await execute_manual_action(db, 1001, "FORCE_RETRY", None)

    assert result["status"] == "ok"
    assert result["to_state"] == "RETRY"


# ── ESCALATE action ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_escalate_from_contacted_transitions_to_intervention():
    tracking = _make_tracking("CONTACTED", attempt=1)
    db = _make_db(tracking)

    with patch("app.services.outreach.settings") as ms:
        ms.MAX_ATTEMPTS = 3
        ms.EXECUTION_MODE = "SHADOW"
        ms.is_shadow = True
        result = await execute_manual_action(db, 1001, "ESCALATE", "High risk student")

    assert result["status"] == "ok"
    assert result["from_state"] == "CONTACTED"
    assert result["to_state"] == "INTERVENTION_REQUIRED"


@pytest.mark.asyncio
async def test_escalate_from_no_response_transitions_to_intervention():
    tracking = _make_tracking("NO_RESPONSE", attempt=2)
    db = _make_db(tracking)

    with patch("app.services.outreach.settings") as ms:
        ms.MAX_ATTEMPTS = 3
        ms.EXECUTION_MODE = "SHADOW"
        ms.is_shadow = True
        result = await execute_manual_action(db, 1002, "ESCALATE", None)

    assert result["status"] == "ok"
    assert result["to_state"] == "INTERVENTION_REQUIRED"


# ── CLOSED state guard ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_any_action_on_closed_is_invalid_transition():
    tracking = _make_tracking("CLOSED", attempt=3)
    db = _make_db(tracking)

    with patch("app.services.outreach.settings") as ms:
        ms.MAX_ATTEMPTS = 3
        ms.EXECUTION_MODE = "SHADOW"
        ms.is_shadow = True
        result = await execute_manual_action(db, 1001, "FORCE_RETRY", None)

    # Blocked either by max-attempts guard or by state machine (CLOSED has no transitions)
    assert result["status"] in ("max_attempts_reached", "invalid_transition")


@pytest.mark.asyncio
async def test_close_case_on_closed_is_invalid_transition():
    tracking = _make_tracking("CLOSED", attempt=0)
    db = _make_db(tracking)

    with patch("app.services.outreach.settings") as ms:
        ms.MAX_ATTEMPTS = 3
        ms.EXECUTION_MODE = "SHADOW"
        ms.is_shadow = True
        result = await execute_manual_action(db, 1001, "CLOSE_CASE", None)

    assert result["status"] == "invalid_transition"


# ── Student not found ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_not_found_when_no_tracking_record():
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute.return_value = result_mock

    result = await execute_manual_action(db, 9999, "CLOSE_CASE", None)
    assert result["status"] == "not_found"


# ── Unknown action ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unknown_action_returns_invalid_action():
    tracking = _make_tracking("CONTACTED", attempt=1)
    db = _make_db(tracking)

    with patch("app.services.outreach.settings") as ms:
        ms.MAX_ATTEMPTS = 3
        ms.EXECUTION_MODE = "SHADOW"
        ms.is_shadow = True
        result = await execute_manual_action(db, 1001, "DO_SOMETHING_WEIRD", None)

    assert result["status"] == "invalid_action"
