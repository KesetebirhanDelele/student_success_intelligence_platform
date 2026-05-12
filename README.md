# Student Success Intelligence Platform (SSIP)

Automated student outreach decision engine. Reads student risk signals from SQL Server, applies eligibility and priority logic, and orchestrates outreach via GHL, Synthflow, SMS, and email.

**Execution mode: SHADOW** — all outbound calls are no-ops until `.env` credentials are filled and `EXECUTION_MODE=LIVE` is explicitly set.

---

## Stack

| Layer | Technology |
|---|---|
| API | Python 3.12 · FastAPI |
| Database | PostgreSQL 16 (via SQLAlchemy async + asyncpg) |
| Source data | SQL Server (read-only, via pyodbc) |
| Scheduler | APScheduler (daily batch) |
| LLM | OpenAI GPT-4o |
| Container | Docker Compose |
| Frontend | Single-page dashboard (`frontend/index.html`) |

---

## Quick Start

```bash
# 1. Copy env template and fill in credentials
cp .env.example .env
# edit .env — fill MSSQL_HOST, MSSQL_USER, MSSQL_PASS, MSSQL_DATABASE

# 2. Build and start
docker compose up -d --build

# 3. Open dashboard
open http://localhost:8080
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | Set automatically by Docker Compose (`postgresql+asyncpg://ssip:ssip@db:5432/ssip`) |
| `MSSQL_HOST` | Yes | SQL Server hostname or IP |
| `MSSQL_PORT` | No | Default: `1433` |
| `MSSQL_USER` | Yes | SQL Server login (read-only account) |
| `MSSQL_PASS` | Yes | SQL Server password |
| `MSSQL_DATABASE` | Yes | Database name containing `AI_ChatBot_TriggerData` |
| `OPENAI_API_KEY` | No | GPT-4o key for LLM analysis (stubbed in SHADOW mode) |
| `GHL_API_KEY` | No | GoHighLevel API key (no-op in SHADOW mode) |
| `GHL_BASE_URL` | No | GHL base URL |
| `GHL_LOCATION_ID` | No | GHL location ID |
| `SYNTHFLOW_API_KEY` | No | Synthflow API key (no-op in SHADOW mode) |
| `SYNTHFLOW_PHONE_NUMBER` | No | Outbound caller ID for Synthflow |
| `EXECUTION_MODE` | No | `SHADOW` (default) or `LIVE`. LIVE requires all credentials filled. |

---

## SQL Server Sync

The sync pulls every row from `AI_ChatBot_TriggerData` on the source SQL Server and upserts them into the local PostgreSQL mirror table `ai_chatbot_triggerdata`.

### How to run a sync

**From the dashboard:** Open the SQL Server Sync card and click **Sync Now**, or expand the card inline and click **Sync Now**.

**Via API:**
```bash
curl -X POST http://localhost:8080/sync/mssql
```

### Sync result shape

```json
{
  "status": "success",
  "rows_scanned": 90,
  "rows_successful": 90,
  "rows_failed": 0,
  "added": 5,
  "updated": 85,
  "connected": true,
  "error": null,
  "failures": []
}
```

| Field | Meaning |
|---|---|
| `status` | `success` — all rows synced; `partial_success` — some rows skipped; `connection_error` — SQL Server unreachable |
| `rows_scanned` | Total rows returned from SQL Server |
| `rows_successful` | Rows that were inserted or updated in PostgreSQL |
| `rows_failed` | Rows skipped due to data quality issues |
| `added` | New rows inserted |
| `updated` | Existing rows updated |
| `failures` | List of `{user_id, reason}` for each skipped row |

### Partial sync (WARNING status)

If some source rows have `NULL` in `HWsBehind` or `AvgEffRating` (which are NOT NULL in PostgreSQL), those rows are **skipped** rather than crashing the entire sync. All valid rows still persist.

The dashboard shows:
- A **WARNING** badge when any rows were skipped
- The count of skipped rows
- Each skipped UserID and the reason (e.g., `Missing required fields: HWsBehind, AvgEffRating`)

Valid rows always land regardless of how many invalid rows are present.

### Data quality rules

| Field | Rule |
|---|---|
| `UserID` | Must not be NULL (primary key) |
| `HWsBehind` | Must not be NULL (NOT NULL integer column) |
| `AvgEffRating` | Must not be NULL (NOT NULL float column) |

NULL values are never silently replaced with defaults. If source data is NULL, the row is quarantined and the operator sees the reason.

### Troubleshooting sync errors

| Symptom | Likely cause | Fix |
|---|---|---|
| `SQL Server not configured` | `MSSQL_HOST`, `MSSQL_USER`, or `MSSQL_DATABASE` is empty in `.env` | Fill the missing env vars and restart: `docker compose up -d` |
| `Connection error: Login failed` | Wrong credentials | Check `MSSQL_USER` / `MSSQL_PASS` |
| `Connection error: TCP Provider` | Wrong host or port, firewall | Verify `MSSQL_HOST` and `MSSQL_PORT`; check network access |
| `partial_success` with skipped rows | Source data has NULL in `HWsBehind` or `AvgEffRating` | Review the skipped UserIDs in the dashboard; fix upstream data and re-sync |

---

## Dashboard

The dashboard at `http://localhost:8080` is a single-page Bootstrap 5 app. It auto-refreshes every 60 seconds.

### Sections

| Section | What it shows |
|---|---|
| System Health | DB connection, MSSQL config status, scheduler last run, execution mode |
| Operational Alerts | Active warnings (unconfigured MSSQL, stuck students, shadow mode reminder) |
| Funnel KPIs | Conversion and response rate metrics |
| State Distribution | Count of students per outreach state |
| Channel Performance | Per-channel attempt / response / resolution rates |
| Student Lookup | Search by UserID — profile, risk badge, outreach history |
| Source Analysis | Per-path breakdown of tracked/untracked/risk-distribution students |
| Work Queue | 7 named queues (all source, untracked, eligible, contacted, intervention, retry due, resolved/closed) with priority-sorted student lists |
| Batch Preview | Dry-run: see what the batch job would do before running |
| Manual Actions | Close / Force Retry / Resolve / Escalate a student case |
| SQL Server Sync | Trigger manual sync; shows last sync result with skipped rows |
| Recent Activity | Latest outreach history entries |

### Expand All

Click **⊞ Expand All** in the navbar to open all cards inline. Each open panel auto-refreshes every 60 seconds.

---

## Running Tests

```bash
docker compose run --rm api python -m pytest tests/ -v
```

Expected: **45 passed** (as of 2026-05-12).

Test files:

| File | Coverage |
|---|---|
| `tests/test_actions.py` | Manual action state-machine guards (8 tests) |
| `tests/test_dashboard.py` | Alert generation rules (5 tests) |
| `tests/test_shadow_safety.py` | SHADOW mode — no outbound HTTP for all 4 channels (6 tests) |
| `tests/test_sync.py` | Sync service — validation, partial sync, skip invariants, no HTTP (12 tests) |
| `tests/test_work_queue.py` | Priority engine, source router, work queue, batch preview (14 tests) |

---

## Architecture

```
SQL Server (read-only)
    │
    ▼  pyodbc / asyncio.to_thread
app/database.py — fetch_students_from_mssql()
    │
    ▼
app/services/sync.py — validate → upsert → return structured result
    │
    ▼
PostgreSQL — ai_chatbot_triggerdata (local mirror)
    │
    ▼
app/services/eligibility.py + priority.py + decision_engine.py
    │
    ▼
app/services/outreach.py — SHADOW: logs only; LIVE: calls GHL / Synthflow / SMS / email
    │
    ▼
app/models.py — StudentOutreachTracking, OutreachHistory, StateTransitionLog
```

**Execution mode gate:** Every outbound call checks `settings.is_shadow`. In SHADOW mode, integrations return a simulated response and make no HTTP calls. To flip to LIVE, set `EXECUTION_MODE=LIVE` in `.env` — this is a strategic decision requiring explicit approval.

---

## Deployment (Production VPS)

```bash
ssh root@<vps-ip>
cd /opt/ssip
git pull origin main
docker compose -f docker-compose.production.yml up -d --build api
```

Check logs:
```bash
docker compose logs -f api
```

---

## Follow-up: Data Quality Issues Table (not yet implemented)

A `data_quality_issues` table has been proposed as a follow-up to persist sync failure history across runs. Fields: `id`, `source_table`, `user_id`, `issue_type`, `issue_message`, `raw_payload` (JSONB), `created_at`, `resolved_at`. This would let operators query historical skipped rows without re-running the sync. Requires a Alembic migration. Not blocking current operation — the failures are already visible in the dashboard per-sync.
