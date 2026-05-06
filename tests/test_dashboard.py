"""Tests for dashboard alert generation and summary data shapes."""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.routers.dashboard import dashboard_alerts, dashboard_summary


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_db(fetchall_returns: list | None = None, scalar_returns: list | None = None):
    """Build an AsyncSession mock that yields predictable results per call."""
    call_index = [0]
    scalar_index = [0]
    fetchall_seq = fetchall_returns or []
    scalar_seq = scalar_returns or []

    async def _execute(_query):
        result = MagicMock()
        if call_index[0] < len(fetchall_seq):
            result.fetchall.return_value = fetchall_seq[call_index[0]]
        else:
            result.fetchall.return_value = []
        if scalar_index[0] < len(scalar_seq):
            result.scalar.return_value = scalar_seq[scalar_index[0]]
            scalar_index[0] += 1
        else:
            result.scalar.return_value = 0
        call_index[0] += 1
        return result

    db = AsyncMock()
    db.execute.side_effect = _execute
    return db


# ── alert tests ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mssql_not_configured_produces_critical_alert():
    db = _make_db()
    with patch("app.routers.dashboard.settings") as ms:
        ms.mssql_configured = False
        ms.is_shadow = False
        ms.MSSQL_HOST = ""
        ms.SYNTHFLOW_API_KEY = ""
        ms.GHL_API_KEY = ""
        with patch("app.routers.dashboard.get_last_run_at", return_value=datetime.now(tz=timezone.utc).isoformat()):
            with patch("app.routers.dashboard.get_scheduler_status", return_value="active"):
                response = await dashboard_alerts(db)

    assert response.status == "success"
    critical = [a for a in response.data["alerts"] if a["severity"] == "CRITICAL"]
    assert len(critical) >= 1
    assert "SQL Server" in critical[0]["message"]


@pytest.mark.asyncio
async def test_shadow_mode_produces_info_alert():
    db = _make_db()
    with patch("app.routers.dashboard.settings") as ms:
        ms.mssql_configured = True
        ms.is_shadow = True
        ms.SYNTHFLOW_API_KEY = ""
        ms.GHL_API_KEY = ""
        with patch("app.routers.dashboard.get_last_run_at", return_value=datetime.now(tz=timezone.utc).isoformat()):
            with patch("app.routers.dashboard.get_scheduler_status", return_value="active"):
                response = await dashboard_alerts(db)

    assert response.status == "success"
    info = [a for a in response.data["alerts"] if a["severity"] == "INFO"]
    assert any("SHADOW" in a["message"] for a in info)


@pytest.mark.asyncio
async def test_scheduler_never_ran_produces_warning():
    db = _make_db()
    with patch("app.routers.dashboard.settings") as ms:
        ms.mssql_configured = True
        ms.is_shadow = False
        ms.SYNTHFLOW_API_KEY = ""
        ms.GHL_API_KEY = ""
        with patch("app.routers.dashboard.get_last_run_at", return_value=None):
            with patch("app.routers.dashboard.get_scheduler_status", return_value="active"):
                response = await dashboard_alerts(db)

    warnings = [a for a in response.data["alerts"] if a["severity"] == "WARNING"]
    assert any("Scheduler" in a["message"] for a in warnings)


@pytest.mark.asyncio
async def test_stuck_contacted_alert_includes_student_id():
    class _Row:
        user_id = 1001

    db = _make_db(fetchall_returns=[[_Row()], []])  # first call: stuck; second: missed retry
    with patch("app.routers.dashboard.settings") as ms:
        ms.mssql_configured = True
        ms.is_shadow = False
        ms.SYNTHFLOW_API_KEY = ""
        ms.GHL_API_KEY = ""
        with patch("app.routers.dashboard.get_last_run_at", return_value=datetime.now(tz=timezone.utc).isoformat()):
            with patch("app.routers.dashboard.get_scheduler_status", return_value="active"):
                response = await dashboard_alerts(db)

    warnings = [a for a in response.data["alerts"] if a["severity"] == "WARNING"]
    assert any(a["student_id"] == 1001 for a in warnings)


@pytest.mark.asyncio
async def test_alert_response_shape():
    db = _make_db()
    with patch("app.routers.dashboard.settings") as ms:
        ms.mssql_configured = True
        ms.is_shadow = True
        ms.SYNTHFLOW_API_KEY = ""
        ms.GHL_API_KEY = ""
        with patch("app.routers.dashboard.get_last_run_at", return_value=datetime.now(tz=timezone.utc).isoformat()):
            with patch("app.routers.dashboard.get_scheduler_status", return_value="active"):
                response = await dashboard_alerts(db)

    assert "alerts" in response.data
    assert "count" in response.data
    for a in response.data["alerts"]:
        assert "severity" in a
        assert "message" in a
        assert "recommended_action" in a
        assert a["severity"] in ("CRITICAL", "WARNING", "INFO")
