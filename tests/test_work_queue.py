"""Tests for priority engine, source router, work queue router, and batch router."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ── Priority scoring ──────────────────────────────────────────────────────────

def test_priority_urgent_score():
    from app.services.priority import score_student, URGENT_THRESHOLD
    student = {"HWsBehind": 5, "AvgEffRating": 0.0, "LastActivityDays": 25}
    result = score_student(student)
    assert result.score >= URGENT_THRESHOLD
    assert result.level == "URGENT"
    assert result.recommended_action == "ESCALATE"


def test_priority_low_score():
    from app.services.priority import score_student, MEDIUM_THRESHOLD
    student = {"HWsBehind": 0, "AvgEffRating": 4.5, "LastActivityDays": 1}
    result = score_student(student)
    assert result.score < MEDIUM_THRESHOLD
    assert result.level == "LOW"
    assert result.recommended_action == "MONITOR"


def test_priority_medium_score():
    from app.services.priority import score_student, MEDIUM_THRESHOLD, HIGH_THRESHOLD
    student = {"HWsBehind": 2, "AvgEffRating": 3.5, "LastActivityDays": 5}
    result = score_student(student)
    assert MEDIUM_THRESHOLD <= result.score < HIGH_THRESHOLD
    assert result.level == "MEDIUM"


def test_priority_no_response_state_overrides_to_force_retry():
    from app.services.priority import score_student
    student = {"HWsBehind": 1, "AvgEffRating": 4.0, "LastActivityDays": 2}
    tracking = {"state": "NO_RESPONSE", "current_attempt": 1}
    result = score_student(student, tracking)
    assert result.recommended_action == "FORCE_RETRY"


def test_priority_intervention_state_overrides_to_escalate():
    from app.services.priority import score_student
    student = {"HWsBehind": 1, "AvgEffRating": 4.0, "LastActivityDays": 2}
    tracking = {"state": "INTERVENTION_REQUIRED", "current_attempt": 2}
    result = score_student(student, tracking)
    assert result.recommended_action == "ESCALATE"


def test_priority_score_caps():
    from app.services.priority import score_student
    # HWsBehind caps at 5 (50 pts), inactivity caps at 25 days (50 pts), eff score caps at 35
    student = {"HWsBehind": 99, "AvgEffRating": 0.0, "LastActivityDays": 999}
    result = score_student(student)
    assert result.score == 135  # 50 + 35 + 50


def test_priority_reason_codes_present():
    from app.services.priority import score_student
    student = {"HWsBehind": 3, "AvgEffRating": 2.0, "LastActivityDays": 10}
    result = score_student(student)
    assert len(result.reason_codes) == 3
    assert any("HW:3" in rc for rc in result.reason_codes)


# ── Source router — unit tests with mocked DB ─────────────────────────────────

@pytest.mark.asyncio
async def test_source_paths_returns_distinct_paths():
    from app.routers.source import source_paths

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [("SQL",), ("SSRS",), ("SSIS",)]
    mock_db.execute = AsyncMock(return_value=mock_result)

    response = await source_paths(db=mock_db)
    assert response.status == "success"
    assert response.data["count"] == 3
    assert "SQL" in response.data["paths"]


@pytest.mark.asyncio
async def test_source_paths_empty_when_no_students():
    from app.routers.source import source_paths

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)

    response = await source_paths(db=mock_db)
    assert response.data["count"] == 0
    assert response.data["paths"] == []


# ── Work queue summary — unit tests ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_work_queue_summary_structure():
    from app.routers.work_queue import work_queue_summary

    mock_db = AsyncMock()

    def make_scalar_result(val):
        r = MagicMock()
        r.scalar.return_value = val
        return r

    def make_fetchall_result(rows):
        r = MagicMock()
        r.fetchall.return_value = rows
        r.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
        return r

    call_count = [0]

    async def mock_execute(q):
        call_count[0] += 1
        n = call_count[0]
        if n == 1:
            return make_scalar_result(10)   # total_source
        elif n == 2:
            return make_fetchall_result([(1,), (2,)])  # tracked user_ids
        elif n == 3:
            rows = [
                MagicMock(state="ELIGIBLE", cnt=3),
                MagicMock(state="CONTACTED", cnt=2),
                MagicMock(state="CLOSED", cnt=1),
            ]
            r = MagicMock()
            r.fetchall.return_value = rows
            return r
        else:
            return make_scalar_result(0)  # retry_due

    mock_db.execute = mock_execute

    response = await work_queue_summary(db=mock_db)
    assert response.status == "success"
    queues = response.data["queues"]
    assert "all_source" in queues
    assert "untracked" in queues
    assert "eligible" in queues
    assert queues["all_source"] == 10
    assert queues["untracked"] == 8   # 10 - 2 tracked


# ── Work queue invalid name ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_work_queue_invalid_name_returns_error():
    from app.routers.work_queue import work_queue_detail

    mock_db = AsyncMock()
    response = await work_queue_detail(queue_name="DOES_NOT_EXIST", db=mock_db)
    assert response.status == "error"
    assert response.error["code"] == "INVALID_QUEUE"


# ── Batch preview — smoke test ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_batch_preview_returns_expected_keys():
    from app.routers.batch import batch_preview

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("app.routers.batch.settings") as ms:
        ms.EXECUTION_MODE = "SHADOW"
        ms.is_shadow = True

        response = await batch_preview(checkpoint_type="SQL", limit=50, db=mock_db)

    assert response.status == "success"
    data = response.data
    assert "checkpoint_type" in data
    assert "decisions" in data
    assert "rows" in data
    assert data["shadow"] is True


# ── Schemas — checkpoint_type now accepts any string ─────────────────────────

def test_trigger_outreach_request_accepts_arbitrary_path():
    from app.schemas import TriggerOutreachRequest
    req = TriggerOutreachRequest(checkpoint_type="MY_NEW_PATH", limit=10)
    assert req.checkpoint_type == "MY_NEW_PATH"


def test_trigger_outreach_request_accepts_legacy_paths():
    from app.schemas import TriggerOutreachRequest
    for path in ("SQL", "SSRS", "SSIS", "POST_COMPLETION"):
        req = TriggerOutreachRequest(checkpoint_type=path)
        assert req.checkpoint_type == path
