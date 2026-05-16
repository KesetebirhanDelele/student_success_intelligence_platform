# spec/08_data_model.md

---

## LAYER 2 — SPECIFICATIONS (DATA MODEL)

---

## 1. PURPOSE

This file defines:

* Database schema
* Table structures
* Relationships
* Constraints
* Indexing strategy

The goal is to ensure:

* Data consistency
* Query performance
* Clear ownership of data

---

## 2. DATABASE OVERVIEW

---

### Dual-Database Architecture

The system uses two databases with distinct roles:

| Database     | Engine       | Role                                              |
|------------- |------------- |------------------------------------------------- |
| SQL Server   | MSSQL        | Source of truth — student academic data (READ-ONLY) |
| PostgreSQL   | asyncpg      | Application database — all system-owned tables   |

SQL Server is **never written to**. All application state (outreach history, notes, insights, action logs, GHL message cache) lives in PostgreSQL. A sync service (`POST /sync/mssql`) copies student rows from SQL Server into `student_trigger_data` in PostgreSQL on demand.

---

### Data Sources

| Source                     | Database     | Ownership                  |
| -------------------------- | ------------ | -------------------------- |
| AI_ChatBot_TriggerData     | SQL Server   | External (Read-Only)       |
| student_trigger_data       | PostgreSQL   | System (synced mirror)     |
| outreach_history           | PostgreSQL   | System                     |
| state_transition_log       | PostgreSQL   | System                     |
| student_notes              | PostgreSQL   | System                     |
| ai_insights                | PostgreSQL   | System                     |
| ghl_messages               | PostgreSQL   | System (GHL message cache) |
| student_campaign_activity  | PostgreSQL   | System (operator logs)     |
| student_quick_action_log   | PostgreSQL   | System (button click audit)|

---

## 3. SQL SERVER TABLES (READ-ONLY SOURCE)

---

## 3.1 AI_ChatBot_TriggerData

---

### Description

Source table containing student academic and engagement data. The system reads this via `SELECT *` to avoid schema drift failures; all unknown columns are filtered before PostgreSQL upsert.

---

### Known Fields (confirmed present in production)

| Field                | Type         | Description                          |
| -------------------- | ------------ | ------------------------------------ |
| UserID               | INT          | Primary identifier                   |
| FirstName            | VARCHAR      | Student first name                   |
| LastName             | VARCHAR      | Student last name                    |
| Email                | VARCHAR      | Email address                        |
| PhoneNumber          | VARCHAR      | Contact number (E.164 normalized)    |
| PathName             | VARCHAR      | Learning path                        |
| HWsBehind            | INT          | Assignments behind                   |
| AvgEffRating         | FLOAT        | Effort rating                        |
| LastActivityDays     | INT          | Days since last activity             |
| AttendancePercentage | FLOAT        | 0–100 scale (not 0–1 decimal)        |
| IPBCStartDate        | DATETIME     | IPBC program start (timezone-naive)  |
| StudentStartDate     | DATETIME     | Student enrollment date              |
| ClassStartDate       | DATETIME     | Cohort class start date              |
| ClassName            | VARCHAR      | Name of the enrolled class           |
| ClassSignupsID       | VARCHAR      | Enrollment record ID                 |
| ActiveStatus         | VARCHAR      | "1", "Active", "active", etc.        |
| StatusI              | VARCHAR      | Primary status label                 |
| StatusII             | VARCHAR      | Secondary status label               |
| LastActivitySection  | VARCHAR(300) | Last content section completed       |
| LastLoginDays        | INT          | Days since last login                |
| LastSubmitted        | VARCHAR(200) | Last homework submission (ISO string)|
| Total_Payments       | FLOAT        | Total payments received              |
| Total_Credits        | FLOAT        | Total credits applied                |
| PaymentBalance       | FLOAT        | Outstanding balance                  |
| ClassValue           | FLOAT        | Full tuition value                   |
| FeePaid              | BIT/BOOL     | One-time fee paid flag               |
| ClassFeesPaid        | FLOAT        | Fees paid to date                    |

### Constraints

* Table is read-only — never written to by this system
* Sync uses `SELECT *` — gracefully handles new or missing columns

---

## 4. POSTGRESQL TABLES (SYSTEM-OWNED)

---

## 4.1 student_trigger_data

---

### Description

Synced mirror of `AI_ChatBot_TriggerData`. Populated via `POST /sync/mssql`. All lifecycle tab queries run against this table.

Schema managed via migration-lite pattern: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in `init_db()` on container startup. No Alembic — safe to re-run.

### Key Columns

| Column               | PG Type           | Notes                                        |
| -------------------- | ----------------- | -------------------------------------------- |
| id                   | SERIAL PK         | Internal row ID                              |
| UserID               | INTEGER UNIQUE    | SQL Server student ID                        |
| FirstName            | VARCHAR(100)      |                                              |
| LastName             | VARCHAR(100)      |                                              |
| Email                | VARCHAR(200)      |                                              |
| PhoneNumber          | VARCHAR(50)       |                                              |
| PathName             | VARCHAR(200)      |                                              |
| HWsBehind            | INTEGER           |                                              |
| AvgEffRating         | DOUBLE PRECISION  |                                              |
| LastActivityDays     | INTEGER           |                                              |
| AttendancePercentage | DOUBLE PRECISION  | 0–100 scale                                  |
| IPBCStartDate        | TIMESTAMP         | Stored without timezone (naive)              |
| StudentStartDate     | TIMESTAMP         |                                              |
| ClassStartDate       | TIMESTAMP         |                                              |
| ClassName            | VARCHAR(200)      |                                              |
| ClassSignupsID       | VARCHAR(100)      |                                              |
| ActiveStatus         | VARCHAR(50)       | Normalized to 1/0 by `_active_student()`     |
| StatusI              | VARCHAR(100)      |                                              |
| StatusII             | VARCHAR(100)      |                                              |
| LastActivitySection  | VARCHAR(300)      | Primary section filter for lifecycle tabs    |
| LastLoginDays        | INTEGER           |                                              |
| LastSubmitted        | VARCHAR(200)      | Stored as string; parsed by `_hw_submitted_days()` |
| Total_Payments       | DOUBLE PRECISION  |                                              |
| Total_Credits        | DOUBLE PRECISION  |                                              |
| PaymentBalance       | DOUBLE PRECISION  |                                              |
| ClassValue           | DOUBLE PRECISION  |                                              |
| FeePaid              | BOOLEAN           |                                              |
| ClassFeesPaid        | DOUBLE PRECISION  |                                              |
| CurrentSection       | VARCHAR(200)      | Legacy — always NULL (not in SQL Server)     |
| synced_at            | TIMESTAMP         | Last sync timestamp                          |
| created_at           | TIMESTAMP         |                                              |

---

## 4.2 outreach_history

---

### Description

Append-only log of every outreach action. One row per attempt.

| Column         | Type      | Description              |
| -------------- | --------- | ------------------------ |
| id             | SERIAL PK |                          |
| user_id        | INTEGER   | FK → student             |
| checkpoint_type| VARCHAR   | SQL/SSRS/SSIS/POST_COMPLETION |
| channel        | VARCHAR   | CALL/SMS/EMAIL/OPERATOR  |
| action         | VARCHAR   | CALL_SIMULATED, etc.     |
| execution_mode | VARCHAR   | SHADOW or LIVE           |
| state_before   | VARCHAR   |                          |
| state_after    | VARCHAR   |                          |
| attempt_number | INTEGER   |                          |
| created_at     | TIMESTAMP |                          |

---

## 4.3 state_transition_log

---

| Column      | Type      | Description           |
| ----------- | --------- | --------------------- |
| id          | SERIAL PK |                       |
| user_id     | INTEGER   |                       |
| from_state  | VARCHAR   |                       |
| to_state    | VARCHAR   |                       |
| trigger     | VARCHAR   | scheduler/operator    |
| actor       | VARCHAR   |                       |
| created_at  | TIMESTAMP |                       |

---

## 4.4 student_notes

---

Internal notes written by operators. Rendered on the unified timeline and in tab "Notes" columns.

| Column     | Type      | Description                         |
| ---------- | --------- | ----------------------------------- |
| id         | SERIAL PK |                                     |
| user_id    | INTEGER   |                                     |
| content    | TEXT      |                                     |
| note_type  | VARCHAR(50)| e.g. "general", "escalation"       |
| visibility | VARCHAR(50)| e.g. "internal", "mentor"          |
| created_by | VARCHAR   |                                     |
| created_at | TIMESTAMP |                                     |

---

## 4.5 ai_insights

---

LLM-generated analysis results for a student or group of students.

| Column      | Type      | Description                         |
| ----------- | --------- | ----------------------------------- |
| id          | SERIAL PK |                                     |
| user_id     | INTEGER   |                                     |
| insight_type| VARCHAR   | "risk", "opportunity", etc.         |
| content     | TEXT      |                                     |
| model_used  | VARCHAR   |                                     |
| created_at  | TIMESTAMP |                                     |

---

## 4.6 ghl_messages

---

Local cache of GHL conversation messages fetched via `GET /ghl-sync/student` or batch sync. Read-only from the GHL API perspective; never written back to GHL.

| Column         | Type      | Description                       |
| -------------- | --------- | --------------------------------- |
| id             | SERIAL PK |                                   |
| user_id        | INTEGER   |                                   |
| contact_id     | VARCHAR   | GHL contact_id                    |
| conversation_id| VARCHAR   | GHL conversation_id               |
| direction      | VARCHAR   | inbound/outbound                  |
| message_type   | VARCHAR   | SMS/CALL/EMAIL                    |
| body           | TEXT      |                                   |
| status         | VARCHAR   |                                   |
| sent_at        | TIMESTAMP |                                   |
| created_at     | TIMESTAMP |                                   |

---

## 4.7 student_campaign_activity

---

Operator-logged campaign activities. Populated when an operator clicks an action button in the lifecycle tabs. Also populated by GHL message sync to surface inbound/outbound messages. Drives "Last Campaign Activity" columns in all six lifecycle tabs.

| Column           | Type         | Notes                                          |
| ---------------- | ------------ | ---------------------------------------------- |
| id               | SERIAL PK    |                                                |
| student_user_id  | INTEGER      | FK → student_trigger_data.UserID               |
| activity_date    | DATE         | Defaults to UTC today                          |
| activity_type    | VARCHAR(100) | "NEWCOMERS", "ENGAGEMENT", "CALL", etc.        |
| activity_label   | VARCHAR(300) | Human-readable label from action button        |
| channel          | VARCHAR(50)  | "OPERATOR", "SMS", "EMAIL", "CALL"             |
| subject          | VARCHAR(300) | Optional subject line (email/SMS)              |
| message_body     | TEXT         | Optional draft body                            |
| source           | VARCHAR(100) | "operator", "ghl_sync"                         |
| created_by       | VARCHAR(100) | Operator identifier                            |
| created_at       | TIMESTAMP    |                                                |
| execution_mode   | VARCHAR(20)  | "SHADOW" or "LIVE"                             |
| shadow_only      | BOOLEAN      | True when no real outbound send occurred       |

---

## 4.8 student_quick_action_log

---

Audit log of every button click in the lifecycle tab action bars. One row per click, regardless of outcome.

| Column          | Type         | Notes                                        |
| --------------- | ------------ | -------------------------------------------- |
| id              | SERIAL PK    |                                              |
| student_user_id | INTEGER      |                                              |
| action_key      | VARCHAR(100) | Stable button identifier, e.g. "log_call"   |
| action_label    | VARCHAR(200) | Display label from the button                |
| tab_name        | VARCHAR(100) | Source tab: "newcomers", "engagement", etc.  |
| status          | VARCHAR(50)  | Always "LOGGED" (no execution in SHADOW)     |
| payload_json    | JSONB        | Optional extra context                       |
| created_by      | VARCHAR(100) | Operator identifier                          |
| created_at      | TIMESTAMP    |                                              |
| execution_mode  | VARCHAR(20)  | "SHADOW" or "LIVE"                           |

---

## 5. RELATIONSHIPS

---

```
SQL Server: AI_ChatBot_TriggerData.UserID
    ↓  (sync via POST /sync/mssql)
PostgreSQL: student_trigger_data.UserID
    ↓  (referenced by all system tables)
outreach_history.user_id
state_transition_log.user_id
student_notes.user_id
ai_insights.user_id
ghl_messages.user_id
student_campaign_activity.student_user_id
student_quick_action_log.student_user_id
```

---

## 6. UNIQUE CONSTRAINTS

---

| Table                   | Constraint                                      | Purpose                    |
| ----------------------- | ----------------------------------------------- | -------------------------- |
| student_trigger_data    | UNIQUE (UserID)                                 | One mirror row per student |
| outreach_history        | UNIQUE (user_id, checkpoint_type, attempt_number)| No duplicate attempt       |
| ghl_messages            | UNIQUE (conversation_id, sent_at, direction)    | Idempotent GHL sync        |

---

## 7. STATE FIELD ENUM (outreach_history / state_transition_log)

---

```
ELIGIBLE → QUEUED → CONTACTED → NO_RESPONSE → RETRY
                             → RESPONDED → ANALYZED → INTERVENTION_REQUIRED
                                                     → RESOLVED
                                                     → CLOSED
```

---

## 8. MIGRATION STRATEGY

---

Schema is managed via the **migration-lite** pattern in `app/database.py`:

```python
# Run on every container startup — safe to re-run
await conn.execute(text(
    "ALTER TABLE student_trigger_data ADD COLUMN IF NOT EXISTS LastActivitySection VARCHAR(300)"
))
```

This approach:
- Requires no migration tooling (no Alembic)
- Is idempotent — safe across multiple container restarts
- Does not DROP or modify existing columns
- Matches the constraint that SQL Server schema may change without notice

When a column is removed from SQL Server but still exists in PostgreSQL, it remains in the PostgreSQL schema as NULL and does not cause sync failures.

---

## 9. DATA CONSISTENCY RULES

---

* No null UserID in any system-owned table
* No invalid state enum values
* All writes stamped with `created_at` (UTC)
* `shadow_only = True` when `EXECUTION_MODE = SHADOW` — no real outbound sends occurred
* `execution_mode` column required on all audit tables for compliance tracing

---

## 10. SCOPE-SPECIFIC BEHAVIOR

---

### MVP / SHADOW

* All action tables populated with `execution_mode = SHADOW`, `shadow_only = True`
* No real communication triggered
* GHL messages are read-only cache; no GHL writes

### LIVE

* `execution_mode = LIVE`, `shadow_only = False`
* GHL writes enabled via `POST /ghl-sync/student`
* Real SMS, call, and email triggers enabled per channel flag

---

## 11. ACCEPTANCE CRITERIA

---

### Case 1 — Insert Record

**Given** outreach triggered
**When** record inserted
**Then** all required fields present, execution_mode stamped

---

### Case 2 — Duplicate Prevention

**Given** same UserID + Checkpoint + Attempt
**When** insert attempted
**Then** rejected by unique constraint

---

### Case 3 — Sync Idempotency

**Given** `POST /sync/mssql` called twice in a row
**When** second call runs
**Then** no duplicate rows — existing rows updated in place

---

### Case 4 — SHADOW Enforcement

**Given** EXECUTION_MODE = SHADOW
**When** any action button clicked in lifecycle tabs
**Then** `student_quick_action_log` and `student_campaign_activity` rows inserted, no outbound HTTP to GHL/SMS/email

---

## 12. REFERENCES

---

Depends on:

* spec/02_system_specifications.md
* state/system_state_model.md
* data/data_lifecycle.md
* meta/project_classification.md

---

## END OF FILE
