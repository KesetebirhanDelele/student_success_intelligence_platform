# spec/07_api_contracts.md

---

## LAYER 2 — SPECIFICATIONS (API CONTRACTS)

---

## 1. PURPOSE

This file defines:

* All external and internal API contracts for the Student Success Intelligence Platform (SSIP)
* Conceptual request/response shapes across all operational and governed historical domains
* API authorization boundaries and role visibility model
* Async operation semantics, idempotency patterns, and lineage-aware query conventions
* Acceptance criteria for immutable historical retrieval, reproducibility visibility, and governance isolation

This spec governs six API surface areas:

| Domain | API Group | Mutability |
|---|---|---|
| Operational student state | §8 Operational Endpoints | Mutable (CRUD + state machine) |
| Monthly snapshots | §9 Snapshot APIs | Append-only after FINALIZED |
| Monthly reports | §10 Report APIs | Append-only after REPORT_PUBLISHED |
| AI insights | §11 AI Insight APIs | Version-append; attribution immutable |
| Configuration versions | §12 Config Version APIs | Immutable once ACTIVE |
| Compliance governance | §13 Compliance APIs | Append-only audit; governance-gated execution |

Canonical inputs: `spec/01_requirements.md`, `spec/03_state_transition_rules.md`, `spec/04_idempotency_concurrency.md`, `spec/08_data_model.md`, `spec/09_warehouse_physical_architecture.md`, `alembic/versions/0002_warehouse_schema.py`, `alembic/versions/0003_config_version_registry.py`.

---

## 2. API ARCHITECTURE PHILOSOPHY

---

### 2.1 Deterministic Responses

* Same request MUST produce same response given same system state
* No hidden side effects
* Governed historical endpoints (snapshot, report, config version) return identical content regardless of when they are called — the record is immutable

---

### 2.2 Idempotency

* Safe retries MUST NOT create duplicate effects
* Every write operation that crosses a governance boundary (FINALIZED, REPORT_PUBLISHED, ACTIVE config) declares an idempotency key
* Duplicate governance-boundary requests return the existing result — they do not re-execute

---

### 2.3 Validation First

* All inputs MUST be validated before processing
* Invalid requests MUST fail fast with HTTP 422 (unprocessable entity) or 400 (bad request)
* Governance boundary violations return HTTP 409 (conflict)

---

### 2.4 Standard Response Envelope

All responses follow:

```json
{
  "status": "success | error",
  "data": {},
  "error": null,
  "meta": {
    "correlation_id": "uuid-v4",
    "timestamp": "ISO8601"
  }
}
```

`meta.correlation_id` propagates from the `X-Correlation-ID` request header if provided; generated server-side otherwise. All downstream log entries and database writes carry this ID.

---

### 2.5 Mutable vs. Immutable API Surfaces

| Surface | Mutability | Write operations |
|---|---|---|
| Operational endpoints (`/students`, `/outreach`, `/sync`, `/notes`, `/lifecycle`) | Mutable | POST, PUT, PATCH as documented |
| Draft snapshot endpoints (`POST /snapshots/draft`) | Mutable until VALIDATING | Lifecycle transitions: DRAFT → VALIDATING |
| Finalized snapshot endpoints (`GET /snapshots/{id}`) | Read-only from standard API | Compliance pathway only for deletion |
| Published report endpoints (`GET /reports/{id}`) | Read-only after REPORT_PUBLISHED | No in-place update; regeneration via POST |
| Active AI insights | Version-append; force-refresh creates new record | No in-place mutation of existing versions |
| Config version active | Read-only; activation via dedicated transition endpoint | No direct PUT/PATCH |
| Compliance workflow | Governance-gated lifecycle transitions only | No arbitrary PUT |

---

### 2.6 Operational vs. Historical Endpoints

| Endpoint class | Data source | Freshness | Query purpose |
|---|---|---|---|
| Operational | `student_trigger_data` (SQL Server mirror) | Current as of last sync | Current state queries |
| Historical | `warehouse.student_snapshots`, `warehouse.monthly_reports` | Immutable snapshots | Point-in-time analytics, trend analysis, audit |
| Lineage | Version chains across all governed domains | Immutable references | Audit, reproducibility, divergence detection |

Historical endpoints MUST NOT perform live SQL Server queries. All historical analytics derive from finalized snapshots only (FAD-2).

---

### 2.7 Lineage-Aware API Patterns

Lineage information is embedded in responses for append-only domains:

* `lineage.version` — the version number of this record (1 for originals)
* `lineage.parent_id` — ID of the predecessor record
* `lineage.is_latest` — whether this is the current version for the (cohort, month) tuple
* `lineage.child_ids` — IDs of records derived from this one

Dedicated `GET /{resource}/{id}/lineage` endpoints return the full chain for audit traversal.

---

### 2.8 Append-Only Historical Workflows

Mutation of governance-boundary records is not permitted. Change is expressed as new records:

| Domain | "Update" semantic | Result |
|---|---|---|
| Published report | Historical regeneration | New row; `lineage_version + 1`; original preserved |
| FINALIZED snapshot | None allowed | Compliance pathway only for deletion |
| AI insight | Force-refresh | New `AIInsightRecord` at `version_number + 1`; prior archived |
| Config version | New version proposal | New record; prior becomes SUPERSEDED after atomic activation |
| Compliance audit | None | Append-only forever |

---

### 2.9 Reproducibility Visibility

The Snapshot Reproducibility Fingerprint (FAD-6) is a first-class API concept. Every finalized snapshot response exposes:

* `fingerprint.schema_version` — Alembic revision active at finalization
* `fingerprint.configuration_registry_version` — config version ID locked at DRAFT→VALIDATING
* `fingerprint.ai_prompt_version` — prompt template version per insight type
* `fingerprint.ai_model_version` — LLM model version per insight type
* `fingerprint.report_template_version` — report template version

Fingerprint components recorded as `UNKNOWN_V0` (pre-tracking era) are surfaced as-is with a `has_unknown_components: true` flag.

---

### 2.10 SQL Server Read-Only Boundary

* The platform NEVER writes to SQL Server
* `POST /sync/mssql` copies from SQL Server → `student_trigger_data`; no write-back
* Historical analytics MUST NOT be served from live SQL Server queries — only from finalized snapshots (FAD-2)
* Access status fields (`LastActivityDays`, `LastLoginDays`) carry `origin_authority: sql_server_authoritative` in timeline events; platform events carry `platform_supplementary`

---

## 3. ERROR HANDLING

---

### Error Response Format

```json
{
  "status": "error",
  "data": null,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable description",
    "context": {}
  },
  "meta": {
    "correlation_id": "uuid-v4",
    "timestamp": "ISO8601"
  }
}
```

---

### HTTP Status Codes

| Code | When used |
|---|---|
| 200 | Success (GET, sync operations) |
| 201 | Resource created (POST that creates a new record) |
| 202 | Accepted (async job initiated; poll for completion) |
| 400 | Malformed request (validation failure on input shape) |
| 401 | Unauthenticated |
| 403 | Unauthorized (authenticated but insufficient role) |
| 404 | Resource not found |
| 409 | Conflict (governance boundary violation, duplicate idempotency key, invalid state transition) |
| 422 | Unprocessable entity (schema-valid request but business-rule violation) |
| 500 | Unexpected internal error |

---

### Error Codes

| Code | Description |
|---|---|
| `INVALID_INPUT` | Input validation failed |
| `NOT_FOUND` | Resource not found |
| `DUPLICATE_REQUEST` | Duplicate idempotency key with divergent payload |
| `INTERNAL_ERROR` | Unexpected error |
| `STATE_VIOLATION` | Invalid state transition attempted |
| `MAX_ATTEMPTS_REACHED` | FORCE_RETRY blocked by attempt ceiling |
| `INVALID_ACTION` | Unknown action_type in manual action |
| `GOVERNANCE_BOUNDARY` | Mutation attempted on a record past its governance boundary |
| `IDEMPOTENCY_CONFLICT` | Same idempotency key reused with different payload |
| `FINALIZED_IMMUTABLE` | Write to a FINALIZED snapshot rejected |
| `PUBLISHED_IMMUTABLE` | Write to a REPORT_PUBLISHED record rejected |
| `CONFIG_ROLLBACK_FORBIDDEN` | Attempt to activate a SUPERSEDED config version |
| `COMPLIANCE_GATE_NOT_MET` | Compliance workflow precondition unsatisfied |
| `NO_ACTIVE_SNAPSHOT` | Historical report requested but no FINALIZED snapshot for (student, month) |
| `FINGERPRINT_MISMATCH` | Source snapshot fingerprint changed since report job started |
| `AUDIT_ENTRY_MISSING` | Compliance execution attempted without pre-action audit entry |

---

## 4. IDEMPOTENCY RULES

---

### Idempotency-Key Header

For all POST operations that create or mutate governed records:

```
Idempotency-Key: <client-generated-uuid>
```

Behavior:
- First call: executes the operation; stores key + outcome
- Subsequent calls with same key: returns stored outcome without re-executing
- Same key with different payload: returns HTTP 409 `IDEMPOTENCY_CONFLICT`

---

### Domain-Specific Keys

| Domain | Idempotency key |
|---|---|
| Outreach trigger | `(user_id, checkpoint_type, contact_attempt)` |
| Snapshot finalization | `(student_id, snapshot_month)` — only one FINALIZED per pair |
| Report publication | `(cohort_id, report_month, template_version, lineage_version)` |
| AI insight generation | `(user_id, insight_type, date_period, version_number)` |
| Config version activation | `(version_id)` — activation is single-use |
| Compliance execution | `(workflow_id, action_type)` |

---

## 5. AUTHENTICATION AND AUTHORIZATION

---

### 5.1 Authentication Tiers

| Scope | Mechanism |
|---|---|
| MVP | Basic token |
| STANDARD | API key (`Authorization: Bearer <api-key>`) |
| PRODUCTION | JWT with role claims; OAuth2 for service accounts |

---

### 5.2 Role-Based Visibility Model

| Role | Operational | Historical snapshots | Reports | AI insights | Config versions | Compliance |
|---|---|---|---|---|---|---|
| **mentor** | Own students (READ) | Own students, FINALIZED | Own cohort, REPORT_PUBLISHED | Own students, AI_REVIEWED | Active (READ) | None |
| **super_mentor** | All students (READ) | All students, FINALIZED | All cohorts, REPORT_PUBLISHED | All students, AI_REVIEWED | Active (READ) | None |
| **instructor** | All students (READ) | All students, FINALIZED | All cohorts, REPORT_PUBLISHED | All students, AI_REVIEWED | Active (READ) | None |
| **operator** | All students (READ+WRITE) | All, FINALIZED | All, any published state | All AI states | All versions (READ) | View workflows |
| **compliance_reviewer** | READ only | All, including COMPLIANCE_HOLD | All published | READ only | Active (READ) | Full workflow + audit export |
| **config_admin** | READ only | READ only | READ only | READ only | Full lifecycle (READ+WRITE) | None |
| **admin** | Full | Full | Full | Full | Full | Full |

**Super-mentor transitive visibility:** A super mentor can view all students, not just those explicitly assigned. Student-assignment filtering logic MUST NOT be applied to the super_mentor role.

---

### 5.3 Governance Boundary Authorization

Write operations past governance boundaries require elevated authorization:

| Operation | Required role |
|---|---|
| Finalize snapshot (`VALIDATING → FINALIZED`) | `finalization_service` account only |
| Publish report | `operator` or `admin` |
| Activate config version | `config_admin` |
| Initiate compliance action | `compliance_reviewer` |
| Execute compliance action (`BEGIN_EXECUTION`) | `compliance_reviewer` + pre-action audit entry |

Standard operator API keys cannot perform these operations. Attempts return HTTP 403.

---

## 6. ASYNC OPERATION MODEL

---

### 6.1 Async Job Pattern

Operations that may exceed 5 seconds (snapshot finalization, report generation, AI generation, batch sync) return HTTP 202:

```json
{
  "status": "success",
  "data": {
    "job_id": "uuid",
    "status": "PENDING",
    "status_endpoint": "/jobs/{job_id}",
    "correlation_id": "uuid"
  }
}
```

---

### 6.2 Job Status Endpoint

```
GET /jobs/{job_id}
```

```json
{
  "status": "success",
  "data": {
    "job_id": "uuid",
    "job_type": "snapshot_finalization | report_generation | ai_generation | ghl_batch_sync",
    "status": "PENDING | IN_PROGRESS | COMPLETED | FAILED",
    "created_at": "ISO8601",
    "completed_at": "ISO8601 | null",
    "result": {},
    "error": null,
    "correlation_id": "uuid"
  }
}
```

---

### 6.3 Polling Expectations

* Minimum poll interval: 2 seconds; recommended: 5 seconds
* Maximum polling window: 90 seconds (exceeds the 60-second report generation SLA)
* After timeout: treat as `FAILED`; retry by issuing a new operation with the same idempotency key
* On `FAILED`: job object includes error context; idempotency key is released for retry

---

### 6.4 Failure Visibility

```json
{
  "status": "FAILED",
  "error": {
    "code": "ERROR_CODE",
    "message": "human-readable",
    "domain_state": "GENERATION_FAILED | REPORT_GENERATION_FAILED | AI_GENERATION_FAILED",
    "retryable": true
  }
}
```

AI generation failures that have a prior `AI_REVIEWED` version also expose `stale_insight_available: true` so callers can serve the stale version with `stale: true` badge.

---

## 7. FILTERING AND QUERY SEMANTICS

---

### 7.1 Standard Query Parameters

| Parameter | Type | Description |
|---|---|---|
| `page` | integer | Page number (1-based) |
| `limit` | integer | Page size (endpoint-specific default; max 500) |
| `sort` | string | Sort field |
| `order` | `asc \| desc` | Sort direction (default `desc`) |

---

### 7.2 Time-Window Filtering

| Parameter | Format | Description |
|---|---|---|
| `from_date` | `YYYY-MM-DD` | Inclusive start date |
| `to_date` | `YYYY-MM-DD` | Inclusive end date |
| `snapshot_month` | `YYYY-MM` | Target snapshot month |
| `report_month` | `YYYY-MM` | Target report month |

Historical endpoints require at least one time scope. Unbounded historical queries are rejected with HTTP 400.

---

### 7.3 Config Version Filtering

| Parameter | Description |
|---|---|
| `config_version` | Filter snapshots/reports by config version number |
| `config_version_status` | Filter config list: `ACTIVE`, `SUPERSEDED`, `ARCHIVED`, `PROPOSED`, `UNDER_REVIEW`, `APPROVED` |

---

### 7.4 Fingerprint Filtering

| Parameter | Description |
|---|---|
| `schema_version` | Filter by Alembic schema version at finalization |
| `ai_model_version` | Filter by LLM model version |
| `ai_prompt_version` | Filter by prompt template version |
| `report_template_version` | Filter by report template version |

---

### 7.5 Timeline Event Filtering

| Parameter | Description |
|---|---|
| `event_type` | `outreach \| note \| ghl_message \| state_transition \| ai_event \| snapshot_event \| report_event \| access_event` |
| `origin_source` | `mirrored_sql_server \| operator \| ghl \| ai_subsystem \| compliance_pathway \| scheduler` |
| `origin_authority` | `sql_server_authoritative \| platform_supplementary \| operator_authorized` |
| `execution_mode` | `SHADOW \| LIVE` |
| `is_authoritative` | `true \| false` |

---

## 8. OPERATIONAL ENDPOINTS (PRESERVED)

---

> All endpoints in this section are preserved from the prior version of this spec. Request/response shapes are unchanged. The standard envelope (`meta.correlation_id`, `meta.timestamp`) now applies to all responses.

---

### 8.1 Health Check

```
GET /health
```

```json
{
  "status": "success",
  "data": {
    "service": "running",
    "scheduler_status": "active",
    "timestamp": "ISO8601"
  }
}
```

---

### 8.2 Outreach Trigger

```
POST /outreach/trigger
```

Request: `{ "checkpoint_type": "SQL | SSRS | SSIS | POST_COMPLETION" }`

Validation: `checkpoint_type` must be valid enum. Duplicate trigger blocked via `processed_events`.

Response: `{ "status": "success", "data": { "triggered": true } }`

---

### 8.3 Student Details

```
GET /students/{user_id}
```

Response includes: `user_id`, `state`, `checkpoint_type`, `current_attempt`, `last_contact_at`, `next_retry_at`, `profile`, `history`, `transitions`.

`profile.risk_level` derived server-side: HIGH if `hws_behind ≥ 3` OR `avg_eff_rating < 2.5` OR `last_activity_days > 7`; MEDIUM if `hws_behind ≥ 2` OR `avg_eff_rating < 3.0` OR `last_activity_days ≥ 5`; else LOW.

---

### 8.4 Metrics

```
GET /metrics
```

Returns: `total_outreach`, `success_rate`, `meeting_rate`, `sentiment_distribution`.

---

### 8.5 Manual Action

```
POST /actions/manual
```

Request:
```json
{
  "user_id": 123,
  "action_type": "CLOSE_CASE | FORCE_RETRY | BOOK_MEETING | ESCALATE",
  "notes": "optional"
}
```

| action_type | Transitions to | Guard |
|---|---|---|
| `CLOSE_CASE` | CLOSED | Blocked if already CLOSED |
| `FORCE_RETRY` | RETRY | Blocked if `current_attempt ≥ MAX_ATTEMPTS` |
| `BOOK_MEETING` | RESOLVED | Must be valid state machine transition |
| `ESCALATE` | INTERVENTION_REQUIRED | Only from CONTACTED, NO_RESPONSE, RETRY, RESPONDED |

---

### 8.6 Dashboard Endpoints

```
GET /dashboard/health
GET /dashboard/alerts
GET /dashboard/summary
GET /dashboard/channel-performance
GET /dashboard/recent-activity?limit=N
```

Shapes and alert trigger conditions unchanged from prior version.

---

### 8.7 Sync Endpoints

```
POST /sync/mssql
GET /sync/status
```

`POST /sync/mssql` is idempotent — safe to call repeatedly. Copies `AI_ChatBot_TriggerData` from SQL Server (READ-ONLY) into `student_trigger_data`. Never writes to SQL Server.

Response: `{ "scanned": N, "added": N, "updated": N, "failed": N, "partial": false }`

---

### 8.8 Lifecycle Tab Endpoints

```
GET /lifecycle/newcomers
GET /lifecycle/engagement
GET /lifecycle/hw-risk
GET /lifecycle/cap-hopefuls
GET /lifecycle/launch-hopefuls
GET /lifecycle/placement-hopefuls
```

Returns `tab`, `total`, `rows[]`. Each row includes all `student_trigger_data` columns plus derived fields. Default limit 2000, max 5000.

Cohort identification thresholds (`cap_hopeful_min_percomp`, `launch_hopeful_min_percomp`, section patterns) are resolved from the active config version at query time, not hardcoded.

---

### 8.9 Quick Actions and Campaign Activity

```
POST /quick-actions/log
GET /campaign-activity/{user_id}
GET /quick-actions/{user_id}
```

SHADOW enforcement: no outbound HTTP to GHL/SMS/email when `execution_mode = SHADOW`. Log records are the only side effect.

---

### 8.10 GHL Sync Endpoints

```
POST /ghl-sync/student
POST /ghl-sync/batch?limit=N
GET /ghl-sync/status
```

`ghl_messages` is a local read cache. No writes back to GHL.

---

### 8.11 Timeline Endpoint (Operational)

```
GET /timeline/{user_id}
```

Merges `outreach_history`, `state_transition_log`, `student_notes`, `ai_insights`, `ghl_messages`. Ordered newest first.

Each event includes: `event_type`, `attribution_timestamp`, `origin_source`, `execution_mode`, `correlation_id`.

The extended timeline including snapshot and report lifecycle events is defined in §14.1.

---

### 8.12 Notes Endpoints

```
POST /notes
GET /notes/{user_id}
```

---

### 8.13 AI Insights (Operational — Current Active)

```
POST /ai-insights/generate
GET /ai-insights/{user_id}
```

Returns the current `AI_REVIEWED` insight. Extended versioning, history, and force-refresh endpoints are in §11.

---

### 8.14 Segment Endpoints

```
GET /segments/summary
GET /segments/{segment_name}
```

Segment names: `cap_hopefuls`, `launch_hopefuls`, `placement_hopefuls`, `new_students`, `at_risk`, `engaged`.

---

### 8.15 GHL Webhook

```
POST /webhook/ghl-update
```

Receives call status, SMS responses, and contact updates from GHL. Idempotent: duplicate events deduplicated via unique constraint on `(conversation_id, sent_at, direction)` in `ghl_messages`.

---

## 9. SNAPSHOT APIs

---

Snapshots are append-only historical artifacts. No API endpoint modifies a FINALIZED snapshot. The only mutation path post-FINALIZED is the Compliance Governance Pathway (§13).

---

### 9.1 Draft Snapshot Creation

```
POST /snapshots/draft
```

Initiates async snapshot draft assembly. Returns HTTP 202.

Request:
```json
{
  "student_id": 12345,
  "snapshot_month": "YYYY-MM",
  "idempotency_key": "client-uuid"
}
```

Response (202):
```json
{
  "status": "success",
  "data": {
    "job_id": "uuid",
    "status": "PENDING",
    "status_endpoint": "/jobs/{job_id}",
    "snapshot_id": null
  }
}
```

On job completion, `result.snapshot_id` is populated. The draft begins in `DRAFT` state.

Idempotency: a second call for `(student_id, snapshot_month)` with no FINALIZED snapshot returns the existing draft's job reference.

---

### 9.2 Snapshot Lifecycle Transition

```
POST /snapshots/{snapshot_id}/lifecycle
```

Request:
```json
{
  "transition": "DRAFT_TO_VALIDATING | VALIDATING_TO_DRAFT | DISCARD",
  "actor_identity": "operator_id_or_service",
  "notes": "optional"
}
```

Allowed transitions from this endpoint:
- `DRAFT → VALIDATING` — locks content; initiates fingerprint computation
- `VALIDATING → DRAFT` — validation failure; operator reviews; retry allowed
- `DRAFT → DISCARDED` — operator discard before finalization

**Finalization (`VALIDATING → FINALIZED`) is exclusively performed by the finalization service account and is NOT accessible via standard API.** Attempts return HTTP 403.

Compliance transitions (`FINALIZED → COMPLIANCE_HOLD`) are exclusively via §13.

Response (200):
```json
{
  "status": "success",
  "data": {
    "snapshot_id": "uuid",
    "from_state": "DRAFT",
    "to_state": "VALIDATING",
    "attribution_timestamp": "ISO8601",
    "correlation_id": "uuid"
  }
}
```

---

### 9.3 Finalized Snapshot Retrieval

```
GET /snapshots/{student_id}/{year_month}
```

Returns the FINALIZED snapshot for a student-month pair. HTTP 404 if none exists.

Response:
```json
{
  "status": "success",
  "data": {
    "snapshot_id": "uuid",
    "student_id": 12345,
    "snapshot_month": "YYYY-MM",
    "status": "FINALIZED",
    "finalized_at": "ISO8601",
    "lineage_version": 1,
    "parent_snapshot_id": null,
    "fingerprint": {
      "schema_version": "0003",
      "configuration_registry_version": "1",
      "ai_prompt_version": { "risk_summary": "v2", "progress_summary": "v1" },
      "ai_model_version": { "risk_summary": "claude-sonnet-4-6", "progress_summary": "claude-sonnet-4-6" },
      "report_template_version": "v1",
      "has_unknown_components": false
    },
    "metrics": {
      "hws_behind": 2,
      "avg_eff_rating": 3.1,
      "attendance_percentage": 72.4,
      "payment_balance": 450.00,
      "segment_classification": "LAUNCH_HOPEFUL",
      "payment_risk_label": "MEDIUM",
      "hw_risk_score": "AT_RISK"
    },
    "ai_narratives": {
      "risk_summary": "frozen text | null if not generated at finalization",
      "progress_summary": "frozen text | null",
      "monthly_narrative": "frozen text | null"
    },
    "config_version_ref": {
      "version_id": 1,
      "version_number": 1,
      "effective_from": "ISO8601"
    }
  }
}
```

`ai_narratives` are physical text copies frozen at FINALIZED. They are not references to `ai_insights` records. Subsequent AI operations do not change them.

---

### 9.4 Historical Snapshot Lookup

```
GET /snapshots/{student_id}?from_date=YYYY-MM-DD&to_date=YYYY-MM-DD&limit=12
```

Paginated list of FINALIZED snapshots across months. Default limit 12, max 60. Include `status=all` query param (operator role required) to include non-FINALIZED states.

Response:
```json
{
  "status": "success",
  "data": {
    "student_id": 12345,
    "total": 6,
    "items": [
      {
        "snapshot_id": "uuid",
        "snapshot_month": "YYYY-MM",
        "status": "FINALIZED",
        "lineage_version": 1,
        "fingerprint_summary": {
          "schema_version": "0003",
          "configuration_registry_version": "1"
        }
      }
    ]
  }
}
```

---

### 9.5 Fingerprint Inspection

```
GET /snapshots/{snapshot_id}/fingerprint
```

Returns the complete Reproducibility Fingerprint for a finalized snapshot, including the full config version threshold set.

Response:
```json
{
  "status": "success",
  "data": {
    "snapshot_id": "uuid",
    "snapshot_month": "YYYY-MM",
    "student_id": 12345,
    "fingerprint": {
      "schema_version": "0003",
      "configuration_registry_version": "1",
      "ai_prompt_version": { "risk_summary": "v2" },
      "ai_model_version": { "risk_summary": "claude-sonnet-4-6" },
      "report_template_version": "v1",
      "has_unknown_components": false
    },
    "config_version_detail": {
      "version_id": 1,
      "version_number": 1,
      "status": "SUPERSEDED",
      "cap_hopeful_min_percomp": 0.30,
      "launch_hopeful_min_percomp": 0.59,
      "rule_set_snapshot_json": {}
    }
  }
}
```

`config_version_detail` is fully populated even when the referenced version is SUPERSEDED or ARCHIVED. Historical auditability requires this always to resolve.

---

### 9.6 Snapshot Lineage Traversal

```
GET /snapshots/{snapshot_id}/lineage
```

Returns the lineage chain (original + all regenerations) for this snapshot's `(student_id, snapshot_month)`.

Response:
```json
{
  "status": "success",
  "data": {
    "snapshot_id": "uuid",
    "student_id": 12345,
    "snapshot_month": "YYYY-MM",
    "lineage": [
      {
        "snapshot_id": "uuid-v1",
        "lineage_version": 1,
        "status": "FINALIZED",
        "finalized_at": "ISO8601",
        "is_latest": false,
        "potentially_divergent": false
      },
      {
        "snapshot_id": "uuid-v2",
        "lineage_version": 2,
        "status": "FINALIZED",
        "finalized_at": "ISO8601",
        "is_latest": true,
        "potentially_divergent": true
      }
    ]
  }
}
```

---

### 9.7 Historical Snapshot Comparison

```
GET /snapshots/compare?snapshot_a={id}&snapshot_b={id}
```

Side-by-side metric comparison for two finalized snapshots. Both must be FINALIZED.

Response:
```json
{
  "status": "success",
  "data": {
    "snapshot_a": { "snapshot_id": "uuid", "snapshot_month": "YYYY-MM", "metrics": {} },
    "snapshot_b": { "snapshot_id": "uuid", "snapshot_month": "YYYY-MM", "metrics": {} },
    "diff": {
      "hws_behind": { "a": 2, "b": 5 },
      "avg_eff_rating": { "a": 3.1, "b": 2.4 },
      "segment_classification": { "a": "LAUNCH_HOPEFUL", "b": "AT_RISK" }
    },
    "fingerprint_comparison": {
      "same_config_version": true,
      "same_ai_prompt": false,
      "same_schema": true
    }
  }
}
```

---

## 10. MONTHLY REPORT APIs

---

Reports are generated exclusively from finalized snapshot data. Published reports are immutable. Historical regeneration creates new lineage; the original published record is never modified.

---

### 10.1 Report Generation Request

```
POST /reports/generate
```

Initiates async generation of a monthly cohort report. Returns HTTP 202.

Request:
```json
{
  "cohort_id": "cohort-identifier",
  "report_month": "YYYY-MM",
  "template_version": "v1",
  "idempotency_key": "client-uuid"
}
```

Preconditions checked before accepting:
- At least one FINALIZED snapshot exists for `(cohort_id, report_month)` in the warehouse
- No duplicate REPORT_PUBLISHED record for same `(cohort_id, report_month, template_version, lineage_version)` intent

If no FINALIZED snapshot exists: HTTP 422 `NO_ACTIVE_SNAPSHOT`.

Response (202):
```json
{
  "status": "success",
  "data": {
    "job_id": "uuid",
    "status": "PENDING",
    "status_endpoint": "/jobs/{job_id}",
    "report_id": null
  }
}
```

---

### 10.2 Published Report Retrieval

```
GET /reports/{cohort_id}/{year_month}
```

Returns the current REPORT_PUBLISHED record (highest `lineage_version`) for a cohort-month pair.

Response:
```json
{
  "status": "success",
  "data": {
    "report_id": "uuid",
    "cohort_id": "cohort-identifier",
    "report_month": "YYYY-MM",
    "status": "REPORT_PUBLISHED",
    "published_at": "ISO8601",
    "published_by": "operator_id",
    "template_version": "v1",
    "lineage_version": 1,
    "parent_report_id": null,
    "is_latest": true,
    "potentially_divergent": false,
    "compliance_affected": false,
    "source_snapshot_fingerprint": {},
    "content": {
      "executive_summary": "text",
      "cohort_highlights": [],
      "intervention_summary": [],
      "student_count": 45,
      "at_risk_count": 8
    }
  }
}
```

`compliance_affected: true` if a compliance action was executed against a contributing student after publication. Aggregate statistics are NOT retroactively adjusted; the report is annotated only.

---

### 10.3 Report Version Lookup

```
GET /reports/{report_id}
```

Returns a specific report record by ID. Returns any lifecycle state (REPORT_PENDING through REPORT_ARCHIVED).

---

### 10.4 Report Publication History

```
GET /reports/{cohort_id}/{year_month}/history
```

All lineage members ordered by `lineage_version` ascending.

Response:
```json
{
  "status": "success",
  "data": {
    "cohort_id": "cohort-identifier",
    "report_month": "YYYY-MM",
    "total_versions": 2,
    "lineage": [
      {
        "report_id": "uuid",
        "lineage_version": 1,
        "status": "REPORT_PUBLISHED",
        "published_at": "ISO8601",
        "template_version": "v1",
        "potentially_divergent": false,
        "is_latest": false
      },
      {
        "report_id": "uuid",
        "lineage_version": 2,
        "status": "REPORT_PUBLISHED",
        "published_at": "ISO8601",
        "template_version": "v1",
        "potentially_divergent": true,
        "is_latest": true,
        "divergence_notes": "Source snapshot config version differs from original publication"
      }
    ]
  }
}
```

---

### 10.5 Report Publication

```
POST /reports/{report_id}/publish
```

Transitions a `REPORT_APPROVED` report to `REPORT_PUBLISHED`. Requires `operator` or `admin` role.

Request:
```json
{
  "published_by": "operator_id",
  "idempotency_key": "client-uuid"
}
```

Response (200):
```json
{
  "status": "success",
  "data": {
    "report_id": "uuid",
    "status": "REPORT_PUBLISHED",
    "published_at": "ISO8601",
    "lineage_version": 1
  }
}
```

---

### 10.6 Historical Report Regeneration

```
POST /reports/{report_id}/regenerate
```

Creates a NEW report version derived from the same snapshot data. The source `REPORT_PUBLISHED` record is not modified.

Request:
```json
{
  "reason": "Template version update",
  "template_version": "v1",
  "requested_by": "operator_id",
  "idempotency_key": "client-uuid"
}
```

Response (202):
```json
{
  "status": "success",
  "data": {
    "job_id": "uuid",
    "parent_report_id": "uuid",
    "new_report_id": null,
    "status": "PENDING",
    "status_endpoint": "/jobs/{job_id}"
  }
}
```

On completion: `result.new_report_id` populated; `result.potentially_divergent` indicates fingerprint divergence from original.

AI narrative content in the regenerated report is reproduced from the physical text copies in the snapshot row — no new LLM call is made (INVARIANT-2).

---

### 10.7 Report Source Fingerprint

```
GET /reports/{report_id}/fingerprint
```

Returns the source snapshot fingerprint captured at report job creation and the template version used.

Response:
```json
{
  "status": "success",
  "data": {
    "report_id": "uuid",
    "source_snapshot_fingerprint": {
      "schema_version": "0003",
      "configuration_registry_version": "1",
      "ai_prompt_version": {},
      "ai_model_version": {},
      "report_template_version": "v1"
    },
    "template_version_at_generation": "v1",
    "potentially_divergent": false,
    "divergence_explanation": null
  }
}
```

---

## 11. AI INSIGHT APIs

---

AI insights are versioned, attributed, and isolated from finalized snapshot content. Force-refresh creates new records; prior versions are archived, never deleted. Attribution metadata is immutable after `AI_GENERATED` state.

---

### 11.1 Active AI Insight Retrieval

```
GET /ai-insights/{user_id}/{insight_type}
```

Returns the current `AI_REVIEWED` insight. If generation failed and a prior `AI_REVIEWED` version exists, returns it with `stale: true`.

Insight types: `risk_summary`, `progress_summary`, `trend_interpretation`, `monthly_narrative`.

Response:
```json
{
  "status": "success",
  "data": {
    "insight_id": "uuid",
    "user_id": 12345,
    "insight_type": "risk_summary",
    "status": "AI_REVIEWED",
    "version_number": 2,
    "stale": false,
    "content": "Risk summary text...",
    "provenance": {
      "model_used": "claude-sonnet-4-6",
      "prompt_version": "v2",
      "generated_at": "ISO8601",
      "input_metrics_hash": "sha256-hash"
    },
    "reviewed_at": "ISO8601",
    "reviewed_by": "operator_id | auto"
  }
}
```

---

### 11.2 AI Insight Version History

```
GET /ai-insights/{user_id}/{insight_type}/history?limit=10
```

All versions newest-first, including `AI_ARCHIVED`.

Response:
```json
{
  "status": "success",
  "data": {
    "user_id": 12345,
    "insight_type": "risk_summary",
    "total_versions": 3,
    "versions": [
      {
        "insight_id": "uuid",
        "version_number": 3,
        "status": "AI_REVIEWED",
        "is_current": true,
        "generated_at": "ISO8601",
        "model_used": "claude-sonnet-4-6",
        "prompt_version": "v3"
      },
      {
        "insight_id": "uuid",
        "version_number": 2,
        "status": "AI_ARCHIVED",
        "is_current": false,
        "generated_at": "ISO8601",
        "archived_at": "ISO8601",
        "archived_reason": "force_refresh"
      }
    ]
  }
}
```

---

### 11.3 Specific AI Insight Version

```
GET /ai-insights/{user_id}/{insight_type}?version={N}
```

Returns the exact version `N`, including `AI_ARCHIVED` versions. Used for historical audit.

---

### 11.4 AI Insight Generation Request

```
POST /ai-insights/generate
```

Request:
```json
{
  "user_id": 12345,
  "insight_type": "risk_summary",
  "force_refresh": false,
  "idempotency_key": "client-uuid"
}
```

Idempotency behavior:
- `force_refresh: false` + valid `AI_REVIEWED` within TTL (`ai_insight_ttl_hours` from active config): returns cached insight with HTTP 200; no new generation
- `force_refresh: true`: transitions existing `AI_REVIEWED` to `AI_REFRESH_REQUESTED`; creates new `AI_PENDING`; returns HTTP 202
- Concurrent in-flight generation for the same `(user_id, insight_type, date_period)`: second request returns HTTP 409 with existing job reference

Response when cached (200):
```json
{
  "status": "success",
  "data": { "served_from_cache": true, "insight_id": "uuid", "version_number": 2 }
}
```

Response when initiated (202): job reference as in §6.1.

---

### 11.5 AI Insight Review (PRODUCTION Scope)

```
POST /ai-insights/{insight_id}/review
```

Transitions `AI_REVIEW_PENDING` to `AI_REVIEWED` (approve) or `AI_ARCHIVED` (reject).

Request:
```json
{
  "action": "approve | reject",
  "reviewer_id": "operator_id",
  "notes": "optional"
}
```

MVP and STANDARD scopes auto-transition `AI_GENERATED → AI_REVIEWED`; this endpoint is available but not required in the workflow.

---

### 11.6 AI Insight Provenance Inspection

```
GET /ai-insights/{insight_id}/provenance
```

Response:
```json
{
  "status": "success",
  "data": {
    "insight_id": "uuid",
    "version_number": 2,
    "model_used": "claude-sonnet-4-6",
    "prompt_version": "v2",
    "generated_at": "ISO8601",
    "input_metrics_hash": "sha256",
    "generation_duration_ms": 3420,
    "input_context_summary": {
      "hws_behind": 2,
      "avg_eff_rating": 3.1
    }
  }
}
```

---

### 11.7 AI Snapshot Isolation — Behavior Guarantee

> **Not an endpoint.** Documents isolation semantics for consumers:

- `GET /snapshots/{snapshot_id}` returns `ai_narratives` — physical text copies frozen at FINALIZED, never updated by any force-refresh or model-change operation.
- `POST /ai-insights/generate` with `force_refresh: true` creates a new `ai_insights` record but does NOT modify any finalized snapshot's `ai_narratives`.
- These are two independent records. A consumer must never assume they are synchronized after finalization.

---

## 12. CONFIG VERSION REGISTRY APIs

---

Exactly one version is ACTIVE at all times. Config changes are prospective-only (FAD-3). SUPERSEDED versions are queryable indefinitely for historical fingerprint lookups.

---

### 12.1 Active Config Version

```
GET /config-versions/active
```

Returns the currently ACTIVE configuration version with all 24 threshold values.

Response:
```json
{
  "status": "success",
  "data": {
    "version_id": 1,
    "version_number": 1,
    "status": "ACTIVE",
    "activated_at": "ISO8601",
    "activated_by": "system_migration_0003",
    "effective_from": "ISO8601",
    "thresholds": {
      "cap_hopeful_min_percomp": 0.30,
      "launch_hopeful_min_percomp": 0.59,
      "cap_section_exclusion_patterns": ["%launch%", "%CAP%"],
      "launch_section_inclusion_pattern": "%CAP%",
      "placement_section_inclusion_pattern": "%launch%",
      "hw_at_risk_min_behind": 1,
      "hw_at_risk_max_eff_rating": 3.0,
      "hw_critical_min_behind": 3,
      "hw_critical_max_eff_rating": 2.0,
      "payment_medium_threshold": 0.01,
      "payment_high_threshold": 1000.00,
      "payment_deviation_alert_threshold": null,
      "priority_hw_weight": 10.0,
      "priority_hw_cap": 50.0,
      "priority_eff_weight": 7.0,
      "priority_eff_cap": 35.0,
      "priority_inactivity_weight": 2.0,
      "priority_inactivity_cap": 50.0,
      "ai_insight_ttl_hours": 24,
      "outreach_retry_window_days": 3,
      "placement_inactivity_alert_days": 7,
      "access_revocation_alert_hours": 48,
      "ai_llm_provider": "anthropic",
      "outreach_provider": "ghl"
    },
    "governance": {
      "proposed_by": "system_migration_0003",
      "approved_by": "system_migration_0003",
      "change_rationale": "V1 baseline configuration"
    }
  }
}
```

---

### 12.2 Historical Config Version Lookup

```
GET /config-versions/{version_number}
```

Returns any version (ACTIVE, SUPERSEDED, ARCHIVED). Response shape identical to §12.1 with `status` reflecting current lifecycle state. Resolves for snapshot fingerprint audits even when ARCHIVED.

---

### 12.3 Config Version List

```
GET /config-versions?status=ACTIVE|SUPERSEDED|ARCHIVED|PROPOSED|UNDER_REVIEW|APPROVED&limit=20
```

`status` defaults to all non-ARCHIVED. Returns paginated list with activation metadata.

Response:
```json
{
  "status": "success",
  "data": {
    "total": 3,
    "items": [
      {
        "version_id": 1,
        "version_number": 1,
        "status": "SUPERSEDED",
        "activated_at": "ISO8601",
        "superseded_at": "ISO8601",
        "prior_version_id": null,
        "superseded_by_version_id": 2
      }
    ]
  }
}
```

---

### 12.4 Config Version Proposal

```
POST /config-versions
```

Creates a new version record in `PROPOSED` state. Requires `config_admin` role.

Request:
```json
{
  "prior_version_id": 1,
  "proposed_by": "admin_user_id",
  "change_rationale": "Adjusting CAP threshold based on Q2 cohort analysis",
  "thresholds": {
    "cap_hopeful_min_percomp": 0.32,
    "launch_hopeful_min_percomp": 0.59
  }
}
```

All 24 threshold fields must be provided (complete snapshot — not a diff). Partial payloads are rejected HTTP 422.

Rollback prohibition: creating a record with values identical to a SUPERSEDED version is allowed (new record is created); `SUPERSEDED → ACTIVE` transition is forbidden regardless of values.

Response (201):
```json
{
  "status": "success",
  "data": {
    "version_id": 2,
    "version_number": 2,
    "status": "PROPOSED",
    "prior_version_id": 1,
    "created_at": "ISO8601"
  }
}
```

---

### 12.5 Config Version Lifecycle Transition

```
POST /config-versions/{version_id}/lifecycle
```

Requires `config_admin` role.

Request:
```json
{
  "transition": "PROPOSE_TO_REVIEW | REVIEW_TO_APPROVED | APPROVED_TO_ACTIVE | SUBMIT_FOR_REVIEW_CHANGES",
  "actor_identity": "admin_user_id",
  "notes": "optional"
}
```

| transition | From | To | Notes |
|---|---|---|---|
| `PROPOSE_TO_REVIEW` | PROPOSED | UNDER_REVIEW | |
| `REVIEW_TO_APPROVED` | UNDER_REVIEW | APPROVED | Approver identity recorded |
| `APPROVED_TO_ACTIVE` | APPROVED | ACTIVE | Atomic; prior ACTIVE becomes SUPERSEDED |
| `SUBMIT_FOR_REVIEW_CHANGES` | UNDER_REVIEW | PROPOSED | Reviewer requests revisions |

`APPROVED_TO_ACTIVE` is atomic: prior ACTIVE version's `status`, `superseded_by_version_id`, and `deactivated_at` are updated in the same transaction as the new ACTIVE insert. No window exists where zero or two versions are ACTIVE.

Rollback transitions (`SUPERSEDED → ACTIVE`, `ARCHIVED → ACTIVE`) return HTTP 409 `CONFIG_ROLLBACK_FORBIDDEN`.

Response (200):
```json
{
  "status": "success",
  "data": {
    "version_id": 2,
    "from_status": "APPROVED",
    "to_status": "ACTIVE",
    "activated_at": "ISO8601",
    "prior_version_superseded": {
      "version_id": 1,
      "version_number": 1,
      "superseded_at": "ISO8601"
    }
  }
}
```

---

### 12.6 Config Version Lineage Traversal

```
GET /config-versions/{version_id}/lineage
```

Full version chain from V1 to current ACTIVE.

Response:
```json
{
  "status": "success",
  "data": {
    "lineage": [
      {
        "version_id": 1,
        "version_number": 1,
        "status": "SUPERSEDED",
        "activated_at": "ISO8601",
        "superseded_at": "ISO8601",
        "is_current": false
      },
      {
        "version_id": 2,
        "version_number": 2,
        "status": "ACTIVE",
        "activated_at": "ISO8601",
        "superseded_at": null,
        "is_current": true
      }
    ]
  }
}
```

---

### 12.7 Snapshots Referencing a Config Version

```
GET /config-versions/{version_id}/snapshots?limit=50
```

FINALIZED snapshots whose reproducibility fingerprint references this config version. Used for governance impact analysis.

Response:
```json
{
  "status": "success",
  "data": {
    "version_id": 1,
    "version_number": 1,
    "snapshot_count": 145,
    "items": [
      {
        "snapshot_id": "uuid",
        "student_id": 12345,
        "snapshot_month": "YYYY-MM",
        "finalized_at": "ISO8601"
      }
    ]
  }
}
```

---

## 13. COMPLIANCE AND AUDIT APIs

---

Compliance workflows are governance operations, not ordinary CRUD. All transitions are gated. Compliance audit records are append-only forever.

---

### 13.1 Compliance Workflow Request

```
POST /compliance/request
```

Initiates a compliance deletion or anonymization workflow. Requires `compliance_reviewer` role.

Request:
```json
{
  "student_id": 12345,
  "action_type": "GDPR_DELETION | FERPA_REMOVAL | ANONYMIZATION_REQUEST | INTERNAL_COMPLIANCE",
  "requester_identity": "compliance_officer_id",
  "legal_basis": "Student request per FERPA §99.3",
  "idempotency_key": "client-uuid"
}
```

At most one active (non-terminal) workflow per student. Duplicate intake returns HTTP 409.

Response (201):
```json
{
  "status": "success",
  "data": {
    "workflow_id": "uuid",
    "student_id": 12345,
    "status": "COMPLIANCE_REQUEST_RECEIVED",
    "action_type": "FERPA_REMOVAL",
    "created_at": "ISO8601"
  }
}
```

---

### 13.2 Compliance Workflow Status

```
GET /compliance/workflows/{student_id}
GET /compliance/workflows/by-id/{workflow_id}
```

First endpoint returns the active (non-terminal) workflow for a student; second returns any workflow by ID including terminal states.

Response:
```json
{
  "status": "success",
  "data": {
    "workflow_id": "uuid",
    "student_id": 12345,
    "status": "UNDER_REVIEW",
    "action_type": "FERPA_REMOVAL",
    "created_at": "ISO8601",
    "last_transition_at": "ISO8601",
    "scope_manifest_complete": false,
    "pre_action_audit_exists": false
  }
}
```

---

### 13.3 Compliance Workflow Lifecycle Transition

```
POST /compliance/workflows/{workflow_id}/lifecycle
```

Requires `compliance_reviewer` role.

Request:
```json
{
  "transition": "START_REVIEW | APPROVE | REJECT | WITHDRAW | BEGIN_EXECUTION | RECORD_COMPLETION",
  "actor_identity": "compliance_officer_id",
  "notes": "required for APPROVE, REJECT"
}
```

| transition | From | To | Gate |
|---|---|---|---|
| `START_REVIEW` | COMPLIANCE_REQUEST_RECEIVED | UNDER_REVIEW | |
| `APPROVE` | UNDER_REVIEW | APPROVED_FOR_ACTION | `scope_manifest` complete |
| `REJECT` | UNDER_REVIEW or COMPLIANCE_REQUEST_RECEIVED | REJECTED | |
| `WITHDRAW` | Any non-terminal | WITHDRAWN | |
| `BEGIN_EXECUTION` | APPROVED_FOR_ACTION | IN_EXECUTION | **Hard gate: pre-action audit entry must exist in `compliance_audit` schema** |
| `RECORD_COMPLETION` | IN_EXECUTION | DELETED or ANONYMIZED | Post-action audit entry written |

`BEGIN_EXECUTION` returns HTTP 422 `AUDIT_ENTRY_MISSING` if no pre-action audit entry exists. Workflow remains in `APPROVED_FOR_ACTION`.

Response (200):
```json
{
  "status": "success",
  "data": {
    "workflow_id": "uuid",
    "from_status": "APPROVED_FOR_ACTION",
    "to_status": "IN_EXECUTION",
    "transition_at": "ISO8601",
    "pre_action_audit_entry_id": "uuid"
  }
}
```

---

### 13.4 Compliance Audit Log Visibility

```
GET /compliance/audit/{student_id}
```

All compliance audit entries for a student. Requires `compliance_reviewer` role. Records are present even if the student's operational data has been deleted.

Response:
```json
{
  "status": "success",
  "data": {
    "student_id": 12345,
    "entries": [
      {
        "entry_id": "uuid",
        "workflow_id": "uuid",
        "entry_type": "PRE_ACTION | POST_ACTION",
        "action_type": "FERPA_REMOVAL",
        "authorized_by": "compliance_officer_id",
        "scope_manifest_snapshot": {},
        "execution_details": {},
        "created_at": "ISO8601"
      }
    ]
  }
}
```

---

### 13.5 Compliance Audit Export

```
GET /compliance/audit/export?student_id={id}&workflow_id={id}&format=json
```

Structured export for compliance auditor review. Format: `json` (default). Requires `compliance_reviewer` role.

This endpoint does not require the student's operational records to exist — audit records survive operational deletion.

---

## 14. TIMELINE AND LINEAGE APIs

---

### 14.1 Extended Timeline Endpoint

```
GET /timeline/{user_id}?event_type=all&from_date=YYYY-MM-DD&to_date=YYYY-MM-DD
```

Extends §8.11 to include snapshot and report lifecycle events.

Each event:
```json
{
  "event_id": "uuid",
  "event_type": "outreach | note | ghl_message | state_transition | ai_event | snapshot_event | report_event | access_event",
  "attribution_timestamp": "ISO8601",
  "display_label": "human-readable string",
  "channel": "SMS | EMAIL | CALL | OPERATOR | SYSTEM | null",
  "origin_source": "mirrored_sql_server | operator | ghl | ai_subsystem | compliance_pathway | scheduler",
  "origin_authority": "sql_server_authoritative | platform_supplementary | operator_authorized | system_automated",
  "is_authoritative": true,
  "execution_mode": "SHADOW | LIVE | null",
  "correlation_id": "uuid",
  "detail": {}
}
```

SQL Server-mirrored access events: `is_authoritative: true`. On conflict with a platform event for the same `(user_id, event_type, attribution_timestamp)`: both records present; SQL Server record is never overwritten; conflict logged with `correlation_id`.

Default limit 100, max 500.

---

### 14.2 Lineage Traversal — Generic

```
GET /lineage/{domain}/{entity_id}
```

Traverses parent-child lineage for any supported domain entity.

Supported domains: `snapshots`, `reports`, `config-versions`, `ai-insights`.

Response:
```json
{
  "status": "success",
  "data": {
    "domain": "reports",
    "entity_id": "uuid",
    "lineage_depth": 2,
    "chain": [
      {
        "version": 1,
        "entity_id": "uuid",
        "status": "REPORT_PUBLISHED",
        "is_root": true,
        "is_latest": false
      },
      {
        "version": 2,
        "entity_id": "uuid",
        "status": "REPORT_PUBLISHED",
        "is_root": false,
        "is_latest": true,
        "potentially_divergent": true
      }
    ]
  }
}
```

---

### 14.3 Fingerprint Divergence Inspection

```
GET /lineage/divergence/{report_id}
```

Fingerprint comparison between the original publication fingerprint and the regeneration source fingerprint.

Response:
```json
{
  "status": "success",
  "data": {
    "report_id": "uuid",
    "lineage_version": 2,
    "original_fingerprint": {},
    "regeneration_fingerprint": {},
    "diverged": true,
    "divergence_components": [
      "configuration_registry_version",
      "ai_prompt_version.risk_summary"
    ],
    "divergence_explanation": "Config V1 at original vs V2 at regeneration; risk_summary prompt v1 at original vs v2 at regeneration"
  }
}
```

---

### 14.4 Regeneration History

```
GET /lineage/regenerations?cohort_id={id}&report_month=YYYY-MM&limit=20
```

All regeneration events for a cohort-month report with reason, actor, outcome, and fingerprint comparison result.

---

## 15. ACCEPTANCE CRITERIA (EXTENDED)

---

### Immutable Historical Retrieval

**Given** a FINALIZED snapshot at month M
**When** `GET /snapshots/{student_id}/YYYY-MM` is called at any point in time
**Then** the same response is returned; `ai_narratives` content is frozen; subsequent AI operations, model upgrades, or config changes do not affect the response

---

**Given** a REPORT_PUBLISHED record
**When** `GET /reports/{cohort_id}/{year_month}` is called
**Then** `content`, `source_snapshot_fingerprint`, and `template_version` are identical across all calls; no in-place mutation has occurred

---

### Lineage Traversal Correctness

**Given** a published report that has been regenerated twice
**When** `GET /reports/{cohort_id}/{year_month}/history` is called
**Then** exactly 3 lineage members returned (`lineage_version` 1, 2, 3); each references its parent via `parent_report_id`; `is_latest: true` only on version 3; all three in `REPORT_PUBLISHED` state

---

**Given** SUPERSEDED config version V1 superseded by ACTIVE V2
**When** `GET /config-versions/{version_id}/lineage` is called
**Then** full chain from V1 to ACTIVE V2 returned; no gap; V1.`superseded_at` equals V2.`activated_at`

---

### Reproducibility Visibility

**Given** any FINALIZED snapshot
**When** `GET /snapshots/{snapshot_id}/fingerprint` is called
**Then** all 5 fingerprint components returned; `UNKNOWN_V0` components surfaced with `has_unknown_components: true`; `config_version_detail` resolves the full 24-field threshold set used at classification time — even if the config version is now ARCHIVED

---

### Governance Isolation

**Given** an attempt to call `POST /snapshots/{snapshot_id}/lifecycle` with a compliance transition
**When** called with standard operator role
**Then** HTTP 403 returned; compliance transitions exclusively require §13 APIs and `compliance_reviewer` role

---

**Given** `POST /compliance/workflows/{workflow_id}/lifecycle` with `BEGIN_EXECUTION`
**When** pre-action audit entry does not exist in `compliance_audit` schema
**Then** HTTP 422 `AUDIT_ENTRY_MISSING` returned; workflow remains in `APPROVED_FOR_ACTION`; no execution begins

---

### Attribution Consistency

**Given** a timeline event with `origin_source: mirrored_sql_server`
**When** a platform event arrives for the same `(user_id, event_type, attribution_timestamp)`
**Then** both records in timeline; SQL Server record has `is_authoritative: true`; platform record has `is_authoritative: false`; neither deleted

---

### Append-Only Behavior

**Given** an attempt to PUT or PATCH a FINALIZED snapshot's metrics
**When** the request is processed
**Then** HTTP 403 (or 404 if no such endpoint exists); snapshot row in `warehouse` unchanged; no UPDATE executed

---

**Given** `POST /config-versions/{version_id}/lifecycle` with `transition: SUPERSEDED_TO_ACTIVE`
**When** the version is SUPERSEDED
**Then** HTTP 409 `CONFIG_ROLLBACK_FORBIDDEN`; no activation occurs; existing ACTIVE version unchanged

---

### Config Lineage Visibility

**Given** a snapshot with `fingerprint.configuration_registry_version = "1"`
**When** `GET /config-versions/1` is called
**Then** full threshold set for V1 returned regardless of whether V1 is ACTIVE, SUPERSEDED, or ARCHIVED; all 24 rule values from spec/01 §12.1–12.7 present

---

## 16. UNRESOLVED API CONCERNS

---

The following items require business owner resolution before service implementation. They do not block schema authoring or migration work.

| ID | Concern | Impact | Owner |
|---|---|---|---|
| U-1 | Snapshot generation trigger: scheduled cron, operator-initiated, or both? | Drives `POST /snapshots/draft` caller and job queue design | Business owner |
| U-2 | Report publication approval gate: does PRODUCTION scope require `REPORT_REVIEW_PENDING` before `POST /reports/{id}/publish`? | Drives review gate exposure in API | Business owner |
| U-3 | AI monthly narrative review: operator approval required before snapshot finalization copies it? | Drives `AI_REVIEW_PENDING` exposure in finalization path | Business owner |
| U-4 | Month-end cutoff: specific UTC timestamp or end-of-business-day per timezone? | Drives scheduler and `snapshot_month` semantics | Business owner (HIGH — blocks scheduler) |
| U-5 | Compliance audit export format: JSON, CSV, signed PDF, or all three? | Drives §13.5 `format` parameter | Compliance authority |
| U-6 | `payment_deviation_alert_threshold` default: currently NULL in V1; what should V2 proposal set? | Drives config V2 proposal | Business owner |
| U-7 | AI monthly narrative audience: executive review or mentor operational use? | Drives role visibility for `monthly_narrative` in §5.2 | Business owner |
| U-8 | GHL message history depth for initial batch sync | Drives `POST /ghl-sync/batch` window parameter | Integration |
| U-9 | Snapshot retention policy: how long are DRAFT and DISCARDED snapshots retained? | Drives retention job and storage estimates | Business owner (HIGH — before first production snapshot) |
| U-10 | UserID cross-system reliability: stable across SQL Server re-imports? | Drives cross-reference reliability across all timeline and snapshot APIs | Technical |
| U-11 | Compliance audit read access: should mentors or instructors see any compliance entries? | Drives §5.2 role visibility table | Compliance authority |

---

## 17. DOWNSTREAM IMPLICATIONS

---

### Service Layer

| New API group | Required service |
|---|---|
| §9 Snapshot APIs | `app/services/snapshot.py` — `draft_create()`, `validate()`, `finalize()` (finalization service account), lifecycle transitions |
| §10 Report APIs | `app/services/report.py` — `generate()`, `publish()`, `regenerate()`, fingerprint comparison |
| §11 AI Insight APIs | Extend `app/services/ai_insights.py` — version history, force-refresh idempotency, review gate, provenance |
| §12 Config Version APIs | `app/services/config_registry.py` — `get_active()`, `propose()`, `atomic_activate()` |
| §13 Compliance APIs | `app/services/compliance.py` — `intake()`, `approve()`, `execute()`, `audit_export()` |
| §14 Lineage APIs | `app/services/lineage.py` — cross-domain lineage traversal, divergence detection |

---

### Repositories

| Service | Repository dependency |
|---|---|
| `snapshot.py` | `warehouse.student_snapshots` via finalization account (INSERT-only) |
| `report.py` | `warehouse.monthly_reports`, `warehouse.report_audit_log` |
| `config_registry.py` | `public.config_version_registry` |
| `compliance.py` | `compliance_audit.deletion_log`, `compliance_audit.scope_manifests` |

---

### Frontend Dashboards

| Dashboard feature | API dependency |
|---|---|
| Historical trend per student | `GET /snapshots/{student_id}?from_date&to_date` |
| Month snapshot with AI narratives | `GET /snapshots/{student_id}/{year_month}` |
| Monthly report viewer | `GET /reports/{cohort_id}/{year_month}` |
| Report version history panel | `GET /reports/{cohort_id}/{year_month}/history` |
| Active config thresholds panel | `GET /config-versions/active` |
| Config lineage audit | `GET /config-versions?status=all` |
| AI insight with staleness indicator | `GET /ai-insights/{user_id}/{type}` (`stale` flag drives UI badge) |
| Compliance workflow tracker | `GET /compliance/workflows/{student_id}` |
| Extended timeline (with lifecycle events) | `GET /timeline/{user_id}?event_type=all` |

---

### Report Rendering

Report rendering reads from `warehouse.student_snapshots` only (FAD-2). It MUST NOT query:
- Live `student_trigger_data`
- `ai_insights` records directly
- SQL Server directly

AI narrative content is read from `snapshot.ai_narratives` (physical text copies), not from `ai_insights`.

---

### Orchestration

| Orchestration concern | API entry point |
|---|---|
| Monthly snapshot batch job | `POST /snapshots/draft` × N students; finalization service per student |
| Monthly report batch job | `POST /reports/generate` per cohort; poll `/jobs/{job_id}` |
| Config version activation | `POST /config-versions/{id}/lifecycle` with `APPROVED_TO_ACTIVE` |
| Stale AI serving | `GET /ai-insights/{user_id}/{type}` returns `stale: true`; orchestrator triggers `POST /ai-insights/generate` |
| Compliance execution batch | `POST /compliance/workflows/{id}/lifecycle` with `BEGIN_EXECUTION` after pre-action audit gate |

---

## 18. REFERENCES

---

Depends on:

* `spec/01_requirements.md` — §3, §4 (FAD-1 through FAD-6), §9, §12, §14
* `spec/03_state_transition_rules.md` — All 6 lifecycle domains; state enums; transition tables; cross-domain invariants §40–44
* `spec/04_idempotency_concurrency.md` — Idempotency keys; irreversible operations; concurrency invariants
* `spec/08_data_model.md` — Conceptual entity definitions; schema separation; access control matrix; data invariants §22
* `spec/09_warehouse_physical_architecture.md` — Physical storage domains; append-only enforcement; lineage storage patterns §1.4–1.6
* `alembic/versions/0002_warehouse_schema.py` — Physical `warehouse.student_snapshots`, `warehouse.monthly_reports`, `warehouse.report_audit_log`
* `alembic/versions/0003_config_version_registry.py` — Physical `public.config_version_registry`; 24 rule columns; exactly-one-ACTIVE invariant

---

## END OF FILE
