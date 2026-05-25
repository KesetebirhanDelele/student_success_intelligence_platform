# spec/08_data_model.md

---

## LAYER 2 — SPECIFICATIONS (DATA MODEL)

---

## 1. PURPOSE

This file defines the conceptual data architecture for the Student Success Intelligence Platform (SSIP). It governs how data is classified, owned, stored, versioned, governed, and consumed across all six operational lifecycle domains.

The data architecture serves seven distinct platform capabilities:

1. **Operational intelligence** — real-time student state derived from the SQL Server mirror and platform-owned records
2. **Immutable reporting** — append-only monthly reports derived exclusively from finalized snapshots
3. **Historical reproducibility** — the ability to regenerate any historical report and produce identical output
4. **AI-generated insight lineage** — versioned, attributed, reviewer-approved AI narratives with snapshot isolation
5. **Communication telemetry** — auditable, attribution-stamped records of all outreach and communication events
6. **Compliance-governed exception workflows** — governance-isolated deletion and anonymization with audit survivability
7. **Longitudinal analytics** — time-series aggregation of student progression across cohorts and months

### Platform Capability Summary

| Capability | Data tier | Mutability | Governance boundary |
|---|---|---|---|
| Operational student state | `public` schema | Mutable (sync-updated) | No boundary — operational |
| Outreach state machine | `public` schema | Mutable state transitions | CLOSED is terminal |
| Draft snapshots | `public` schema | Mutable until VALIDATING | FINALIZED is irreversible |
| Finalized snapshots | `warehouse` schema | Append-only after FINALIZED | Immutable; compliance pathway only |
| Published reports | `warehouse` schema | Append-only after REPORT_PUBLISHED | New `lineage_version` on regeneration |
| Active AI insights | `public` schema | Version-append only | Attribution locked at AI_GENERATED |
| Configuration versions | `public` schema | Immutable once ACTIVE | Rollback forbidden |
| Compliance audit | `compliance_audit` schema | Append-only always | Survives operational deletion |

### What This File Does NOT Define

* Physical DDL, SQL, or migration code — see `alembic/versions/`
* Physical index strategies — see Alembic migration files
* ORM model field definitions — see `app/models.py`
* API request/response shapes — see `spec/07_api_contracts.md`
* State transition rules — see `spec/03_state_transition_rules.md`
* Idempotency and concurrency rules — see `spec/04_idempotency_concurrency.md`

---

## 2. DATABASE ARCHITECTURE

---

### Dual-Database Architecture

The platform uses two database engines with strictly defined roles:

| Database | Engine | Role |
|---|---|---|
| SQL Server | MSSQL | Source of truth for student academic data — READ-ONLY |
| PostgreSQL | asyncpg | Application database — all system-owned tables, schemas, and archive |

SQL Server is **never written to**. All application state lives in PostgreSQL. A sync service (`POST /sync/mssql`) copies student rows from SQL Server into `student_trigger_data` in PostgreSQL on demand.

---

### PostgreSQL Schema Separation

PostgreSQL is divided into three isolated schemas with distinct access controls and governance rules:

| Schema | Purpose | Mutability | Standard service account access |
|---|---|---|---|
| `public` | Operational data — all current tables, state machines, AI insights, config registry | Mutable (standard CRUD) | Full read/write |
| `warehouse` | Immutable historical archive — finalized snapshots, published reports, report audit logs | Append-only (no UPDATE/DELETE) | SELECT-only |
| `compliance_audit` | Governance-isolated audit trail — deletion/anonymization records, pre/post-action audit entries | Append-only always | SELECT-only |

The `warehouse` and `compliance_audit` schemas have **no cross-schema FK dependencies**. This ensures:

* Compliance audit records survive even if operational records are deleted
* Warehouse data can be archived independently of operational state
* Schema-level access controls enforce governance boundaries at the database layer

---

### Data Sources

| Source | Schema | Ownership | Authority level |
|---|---|---|---|
| AI_ChatBot_TriggerData | SQL Server | External (Read-Only) | Authoritative — student academic state |
| student_trigger_data | public | Platform (synced mirror) | Derivative — current as of last sync |
| outreach_history | public | Platform | Platform-owned |
| state_transition_log | public | Platform | Platform-owned |
| student_notes | public | Platform | Platform-owned |
| ai_insights | public | Platform | Platform-owned (versioned) |
| ghl_messages | public | Platform (GHL cache) | Derivative — GHL API is real-time source |
| student_campaign_activity | public | Platform | Platform-owned |
| student_quick_action_log | public | Platform | Platform-owned |
| processed_events | public | Platform | Idempotency store |
| config_version_registry | public | Platform | Platform-owned (governance) |
| warehouse.student_snapshots | warehouse | Platform | Immutable historical record |
| warehouse.monthly_reports | warehouse | Platform | Immutable publication record |
| warehouse.report_audit_log | warehouse | Platform | Append-only event log |
| compliance_audit.deletion_log | compliance_audit | Platform (compliance pathway) | Governance-isolated audit |

---

### Conceptual Data Class Table

| Data class | Schema | Mutability model | Governance |
|---|---|---|---|
| SQL Server mirror | public | Upserted on sync | SQL Server owns source |
| Outreach state | public | State machine transitions | CLOSED is terminal |
| AI insights | public | Version-append | Attribution locked after generation |
| Draft snapshots | public → warehouse | Mutable → immutable on FINALIZED | FINALIZED irreversible |
| Published reports | warehouse | Append-only | REPORT_PUBLISHED irreversible |
| Config versions | public | Immutable once ACTIVE | Rollback forbidden |
| Compliance workflows | public + compliance_audit | Mutable workflow; append-only audit | Terminal states irreversible |
| Event logs | public | Append-only | No modification |

---

Sections 3–6 document the existing operational tables in the `public` schema as-at Phase 5. Conceptual entity definitions for the `warehouse` schema, `compliance_audit` schema, AI versioning, config version registry, compliance governance, and report publication are in Sections 13–26.

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

## 7. STATE FIELD ENUMS

---

State field definitions across all six lifecycle domains. These are conceptual definitions; physical enforcement is governed by `spec/03_state_transition_rules.md`.

### Domain 1 — Outreach Lifecycle (student_outreach_tracking, outreach_history)

```
ELIGIBLE → QUEUED → CONTACTED → NO_RESPONSE → RETRY
                             → RESPONDED → ANALYZED → INTERVENTION_REQUIRED
                                                     → RESOLVED
                                                     → CLOSED
```

CLOSED is terminal. No outbound transitions from application code.

### Domain 2 — Snapshot Lifecycle (warehouse.student_snapshots)

```
DRAFT → VALIDATING → FINALIZED
↓                    ↓               ↓
DISCARDED            REGENERATION_REQUESTED    COMPLIANCE_HOLD → COMPLIANCE_DELETED
```

FINALIZED is the governance boundary. The only outbound transitions are REGENERATION_REQUESTED (new lineage) and COMPLIANCE_HOLD (compliance pathway only). Both are irreversible once crossed.

### Domain 3 — Monthly Report Lifecycle (warehouse.monthly_reports)

```
REPORT_PENDING → REPORT_GENERATING → REPORT_GENERATED → REPORT_REVIEW_PENDING
                 ↓                                       ↓
       REPORT_GENERATION_FAILED                REPORT_APPROVED → REPORT_PUBLISHED
                                               REPORT_REJECTED
```

REPORT_PUBLISHED is the governance boundary. Regeneration creates a new record with incremented `lineage_version`; the original REPORT_PUBLISHED record is never modified.

### Domain 4 — AI Insight Lifecycle (ai_insights)

```
AI_PENDING → AI_GENERATING → AI_GENERATED → AI_REVIEW_PENDING → AI_REVIEWED
             ↓                              ↓
     AI_GENERATION_FAILED             AI_REJECTED

AI_REVIEWED → AI_REFRESH_REQUESTED → (new AI_PENDING record, version_number + 1)
```

AI_GENERATED locks attribution metadata (`prompt_version`, `model_used`). AI_REVIEWED locks `content_text`. Force-refresh creates a new record; prior versions are archived.

### Domain 5 — Config Version Lifecycle (config_version_registry)

```
DRAFT → UNDER_REVIEW → APPROVED → ACTIVE → SUPERSEDED
                       ↓
                   REJECTED
```

Exactly one ACTIVE version at all times. ACTIVE → SUPERSEDED is the governance boundary. SUPERSEDED → ACTIVE is forbidden and constitutes a defect if it occurs.

### Domain 6 — Compliance Governance Lifecycle

```
REQUESTED → UNDER_REVIEW → APPROVED_FOR_ACTION → IN_EXECUTION → COMPLETED_DELETED
            ↓              ↓                                   → COMPLETED_ANONYMIZED
         REJECTED       REJECTED                               → PARTIALLY_COMPLETED
                                                                  ↓
                                                              UNDER_REVIEW (recovery)
```

Pre-action audit entry in `compliance_audit` schema is a hard gate before APPROVED_FOR_ACTION → IN_EXECUTION. Terminal states (COMPLETED_DELETED, COMPLETED_ANONYMIZED, REJECTED) are irreversible.

---

## 8. MIGRATION STRATEGY

---

Schema changes are managed via **Alembic** (async-compatible, PostgreSQL-only). The migration-lite `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` pattern in `app/database.py` is **grandfathered for SQL Server mirror columns only** — those change when the SQL Server schema changes. All application-owned schema changes use Alembic exclusively.

### Current Baseline

`alembic/versions/0001_baseline.py` — full baseline covering all 11 tables as-at Phase 5 (`public` schema only).

### Upcoming Migrations

| Revision | File | Status | What it adds |
|---|---|---|---|
| 0002 | `0002_warehouse_schema.py` | **Unblocked** | `warehouse` schema; `warehouse.student_snapshots`, `warehouse.monthly_reports`, `warehouse.report_audit_log` |
| 0003 | `0003_config_version_registry.py` | **Unblocked** | `public.config_version_registry`; seed V1 with current Section 12 defaults |
| 0004 | `0004_compliance_schema.py` | **Unblocked** | `compliance_audit` schema; `compliance_audit.deletion_log` |
| 0005 | `0005_ai_insights_versioning.py` | After 0002 | `version_number`, `prompt_version`, `model_version`, `ai_idempotency_key` columns on `ai_insights` |
| 0006 | `0006_snapshot_lifecycle.py` | After 0002, 0003 | Snapshot lifecycle tracking tables in `public` schema |

### Rules

* All schema changes MUST be tracked as new Alembic revisions — no exceptions
* `_NEW_TRIGGER_COLS` in `app/database.py` is for SQL Server mirror columns only — never add application-owned columns there
* `warehouse` and `compliance_audit` schemas have their own migration scripts; never mix into a `public` migration
* New installation: `alembic upgrade head`
* Existing deployment (tables already from `init_db`): `alembic stamp head` first, then future upgrades run normally

---

## 9. DATA CONSISTENCY RULES

---

### Universal Rules (all tables, all schemas)

* No null UserID in any system-owned table
* All writes stamped with `created_at` (TIMESTAMPTZ, UTC)
* All service calls carry a `correlation_id` (UUID v4, generated at request entry point, propagated downstream)
* No state enum value outside the defined domain-specific set
* `execution_mode` required on all audit and action tables (`SHADOW` or `LIVE`)

### Outreach Domain Rules

* `shadow_only = True` when `execution_mode = SHADOW` — no real outbound sends occurred
* Duplicate attempt rejected by unique constraint `(user_id, checkpoint_type, attempt_number)`
* State transitions must follow the defined state machine; no skipped states

### Snapshot Domain Rules

* No duplicate FINALIZED snapshot per `(student_id, snapshot_month)` — enforced at application layer before write
* Reproducibility fingerprint (all 5 components per FAD-6) must be computed and stored at FINALIZED
* Post-FINALIZED row is immutable from application service accounts — enforced at schema-access layer
* AI narrative text in snapshot row is a physical copy, not a reference to `ai_insights` (FAD-1)
* Config version reference captured at DRAFT → VALIDATING and immutable thereafter (FAD-3)

### Report Domain Rules

* No in-place modification of REPORT_PUBLISHED records
* Regenerated reports create new `lineage_version`; they never overwrite the original
* `source_snapshot_fingerprint` captured at job creation; mismatch → REPORT_GENERATION_FAILED
* `POTENTIALLY_DIVERGENT` flag set when regeneration source fingerprint differs from the original publication fingerprint

### AI Insight Domain Rules

* Attribution metadata (`prompt_version`, `model_used`, `generated_at`) immutable after AI_GENERATED
* `version_number` increments on each force-refresh; no in-place mutation of any version
* In-flight dedup: check for `(AI_PENDING, AI_GENERATING, AI_REVIEW_PENDING)` on `(student_id, insight_type, date_period)` before creating a new request
* Prior versions are archived, not deleted, when a new version is created

### Config Version Domain Rules

* Exactly one ACTIVE config version at all times; zero-ACTIVE window is a system defect
* APPROVED → ACTIVE and old ACTIVE → SUPERSEDED must be atomic (single transaction)
* SUPERSEDED → ACTIVE is a defect; no code path should produce it

### Compliance Domain Rules

* At most one active (non-terminal) compliance workflow per student — duplicate intakes rejected
* Pre-action audit entry in `compliance_audit` schema must exist before IN_EXECUTION begins
* Post-action audit entry must be written after completion; failure to write is an incident, not a warning
* `compliance_audit` schema has no FK dependencies on other schemas
* Standard application service account cannot write to `compliance_audit` schema

### Cross-Schema Rules

* `warehouse` schema: standard application service account has SELECT-only access
* `compliance_audit` schema: standard application service account has SELECT-only access; writes via compliance pathway service account only
* Event attribution fields (`origin_source`, `origin_authority`, `correlation_id`) must be populated on all append-only log entries
* SQL Server authoritative events carry `origin_authority = sql_server_authoritative` and must not be overwritten by platform events

---

## 10. SCOPE-SPECIFIC BEHAVIOR

---

### MVP / SHADOW (current production state)

| Domain | Behavior in SHADOW |
|---|---|
| Outreach | `execution_mode = SHADOW`, `shadow_only = True`; no real outbound communication |
| Snapshots | Governance and finalization rules apply equally; `execution_mode = SHADOW` stamped on snapshot records |
| Reports | Generation and publication rules apply identically in SHADOW |
| AI insights | AI generation fully operational; experimental context not permitted for snapshot finalization |
| Config versions | Full governance model operational |
| Compliance | Not mode-gated; compliance workflows operate identically regardless of `execution_mode` |

### STANDARD (after GHL, Synthflow, LLM credentials filled)

* `execution_mode = LIVE`, `shadow_only = False`
* GHL writes enabled via `POST /ghl-sync/student`
* Real SMS, call, and email triggers active per channel flag
* All other domains: unchanged from SHADOW behavior

### PRODUCTION (warehouse schema + reporting live)

* `warehouse` schema migration deployed and operational
* Monthly snapshot generation job active
* Report generation and publication job active
* Config version registry seeded with V1
* Compliance pathway service account configured and restricted

---

## 11. ACCEPTANCE CRITERIA

---

### Case 1 — Insert Record

**Given** outreach triggered
**When** record inserted
**Then** all required fields present, `execution_mode` stamped

### Case 2 — Duplicate Prevention (Outreach)

**Given** same UserID + Checkpoint + Attempt
**When** insert attempted
**Then** rejected by unique constraint

### Case 3 — Sync Idempotency

**Given** `POST /sync/mssql` called twice in a row
**When** second call runs
**Then** no duplicate rows — existing rows updated in place

### Case 4 — SHADOW Enforcement

**Given** `EXECUTION_MODE = SHADOW`
**When** any action button clicked in lifecycle tabs
**Then** `student_quick_action_log` and `student_campaign_activity` rows inserted; no outbound HTTP to GHL/SMS/email

### Case 5 — Snapshot Finalization Immutability

**Given** a snapshot row in FINALIZED state
**When** application layer attempts UPDATE on any field
**Then** schema-level permission denied; write blocked; error surfaced as an unexpected system error (not a user-facing error)

### Case 6 — Reproducibility Under Replay

**Given** a FINALIZED snapshot row and a report template version
**When** report generation is triggered twice (original + regeneration with same source fingerprint)
**Then** output is identical; `source_snapshot_fingerprint` matches; no `POTENTIALLY_DIVERGENT` flag

### Case 7 — Config Version Atomic Swap

**Given** config version V1 is ACTIVE
**When** V2 is promoted to ACTIVE
**Then** V1 → SUPERSEDED and V2 → ACTIVE in a single atomic operation; at no point are zero or two versions ACTIVE

### Case 8 — Compliance Pre-Action Gate

**Given** a compliance workflow in APPROVED_FOR_ACTION state
**When** execution attempts transition to IN_EXECUTION
**Then** pre-action audit entry must exist in `compliance_audit` schema; if absent, transition is blocked

### Case 9 — AI Snapshot Isolation

**Given** a student snapshot is FINALIZED with AI narrative text embedded
**When** a force-refresh AI operation runs for the same student and insight type
**Then** the FINALIZED snapshot row is unchanged; the new AI version is a new record in `ai_insights`; the snapshot retains its physical copy

### Case 10 — Compliance Audit Survivability

**Given** a student's operational records are deleted via the compliance pathway
**When** the `compliance_audit` schema is queried
**Then** pre-action and post-action entries are present and unmodified; no FK cascade deleted them

### Case 11 — SQL Server Authority Preserved

**Given** an access history event with `origin_source = mirrored_sql_server` exists
**When** a platform access event arrives for the same `(user_id, event_type, attribution_timestamp)`
**Then** the SQL Server-authoritative record is not overwritten; both records are retained; conflict is logged with `correlation_id`

### Case 12 — Fingerprint Drift Prevention

**Given** a snapshot is in DRAFT and AI generation runs for the student
**When** the snapshot transitions to VALIDATING
**Then** fingerprint is computed at VALIDATING → FINALIZED using versions active at that moment; AI changes after VALIDATING do not affect the fingerprint

---

## 12. DOWNSTREAM IMPLICATIONS

---

The conceptual entities and governance rules in Sections 13–26 have direct downstream implications. This section maps each concept to its downstream artifact.

| Downstream artifact | Sections driving it | Status |
|---|---|---|
| `spec/07_api_contracts.md` | Snapshot CRUD, Report lifecycle, AI versioning, Config activation, Compliance workflow | Update after schema |
| `alembic/versions/0002_warehouse_schema.py` | Sections 13, 14, 20 | **Unblocked — write first** |
| `alembic/versions/0003_config_version_registry.py` | Section 18 | **Unblocked** |
| `alembic/versions/0004_compliance_schema.py` | Sections 13, 19 | **Unblocked** |
| `app/models.py` | AI versioning fields (Section 17) | After migration 0005 |
| `app/services/snapshot.py` (new) | Sections 14, 17, 18 | After warehouse migration |
| `app/services/compliance.py` (new) | Sections 19, 22 | After compliance migration |
| Observability instrumentation | Section 16 (events), Section 22 (invariants) | At service-layer implementation |

---

## 13. SCHEMA OWNERSHIP ARCHITECTURE

---

PostgreSQL schema separation enforces governance boundaries at the database layer.

### `public` — Operational Data

All current production tables live here. The standard application service account has full CRUD access.

Current contents:
* Student mirror: `student_trigger_data`
* Outreach state machine: `student_outreach_tracking`, `outreach_history`, `state_transition_log`
* Notes and insights: `student_notes`, `ai_insights`
* GHL cache: `ghl_messages`
* Action audit: `student_campaign_activity`, `student_quick_action_log`
* Idempotency store: `processed_events`

Upcoming additions:
* `config_version_registry` — config version governance (migration 0003)
* Snapshot lifecycle tracking tables (migration 0006)

### `warehouse` — Immutable Historical Archive

Append-only historical records. The standard application service account has **SELECT-only** access. Write access is granted only to the finalization service account.

Expected contents:
* `warehouse.student_snapshots` — one row per `(student_id, snapshot_month)` per finalization; all metrics, fingerprint, and inline AI text (FAD-1)
* `warehouse.monthly_reports` — one row per `(cohort_id, report_month, template_version, lineage_version)`
* `warehouse.report_audit_log` — append-only report lifecycle event log

No UPDATE or DELETE is permitted from any application-layer service account. Deletion is possible only via the compliance pathway with a restricted service account.

### `compliance_audit` — Governance-Isolated Audit Trail

Append-only compliance records written only by the compliance pathway service account. **No FK dependencies on other schemas.**

Expected contents:
* `compliance_audit.deletion_log` — pre-action and post-action entries for every deletion and anonymization

Properties:
* Records cannot be deleted by any application service account
* Survive even if the student's operational and warehouse records are removed
* Not subject to operational data retention policies
* Must be exportable for compliance auditor review

### Access Control Matrix

| Schema | Standard service account | Finalization service account | Compliance pathway account |
|---|---|---|---|
| `public` | READ + WRITE | READ only | READ only |
| `warehouse` | SELECT only | INSERT only (no UPDATE/DELETE) | SELECT only |
| `compliance_audit` | SELECT only | None | INSERT only (no UPDATE/DELETE) |

---

## 14. SNAPSHOT-CENTRIC HISTORICAL ARCHITECTURE

---

The monthly student snapshot is the primary unit of historical intelligence. All historical analytics, trend analysis, and reproducible reporting derive from snapshot data only (FAD-2). No live SQL Server queries for historical analytics.

### Core Conceptual Entities

#### StudentSnapshot

The authoritative monthly aggregate of a student's state.

* **Identity:** `(student_id, snapshot_month)` — uniquely identifies one snapshot per student per month
* **Lifecycle:** Domain 2 states — DRAFT → VALIDATING → FINALIZED (see `spec/03_state_transition_rules.md` Section 14)
* **Governance boundary:** FINALIZED — the row is immutable after this state
* **Content:**
  * All SQL Server metric values as of the `snapshot_month` cutoff (physical copy from mirror at sync time)
  * Derived metrics: `segment_classification`, `payment_risk_label`, `hw_risk_score` — computed at finalization
  * AI narrative text — physical copy as inline TEXT columns (FAD-1); not a reference to `ai_insights`
  * Reproducibility fingerprint — all 5 components (FAD-6)
  * Config version reference — locked at DRAFT → VALIDATING (FAD-3)
* **Mutability:** DRAFT is fully mutable; VALIDATING locks content for fingerprint computation; FINALIZED is immutable

#### SnapshotReproducibilityFingerprint

Embedded within `StudentSnapshot`. A 5-component identifier of the exact system state used to produce this snapshot (FAD-6).

| Component | What it captures |
|---|---|
| `schema_version` | PostgreSQL schema migration version active at finalization |
| `configuration_registry_version` | Config version active at DRAFT → VALIDATING |
| `ai_prompt_version` (per insight type) | Prompt template version used for each AI insight type |
| `ai_model_version` (per insight type) | LLM model version used for each AI insight type |
| `report_template_version` | Report template version active at snapshot time |

Unknown components (pre-tracking era) are recorded as `UNKNOWN_V0`.

#### FrozenAINarrativeCopy

AI-generated text embedded inline in the snapshot row. Not a separate entity — TEXT columns within `StudentSnapshot` (FAD-1).

* Copied at VALIDATING → FINALIZED from the current AI_REVIEWED version for each insight type
* No FK reference to `ai_insights` — the actual text is embedded in the row
* Future AI operations (refresh, model change, new generation) have **no effect** on any finalized snapshot
* Regeneration reads physical text from the snapshot row directly — never from `ai_insights`
* If AI_REVIEWED does not exist at finalization time: column is empty; fingerprint records `UNKNOWN_V0` for that insight type

#### SnapshotLineage

Tracks the parent-child relationship when a snapshot is regenerated.

* `lineage_version = 1` for the original; increments on each regeneration
* Regenerated records reference the parent via `parent_snapshot_id`
* `POTENTIALLY_DIVERGENT` flag set when the regeneration's source fingerprint differs from the original
* All lineage members are preserved; no deletion of prior lineage members

### Draft vs. Finalized Behavior

| Behavior | DRAFT | FINALIZED |
|---|---|---|
| SQL Server field re-sync | Allowed | Not allowed |
| AI narrative regeneration | Allowed (prior attempt abandoned) | Not allowed (text is physical copy) |
| Config version change | Possible if before VALIDATING | Not allowed (locked at VALIDATING) |
| Metric recomputation | Allowed | Not allowed |
| Write by standard service account | Allowed | Not allowed (warehouse SELECT-only) |
| Compliance deletion path | DISCARDED | COMPLIANCE_HOLD → COMPLIANCE_DELETED |

### Snapshot and Report Relationship

```
StudentSnapshot (FINALIZED, in warehouse.student_snapshots)
    ↓ source for
MonthlyReportArtifact (generated from snapshot data + report template)
    ↓ published as
REPORT_PUBLISHED record (warehouse.monthly_reports — append-only)
```

Historical regeneration path:

```
Regeneration request for (cohort_id, report_month)
    ↓ reads from
warehouse.student_snapshots (read-only; no live SQL Server queries — FAD-2)
    ↓ generates
new MonthlyReportArtifact (new lineage_version)
    ↓ publishes as
new REPORT_PUBLISHED record (original preserved; lineage_version incremented)
```

---

## 15. OPERATIONAL INTELLIGENCE DOMAIN MODEL

---

Operational intelligence derives from the SQL Server mirror and platform-owned augmentation. Historical intelligence derives from finalized snapshots. No direct SQL Server queries for historical analytics (FAD-2).

### Intelligence Sub-Domains

#### Coursework Engagement Intelligence

* **Source:** SQL Server — `HWsBehind`, `AvgEffRating`, `LastActivitySection`, `LastSubmitted`
* **Derived metrics:** `hw_risk_score` (CRITICAL/HIGH/MEDIUM/LOW), `days_since_last_submission`
* **Current state:** computed live from `student_trigger_data` by priority and segmentation services
* **Historical state:** preserved in `warehouse.student_snapshots` at `snapshot_month` boundary

#### Attendance and Progression Intelligence

* **Source:** SQL Server — `AttendancePercentage`, `IPBCStartDate`, `StudentStartDate`, `ClassStartDate`
* **Derived metrics:** `weeks_in_program`, `milestone_progression`
* **Note:** `AttendancePercentage` is a 0-to-1 fraction in SQL Server; normalized to 0–100 at sync
* **Historical state:** preserved in snapshots; SQL Server value locked at snapshot cutoff

#### Segment Classification Intelligence

* **Buckets:** NEWCOMERS (≤90 days), CAP_HOPEFULS (att > 50%), LAUNCH_HOPEFULS (att > 70% + CAP Project section), PLACEMENT_HOPEFULS (att > 70% + Launch section), HYPER_ACTIVE (logins ≥ 7 AND eff > 90)
* **Current state:** computed live from `student_trigger_data` by `app/services/segmentation.py`
* **Historical state:** `segment_classification_at_snapshot` preserved in `warehouse.student_snapshots`
* **Config dependency:** segment thresholds are governed by the active config version; historical snapshots retain the classification valid at their `snapshot_month`

#### Financial Intelligence

* **Source:** SQL Server — `Total_Payments`, `Total_Credits`, `PaymentBalance`, `ClassValue`, `FeePaid`, `ClassFeesPaid`
* **Derived:** `payment_risk_label` (HIGH/MEDIUM/CLEAR), `is_bundle_deal`, `actual_balance` (bundle-corrected)
* **Bundle detection:** `Total_Credits > 0` AND `PaymentBalance == 0` → `actual_balance = ClassValue − Total_Payments − Total_Credits`
* **Historical:** preserved in snapshots with both stored SQL Server values and derived values

#### Mentor Operational Visibility

* **Source:** platform-owned — `StudentNote`, `StudentCampaignActivity`, `StudentQuickActionLog`
* **Historical:** all entries are append-only; timeline events preserved indefinitely
* **Live view:** aggregated from operational tables; rendered in unified timeline

#### Communication Telemetry

* **Sources:** GHL API cache (`ghl_messages`) + `outreach_history` + `student_campaign_activity`
* **Historical:** `outreach_history` is append-only; GHL messages cached with idempotency on `ghl_message_id`
* **Attribution:** every record carries `source` (operator / ghl_sync / system) and `execution_mode`

#### Access History Intelligence

* **Source:** SQL Server authoritative — `LastActivityDays`, `LastLoginDays`, `Past10DaysLogon` (FAD-5)
* **Platform supplementary:** platform events stored as context only; do not replace SQL Server-derived values
* **Historical:** SQL Server values captured at sync time; snapshot preserves sync-time values

### Operational vs. Historical Responsibilities

| Intelligence type | Operational source | Historical source |
|---|---|---|
| Current student state | `student_trigger_data` (live mirror) | `warehouse.student_snapshots` |
| Current segment classification | `segmentation.py` (live from mirror) | `snapshot.segment_classification` |
| Current payment risk | `payment.py` (live from mirror) | `snapshot.payment_risk_label` |
| Access history | SQL Server via `student_trigger_data` | Snapshot's access fields |
| Trend analysis | Not supported from SQL Server directly (FAD-2) | `warehouse.student_snapshots` over time |
| Cohort performance | Aggregated at query time | `warehouse.student_snapshots` — only authorized historical source |

---

## 16. UNIFIED EVENT AND TIMELINE MODEL

---

All platform events normalize to a common timeline schema for rendering and audit trail construction.

### Conceptual Event Taxonomy

#### CommunicationEvent

Outbound or inbound communication involving a student.

* **Subtypes:** `OutreachAttempt` (system-generated), `OperatorLoggedActivity` (from `student_campaign_activity`), `GHLMessageCached` (from `ghl_messages`)
* **Key attribution:** `origin_source`, `channel` (SMS / EMAIL / CALL), `execution_mode`, `attribution_timestamp`

#### AccessHistoryEvent

Student access and engagement with the platform or learning content.

* **Authority:** SQL Server is primary; platform events are supplementary (FAD-5)
* **Deduplication:** `(user_id, event_type, attribution_timestamp)` — SQL Server origin wins on conflict
* **Conflict rule:** SQL Server-authoritative records must not be overwritten; both stored; conflict logged

#### AILifecycleEvent

AI insight generation milestones.

* **Subtypes:** `GenerationRequested`, `GenerationCompleted`, `ReviewApproved`, `RefreshRequested`, `SnapshotCopyMade`
* **Key attribution:** `ai_idempotency_key`, `insight_type`, `prompt_version_at_request`, `model_used_at_generation`, `version_number`

#### SnapshotLifecycleEvent

Snapshot state transitions (always append-only).

* **Subtypes:** `DraftCreated`, `FinalizationCompleted`, `RegenerationRequested`, `ComplianceHoldApplied`, `Discarded`
* Every event carries `correlation_id`, `snapshot_month`, `student_id`

#### ReportLifecycleEvent

Report generation and publication milestones.

* **Subtypes:** `GenerationJobCreated`, `GenerationCompleted`, `PublicationCommitted`, `RegenerationRequested`, `PotentiallyDivergentFlagged`
* **Key attribution:** `report_idempotency_key`, `source_snapshot_fingerprint_at_job_start`, `lineage_version`

#### ComplianceLifecycleEvent

Compliance workflow milestones. Stored in `compliance_audit` schema only.

* **Subtypes:** `RequestIntake`, `ReviewStarted`, `ApprovalGranted`, `PreActionAuditCreated`, `ExecutionStarted`, `ExecutionCompleted`, `PostActionAuditCreated`, `WorkflowRejected`
* **Key attribution:** `workflow_id`, `action_type`, `sequence_number`, `scope_manifest_version`

#### ConfigLifecycleEvent

Configuration version governance events.

* **Subtypes:** `VersionCreated`, `VersionApproved`, `VersionActivated`, `VersionSuperseded`, `VersionRejected`

### Event Attribution Standard

All events must carry:

| Field | Description |
|---|---|
| `correlation_id` | UUID v4 generated at request entry point; propagated through all downstream log entries and DB writes |
| `attribution_timestamp` | When the event occurred — not when it was synced or logged |
| `origin_source` | `mirrored_sql_server` / `operator` / `system` / `ghl_sync` / `compliance_pathway` |
| `origin_authority` | `sql_server_authoritative` / `platform_supplementary` / `platform_owned` |
| `execution_mode` | `SHADOW` / `LIVE` |

SQL Server mirrored events: `origin_source = mirrored_sql_server`, `origin_authority = sql_server_authoritative`. Must not be overwritten by platform events for the same `(user_id, event_type, attribution_timestamp)`.

### Unified Timeline Rendering

All event types normalized to a common display entry, sorted by `attribution_timestamp`:

* `event_type`, `attribution_timestamp`, `display_label`, `channel`
* `origin_source_label` (SQL Server Mirror / Operator / System / GHL Sync / Compliance)
* `execution_mode_badge` (SHADOW / LIVE)
* `is_authoritative` (bool — true for SQL Server-sourced events)
* `detail_json` (event-type-specific context)

---

## 17. AI INSIGHT AND REPRODUCIBILITY MODEL

---

AI-generated insights are versioned, attributed, and isolated from finalized snapshot content.

### Conceptual Entities

#### AIInsightRecord

The live AI generation result for a specific `(student_id, insight_type, date_period)`.

* **Identity:** `(student_id, insight_type, date_period, version_number)`
* **Lifecycle states:** Domain 4 (AI_PENDING → AI_GENERATING → AI_GENERATED → AI_REVIEW_PENDING → AI_REVIEWED)
* **Attribution fields (immutable after AI_GENERATED):** `prompt_version`, `model_used`, `generated_at`
* **Text field (immutable after AI_REVIEWED):** `content_text`
* **Force-refresh:** creates new `AIInsightRecord` with `version_number + 1`; prior transitions to `AI_REFRESH_REQUESTED` then archived

#### AIInsightVersionHistory

The collection of all `AIInsightRecords` for a `(student_id, insight_type, date_period)`.

* Serving state: current = most recent AI_REVIEWED version
* Archive state: all prior versions retained — never deleted
* Entire history is append-only; no in-place modification of any version
* Queryable for audit and historical explainability

#### FrozenSnapshotNarrative

AI text embedded in the snapshot row at finalization time (FAD-1).

* Physical embedding: actual text string stored as TEXT columns in the snapshot row
* No FK reference to `ai_insights`
* Isolation guarantee: immune to all future AI operations (refresh, model change, new generation)
* Source at finalization: the AI_REVIEWED text at the moment of VALIDATING → FINALIZED
* If AI_REVIEWED does not exist at finalization: column is empty; fingerprint records `UNKNOWN_V0`

#### SnapshotAIIsolationBoundary

The conceptual boundary separating live AI operations from finalized snapshot content.

* Finalization: copies AI_REVIEWED text into snapshot row — one-time, one-direction
* Post-finalization: `ai_insights` lifecycle operations have no effect on any snapshot row
* Regeneration reads: physically from snapshot row — never from `ai_insights` directly
* Locking: no locking relationship between `ai_insights` operations and snapshot reads during regeneration

### Active vs. Archived AI Versions

| State | Is served | Is modifiable | Notes |
|---|---|---|---|
| AI_REVIEWED (latest) | Yes (current) | No | Active version |
| AI_REVIEWED (prior versions) | No (archived) | No | Superseded by force-refresh |
| AI_GENERATION_FAILED | No | No | Terminal failure |
| AI_REJECTED | No (archived) | No | Reviewer-rejected |
| AI_PENDING / AI_GENERATING | No | In-flight only | Not yet complete |

### Reproducibility Semantics

* Same snapshot row + same report template → identical report output, always
* AI prompt changes affect future snapshots only; historical snapshots retain their physical text copy
* Historical regeneration produces same output regardless of current `ai_insights` state
* Attribution metadata in snapshot fingerprint records exactly which `prompt_version` and `model_version` were used per insight type
* When fingerprint components are `UNKNOWN_V0`: reproducibility is best-effort (pre-tracking era)

---

## 18. CONFIGURATION VERSION REGISTRY MODEL

---

The configuration version registry governs which classification thresholds and behavioral parameters are active for snapshot generation and student classification.

### Conceptual Entities

#### ConfigVersionRecord

A versioned, immutable set of classification thresholds and behavioral parameters.

* **Identity:** `(version_number, effective_from)`
* **Lifecycle:** Domain 5 states (DRAFT → UNDER_REVIEW → APPROVED → ACTIVE → SUPERSEDED)
* **Activation rule:** exactly one ACTIVE version at all times; atomic swap required
* **Rollback prohibition:** SUPERSEDED → ACTIVE is forbidden; a new version must be authored
* **Contents:** all threshold values from `spec/01_requirements.md` Section 12 — HWsBehind thresholds, attendance percentages, engagement thresholds, payment risk thresholds, segmentation boundaries, retry intervals, decay parameters

#### ConfigActivationLineage

Append-only log of all activation events.

* Records: `(version_number, activated_at, superseded_at, activated_by, correlation_id)`
* Enables historical query: "which config version was active at `snapshot_month` X?"
* Used to populate `configuration_registry_version` in the reproducibility fingerprint

#### SnapshotConfigVersionReference

The binding of a `StudentSnapshot` to the config version used for its classification.

* Captured at DRAFT → VALIDATING; immutable after capture
* Multiple snapshots in the same batch may reference different config versions if an activation occurred mid-batch — this is expected and correct (FAD-3)
* Historical analytics always use the locked reference — never the current active version

### Governance Invariants

* Zero-ACTIVE window: impossible — atomic swap ensures continuity
* Two-ACTIVE window: impossible — only one activation in flight at a time
* Historical reclassification: forbidden (FAD-3 — prospective-only enforcement)
* Config rollback: forbidden — SUPERSEDED → ACTIVE is a defect if it occurs in any code path

### Historical Auditability

Given any finalized snapshot, it is possible to reconstruct:

1. Which config version was active at classification time (from `SnapshotConfigVersionReference`)
2. What the exact threshold values were (from `ConfigVersionRecord` contents)
3. Why the student received a particular classification — reconstructable from data alone, no inference required

---

## 19. COMPLIANCE GOVERNANCE MODEL

---

Compliance workflows are governance operations on the platform's historical data. They are isolated from the standard operational data model.

### Conceptual Entities

#### ComplianceWorkflowRecord

A governance request for deletion or anonymization of a student's data.

* **Identity:** `(student_id, action_type, request_timestamp)`
* **Lifecycle:** Domain 6 states; at most one active (non-terminal) workflow per student
* **Terminal states:** COMPLETED_DELETED, COMPLETED_ANONYMIZED, REJECTED — all irreversible
* **action_type values:** GDPR_DELETION / FERPA_REMOVAL / ANONYMIZATION_REQUEST / INTERNAL_COMPLIANCE

#### ComplianceAuditEntry

Append-only record in `compliance_audit` schema. No FK dependencies on other schemas.

* **Identity:** `(student_id, action_type, workflow_id, sequence_number)`
* **Two required entries per execution:**
  * **Pre-action entry** — must exist before IN_EXECUTION begins (hard gate)
  * **Post-action entry** — must be written after completion; failure to write is an incident
* Survives even if operational data is deleted; not subject to operational data retention policies

#### ComplianceScopeManifest

The set of tables and record identifiers subject to the compliance action.

* Captured at APPROVED_FOR_ACTION; must be current at IN_EXECUTION
* Stale manifest requires update before execution can proceed
* Per-table completion status logged during IN_EXECUTION for partial failure recovery
* Persisted in `compliance_audit` schema for audit exportability

### Governance Isolation Principles

* Compliance actions are governance operations — not operational mutations via standard service accounts
* The compliance pathway is the only authorized path for deletion/anonymization of finalized snapshot records
* Standard application service accounts cannot write to `compliance_audit` schema
* DRAFT snapshots are disposable via the DISCARDED path; FINALIZED snapshots require the compliance pathway
* Compliance audit records are append-only forever — no retention policy applies to them

### Data Location and Deletion Path

| Data location | Compliance deletion path |
|---|---|
| `public` schema operational records | Direct deletion via compliance pathway service account |
| `warehouse.student_snapshots` | COMPLIANCE_HOLD → COMPLIANCE_DELETED via compliance pathway |
| `warehouse.monthly_reports` | Separate scope manifest entry; record flagged COMPLIANCE_AFFECTED |
| `compliance_audit` schema | Never deleted — append-only always |

### Historical Reproducibility After Deletion

* Student's snapshot data removed from `warehouse` schema
* Historical trend analysis produces gaps for that student's months — expected and acceptable
* Reports generated from the deleted snapshot data flagged as COMPLIANCE_AFFECTED
* `compliance_audit.deletion_log` records which data was removed, when, and by whom

---

## 20. REPORT ARTIFACT AND PUBLICATION MODEL

---

Monthly reports are generated from finalized snapshots and published as immutable artifacts. Historical regeneration is always read-only from the warehouse schema (FAD-2).

### Conceptual Entities

#### MonthlyReportArtifact

The generated report for a `(cohort_id, report_month)`.

* **Identity:** `(cohort_id, report_month, template_version, lineage_version)`
* **Lifecycle:** Domain 3 states — REPORT_PENDING → ... → REPORT_PUBLISHED
* **Publication boundary:** REPORT_APPROVED → REPORT_PUBLISHED is irreversible; no in-place modification
* **`lineage_version = 1`** for the original; incremented for each regeneration

#### ReportTemplateVersion

A versioned specification of the report's layout, sections, and metric definitions.

* Part of the reproducibility fingerprint (FAD-6)
* Changes create a new `template_version` — never a modification of existing
* Captured in the report idempotency key at job creation
* Historical regeneration with a different `template_version` flags POTENTIALLY_DIVERGENT

#### ReportLineage

The parent-child history of a `(cohort_id, report_month)` across regenerations.

* `lineage_version` increments on each regeneration
* Original publication preserved; regenerated report is a new record
* `POTENTIALLY_DIVERGENT` set when source snapshot fingerprint at regeneration differs from original publication fingerprint
* All lineage members preserved; no deletion permitted

#### ReportSourceBinding

The binding of a `MonthlyReportArtifact` to its source snapshots.

* `source_snapshot_fingerprint` captured at job creation (REPORT_PENDING time)
* Mismatch detection: if snapshot changes after job start → REPORT_GENERATION_FAILED
* Historical regeneration reads from `warehouse.student_snapshots` only (FAD-2 — no live SQL Server queries)

### Publication vs. Regeneration Semantics

| Operation | Record behavior | `lineage_version` | Original preserved? | `POTENTIALLY_DIVERGENT`? |
|---|---|---|---|---|
| First publication | Creates REPORT_PUBLISHED record | 1 | N/A | No |
| Regeneration (same source fingerprint) | Creates new REPORT_PUBLISHED record | N+1 | Yes | No |
| Regeneration (different source fingerprint) | Creates new REPORT_PUBLISHED record | N+1 | Yes | Yes — flagged |
| In-place update | **Not permitted** | — | — | — |

---

## 21. DATA OWNERSHIP AND SOURCE AUTHORITY

---

### SQL Server Authoritative Domains (READ-ONLY)

| Domain | Fields | Authority type |
|---|---|---|
| Student identity | `UserID`, `FirstName`, `LastName`, `Email`, `PhoneNumber` | Primary key authority |
| Enrollment state | `ActiveStatus`, `StatusI`, `StatusII`, `ClassSignupsID`, `ClassName` | Business state authority |
| Coursework engagement | `HWsBehind`, `AvgEffRating`, `LastActivitySection`, `LastSubmitted` | Metric authority |
| Attendance/progression | `AttendancePercentage`, `IPBCStartDate`, `StudentStartDate`, `ClassStartDate` | Progression authority |
| Financial record | `Total_Payments`, `Total_Credits`, `PaymentBalance`, `ClassValue`, `FeePaid`, `ClassFeesPaid` | Financial authority |
| Access history | `LastActivityDays`, `LastLoginDays`, `Past10DaysLogon` | Access authority (FAD-5) |
| Path enrollment | `PathName` | Classification input authority |

### PostgreSQL Authoritative Domains (PLATFORM-OWNED)

| Domain | Tables | Notes |
|---|---|---|
| Outreach state machine | `student_outreach_tracking`, `outreach_history`, `state_transition_log` | Platform-owned entirely |
| Student notes | `student_notes` | Operator-created |
| AI insight lineage | `ai_insights` | Platform-generated; versioned |
| GHL message cache | `ghl_messages` | Platform-owned copy; GHL API is real-time source |
| Campaign activity | `student_campaign_activity` | Platform audit |
| Quick action audit | `student_quick_action_log` | Platform audit |
| Idempotency store | `processed_events` | Platform infrastructure |
| Monthly snapshots | `warehouse.student_snapshots` | Immutable historical archive |
| Monthly reports | `warehouse.monthly_reports` | Immutable publication archive |
| Config version registry | `config_version_registry` | Governance record |
| Compliance audit | `compliance_audit.deletion_log` | Governance audit trail |

### Data Mutability Classification

| Data class | Mutability | Owner | Retention model |
|---|---|---|---|
| SQL Server source | SQL Server may update anytime; mirror updated on sync | SQL Server | SQL Server policies |
| `student_trigger_data` | Upserted on each sync | Platform (derivative) | Operational window |
| Outreach state | State machine transitions; no retroactive changes | Platform | Operational indefinitely |
| DRAFT snapshots | Fully mutable | Platform | Deleted on DISCARDED; promoted to warehouse on FINALIZED |
| FINALIZED snapshots | Immutable (warehouse schema) | Platform | Until compliance deletion |
| AI insights (current) | Version-append; no in-place mutation | Platform | Active/archived lifecycle |
| AI insights (archived) | Immutable | Platform | Retained indefinitely |
| REPORT_PUBLISHED records | Immutable | Platform | Until compliance action |
| Config version (ACTIVE/SUPERSEDED) | Immutable once ACTIVE | Platform | Retained indefinitely for audit |
| Compliance audit entries | Append-only; no deletion ever | Compliance pathway | Permanent |
| Event logs | Append-only | Platform | Retained indefinitely |

### Mirrored Data Expectations

* `student_trigger_data` is current as of the most recent `POST /sync/mssql` call
* FINALIZED snapshot rows capture SQL Server values **at the `snapshot_month` cutoff** — re-syncing does not update finalized snapshot content
* Platform-computed values (`segment_classification`, `payment_risk_label`, AI narrative) are platform-owned — SQL Server has no authority over them

---

## 22. CROSS-DOMAIN DATA INVARIANTS

---

Platform-wide invariants holding across all lifecycle domains. These are data consistency guarantees, not implementation constraints.

**DATA-INVARIANT-1: Append-only finalized reporting**
> No UPDATE or DELETE on finalized snapshots, published reports, or compliance audit entries from application service accounts. Enforced at application layer (lifecycle state machine) and database layer (warehouse schema SELECT-only for standard service account).

**DATA-INVARIANT-2: Reproducibility under replay**
> Given identical snapshot row data and report template version, report generation always produces identical output. Physical AI text copies (FAD-1), frozen config version references (FAD-3), and frozen fingerprint (FAD-6) together guarantee this.

**DATA-INVARIANT-3: AI snapshot isolation**
> Post-finalization AI operations (force-refresh, model upgrade, new generation) cannot modify any finalized snapshot row. The snapshot's AI text is a physical copy. Regeneration reads from snapshot rows — `ai_insights` operations have no effect on regeneration output.

**DATA-INVARIANT-4: Config version consistency at snapshot finalization**
> Each snapshot records the config version active at DRAFT → VALIDATING. Multiple snapshots in the same batch may legitimately reference different config versions if an activation occurred mid-batch. Historical analytics always use the locked reference — never the current active version.

**DATA-INVARIANT-5: Compliance audit survivability**
> `compliance_audit` schema has no FK dependencies on other schemas. Compliance audit records survive even if the student's operational and warehouse records are deleted. Pre-action audit entry existence is a hard gate for IN_EXECUTION.

**DATA-INVARIANT-6: SQL Server authority over access state**
> Platform events supplement but never replace SQL Server access metrics (FAD-5). On conflict: SQL Server value governs for analytics; both records are retained; conflict is logged; SQL Server-authoritative record is never overwritten.

**DATA-INVARIANT-7: Historical regeneration read-only source**
> Report regeneration reads from `warehouse.student_snapshots` only (FAD-2). No live SQL Server queries for historical analytics or report generation. In-flight regeneration continues even if the source snapshot enters COMPLIANCE_HOLD — both proceed in parallel.

**DATA-INVARIANT-8: Governance boundary irreversibility**
> The following transitions are irreversible by platform design: FINALIZED (snapshot), REPORT_PUBLISHED (report), ACTIVE → SUPERSEDED (config), terminal compliance states. No application-layer service account code path can revert these. The compliance pathway is the only authorized mechanism for modifying post-finalization records.

---

## 23. FUTURE-SCALE CONSIDERATIONS

---

Conceptual concerns for platform evolution. No infrastructure design.

### Large Historical Archives

* Snapshot and report archives grow indefinitely at O(students × months) and O(cohorts × months)
* Query patterns shift from operational (current state) to analytical (multi-month trends) as the archive grows
* Retention policy for DRAFT and DISCARDED states is an unresolved business question (U-9) — must be resolved before first production snapshot
* The warehouse schema's append-only design supports future partitioning without schema changes

### AI Provider Evolution

* Reproducibility fingerprint records `model_version` per insight type; historical records are auditable even after model changes
* Future LLM providers require the same attribution fields: `prompt_version`, `model_version`, `generated_at`, `model_response_metadata`
* Physical copy semantics (FAD-1) mean model changes affect only future snapshots; historical content is preserved as-is

### Report Template Evolution

* `template_version` in the fingerprint enables detection of format changes during historical regeneration (POTENTIALLY_DIVERGENT flag applies)
* Long-term template management suggests a template version registry (analogous to `config_version_registry`); a conceptual template registry is a forward-looking entity for the report domain

### Vector Search and RAG Integration

* AI narrative text stored in snapshot rows (FAD-1) makes snapshot rows the authoritative source for embedding generation
* `FrozenSnapshotNarrative` text is a strong candidate for embedding-based retrieval (RAG over student history)
* Embedding generation must derive from frozen snapshot content without mutating the snapshot row
* A conceptual `vector_embeddings` entity referencing `snapshot_id` and `embedding_model_version` is the appropriate design pattern

### Enterprise Compliance Requirements

* `compliance_audit` schema must be exportable for compliance auditors without granting full schema access
* Export format (NDJSON, signed PDF, structured CSV) is not yet specified
* FERPA, GDPR, and state-level data privacy regulations may impose specific requirements on retention and export formats
* Row-level security or audit-specific read-only credentials may be needed for auditor access

---

## 24. ACCEPTANCE CRITERIA (EXTENDED)

---

Extends the cases in Section 11 with cross-domain governance scenarios.

### Case 13 — Config Version Lineage Query

**Given** two consecutive versions V1 (SUPERSEDED) and V2 (ACTIVE)
**When** querying config activation lineage
**Then** V1.superseded_at equals V2.activated_at; no gap; no overlap; query "config active on date X" returns exactly one record

### Case 14 — Historical Segment Classification Auditability

**Given** a FINALIZED snapshot with `segment_classification = LAUNCH_HOPEFUL` at `snapshot_month = 2026-04`
**When** querying the snapshot's config version reference
**Then** the threshold values in that config version satisfy LAUNCH_HOPEFUL criteria for that student's metrics; explanation reconstructable from data alone — no inference required

### Case 15 — Compliance Audit Schema Independence

**Given** a student's `public` schema records are deleted via compliance pathway
**When** querying `compliance_audit.deletion_log`
**Then** pre-action and post-action entries are present and unmodified; no FK cascade was triggered; all required audit fields are populated; records are queryable independently of the deleted student's public schema rows

### Case 16 — Mirrored Source Attribution Conflict

**Given** two events for the same `(user_id, event_type, attribution_timestamp)` — one with `origin_source = mirrored_sql_server`, one with `origin_source = ghl_sync`
**When** both are processed
**Then** both records exist in the timeline; SQL Server event has `is_authoritative = true`; GHL sync event has `is_authoritative = false`; conflict logged with `correlation_id`; no record deleted

### Case 17 — Warehouse Schema Permission Enforcement

**Given** the standard application service account attempts an INSERT to `warehouse.student_snapshots`
**When** the insert is executed
**Then** the database rejects it with a permission error; no data is written; the application surfaces this as an unexpected system error

### Case 18 — Report Artifact Preservation Under Regeneration

**Given** a REPORT_PUBLISHED record with `lineage_version = 1` for `(cohort_id, report_month)`
**When** regeneration produces a new REPORT_PUBLISHED record with `lineage_version = 2`
**Then** the `lineage_version = 1` record is unchanged; `lineage_version = 2` record references it as parent; both are independently queryable

---

## 25. DOWNSTREAM IMPLICATIONS

---

### API Contracts (spec/07_api_contracts.md)

| New capability | Required API additions |
|---|---|
| Snapshot lifecycle | `POST /snapshots`, `GET /snapshots/{student_id}/{month}`, `PUT /snapshots/{id}/state` |
| Report publication | `POST /reports/generate`, `GET /reports/{cohort_id}/{month}`, `POST /reports/{id}/publish` |
| AI insight versioning | `GET /ai-insights/{user_id}/{type}?version=N`; version history endpoint |
| Config version activation | `POST /config-versions`, `POST /config-versions/{id}/activate`, `GET /config-versions/active` |
| Compliance workflow | `POST /compliance/request`, `GET /compliance/workflows/{student_id}`, `POST /compliance/workflows/{id}/approve` |
| Unified timeline events | Extend `GET /timeline/{user_id}` to include snapshot and report lifecycle events |
| Fingerprint query | `GET /snapshots/{id}/fingerprint` |

### Warehouse Schema (alembic/versions/0002_warehouse_schema.py)

| Conceptual entity | Physical implication |
|---|---|
| `warehouse` schema | `CREATE SCHEMA warehouse` required first |
| `warehouse.student_snapshots` | All snapshot lifecycle fields; all reproducibility fingerprint columns; all SQL Server metric columns as of `snapshot_month`; all derived metric columns; inline AI narrative TEXT columns (FAD-1) |
| `warehouse.monthly_reports` | All report lifecycle fields; `report_idempotency_key`; `source_snapshot_fingerprint`; `lineage_version`; `POTENTIALLY_DIVERGENT` flag |
| `warehouse.report_audit_log` | Append-only report lifecycle event log |
| Pre-migration note | Benchmark AI narrative text lengths before finalizing TEXT vs. separate linked table design (FAD-1 implementation implication noted in spec/04 Section 25) |

### Compliance Schema (alembic/versions/0004_compliance_schema.py)

| Conceptual entity | Physical implication |
|---|---|
| `compliance_audit` schema | `CREATE SCHEMA compliance_audit`; no FK dependencies on other schemas |
| `compliance_audit.deletion_log` | `workflow_id`, `student_id`, `action_type`, `sequence_number`, `entry_type` (PRE_ACTION / POST_ACTION), `scope_manifest_snapshot` (JSONB), `execution_details` (JSONB), `created_at` |

### Config Version Registry (alembic/versions/0003_config_version_registry.py)

| Conceptual entity | Physical implication |
|---|---|
| `public.config_version_registry` | `version_number`, `effective_from`, `status`, all threshold fields from `spec/01_requirements.md` Section 12, `activated_at`, `superseded_at`, `activated_by` |
| Seed record | V1 seeded with current Section 12 defaults at `status = ACTIVE` |

### Observability Requirements

| Concern | Instrumentation requirement |
|---|---|
| Snapshot finalization | Structured event on VALIDATING → FINALIZED; include all fingerprint components; `correlation_id` |
| Report generation | Start/end events with `source_snapshot_fingerprint`; `duration_ms`; POTENTIALLY_DIVERGENT flag |
| AI generation | Events with `prompt_version`, `model_version`, `duration_ms`, `outcome` |
| Config version activation | Activation event with both old and new version numbers; `correlation_id` |
| Compliance execution | Pre-action and post-action events; `scope_manifest_version`; `correlation_id` |

---

## 26. REFERENCES

---

### Governing Documents

* `spec/01_requirements.md` — Sections 12 (default thresholds), 13 (FAD-1 through FAD-6), 14 (dependency sequencing)
* `spec/03_state_transition_rules.md` — All lifecycle domains (Sections 1–45); all state enums and transition tables
* `spec/04_idempotency_concurrency.md` — All 6 domains; idempotency keys, concurrency invariants, acceptance criteria
* `spec/07_api_contracts.md` — API endpoints; request/response shapes
* `alembic/versions/0001_baseline.py` — Baseline migration (`public` schema, Phase 5 tables)
* `alembic/versions/0002_warehouse_schema.py` — Warehouse schema (pending authoring)
* `alembic/versions/0003_config_version_registry.py` — Config version registry (pending authoring)
* `alembic/versions/0004_compliance_schema.py` — Compliance audit schema (pending authoring)
* `app/models.py` — ORM model definitions (physical source of truth for `public` schema)

### Legacy References (still valid)

* `spec/02_system_specifications.md`
* `state/system_state_model.md`
* `data/data_lifecycle.md`
* `meta/project_classification.md`

---

## END OF FILE
