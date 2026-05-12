"""Tests for the SQL Server → PostgreSQL sync service.

Validates:
- Happy path: all rows valid → success
- Partial path: rows with NULL NOT NULL fields → partial_success
- Skip invariant: invalid rows never reach the DB
- Valid rows always persist regardless of invalid siblings
- Structured failure details (user_id + reason) in response
- No outbound HTTP communication during sync
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.sync import sync_from_mssql, _validate_row


# ── Unit: _validate_row ───────────────────────────────────────────────────────

def test_validate_row_passes_complete_row():
    row = {"UserID": 1, "HWsBehind": 2, "AvgEffRating": 0.8, "LastActivityDays": 5}
    assert _validate_row(row) == []


def test_validate_row_flags_null_hws_behind():
    row = {"UserID": 47000, "HWsBehind": None, "AvgEffRating": 0.8}
    missing = _validate_row(row)
    assert "HWsBehind" in missing


def test_validate_row_flags_null_avg_eff_rating():
    row = {"UserID": 47420, "HWsBehind": 3, "AvgEffRating": None}
    missing = _validate_row(row)
    assert "AvgEffRating" in missing


def test_validate_row_flags_both_null():
    row = {"UserID": 47000, "HWsBehind": None, "AvgEffRating": None}
    missing = _validate_row(row)
    assert "HWsBehind" in missing
    assert "AvgEffRating" in missing


def test_validate_row_flags_null_user_id():
    row = {"UserID": None, "HWsBehind": 1, "AvgEffRating": 0.5}
    missing = _validate_row(row)
    assert "UserID" in missing


# ── Integration: sync_from_mssql ─────────────────────────────────────────────

def _make_db(existing_record=None):
    """Build a mock AsyncSession that behaves like SQLAlchemy for these tests."""
    db = AsyncMock()
    db.get = AsyncMock(return_value=existing_record)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


VALID_ROW_A = {
    "UserID": 1001, "FirstName": "Alice", "LastName": "Smith",
    "Email": "alice@example.com", "PhoneNumber": "+15550001001",
    "PathName": "SQL", "HWsBehind": 2, "AvgEffRating": 0.85, "LastActivityDays": 3,
}
VALID_ROW_B = {
    "UserID": 1002, "FirstName": "Bob", "LastName": "Jones",
    "Email": "bob@example.com", "PhoneNumber": "+15550001002",
    "PathName": "SSRS", "HWsBehind": 0, "AvgEffRating": 0.92, "LastActivityDays": 1,
}
INVALID_ROW_NULL_HWS = {
    "UserID": 47000, "FirstName": "Carol", "LastName": "Lee",
    "Email": "carol@example.com", "PhoneNumber": "+15550047000",
    "PathName": "SQL", "HWsBehind": None, "AvgEffRating": None, "LastActivityDays": 9,
}
INVALID_ROW_NULL_AVG = {
    "UserID": 47420, "FirstName": "Dan", "LastName": "Kim",
    "Email": "dan@example.com", "PhoneNumber": "+15550047420",
    "PathName": "SSIS", "HWsBehind": None, "AvgEffRating": None, "LastActivityDays": 91,
}


@pytest.mark.asyncio
async def test_sync_all_valid_rows_returns_success():
    db = _make_db(existing_record=None)  # no existing records → all inserts
    rows = [VALID_ROW_A, VALID_ROW_B]

    with patch("app.services.sync.fetch_students_from_mssql", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = (rows, None)
        result = await sync_from_mssql(db)

    assert result["status"] == "success"
    assert result["rows_scanned"] == 2
    assert result["rows_successful"] == 2
    assert result["rows_failed"] == 0
    assert result["failures"] == []
    assert result["connected"] is True
    assert result["error"] is None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_partial_null_hws_behind_returns_partial_success():
    db = _make_db(existing_record=None)
    rows = [VALID_ROW_A, INVALID_ROW_NULL_HWS]

    with patch("app.services.sync.fetch_students_from_mssql", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = (rows, None)
        result = await sync_from_mssql(db)

    assert result["status"] == "partial_success"
    assert result["rows_scanned"] == 2
    assert result["rows_successful"] == 1
    assert result["rows_failed"] == 1
    assert len(result["failures"]) == 1
    assert result["failures"][0]["user_id"] == 47000
    assert "HWsBehind" in result["failures"][0]["reason"]


@pytest.mark.asyncio
async def test_sync_partial_null_avg_eff_rating_returns_partial_success():
    db = _make_db(existing_record=None)
    rows = [VALID_ROW_B, INVALID_ROW_NULL_AVG]

    with patch("app.services.sync.fetch_students_from_mssql", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = (rows, None)
        result = await sync_from_mssql(db)

    assert result["status"] == "partial_success"
    assert result["rows_failed"] == 1
    assert result["failures"][0]["user_id"] == 47420
    assert "AvgEffRating" in result["failures"][0]["reason"]


@pytest.mark.asyncio
async def test_sync_skips_invalid_but_persists_valid_rows():
    """Valid rows must be added to the DB session; invalid rows must not be."""
    db = _make_db(existing_record=None)
    rows = [VALID_ROW_A, INVALID_ROW_NULL_HWS, INVALID_ROW_NULL_AVG]

    with patch("app.services.sync.fetch_students_from_mssql", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = (rows, None)
        result = await sync_from_mssql(db)

    # Only VALID_ROW_A should have been added
    assert db.add.call_count == 1
    added_instance = db.add.call_args[0][0]
    assert added_instance.UserID == VALID_ROW_A["UserID"]

    assert result["rows_successful"] == 1
    assert result["rows_failed"] == 2


@pytest.mark.asyncio
async def test_sync_failure_details_contain_user_id_and_reason():
    db = _make_db(existing_record=None)
    rows = [INVALID_ROW_NULL_HWS, INVALID_ROW_NULL_AVG]

    with patch("app.services.sync.fetch_students_from_mssql", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = (rows, None)
        result = await sync_from_mssql(db)

    assert result["status"] == "partial_success"
    for failure in result["failures"]:
        assert "user_id" in failure
        assert "reason" in failure
        assert isinstance(failure["reason"], str)
        assert len(failure["reason"]) > 0

    user_ids = {f["user_id"] for f in result["failures"]}
    assert 47000 in user_ids
    assert 47420 in user_ids


@pytest.mark.asyncio
async def test_sync_connection_failure_returns_connection_error():
    db = _make_db()

    with patch("app.services.sync.fetch_students_from_mssql", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = ([], "Login failed for user 'ssip_reader'")
        result = await sync_from_mssql(db)

    assert result["status"] == "connection_error"
    assert result["connected"] is False
    assert result["rows_scanned"] == 0
    assert "Login failed" in result["error"]
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_no_outbound_http_calls():
    """Sync must never trigger outbound HTTP — shadow mode integrity check."""
    db = _make_db(existing_record=None)
    rows = [VALID_ROW_A, INVALID_ROW_NULL_HWS]

    with patch("app.services.sync.fetch_students_from_mssql", new_callable=AsyncMock) as mock_fetch:
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_fetch.return_value = (rows, None)
                await sync_from_mssql(db)
                mock_post.assert_not_called()
                mock_get.assert_not_called()
