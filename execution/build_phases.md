# execution/build_phases.md

---

## LAYER 4 — EXECUTION PLAN (BUILD PHASES)

---

> **Version note:** This file was completely rewritten on 2026-05-25 to reflect the finalized governed historical intelligence platform architecture. The previous version described an MVP-era outreach-only sequencing model (Foundation → Outreach → Decision → State → Loop → Retry → LLM → Failure → Observability → UX) that is architecturally insufficient for the governed platform defined in spec/01 through spec/09.

---

## 1. PURPOSE

This file defines:

* Detailed breakdown of build phases for the governed historical intelligence platform
* Objectives, components, dependencies, validation checkpoints, and exit criteria for each phase
* Governance-aware sequencing that ensures architectural invariants are never violated during implementation
* Architecture-preservation rules that prevent accidental invariant violations by implementation teams

---

## 2. WHY OLD SEQUENCING WAS INSUFFICIENT

The previous build phases reflected a feature-first model with these structural deficiencies:

| Deficiency | Impact on Governed Architecture |
|---|---|
| Observability as Phase 9 (second-to-last) | Governance-sensitive operations cannot execute safely before structured observability is in place |
| Dashboard as final milestone | Governance readiness is the correct production gate; dashboard completion is an intermediate milestone |
| No governance validation gates | Phases chained linearly with no invariant checkpoints; architectural violations accumulate silently |
| Single application service account assumed | Three-SA model (standard / finalization / compliance) did not exist in execution sequencing |
| No config governance | Cohort thresholds were hardcoded; Config Version Registry and prospective-only enforcement did not exist |
| No compliance workflow | Pre-action audit gate, compliance_audit schema isolation, and deletion pathway did not exist |
| No lineage or reproducibility model | Snapshot fingerprint, FAD-1 frozen AI copy, FAD-2 snapshot-centric historical — none were part of execution sequencing |
| AI treated as Phase 7 (late-stage add-on) | AI enrichment must precede snapshot finalization; inserting it late violates FAD-1 |
| Idempotency as Phase 6 add-on | Idempotency must be enforced from the first record written, not retrofitted later |

The finalized architecture requires **governance-first sequencing**: establish immutable foundations before any operation that creates governance-sensitive data.

---

## 3. PHASE ARCHITECTURE PRINCIPLES

---

### 3.1 Governance-First

Governance infrastructure (schema isolation, service accounts, config registry, observability) must be in place BEFORE any service executes that creates governance-sensitive records. A finalized snapshot created before governance infrastructure exists is an unauditable artifact.

### 3.2 Observability-First

Structured observability (JSON log schema, correlation_id propagation, governance transition log entries) must be operational BEFORE any LIVE execution of governance-sensitive workflows. Running a snapshot finalization job without observability means the governance boundary crossing is unrecorded in operational telemetry — a spec/06 defect.

### 3.3 Lineage-Safe

Every service must be built with full lineage awareness before it writes its first governance-quality record. Retrofitting lineage after records exist is an audit gap that cannot be corrected without data reconstruction.

### 3.4 Replay-Safe by Construction

Services must enforce idempotency from their first deployment. A service that processes its first record without idempotency keys and then adds them later has created a window of non-idempotent records that cannot be retroactively made safe.

### 3.5 SHADOW Before LIVE

Every outbound-communication and governance-boundary-crossing service must operate in SHADOW mode exclusively until Phase 12 certification. SHADOW mode is not a debugging convenience — it is a mandatory operational tier.

### 3.6 Dependency Ordering Preserves Invariants

Phases must be sequenced so that downstream services never execute before their upstream dependencies are validated. A report generation service that executes before finalized snapshots exist violates FAD-2. Phase sequencing enforces this as hard dependencies, not soft suggestions.

---

## 4. PHASE DEPENDENCY MAP

```
Phase 1: Infrastructure & Governance Foundation
    │
    └──── Phase 2: Database & Migration Hardening
              │
              ├──── Phase 3: SQL Server Synchronization
              │         │
              │         ├──── Phase 4: Unified Timeline Ingestion
              │         │         │
              │         │         └──── (feeds Phase 5 timeline events)
              │         │
              │         └──── Phase 5: Snapshot Orchestration (DRAFT→VALIDATING only)
              │                   │
              │                   ├──── Phase 6: AI Enrichment (AI_REVIEWED gate)
              │                   │         │
              │                   │         └──── (feeds Phase 5 FINALIZED boundary)
              │                   │
              │                   └──── Phase 7: Report Publication & Lineage
              │                             │
              │                             └──── Phase 10: Observability & Replay
              │
              ├──── Phase 8: Config Governance Activation
              │         │
              │         └──── (feeds Phase 5 config binding at VALIDATING)
              │
              └──── Phase 9: Compliance Workflow Enablement
                        │
                        └──── (depends on Phase 2, 3, 5, 7)

Phase 10: Observability & Replay Diagnostics
    │       (depends on Phase 5, 6, 7)
    │
    └──── Phase 11: Operational Dashboards
              │
              └──── Phase 12: Production Governance Readiness
```

**Note on Phase 5 / Phase 6 interlocking:** Phase 5's DRAFT→VALIDATING sub-phase does not require AI_REVIEWED insights. Phase 5's VALIDATING→FINALIZED boundary does. Recommended order: implement Phase 5 through VALIDATING, then implement Phase 6 through AI_REVIEWED, then complete Phase 5 finalization.

---

## 5. PHASE 1 — INFRASTRUCTURE & GOVERNANCE FOUNDATION

---

### Objective

Establish core service scaffolding, structured observability framework, SHADOW mode enforcement, and service account credential wiring. No governance-sensitive records may be created until this phase's exit criteria are satisfied.

---

### Components

* FastAPI service with health endpoint returning `execution_mode` and schema connectivity status
* PostgreSQL connection wiring: three named SA connection strings (standard, finalization, compliance pathway); no superuser connection in application code paths
* SQL Server connection wiring: read-only connection string only; no write grants provisioned (FAD-5)
* Structured JSON logging — universal log schema from spec/06 §2.1 enforced from the first log line; no unstructured string logging in any code path
* Correlation ID middleware: UUID v4 generated at every request entry point and propagated through all downstream log entries for that request
* EXECUTION_MODE enforcement: SHADOW mode as the immutable default; all outbound communication paths refuse LIVE execution without Phase 12 certification
* Environment-variable credential loading with redaction: any log line referencing a credential value must emit `<redacted>`, not the value

---

### Dependencies

* None (root phase)

---

### Validation Checkpoints

1. Health endpoint returns 200 with `execution_mode: SHADOW` in response body
2. First log line emitted by service conforms to universal log schema (all required fields present)
3. Correlation ID generated at request entry point appears in all log lines for that request
4. Attempting INSERT on `warehouse` schema with standard SA raises PostgreSQL `insufficient_privilege` (requires Phase 2 to verify physically; wire the check into Phase 1 startup)
5. SQL Server write attempt blocked: application-layer enforcement produces a `SQL_SERVER_WRITE_ATTEMPTED` log entry with `error_class: ArchitecturalViolation` before any connection attempt
6. All three SA credentials loaded from environment variables; none hard-coded in source

---

### Observability Requirements

* Service startup log: `event: service_startup`, `execution_mode`, `environment`, `outcome`
* Health check log: database connectivity status for each of the three schema targets
* All log entries from this phase forward carry `timestamp`, `level`, `service`, `event`, `correlation_id`, `outcome`

---

### Governance Implications

* EXECUTION_MODE defaults to SHADOW permanently until Phase 12 explicitly certifies LIVE eligibility. No environment variable, feature flag, or ad-hoc code change may bypass this.
* Service account separation must be wired in Phase 1 and must never be collapsed into a single superuser credential in any subsequent phase.

---

### Rollback Boundaries

Phase 1 is fully reversible. No governance-sensitive data exists.

---

### Exit Criteria

1. Service starts; health endpoint returns 200
2. First structured log line emitted conforming to universal log schema
3. Correlation ID present in all log lines for a test request
4. SA credential separation wired (three named connection strings; no superuser)
5. SQL Server write attempt produces architectural violation log entry before any network call

---

---

## 6. PHASE 2 — DATABASE & MIGRATION HARDENING

---

### Objective

Apply all Alembic migrations in the correct sequence, verify all schema-level permission grants, confirm the physical storage architecture matches spec/09_warehouse_physical_architecture.md, and confirm Config Version V1 seed is ACTIVE. No phase that creates governance-sensitive data (Phase 5 and later) may begin until this phase is complete.

---

### Components

* **Migration 0002** (`0002_warehouse_schema.py`): `warehouse` and `compliance_audit` schema creation; all four warehouse tables; both compliance_audit tables; all schema-level permission GRANTs including the sole UPDATE grant on `warehouse.student_snapshots.status` for compliance pathway SA (spec/10 §correction-2)
* **Migration 0003** (`0003_config_version_registry.py`): `public.config_version_registry` creation; V1 seed record at `status = ACTIVE` with all spec/01 §12 threshold defaults; partial unique index enforcing exactly-one-ACTIVE invariant
* **Migration 0004**: `public.snapshot_draft_queue` and `public.student_timeline_events` tables
* **Migration 0005** (future): scheduled job tracking table; added when scheduler service is implemented
* **Pre-migration benchmarking** (before finalizing 0002 column types): query `ai_insights` for P95 AI text payload size per insight type (spec/09 §11.2); two-table architecture is the default; benchmarking confirms or overrides
* **Alembic revision chain verification**: `0001 → 0002 → 0003 → 0004` chain must be linear and verified after each migration

---

### Dependencies

* Phase 1 exit criteria satisfied

---

### Validation Checkpoints

1. `alembic upgrade head` completes without error; `alembic current` reports correct revision hash
2. **Standard SA**: SELECT on warehouse schema succeeds; INSERT raises `insufficient_privilege`
3. **Finalization SA**: INSERT on `warehouse.student_snapshots`, `warehouse.snapshot_ai_narratives`, `warehouse.monthly_reports`, `warehouse.report_audit_log` succeeds; UPDATE on those tables (other than `status` column via compliance pathway) raises `insufficient_privilege`
4. **Compliance pathway SA**: INSERT on `compliance_audit.deletion_log` and `compliance_audit.scope_manifests` succeeds; INSERT on warehouse tables raises `insufficient_privilege`; UPDATE `status` on `warehouse.student_snapshots` succeeds (sole exception)
5. Config Version Registry has exactly one row with `status = ACTIVE`
6. Partial unique index: attempt inserting a second `status = ACTIVE` row in `config_version_registry` — fails with unique constraint violation
7. `snapshot_draft_queue` and `student_timeline_events` tables exist in public schema and are writable by standard SA
8. `alembic downgrade` to 0001 reverses grants, drops tables, and drops schemas without error

---

### Observability Requirements

* Migration execution log: migration file, revision chain step, duration_ms, outcome
* Permission grant verification log per SA: each GRANT confirmed with `event: grant_verified`, SA identity, table, privilege type
* Config V1 seed confirmation log: version_number, status, rule count, created_at

---

### Governance Implications

* All schema-level permission grants are physical database enforcement mechanisms, not application conventions. Their correctness is a prerequisite for all seven platform invariants (INVARIANT-1 through INVARIANT-7).
* A missing V1 seed violates DATA-INVARIANT-4 (exactly-one-ACTIVE config version at all times). No snapshot can be generated without an ACTIVE config version.
* Migration 0002 contains both `warehouse` and `compliance_audit` schemas per FAD-4. They must not be split into separate migrations.

---

### Rollback Boundaries

`alembic downgrade` is the safe rollback path if no application service has yet written to the new schemas. Once data exists in `warehouse` or `compliance_audit`, migration rollback is destructive and requires operator decision with explicit confirmation.

---

### Exit Criteria

1. `alembic upgrade head` succeeds; revision chain verified
2. Three-SA permission model verified against all seven checkpoints above
3. Config V1 seed ACTIVE; second ACTIVE insert rejected by partial unique index
4. Timeline and draft queue tables exist and writable by standard SA
5. Pre-migration AI payload benchmarking completed; two-table architecture confirmed or overridden by data

---

---

## 7. PHASE 3 — SQL SERVER SYNCHRONIZATION

---

### Objective

Implement the idempotent, schema-drift-tolerant SQL Server → PostgreSQL synchronization service. This is the authoritative data ingestion boundary (FAD-5). All downstream services consume from `public.student_trigger_data`; no downstream service ever queries SQL Server directly.

---

### Components

* SQL Server sync service: idempotent UPSERT to `public.student_trigger_data` on conflict `(UserID)`
* Schema drift detection: missing or renamed columns detected at sync time, logged as structured drift events, partial sync completes for intact columns without error
* Attribution assignment: all records upserted via sync carry `origin_source: mirrored_sql_server` and `origin_authority: sql_server_authoritative`
* Attribution timestamp: `attribution_timestamp` on each synced record reflects the SQL Server record's operational timestamp, not sync processing timestamp
* `processed_events` dedup: each sync batch registers an idempotency key; replay of same batch produces identical result without duplicate processing
* Sync endpoint: `POST /sync/mssql` for manual trigger; scheduler hook registered in Phase 5

---

### Dependencies

* Phase 1 and Phase 2 exit criteria satisfied

---

### Validation Checkpoints

1. Sync completes without error against real SQL Server connection
2. **Idempotency**: running sync twice produces identical `student_trigger_data` row counts and field values
3. **Schema drift**: remove a column from the test query; partial sync completes for remaining columns; drift event logged with `SEVERITY: MEDIUM`
4. **FAD-5 compliance**: SQL Server write attempt produces architectural violation log entry; verify no write was issued by inspecting SQL Server query log
5. Sync job log entry conforms to spec/06 §2.8: `origin_source`, `origin_authority`, `rows_synced`, `drift_detected`, `duration_ms`, `outcome`, `correlation_id`
6. Attribution timestamp on synced rows matches SQL Server source record timestamps, not sync execution timestamp

---

### Observability Requirements

* Sync start log: job_type, student_count_target, correlation_id, execution_mode
* Per-batch progress for large cohorts (every 100 students logged)
* Sync completion: rows_synced, rows_upserted, rows_skipped, drift_detected, drift_fields (if any), duration_ms, outcome
* Schema drift alert: `SEVERITY: LOW` for additive new columns; `SEVERITY: MEDIUM` for missing expected columns
* Attribution preservation log: sample of 3 records confirming attribution_timestamp matches SQL Server source

---

### Governance Implications

* FAD-5 is enforced here at the connection level (read-only DSN) and the application level (architectural violation log entry on write attempt). Both layers must be verified.
* Every downstream service that consumes student operational state reads from `student_trigger_data`. No service may bypass this boundary by querying SQL Server directly — that would create an unattributed data path outside the governance model.

---

### Rollback Boundaries

`public.student_trigger_data` is a mutable mirror. Rollback from a bad sync: `TRUNCATE student_trigger_data`, rerun sync from SQL Server. No warehouse or compliance schemas are touched.

---

### Exit Criteria

1. Sync completes idempotently
2. Schema drift detection functional and logged
3. SQL Server write attempt produces architectural violation log entry and is blocked
4. Attribution fields present and correct on all synced rows
5. Sync log entry complete and conformant to spec/06

---

---

## 8. PHASE 4 — UNIFIED TIMELINE INGESTION

---

### Objective

Implement the unified `student_timeline_events` ingestion pipeline that normalizes events from all sources into the shared chronological timeline with full attribution preservation. Timeline events are append-only and carry immutable `origin_source` and `origin_authority` from their originating source.

---

### Components

* Timeline ingestion service: normalize events from SQL Server sync, GHL webhooks, and platform operations; assign `origin_source`, `origin_authority`, `attribution_timestamp` (originating event time, not processing time)
* GHL webhook ingestion: communication events ingested with `origin_source: ghl`; deduplication key `(ghl_message_id, event_type)`; `attribution_timestamp` = GHL message timestamp
* SQL Server lifecycle event detection: consecutive sync comparison detects state changes; emits timeline events with `origin_source: mirrored_sql_server`
* Platform operation events: outreach attempts, operator actions, AI lifecycle events emitted with `origin_source: platform_system` or `origin_source: platform_manual`
* Deduplication via `processed_events`: event idempotency key prevents duplicate timeline rows from replay ingestion
* Attribution immutability enforcement: `origin_source`, `origin_authority`, and `attribution_timestamp` columns must be non-updatable at the application layer from the first event

---

### Dependencies

* Phase 3 exit criteria satisfied
* `student_timeline_events` table exists (Phase 2 migration 0004)

---

### Validation Checkpoints

1. GHL webhook event ingested with correct `origin_source: ghl` and `attribution_timestamp` = GHL message timestamp
2. SQL Server lifecycle transition (simulated by two consecutive syncs with different ActiveStatus) emits timeline event with `origin_source: mirrored_sql_server`
3. **Replay safety**: submitting same GHL event twice produces exactly one timeline row
4. **Attribution immutability**: attempting UPDATE on `origin_source` of an existing timeline row is blocked at application layer; log entry emitted with `error_class: AttributionTamperingAttempt`
5. Timeline query for a student returns events in `attribution_timestamp DESC` order with correct `origin_source` per event

---

### Observability Requirements

* Ingestion batch log: source, events_received, events_written, duplicates_discarded, failed, correlation_id, duration_ms
* Attribution preservation log: confirms `attribution_timestamp` = original event time for all source types
* Dedup detection log: `event: timeline_duplicate_discarded`, idempotency_key, origin_source, correlation_id

---

### Governance Implications

* INVARIANT-5 (source attribution consistency): every timeline event carries `origin_source` and `origin_authority` as immutable attribution fields. Implementation must enforce this from the first event.
* SQL Server-sourced events are authoritative for student operational state (FAD-5). Platform-supplementary events are contextual and must not override SQL Server authoritative fields.

---

### Rollback Boundaries

`student_timeline_events` is append-only. Deleting a wrongly ingested event requires compliance pathway escalation — not a DBA truncate. This makes correctness in Phase 4 critical; there is no easy undo.

---

### Exit Criteria

1. Events from all three sources (SQL Server, GHL, platform) ingest correctly with correct attribution
2. Replay safety confirmed — no duplicate events after re-ingestion
3. Attribution timestamp = originating event timestamp verified for each source type
4. Deduplication via `processed_events` functional
5. Timeline query returns events in correct chronological order

---

---

## 9. PHASE 5 — SNAPSHOT ORCHESTRATION

---

### Objective

Implement the full snapshot lifecycle state machine: `DRAFT → VALIDATING → FINALIZED`. This is the primary governance boundary in the platform. Phase 5 is implemented in two sub-phases: (a) DRAFT→VALIDATING, which does not require AI_REVIEWED insights; (b) VALIDATING→FINALIZED, which requires Phase 6 to be complete through AI_REVIEWED state.

---

### Components

**Sub-phase A — DRAFT→VALIDATING (may begin before Phase 6):**
* `snapshot_draft_queue` DRAFT creation with idempotency key `(student_id, snapshot_month, 'DRAFT')`
* VALIDATING phase: pull all metric fields from `student_trigger_data` (never from SQL Server directly); compute derived metrics (segment classification, payment risk, homework risk, actual_balance); pull communication summary; read ACTIVE config version from `config_version_registry` and lock `fingerprint_config_registry_version`

**Sub-phase B — VALIDATING→FINALIZED (requires Phase 6 AI_REVIEWED):**
* Compute all 5 reproducibility fingerprint components: `schema_version`, `config_registry_version`, `ai_prompt_version`, `ai_model_version`, `report_template_version`
* Copy AI_REVIEWED text from `ai_insights` for each insight type into finalization payload
* Atomic transaction via finalization SA: INSERT into `warehouse.student_snapshots` and `warehouse.snapshot_ai_narratives` simultaneously; both rows exist or neither does
* Mark `snapshot_draft_queue` row as FINALIZED; emit SnapshotLifecycleEvent to `student_timeline_events`
* Month-end APScheduler trigger registered

---

### Dependencies

* Phase 1, Phase 2, Phase 3, Phase 4 exit criteria satisfied
* Phase 8 at minimum through read-path (ACTIVE config version readable) before sub-phase A VALIDATING
* Phase 6 complete through AI_REVIEWED state before sub-phase B FINALIZED boundary

---

### Validation Checkpoints

1. DRAFT creation is idempotent: creating DRAFT for `(student_id, snapshot_month)` twice produces one row
2. VALIDATING reads from `student_trigger_data` only; no SQL Server query issued
3. Config version binding: `fingerprint_config_registry_version` matches ACTIVE version in `config_version_registry` at VALIDATING time
4. **Finalization atomicity**: snapshot row and AI narrative companion row both inserted; verify both exist or both absent after simulated failure mid-transaction
5. **Post-finalization immutability**: attempt UPDATE on `warehouse.student_snapshots` with standard SA — `insufficient_privilege`
6. **FAD-1 isolation**: after finalization, force-refresh of corresponding AI insight produces a new `ai_insights` row; `warehouse.snapshot_ai_narratives` row is unchanged
7. Full 5-component reproducibility fingerprint is non-null on finalized snapshot row
8. Governance transition log entry: `snapshot_state_transition` with `to_state: FINALIZED`, full `fingerprint_components`, `actor_identity: finalization_service_account`
9. Duplicate finalization attempt for same `(student_id, snapshot_month)` returns existing row without creating a second `warehouse.student_snapshots` row

---

### Observability Requirements

All snapshot events must conform to spec/06 §2.4 and §2.5:
* DRAFT→VALIDATING transition log: student_count, config_version_bound, correlation_id
* VALIDATING→FINALIZED governance transition log: full 5-component fingerprint, actor_identity, attribution_timestamp
* Snapshot AI isolation confirmation (spec/06 §7.7): every force-refresh after finalization emits `snapshot_ai_isolation_confirmed` with `frozen_text_modified: false`
* Monthly batch completion: total_students, success_count, failed_count, stale_ai_used_count, duration_ms, correlation_id

---

### Governance Implications

* FINALIZED is the primary governance boundary. After this boundary, no UPDATE is possible from any application SA other than compliance pathway on the `status` column.
* The finalization SA credentials must never be passed to any code path other than the finalization boundary. Any code that opens a finalization SA connection outside the finalization service is an architectural violation.
* FAD-3 (prospective-only config): the config version active at VALIDATING time is locked to this snapshot permanently. No future config changes retroactively affect this snapshot's classification.
* FAD-1 is enforced at finalization: AI text is a physical copy in the snapshot. Subsequent AI insight updates have zero effect on finalized snapshot content.

---

### Rollback Boundaries

**Before FINALIZED:** DRAFT and VALIDATING rows in `snapshot_draft_queue` are safe to delete and recreate. No warehouse rows affected.

**After FINALIZED:** No rollback through the application. Only the compliance pathway can delete or anonymize a finalized snapshot. Any other deletion attempt is a governance violation.

---

### Exit Criteria

1. DRAFT→VALIDATING→FINALIZED state machine completes end-to-end
2. Finalization is idempotent (second trigger returns existing row)
3. Snapshot and AI narrative companion inserted atomically
4. Post-finalization immutability enforced by database (standard SA UPDATE rejected)
5. FAD-1 AI isolation confirmed (force-refresh does not modify snapshot AI content)
6. Full 5-component reproducibility fingerprint present on finalized snapshot
7. Governance transition log entry with fingerprint_components emitted

---

---

## 10. PHASE 6 — AI ENRICHMENT ORCHESTRATION

---

### Objective

Implement the full AI insight lifecycle: generation, versioning, TTL management, force-refresh idempotency, stale serving, and snapshot isolation confirmation. Phase 6 must reach AI_REVIEWED state before Phase 5's FINALIZED boundary can execute.

---

### Components

* AI insight generation service: per-student per-type generation; prompt version locked at generation time; model version logged; PII strictly excluded from prompts
* Versioning: each generation creates a new `ai_insights` row; prior versions retained; `version_number` incremented sequentially
* TTL management: AI_REVIEWED insights served until TTL (`ai_insight_ttl_hours` from active config version); stale insights served with `stale: true` flag and `stale_for_hours` value
* Force-refresh idempotency: key `(student_id, insight_type, date_period, prompt_version, version_number)`; concurrent force-refresh attempts produce exactly one new generation
* AI provider retry: exponential backoff, max 2 retries; after exhaustion, serve last AI_REVIEWED insight with `stale: true`; never block snapshot finalization on AI generation failure
* PII prohibition: enforced at prompt assembly layer — only anonymized metrics and program context; runtime assertion in prompt builder that rejects any prompt containing detected PII patterns
* Snapshot AI isolation assertion: any force-refresh after finalization generates new `ai_insights` row; `warehouse.snapshot_ai_narratives` row for that snapshot is structurally unreachable from the AI generation path

---

### Dependencies

* Phase 1, Phase 2, Phase 3 exit criteria satisfied
* AI provider credentials provisioned in environment variables

---

### Validation Checkpoints

1. Force-refresh creates new version record; prior version retained; `version_number` incremented
2. Stale insight served after TTL expiry: response includes `stale: true`, `stale_for_hours`
3. AI provider outage simulation: after 2 retries exhausted, last AI_REVIEWED insight returned with `stale: true`; no error response to caller
4. PII not present in any AI prompt: verified by inspecting prompt assembly component log (metadata fields only; content_text never logged)
5. Concurrent force-refresh: exactly one new `ai_insights` row created from two simultaneous requests
6. **Snapshot isolation**: finalize a snapshot; force-refresh the insight; confirm `warehouse.snapshot_ai_narratives` row is unchanged
7. AI generation log conforms to spec/06 §2.6: insight_type, prompt_version, model_used, version_number, is_force_refresh, latency_ms, retry_count, outcome — content_text absent

---

### Observability Requirements

* AI generation log entries per spec/06 §2.6 (metadata only; no content text in any field)
* Stale AI detection log: `event: stale_insight_served`, stale_for_hours, insight_version, student_id (opaque), correlation_id
* AI provider failure log: error_class (TimeoutError / RateLimitError / etc.), attempt_number, fallback_action
* At snapshot finalization: `event: snapshot_ai_isolation_confirmed`, frozen_text_modified: false, correlation_id

---

### Governance Implications

* AI insight attribution metadata (prompt_version, model_used, generated_at) is immutable after generation. Enforce via database constraint; not application convention.
* INVARIANT-3 (AI snapshot isolation): `warehouse.snapshot_ai_narratives` is a physical copy separated from `ai_insights`. No code path updates the snapshot AI narrative after finalization. The architectural separation (two separate tables, finalization SA INSERT-only) is the enforcement mechanism.

---

### Rollback Boundaries

A failed generation produces no persisted row. A bad generation is superseded by force-refresh. No compliance pathway needed for AI insight cleanup during development.

---

### Exit Criteria

1. Generation, versioning, and TTL management functional
2. Force-refresh idempotency confirmed
3. Stale insight serving with `stale: true` flag functional
4. AI provider failure handled (stale serving without error response to caller)
5. Snapshot AI isolation confirmed after finalization
6. PII prohibition enforced at prompt assembly
7. AI log entries conform to spec/06 (metadata only)

---

---

## 11. PHASE 7 — REPORT PUBLICATION & LINEAGE

---

### Objective

Implement the monthly report generation pipeline from finalized snapshots, the publication boundary, and historical report regeneration with lineage versioning. Every step reads exclusively from `warehouse.student_snapshots` and `warehouse.snapshot_ai_narratives` — no SQL Server queries, no live operational table joins (FAD-2).

---

### Components

* Report generation service: assembles `warehouse.monthly_reports` from finalized snapshots; reads frozen AI narrative text from `warehouse.snapshot_ai_narratives`; computes aggregate statistics
* Report idempotency key: `hash(cohort_id, report_month, template_version, lineage_version)` checked via `processed_events`
* Report state machine: REPORT_PENDING → REPORT_GENERATING → REPORT_GENERATED → REPORT_REVIEW_PENDING → REPORT_APPROVED → REPORT_PUBLISHED
* Publication boundary: REPORT_PUBLISHED is immutable; no UPDATE after this state
* `warehouse.report_audit_log`: append-only lifecycle log; one entry per state transition; written before each transition completes
* **Historical regeneration**: operator-triggered; creates new row with `lineage_version = N+1`, `parent_report_id` = prior REPORT_PUBLISHED row ID; original row unmodified
* Fingerprint divergence detection: at regeneration start, stored vs. current fingerprint compared; `POTENTIALLY_DIVERGENT` flag set if different; both fingerprints logged; SEVERITY: MEDIUM alert raised; regeneration continues — divergence is an audit finding, not a blocker

---

### Dependencies

* Phase 5 exit criteria satisfied (finalized snapshots must exist)
* Phase 2 exit criteria satisfied (`warehouse.monthly_reports` and `report_audit_log` tables exist)

---

### Validation Checkpoints

1. **FAD-2 compliance**: report generation issues zero SQL Server queries and zero `student_trigger_data` joins; verified by query log inspection
2. Report idempotency: generating same report twice returns existing row; no duplicate in `warehouse.monthly_reports`
3. **REPORT_PUBLISHED immutability**: attempt UPDATE on published report with standard SA — `insufficient_privilege`
4. Historical regeneration: prior REPORT_PUBLISHED row unchanged; new row created with `lineage_version = N+1` and `parent_report_id` set
5. Fingerprint divergence: simulate divergence (test config version change); confirm `POTENTIALLY_DIVERGENT` flag set on new report row; both fingerprint versions logged; SEVERITY: MEDIUM alert raised
6. `warehouse.report_audit_log` has one entry per state transition for each report
7. Historical regeneration reads AI narrative from `warehouse.snapshot_ai_narratives`; zero AI provider calls made

---

### Observability Requirements

* Report generation phase log entries (spec/06 §4): each phase with correlation_id, phase_name, outcome, duration_ms
* Historical regeneration log: `execution_type: regeneration`, source snapshot IDs, `fingerprint_match`, `new_lineage_version`, `causation_id` (points to original job correlation_id)
* Fingerprint divergence log: both stored and current fingerprint values; differing components identified by name
* `report_audit_log` entry written atomically before regeneration completes; if audit write fails, regeneration rolls back

---

### Governance Implications

* FAD-2: report generation must not query SQL Server or `student_trigger_data`. Violation is a production defect.
* Historical regeneration creates a new lineage version additively. The original REPORT_PUBLISHED row is a permanent historical record.
* `POTENTIALLY_DIVERGENT` is preserved on the regenerated report indefinitely. It cannot be cleared except by a subsequent regeneration that does achieve fingerprint match.

---

### Rollback Boundaries

**REPORT_REVIEW_PENDING and earlier**: reports may be discarded (soft delete via state transition to DISCARDED). New generation initiated.
**REPORT_PUBLISHED**: no rollback through application. Compliance pathway only. Historical regeneration creates an additive lineage version — it does not remove the original.

---

### Exit Criteria

1. Report generation reads only from warehouse schema (FAD-2 verified by query log)
2. Report idempotency confirmed
3. REPORT_PUBLISHED immutability enforced by database
4. Historical regeneration creates new lineage version without modifying original
5. Fingerprint divergence detected and `POTENTIALLY_DIVERGENT` flag set when applicable
6. `report_audit_log` has entries for all state transitions
7. Regeneration uses frozen AI narrative (zero AI provider calls confirmed)

---

---

## 12. PHASE 8 — CONFIG GOVERNANCE ACTIVATION

---

### Objective

Implement the Config Version Registry governance lifecycle: proposal, approval, atomic activation, supersession, and rollback prohibition. Config governance must be operational — at minimum with V1 readable — before Phase 5 snapshot generation can bind a config version at VALIDATING time.

---

### Implementation Note

Phase 8's read path (returning ACTIVE config) must be functional before Phase 5's VALIDATING sub-phase. The management plane (proposal/approval/activation) may be built concurrently with Phase 5's DRAFT sub-phase. Both must be complete before Phase 5's FINALIZED boundary is activated.

---

### Components

* Config version read service: returns single ACTIVE config version; always exactly one (DATA-INVARIANT-4)
* Config version proposal API: creates new version in DRAFT state with rule values; requires authorized actor identity
* Approval pathway: DRAFT → APPROVED transition with reviewer identity recorded
* **Atomic activation**: APPROVED → ACTIVE with simultaneous old ACTIVE → SUPERSEDED in a single database transaction; no zero-ACTIVE window; exactly-one-ACTIVE enforced by partial unique index
* **Rollback prohibition**: no SUPERSEDED → ACTIVE path exists; "rollback" requires creating a new version reproducing prior values; attempt produces `CONFIG_ROLLBACK_FORBIDDEN` error
* Historical lineage: all versions retained with `activated_at` / `superseded_at` timestamps; historical config at any date reconstructable

---

### Dependencies

* Phase 2 exit criteria satisfied (`config_version_registry` and V1 seed must exist)

---

### Validation Checkpoints

1. Exactly-one-ACTIVE: attempt inserting second `status = ACTIVE` row — fails with partial unique index constraint violation
2. Atomic activation: concurrent activation of two different versions — exactly one succeeds; no zero-ACTIVE window during transition
3. **Rollback prohibition**: attempt SUPERSEDED → ACTIVE transition — rejected with `CONFIG_ROLLBACK_FORBIDDEN` error; governance violation log entry emitted
4. Historical config resolution: query config active at a past date — returns correct historical version
5. Config version reference on snapshot: `fingerprint_config_registry_version` matches ACTIVE version at VALIDATING time; confirmed by snapshot validation

---

### Observability Requirements

* Config activation governance transition log: actor_identity, from_version, to_version, correlation_id, outcome
* Rollback prohibition log: `error_class: GovernanceViolation`, attempted_operation, `SEVERITY: CRITICAL`
* ACTIVE version drift alert: if `config_version_registry` has zero ACTIVE rows — `SEVERITY: CRITICAL` (DATA-INVARIANT-4 violated)

---

### Governance Implications

* FAD-3 (prospective-only semantics): a new ACTIVE config version does NOT recalculate prior snapshots. Snapshots permanently reference the config version active at their VALIDATING time. The append-only lineage model depends on this irreversibility.
* Rollback is forbidden because it would create ambiguity in historical snapshot interpretation. A "rollback" is a new version creation.
* The exactly-one-ACTIVE invariant must be tested at both layers: the partial unique index (DB layer) and the atomic swap transaction (application layer) are independent safeguards.

---

### Rollback Boundaries

Config version records are never deleted. "Rollback" is new version creation. This is by design.

---

### Exit Criteria

1. Exactly-one-ACTIVE enforced by DB-layer partial unique index
2. Atomic activation completes without zero-ACTIVE window
3. Rollback prohibition enforced and logged as GovernanceViolation with SEVERITY: CRITICAL
4. Historical config resolution correct for any past date
5. Config version reference correct on newly generated snapshots

---

---

## 13. PHASE 9 — COMPLIANCE WORKFLOW ENABLEMENT

---

### Objective

Implement the compliance governance workflow. Compliance is the last enablement step because it requires all data-producing services to be operational to accurately enumerate scope manifests.

---

### Components

* Compliance workflow state machine: REQUESTED → UNDER_REVIEW → APPROVED_FOR_ACTION → IN_EXECUTION → COMPLETED_DELETED / COMPLETED_ANONYMIZED
* Scope manifest capture at APPROVED_FOR_ACTION: enumerates all tables and record IDs in scope; inserted into `compliance_audit.scope_manifests` via compliance pathway SA
* **Pre-action audit hard gate** (FAD-4): before IN_EXECUTION begins, verify a PRE_ACTION entry exists in `compliance_audit.deletion_log`; if absent, block transition and raise GovernanceGateViolation incident
* Deletion execution: compliance pathway SA deletes records per scope manifest; sets `status = COMPLIANCE_DELETED` on `warehouse.student_snapshots` rows using column-level UPDATE grant
* POST_ACTION audit entry: written at completion via compliance pathway SA; failure to write post-action entry is itself an incident
* At-most-one-active workflow: duplicate workflow for same student rejected
* Survivability guarantee: `compliance_audit.deletion_log` rows survive operational deletions because they have no FK dependencies on operational or warehouse tables

---

### Dependencies

* Phase 2 exit criteria satisfied (compliance_audit schema exists with correct INSERT-only grants)
* Phase 3, Phase 5, Phase 7 exit criteria satisfied (all data-producing services must be operational for accurate scope enumeration)

---

### Validation Checkpoints

1. At-most-one-active workflow: creating duplicate workflow for same student is rejected
2. **Pre-action hard gate**: attempt IN_EXECUTION without PRE_ACTION entry — blocked; GovernanceGateViolation log entry with `SEVERITY: CRITICAL`
3. **Survivability**: delete all `student_trigger_data` rows for a test student; verify `compliance_audit.deletion_log` rows for that student still exist
4. Snapshot `status = COMPLIANCE_DELETED` set after compliance deletion; row exists but is excluded from operational queries
5. **Report survivability**: reports generated before deletion remain accessible (warehouse rows not subject to cascade)
6. Standard SA cannot INSERT, UPDATE, or DELETE on `compliance_audit` schema — `insufficient_privilege`

---

### Observability Requirements

* Compliance execution log entries per spec/06 §2.9 and §9
* Pre-action gate block: GovernanceGateViolation with `SEVERITY: CRITICAL`, unmet_preconditions list, correlation_id
* Compliance completion log: tables_affected, record_counts_per_table, outcome, correlation_id
* Survivability confirmation: post-completion query logged confirming compliance_audit rows intact

---

### Governance Implications

* The pre-action audit hard gate is a FAD-4 architecture decision, not an implementation preference. No bypass path is permitted for any reason.
* The compliance pathway SA is the only entity with UPDATE privilege on any warehouse table. This privilege is column-scoped to `status` on `warehouse.student_snapshots` only.
* Compliance audit records are permanent. No archival or deletion path exists for `compliance_audit` schema.

---

### Rollback Boundaries

Compliance workflow execution is irreversible by design. PARTIALLY_COMPLETED workflows require manual triage via the compliance audit log. No automated rollback exists.

---

### Exit Criteria

1. Compliance workflow state machine functional end-to-end
2. Pre-action hard gate enforced (missing PRE_ACTION entry blocks IN_EXECUTION)
3. Compliance audit survivability confirmed (rows persist after operational deletions)
4. Snapshot COMPLIANCE_DELETED status set correctly via compliance pathway SA
5. Standard SA blocked from any write to compliance_audit schema

---

---

## 14. PHASE 10 — OBSERVABILITY & REPLAY DIAGNOSTICS

---

### Objective

Validate that the operational observability layer is complete and correct across all phases. This phase does not add new services — it validates and hardens existing observability against the spec/06 §15 acceptance criteria. Incomplete observability is a governance defect.

---

### Components

* Correlation/causation chain validation: end-to-end trace from sync job → snapshot finalization → report generation; single `correlation_id` → `causation_id` chain reconstructable without querying application state
* Governance transition log completeness: every FINALIZED, REPORT_PUBLISHED, config ACTIVE, and compliance IN_EXECUTION transition has a governance-quality log entry with required fields
* Replay differentiation test: replay ingestion run confirmed as `execution_type: replay` with `causation_id` pointing to original job, duplicate detection entries
* Fingerprint divergence diagnostics: simulated fingerprint divergence at regeneration; component-level diff logged
* Stale AI detection end-to-end: AI TTL expiry simulation; `stale_insight_served` log with `stale_for_hours`
* Stuck workflow detection: job that fails mid-execution without cleanup; stuck workflow alert at SEVERITY: MEDIUM after heartbeat timeout

---

### Dependencies

* Phase 5, Phase 6, Phase 7 exit criteria satisfied

---

### Validation Checkpoints

All 8 spec/06 §15 acceptance criteria must be met:

| AC | Description |
|---|---|
| AC-1 | Cross-domain correlation_id → causation_id chain reconstructs multi-hop lineage |
| AC-2 | FINALIZED governance transition entry contains full 5-component fingerprint_components |
| AC-3 | Historical regeneration log contains execution_type: regeneration, fingerprint_match, divergence_flag |
| AC-4 | GHL webhook origin_source: ghl; derived from platform routing, not from webhook payload |
| AC-5 | compliance_audit rows queryable after student operational data deleted |
| AC-6 | Student email never appears in any log stream entry (verified by log scan) |
| AC-7 | Job exceeding 60s SLA emits within_sla: false; HIGH alert raised |
| AC-8 | Phase failure in snapshot orchestration produces error_class and recovery_path log entry |

---

### Observability Requirements

Phase 10 validates observability — no new infrastructure added. The exit criteria are the AC-1 through AC-8 checklist above.

---

### Governance Implications

A governance boundary crossing without a governance-quality log entry is a telemetric gap that reduces forensic capability even if the database audit record exists. Phase 10 confirms that no governance boundary in the platform is telemetrically dark.

---

### Exit Criteria

All 8 spec/06 §15 acceptance criteria (AC-1 through AC-8) satisfied and verified by test.

---

---

## 15. PHASE 11 — OPERATIONAL DASHBOARDS

---

### Objective

Implement role-differentiated read-only dashboard API endpoints. All data is served from PostgreSQL; no dashboard endpoint queries SQL Server directly. Dashboards observe the governed system; they do not participate in governance state transitions.

---

### Components

* Student operational view: risk classification, priority score, AI insights (with stale flag), lifecycle position
* Historical view: finalized snapshots per student, per-month trend analytics, point-in-time state reconstruction
* Governance operations dashboard: governance transition log, fingerprint divergence alerts, config version activation history, compliance workflow status
* Report dashboard: publication history, lineage versions, regeneration history, divergence flags
* Alerts dashboard: CRITICAL/HIGH/MEDIUM alert queue with resolution status
* **Role-differentiated access**: mentor sees assigned students only; super mentor sees supervised mentors' students (transitive rule); operator sees all; compliance_reviewer sees compliance dashboard; config_admin sees config governance dashboard; admin sees all

---

### Dependencies

* Phase 3, Phase 5, Phase 6, Phase 7, Phase 8, Phase 10 exit criteria satisfied

---

### Validation Checkpoints

1. Mentor endpoint returns only assigned students (not all students)
2. Super mentor transitive visibility: returns all students of supervised mentors
3. Historical report endpoint: zero SQL Server queries; reads from warehouse schema only
4. Governance dashboard: displays full governance transition timeline for a given correlation_id
5. Alert dashboard: CRITICAL alerts surface at page load; unacknowledged alerts are not silently dismissed
6. Compliance dashboard: accessible to compliance_reviewer only; all other roles receive 403

---

### Observability Requirements

* All dashboard API calls logged: actor_identity, role, endpoint, response_size, duration_ms, outcome, correlation_id
* Role authorization failures logged as `error_class: AuthError` with `SEVERITY: HIGH`

---

### Governance Implications

Dashboard APIs are read-only. No dashboard endpoint may trigger a governance state transition. Dashboard APIs observe the governed system; they are not part of it.

---

### Exit Criteria

1. All role-differentiated endpoints return correct scoped data
2. Historical view reads from warehouse schema only
3. Governance operations dashboard displays correlation_id trace
4. Alert dashboard surfaces unacknowledged CRITICAL/HIGH alerts
5. Role authorization enforced (unauthorized access test cases pass)

---

---

## 16. PHASE 12 — PRODUCTION GOVERNANCE READINESS

---

### Objective

Certify that the full system meets all governance readiness requirements before LIVE execution is enabled. This phase is the final gate before any outbound communication, finalization job, or compliance operation runs in LIVE mode. Governance readiness — not dashboard completion — is the production milestone.

---

### Components

* LIVE enablement gate: formal sign-off that Phase 1–11 exit criteria are all met
* Replay validation: historical replay of a test month produces identical output to the original run
* Compliance survivability test: end-to-end compliance workflow against test data; audit trail persistence confirmed
* Audit export test: compliance_reviewer can export audit log for a completed workflow
* Observability completeness gate: spec/06 §15 AC-1 through AC-8 all satisfied
* Security validation: three-SA permission model verified; no superuser in application code; PII redaction confirmed by log scan
* SLA validation: snapshot batch completes within target; historical regeneration ≤ 60 seconds
* **SHADOW→LIVE transition**: explicit operator approval; `EXECUTION_MODE` toggled to LIVE; first LIVE execution logged with governance transition entry

---

### Dependencies

* All Phase 1–11 exit criteria satisfied

---

### Unresolved Concerns That Block This Phase

| Concern | Source | Severity |
|---|---|---|
| US-1: Authentication mechanism not specified | spec/09 §14 | HIGH — blocks multi-user LIVE deployment |
| US-2: SQL Server read-only at SQL Server RBAC level unverified | spec/09 §14 | HIGH — must be verified at SQL Server level, not just application convention |
| UO-1: Log aggregation platform and DPA not specified | spec/06 §16 | HIGH — required before PII flows through log pipeline |
| UO-2: Distributed scheduler coordination strategy not specified | spec/06 §16 | HIGH — APScheduler in-memory job store cannot coordinate across horizontal instances |

---

### Validation Checkpoints

1. All spec/06 §15 AC-1 through AC-8 satisfied
2. All spec/09 §13 AC-1 through AC-7 satisfied
3. US-1 resolved (authentication implemented)
4. US-2 verified (SQL Server read-only confirmed at RBAC layer)
5. UO-1 resolved (log aggregation platform selected; DPA verified)
6. UO-2 resolved (scheduler coordination strategy confirmed)
7. Replay validation: test month replay produces identical output to original run
8. SLA: snapshot batch ≤ 60s average per student; historical regeneration ≤ 60s total
9. Compliance survivability end-to-end test passed
10. SHADOW→LIVE transition logged as governance transition entry with authorized actor identity

---

### Governance Implications

LIVE mode activation is itself a governance event and must be logged as one. The first outbound communication in LIVE mode must have a correlated governance transition log entry that includes `execution_mode: LIVE`, actor identity, authorization basis, and correlation_id.

---

### Exit Criteria

ALL of the following must be true before LIVE execution is enabled:

1. Phase 1–11 exit criteria all satisfied
2. AC-1 through AC-8 from spec/06 §15 all satisfied
3. AC-1 through AC-7 from spec/09 §13 all satisfied
4. US-1 and US-2 resolved
5. UO-1 and UO-2 resolved
6. Replay validation passed
7. Compliance survivability test passed
8. SLA thresholds met
9. SHADOW→LIVE transition logged with governance transition entry and authorized actor identity

---

---

## 17. ARCHITECTURE-PRESERVATION RULES

Implementation teams must treat the following as production defects, not preferences:

| Rule | Prohibited Action | Correct Behavior |
|---|---|---|
| AP-1 | UPDATE or DELETE on `warehouse.student_snapshots` or `warehouse.snapshot_ai_narratives` by standard SA or finalization SA | No UPDATE/DELETE grants; compliance pathway column-level UPDATE on `status` only |
| AP-2 | UPDATE or DELETE on any `warehouse.monthly_reports` row | No UPDATE/DELETE grants on warehouse schema |
| AP-3 | FINALIZED → any prior state transition in snapshot lifecycle | FINALIZED is terminal; reverse transitions blocked at application and DB |
| AP-4 | REPORT_PUBLISHED → any prior state transition | REPORT_PUBLISHED is terminal |
| AP-5 | Config version SUPERSEDED → ACTIVE transition | Create a new version reproducing prior values instead |
| AP-6 | Assigning `lineage_version = 1` to a regenerated report | Regeneration always increments; `parent_report_id` must be set |
| AP-7 | Any SQL Server write from any service or script | FAD-5; SQL Server connection is read-only; no exceptions |
| AP-8 | Querying SQL Server or `student_trigger_data` during report generation or regeneration | FAD-2; reports read from warehouse schema only |
| AP-9 | Modifying `warehouse.snapshot_ai_narratives` after finalization | FAD-1; AI text in snapshot is a permanent physical copy |
| AP-10 | AI provider call during historical regeneration | AI content reproduced from physical copy; no new LLM calls |
| AP-11 | PII in any log entry | Email → `***@***`; phone → `***`; name → `[REDACTED]`; UserID → opaque hash only |
| AP-12 | AI insight content text in any log entry | AI content is never logged; metadata only (spec/06 §2.6) |
| AP-13 | Observability system storing student data as a searchable corpus | Telemetry minimization; observability is not a shadow data warehouse |
| AP-14 | Beginning IN_EXECUTION on compliance workflow without verified PRE_ACTION audit entry | FAD-4 pre-action hard gate is non-negotiable |
| AP-15 | Enabling LIVE mode without Phase 12 certification | LIVE mode requires explicit governance sign-off |

---

---

## 18. SCOPE-SPECIFIC EXECUTION

---

### MVP

MVP may reduce behavior but MUST NOT violate architectural invariants.

**Mandatory at MVP:**
* Three-schema PostgreSQL architecture with correct permission grants (Phase 2 — non-negotiable)
* SQL Server read-only boundary (FAD-5, Phase 3 — non-negotiable)
* Structured JSON logging with correlation_id (Phase 1 — non-negotiable)
* SHADOW mode default (Phase 1 — non-negotiable)
* Config Version Registry with V1 seed (Phase 2 — non-negotiable)

**MVP may defer:**
* Snapshot orchestration and report generation (Phases 5, 7)
* AI enrichment beyond basic generation (Phase 6)
* Compliance workflow (Phase 9)
* Historical regeneration (Phase 7 sub-feature)
* Config version proposal/approval management plane (Phase 8 — read path mandatory; management plane may defer)
* Replay validation (Phase 10)
* Governance operations dashboard (Phase 11 sub-feature)

### STANDARD

Adds to MVP: full snapshot orchestration (Phase 5), AI enrichment through AI_REVIEWED (Phase 6), monthly report generation (Phase 7, through publication), config version management plane (Phase 8), core observability validation (Phase 10 subset), operational and historical dashboard views (Phase 11 core).

### PRODUCTION

Adds to STANDARD: historical regeneration (Phase 7), compliance workflow (Phase 9), full observability and replay diagnostics (Phase 10 complete), governance operations and compliance dashboards (Phase 11 complete), Phase 12 production governance readiness certification, LIVE mode enabled only after Phase 12.

---

---

## 19. VALIDATION GATE CATALOGUE

| Gate | Triggered by | Required Evidence |
|---|---|---|
| VG-1 | Phase 1 exit | Service in SHADOW mode; structured logs emitting; three SA credentials wired |
| VG-2 | Phase 2 exit | `alembic upgrade head` succeeds; three-SA permission model verified; V1 seed ACTIVE |
| VG-3 | Phase 3 exit | Double-sync produces identical state; FAD-5 verified by query log |
| VG-4 | Phase 4 exit | Timeline events carry correct origin_source; replay dedup confirmed |
| VG-5 | Phase 5 exit | Finalized snapshot unmodifiable by standard SA; FAD-1 AI isolation confirmed |
| VG-6 | Phase 6 exit | AI force-refresh does not modify finalized snapshot AI content |
| VG-7 | Phase 7 exit | Report reads from warehouse only; regeneration creates new lineage version; original unchanged |
| VG-8 | Phase 8 exit | Exactly-one-ACTIVE enforced; rollback prohibition tested; historical resolution correct |
| VG-9 | Phase 9 exit | compliance_audit rows persist after operational deletions; pre-action gate tested |
| VG-10 | Phase 10 exit | spec/06 §15 AC-1 through AC-8 all satisfied |
| VG-11 | Phase 11 exit | Role-differentiated endpoints correct; unauthorized access blocked |
| VG-12 | Phase 12 exit | All prior gates satisfied; US-1, US-2, UO-1, UO-2 resolved; LIVE authorized |

---

---

## 20. ACCEPTANCE CRITERIA

**AC-1 — Architecture-Preserving Rollout**
Given Phases 1–12 executed in sequence, when production deployment is complete, then all INVARIANT-1 through INVARIANT-7 (spec/03 §40) are enforced simultaneously at the database layer and application layer.

**AC-2 — Governance-Safe Implementation**
Given any implementation team member follows these build phases, when any governance-sensitive operation runs, then the corresponding governance telemetry entry exists in the database audit log and the operational log simultaneously, correlated by `correlation_id`.

**AC-3 — Reproducibility-Safe Execution**
Given a finalized snapshot for month M, when a report is generated for month M in any subsequent month, then the output is identical regardless of the current AI model, prompt version, or config version.

**AC-4 — Replay-Safe Orchestration**
Given any job in the platform (sync, snapshot, report, AI generation), when that job is executed twice with the same inputs, then the second execution produces no duplicate records and no duplicate side effects.

**AC-5 — Observability-First Readiness**
Given LIVE mode is enabled, when any governance boundary is crossed, then the structured log entry and the database audit record both exist and are correlated by `correlation_id` within the same execution window.

**AC-6 — Immutable Historical Protection**
Given a finalized snapshot or published report, when any code path attempts UPDATE or DELETE using a non-compliance-pathway SA, then the database rejects the operation with `insufficient_privilege`; the rejection is logged.

---

---

## 21. REFERENCES

| Document | Role |
|---|---|
| `spec/01_requirements.md` | FADs, NFRs, scope behaviors, configuration thresholds |
| `spec/03_state_transition_rules.md` | State machines; INVARIANT-1 through INVARIANT-7 |
| `spec/04_idempotency_concurrency.md` | Idempotency keys; concurrency invariants; irreversible operations |
| `spec/05_external_integrations.md` | SQL Server sync boundary; GHL ingestion; AI provider integration |
| `spec/06_observability_operations.md` | Universal log schema; governance transition entries; AC-1 through AC-8 |
| `spec/07_api_contracts.md` | API endpoints; governance-specific error codes |
| `spec/08_data_model.md` | Conceptual data model; schema isolation; data invariants |
| `spec/09_security_privacy.md` | Three-SA model; RBAC; schema isolation; security acceptance criteria |
| `spec/09_warehouse_physical_architecture.md` | Physical storage; migration readiness; permission grants |
| `spec/10_pre_migration_storage_validation.md` | Pre-authoring validation; migration risk; benchmarking |
| `alembic/versions/0002_warehouse_schema.py` | Warehouse and compliance_audit migration |
| `alembic/versions/0003_config_version_registry.py` | Config version registry migration with V1 seed |
| `execution/implementation_plan.md` | Service implementation order; hard dependencies; rollout model |
| `PROGRESS.md` | Authoritative record of delivered work |

---

## END OF FILE
