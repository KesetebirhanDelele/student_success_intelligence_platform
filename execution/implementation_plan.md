# execution/implementation_plan.md

---

## LAYER 4 — EXECUTION PLAN (BUILD)

---

> **Version note:** This file was completely rewritten on 2026-05-25 to reflect the finalized governed historical intelligence platform architecture. The previous version described a feature-first sequencing model (Foundation → Outreach → Decision Engine → State → LLM → Failure → UX) that is insufficient for the governed architecture. That model treated dashboard completion as the final milestone; governance readiness is the correct final milestone.

---

## 1. PURPOSE

This file defines:

* Authoritative record of what has been delivered (Phases 1–5 + architectural hardening)
* Canonical service implementation order for all remaining work
* Hard dependencies between services and why they exist
* Orchestration, lineage, and governance dependency chains
* MVP / STANDARD / PRODUCTION strategy recast for the governed architecture
* SHADOW → LIVE rollout model with enablement gates
* Operational readiness model and production certification
* Failure and recovery execution rules per service domain
* Unresolved implementation concerns blocking production go-live

---

## 2. BUILD PRINCIPLES

---

### 2.1 Governance-First

Architecture first, features second. The three-schema PostgreSQL model, service account separation, Config Version Registry, and compliance audit schema must be established before any service writes to governed schemas. This is a hard sequencing constraint, not a preference.

### 2.2 Observability Before LIVE

Structured observability — JSON log schema, correlation_id propagation, governance transition log entries — must be operational before LIVE execution of any governance-sensitive workflow. Running a snapshot finalization job without a governance-quality log entry is a spec/06 defect.

### 2.3 Idempotency From the First Record

Idempotency keys must be enforced from the first write. A service that writes its first record without an idempotency key and adds one later has created a window of non-idempotent records that cannot be retroactively made safe.

### 2.4 Lineage-Aware by Construction

Every service must carry attribution fields (`origin_source`, `origin_authority`, `attribution_timestamp`) from its first event. Retrofitting lineage after records exist is an audit gap.

### 2.5 MVP May Reduce Behavior, Not Architecture

MVP scope may skip features. It may not violate architectural invariants. The three-schema architecture, SQL Server read-only boundary, SHADOW mode, and Config V1 seed are mandatory at all scope tiers including MVP.

### 2.6 Dashboard Is Not the Final Milestone

Dashboard completion is a STANDARD tier milestone. Production governance readiness — confirmed by Phase 12 certification — is the production milestone.

---

## 3. DELIVERED PHASES (AUTHORITATIVE RECORD)

---

The following phases have been delivered as of 2026-05-25. For per-task detail, see `PROGRESS.md`.

### Phase 1 — Core MVP

* FastAPI service, PostgreSQL and SQL Server connectivity, health endpoint, scheduler shell, dashboard shell
* Single-schema PostgreSQL (pre-warehouse-architecture)

### Phase 2 — GHL Integration

* Phone-based contact lookup, GHL message cache, SHADOW read-only outreach mode

### Phase 3 — AI Insights

* LLM generation, unified timeline, student notes, right-side drawer

### Phase 4 — Operational Intelligence

* Segments, payment tracking, source routing, batch processing, work queue, priority scoring

### Phase 5 — Student Lifecycle Tabs

* Six lifecycle tabs, action bars, quick action logging, campaign activity tracking

### Architecture Hardening (Phase 7 in PROGRESS.md)

* Alembic migration support with baseline migration 0001
* Warehouse-preparation indexes
* Service extraction: priority, payment, alerts, date utilities

### Architecture Harmonization & Pre-Warehouse Specification Finalization (Phase 8 in PROGRESS.md)

* spec/01 finalized with 6 FADs and NFR completion
* spec/03 extended to all 6 lifecycle domains with INVARIANT-1 through INVARIANT-7
* spec/04 extended with multi-domain idempotency and concurrency model
* spec/09_warehouse_physical_architecture.md authored
* spec/10_pre_migration_storage_validation.md authored with pre-authoring checklist
* spec/07_api_contracts.md evolved to governed historical intelligence API spec
* alembic/versions/0002_warehouse_schema.py authored
* alembic/versions/0003_config_version_registry.py authored
* spec/05_external_integrations.md evolved to governed integration architecture spec
* spec/08_data_model.md evolved to governed historical intelligence data model
* spec/09_security_privacy.md evolved to governed security and privacy architecture spec
* spec/06_observability_operations.md authored as governed observability architecture spec

---

## 4. RECONCILIATION: WHY THE PREVIOUS SEQUENCING IS REPLACED

---

The previous plan used the sequence:

```
Foundation → Outreach → Decision Engine → State → LLM → Failure → UX
```

This sequence was correct for an MVP outreach automation system. It is insufficient for the governed historical intelligence platform because:

| Previous assumption | Finalized architecture reality |
|---|---|
| Single PostgreSQL schema with full application access | Three-schema PostgreSQL with three service accounts and distinct permission profiles |
| LLM integration is an isolated feature (Phase 5) | AI enrichment must precede snapshot finalization; snapshot isolation (FAD-1) requires AI to be functional first |
| Failure handling is a Phase 6 add-on | Idempotency and replay safety must be enforced from the first write in every service |
| Dashboard is the final milestone | Governance readiness (Phase 12 certification) is the production milestone |
| Observability is Phase 6 (near-last) | Observability must be operational before the first governance-sensitive execution |
| Config thresholds are implementation constants | Config thresholds are a governed registry (Config Version Registry); version is locked to each snapshot at generation time |
| No compliance pathway | Compliance workflow with pre-action audit gate is an explicit architecture decision (FAD-4) |
| No lineage model | Reproducibility fingerprint, lineage versioning, and causation_id chain are first-class platform concepts |

The new sequence is:

```
Governance Foundation → Migration Hardening → SQL Server Sync → Timeline Ingestion
→ Config Governance (read path) → Snapshot Orchestration (DRAFT→VALIDATING)
→ AI Enrichment (through AI_REVIEWED) → Snapshot Orchestration (VALIDATING→FINALIZED)
→ Report Publication → Config Governance (management plane)
→ Compliance Workflow → Observability Validation
→ Operational Dashboards → Production Governance Readiness
```

---

## 5. SERVICE IMPLEMENTATION ORDER

---

This section defines the canonical implementation order for all services, with the rationale for each ordering constraint.

---

### 5.1 SQL Server Ingestion Service

**Implements:** `POST /sync/mssql`, idempotent UPSERT to `public.student_trigger_data`

**Must be built before:**
* All other services — this is the data source for all downstream intelligence

**Why sequencing matters:**
* Every derived metric, segment classification, and snapshot is computed from `student_trigger_data`
* Building any downstream service before sync is operational creates a service that operates on stale or empty data, producing records with broken lineage

**Governance blocker:**
* YES — downstream services depend on `student_trigger_data` rows existing with correct attribution fields

**Idempotency requirement:**
* Sync batch idempotency key in `processed_events`; UPSERT on conflict `(UserID)`

**Lineage dependency:**
* `origin_source: mirrored_sql_server`, `origin_authority: sql_server_authoritative` must be set on every synced row from the first sync run

---

### 5.2 Unified Timeline Ingestion Service

**Implements:** `student_timeline_events` append-only ingestion from SQL Server sync, GHL webhooks, and platform operations

**Must be built before:**
* Snapshot orchestration (snapshots emit SnapshotLifecycleEvent to timeline at finalization)
* Any dashboard that displays a student's communication or lifecycle history

**Why sequencing matters:**
* Timeline events are append-only from their first insertion; retroactively adding attribution fields to existing rows is architecturally prohibited
* GHL webhook events arriving before the ingestion service is deployed are permanently unrecorded (no backfill mechanism without replay)

**Governance blocker:**
* Moderate — snapshot finalization emits a timeline event; if timeline ingestion is not functional, finalization log is incomplete

**Idempotency requirement:**
* Event idempotency key in `processed_events`; deduplication key per source type

**Lineage dependency:**
* `attribution_timestamp` = originating event time for all sources; NOT processing time

---

### 5.3 Snapshot Orchestration Service

**Implements:** `snapshot_draft_queue` state machine through DRAFT → VALIDATING → FINALIZED

**Must be built before:**
* Report generation service (reports read from finalized snapshots — FAD-2)

**Must be built after:**
* SQL Server sync (VALIDATING pulls from `student_trigger_data`)
* Config governance read path (VALIDATING binds config version)
* AI enrichment through AI_REVIEWED state (FINALIZED copies AI text — FAD-1)
* Unified timeline ingestion (FINALIZED emits SnapshotLifecycleEvent)
* Phase 2 migrations deployed (warehouse schema and permission grants must exist)

**Why sequencing matters:**
* A snapshot written to `warehouse.student_snapshots` before the schema permission grants are in place is written with incorrect access control
* A snapshot finalized before AI enrichment is functional will freeze stale or absent AI content — the most significant FAD-1 implementation risk

**Governance blocker:**
* YES — FINALIZED is the primary governance boundary. All invariants depend on this service being built correctly before it writes any production records.

**Idempotency requirement:**
* DRAFT idempotency key: `(student_id, snapshot_month, 'DRAFT')` in `snapshot_draft_queue`
* Finalization is once-per-`(student_id, snapshot_month)`; duplicate attempts return existing row

**Lineage dependency:**
* `fingerprint_config_registry_version` bound at VALIDATING
* Full 5-component fingerprint locked at FINALIZED
* Finalization SA used exclusively for warehouse INSERT

---

### 5.4 Config Resolution Service

**Implements:** ACTIVE config version read; config version proposal/approval/activation management plane

**Must be built before:**
* Snapshot orchestration's VALIDATING sub-phase (VALIDATING reads ACTIVE config version)

**Why sequencing matters:**
* Every snapshot must reference the config version that was ACTIVE at its VALIDATING time (FAD-3)
* Building snapshot orchestration before a reliable config read service produces snapshots with broken `fingerprint_config_registry_version` — an audit gap that cannot be corrected retroactively

**Governance blocker:**
* YES — config version binding is a reproducibility fingerprint component; a snapshot with a null or incorrect config version reference violates FAD-6

**Idempotency requirement:**
* Atomic swap transaction is itself the idempotency mechanism; partial unique index prevents double-ACTIVE at DB layer

**Lineage dependency:**
* All prior config versions retained with `activated_at` / `superseded_at` for historical reconstruction

---

### 5.5 AI Enrichment Orchestration Service

**Implements:** AI insight generation, versioning, TTL, force-refresh idempotency, stale serving, snapshot isolation

**Must be built before:**
* Snapshot orchestration's FINALIZED boundary (FINALIZED copies AI_REVIEWED text from `ai_insights`)

**Must be built after:**
* SQL Server sync (AI prompts use student metrics from `student_trigger_data`)
* Config resolution service (TTL is configurable via `ai_insight_ttl_hours` in active config)

**Why sequencing matters:**
* A snapshot finalized before AI enrichment is available either (a) has no AI content — violating the snapshot completeness requirement, or (b) uses stale placeholder content — producing a misleading reproducibility fingerprint

**Governance blocker:**
* YES — for snapshots to be reproducible (FAD-1, FAD-6), AI content must be available and correctly attributed before finalization

**Idempotency requirement:**
* Force-refresh idempotency key: `(student_id, insight_type, date_period, prompt_version, version_number)`

**Lineage dependency:**
* `prompt_version` and `model_used` locked at generation time; immutable after AI_GENERATED state
* `causation_id` set to parent job correlation_id when triggered by snapshot batch

---

### 5.6 Report Generation Service

**Implements:** Monthly report assembly from finalized snapshots; `warehouse.monthly_reports` lifecycle through REPORT_PUBLISHED; `warehouse.report_audit_log`

**Must be built before:**
* Historical regeneration (requires at least one REPORT_PUBLISHED row to regenerate from)
* Report dashboard (requires published reports to exist)

**Must be built after:**
* Snapshot orchestration (requires finalized snapshots for the target month)

**Why sequencing matters:**
* FAD-2: report generation must read exclusively from `warehouse.student_snapshots` and `warehouse.snapshot_ai_narratives`; a report service built before finalized snapshots exist has no validated data source
* Building report generation after a first production finalization run ensures the service is tested against real warehouse data, not synthetic data that may not reflect AI narrative structure

**Governance blocker:**
* YES — REPORT_PUBLISHED is an irreversible governance boundary; the service must be correct before it crosses it

**Idempotency requirement:**
* Report idempotency key: `hash(cohort_id, report_month, template_version, lineage_version)` in `processed_events`

**Lineage dependency:**
* `source_snapshot_fingerprint_json` captured at report generation start
* `report_audit_log` entry written before each state transition completes

---

### 5.7 Publication Workflows

**Implements:** Report publication API endpoints: `REPORT_APPROVED → REPORT_PUBLISHED` boundary; audit log entry at publication

**Must be built before:**
* Historical regeneration (publication history must exist)

**Must be built after:**
* Report generation service (publication is a transition on an existing REPORT_GENERATED row)

**Why sequencing matters:**
* Publication is an irreversible governance boundary; the publication service must enforce immutability from its first execution
* Building publication before the report generation service exists creates a publication service with no testable input

**Governance blocker:**
* YES — REPORT_PUBLISHED immutability is a platform invariant (INVARIANT-1)

---

### 5.8 Compliance Workflow Service

**Implements:** Compliance workflow state machine; scope manifest capture; compliance_audit writes via compliance pathway SA; deletion/anonymization execution

**Must be built last among data services** (see rationale):

**Must be built after:**
* All data-producing services (Phase 3, 5, 6, 7) — accurate scope manifest enumeration requires all tables to exist and contain representative records
* Phase 2 compliance_audit schema and permission grants

**Why sequencing matters:**
* The compliance scope manifest at APPROVED_FOR_ACTION enumerates every record across every table that will be affected. If a table doesn't exist yet or contains no production data, the scope manifest is inaccurate.
* Building compliance workflow before all services are operational produces scope manifests with incomplete table coverage — a compliance accuracy defect.

**Governance blocker:**
* YES — the pre-action audit hard gate (FAD-4) must be enforced from the compliance workflow's first execution

**Idempotency requirement:**
* At-most-one-active workflow per student; duplicate workflow creation rejected

---

### 5.9 Replay and Regeneration Workflows

**Implements:** Historical report regeneration with lineage versioning; fingerprint divergence detection; replay ingestion re-processing

**Must be built after:**
* Report generation service (requires at least one REPORT_PUBLISHED row)
* Observability validation (Phase 10) — replay workflows must produce correct `execution_type: regeneration` and `causation_id` entries

**Why sequencing matters:**
* Regeneration creates a new lineage version based on an existing published report; building it before any reports exist produces a service with no testable input
* Fingerprint divergence detection requires a stored fingerprint (from the original report) and a current fingerprint (from the current system state) — both must exist for the comparison to be meaningful

**Governance blocker:**
* Moderate — regeneration creates a new lineage version; the original is never modified; reversibility is by design

---

### 5.10 Operational Dashboards

**Implements:** Read-only dashboard API endpoints; role-differentiated views; historical, governance operations, report, and alert dashboards

**Must be built last** (among functional services):
* Dashboards observe the governed system; they depend on all data-producing services being operational
* Building dashboards before finalized snapshots exist produces dashboard endpoints that return empty responses — not a useful test

**Governance blocker:**
* No — dashboards are read-only; they do not participate in governance state transitions

---

## 6. HARD DEPENDENCIES

---

| Service | Depends on | Dependency type |
|---|---|---|
| SQL Server sync | Phase 1 (SA credentials, structured logging) | Infrastructure dependency |
| Timeline ingestion | SQL Server sync | Data source dependency |
| Config read path | Phase 2 migration 0003 (config_version_registry, V1 seed) | Schema dependency |
| Snapshot orchestration — DRAFT sub-phase | SQL Server sync, Phase 2 migrations | Data + schema dependency |
| Snapshot orchestration — VALIDATING sub-phase | Config read path (ACTIVE version readable) | Governance dependency |
| AI enrichment | SQL Server sync, Phase 1 (AI provider credentials) | Data + credential dependency |
| Snapshot orchestration — FINALIZED boundary | AI enrichment (AI_REVIEWED state reachable), Timeline ingestion | Lineage + governance dependency |
| Report generation | Snapshot orchestration (finalized snapshots exist) | Data source dependency |
| Publication workflows | Report generation | State machine dependency |
| Historical regeneration | Report generation, Publication workflows | Lineage dependency |
| Compliance workflow | All data-producing services, Phase 2 compliance_audit schema | Scope accuracy + schema dependency |
| Operational dashboards | All functional services | Read source dependency |
| Phase 12 certification | All services, Observability validation (Phase 10) | Governance readiness dependency |

---

## 7. MVP / STANDARD / PRODUCTION STRATEGY

---

### 7.1 What Is Mandatory at All Scope Tiers

The following are not optional at any tier — they are architectural invariants, not features:

| Item | Reason mandatory at all tiers |
|---|---|
| Three-schema PostgreSQL with permission grants | Without schema isolation, warehouse and compliance data are unprotected at the database layer |
| SQL Server read-only boundary | FAD-5; SQL Server write from any tier is a production defect |
| Structured JSON logging with correlation_id | Without this, governance boundary crossings are telemetrically dark |
| SHADOW mode as default | LIVE execution without operational readiness certification is not permitted |
| Config Version Registry with V1 seed | Without V1 ACTIVE, DATA-INVARIANT-4 is violated from the first snapshot attempt |
| Idempotency keys from first write | Non-idempotent records cannot be retroactively made safe |

---

### 7.2 MVP Tier

**Included:**
* Phases 1–4 (infrastructure, migrations, SQL Server sync, timeline ingestion)
* Outreach automation (existing Phase 1–5 delivered work)
* Config resolution read path (V1 ACTIVE readable)
* AI insight generation and TTL management (Phase 6 core)
* Basic operational dashboard (lifecycle tabs, priority scoring, work queue — already delivered)

**Deferred:**
* Snapshot orchestration and finalization (Phase 5)
* Report generation and publication (Phase 7)
* Historical regeneration (Phase 7 sub-feature)
* Config version management plane (Phase 8 — management plane only; read path mandatory)
* Compliance workflow (Phase 9)
* Replay validation (Phase 10)
* Governance operations dashboard (Phase 11 sub-feature)

**MVP Validation Gates (non-negotiable before MVP LIVE):**
1. Phase 2 migration integrity verified
2. SQL Server read-only boundary verified at connection level
3. SHADOW mode operational and logged
4. Config V1 seed ACTIVE

---

### 7.3 STANDARD Tier

**Adds to MVP:**
* Full snapshot orchestration through FINALIZED (Phase 5 complete)
* Monthly report generation through REPORT_PUBLISHED (Phase 7 core)
* Config version management plane — proposal, approval, atomic activation (Phase 8)
* Core observability validation (Phase 10, AC-1 through AC-5)
* Historical report retrieval endpoint (read-only; regeneration deferred to PRODUCTION)
* Extended dashboard views (historical, AI insights, alerts)

**STANDARD Validation Gate:**
Phase 1–8 exit criteria and Phase 10 (AC-1 through AC-5) satisfied before STANDARD deployment.

---

### 7.4 PRODUCTION Tier

**Adds to STANDARD:**
* Historical regeneration with lineage versioning and fingerprint divergence detection (Phase 7 sub-feature)
* Compliance workflow end-to-end (Phase 9)
* Full observability and replay diagnostics (Phase 10, all 8 ACs)
* Governance operations dashboard and compliance dashboard (Phase 11)
* Phase 12 production governance readiness certification
* LIVE mode enabled only after Phase 12

---

## 8. SHADOW → LIVE ROLLOUT MODEL

---

### 8.1 SHADOW Mode Requirements

* All outbound communications (GHL triggers, email, webhooks) execute in SHADOW mode by default
* SHADOW mode must be logged: every outbound communication path emits `execution_mode: SHADOW` in its log entry
* SHADOW mode is not a failure state — it is a mandatory operational phase for all governance-sensitive services
* Scheduler runs in SHADOW mode generate full logs and records; no outbound effects

### 8.2 LIVE Enablement Gates

The following conditions must ALL be true before LIVE execution is authorized:

| Gate | Description |
|---|---|
| Phase 12 exit criteria satisfied | All 12 phases complete with exit criteria verified |
| US-1 resolved | Authentication mechanism implemented |
| US-2 verified | SQL Server read-only confirmed at SQL Server RBAC level (not just application convention) |
| UO-1 resolved | Log aggregation platform selected; DPA verified for PII-containing log streams |
| UO-2 resolved | Scheduler coordination strategy confirmed for horizontal deployment |
| Replay validation passed | Test month replay produces identical output |
| Compliance survivability test passed | compliance_audit rows persist after operational deletions |
| SLA thresholds met | Snapshot batch ≤ 60s average per student; regeneration ≤ 60s total |
| Observability completeness | spec/06 §15 AC-1 through AC-8 all satisfied |

### 8.3 LIVE Activation Process

1. Authorized operator reviews Phase 12 exit criteria checklist (all must be checked)
2. EXECUTION_MODE environment variable set to LIVE on the target deployment
3. Deployment restarted; first request log entry includes `execution_mode: LIVE` and governance transition entry
4. First outbound communication in LIVE mode has correlated governance transition log entry: actor identity, authorization basis, correlation_id
5. Operations team monitors SHADOW→LIVE transition for 24 hours before considering rollout complete

### 8.4 LIVE Mode Cannot Be Set Retroactively

A record created in SHADOW mode cannot be "upgraded" to LIVE mode. If a SHADOW run produces records that should have been LIVE, the correct action is to rerun the job in LIVE mode (which is idempotent due to idempotency keys).

---

## 9. OPERATIONAL READINESS MODEL

---

### 9.1 SHADOW Rollout Expectations

During SHADOW operation:
* Full sync, snapshot, AI enrichment, and report generation pipelines run in SHADOW
* All governance transition log entries are produced
* No outbound communications (GHL messages, notifications) are sent
* Operator can validate all governance invariants against real data before enabling LIVE

### 9.2 Production Certification Checkpoints

| Checkpoint | Evidence required |
|---|---|
| Migration integrity | `alembic upgrade head` verified; three-SA permission model confirmed |
| Sync idempotency | Double-sync produces identical state |
| Snapshot reproducibility | Same inputs produce same finalized snapshot across two runs |
| AI isolation | Force-refresh does not modify finalized snapshot AI content |
| Report lineage | Regeneration creates new lineage version; original unchanged |
| Config governance | Rollback prohibition enforced; exactly-one-ACTIVE enforced |
| Compliance survivability | compliance_audit rows persist after operational deletions |
| Observability completeness | AC-1 through AC-8 from spec/06 §15 all satisfied |
| Security model | Three-SA verification; PII redaction confirmed by log scan |

### 9.3 Replay Validation Expectations

* A test month's snapshot generation is run twice with identical inputs
* Both runs produce finalized snapshots with identical reproducibility fingerprints
* Both runs produce identical `warehouse.snapshot_ai_narratives` content (because AI_REVIEWED source insight is the same)
* A report generated from both snapshot sets produces identical `report_content_json`
* Log stream analysis confirms `execution_type: original` on first run and `execution_type: replay` on second run with correct `causation_id` chain

### 9.4 Operational Staffing Assumptions

* LIVE execution requires at least one operator with access to the alerts dashboard
* CRITICAL alerts (governance violations, compliance gate blocks) require response within 15 minutes
* HIGH alerts (finalization failures, SLA breaches) require response within 1 hour
* Monthly snapshot batch execution is monitored by an operator present during the run
* Compliance workflows require a designated compliance authority before any IN_EXECUTION transition

---

## 10. FAILURE AND RECOVERY EXECUTION RULES

---

### 10.1 SQL Server Sync Recovery

| Failure scenario | Recovery approach | Idempotency guarantee |
|---|---|---|
| SQL Server unreachable mid-batch | Partial sync completes for rows already processed; resume from last successful row on retry | UPSERT on conflict; no duplicates |
| Schema drift (missing columns) | Partial sync completes for intact columns; drift logged; downstream services receive columns available | Drift event logged; no silent corruption |
| Full sync failure | Re-trigger `POST /sync/mssql`; idempotent by design | `processed_events` dedup key |
| Corrupted sync data (bad SQL Server data) | Sync completes; downstream validation flags anomalies; no data blocked | Operational resilience over correctness gating |

### 10.2 Snapshot Recovery

| Failure scenario | Recovery approach | Idempotency guarantee |
|---|---|---|
| DRAFT creation fails | Retry DRAFT creation; idempotency key prevents duplicate | `(student_id, snapshot_month, 'DRAFT')` |
| VALIDATING fails (SQL Server data unavailable) | Draft queue row remains VALIDATING; job resumes at VALIDATING without data loss | VALIDATING is re-runnable from SQL Server mirror |
| FINALIZED transaction fails (warehouse INSERT fails) | Draft queue row remains VALIDATING; retry at finalization without duplicate warehouse row | Partial unique index on `(student_id, snapshot_month) WHERE status='FINALIZED'` |
| AI content unavailable at FINALIZED boundary | Stale AI content frozen; `stale_insight_used: true` logged; finalization continues | FAD-1: frozen at finalization; stale noted in log |
| Month-end batch partial failure | FAILED students recorded in batch log; re-running batch resumes from VALIDATING for failed students only | All idempotency keys prevent reprocessing of successful students |

### 10.3 AI Enrichment Recovery

| Failure scenario | Recovery approach | Idempotency guarantee |
|---|---|---|
| AI provider timeout | Retry with exponential backoff, max 2 retries | Same idempotency key produces same version_number |
| AI provider exhausted | Serve last AI_REVIEWED insight with `stale: true`; no error to caller | Stale serving is a graceful degradation, not a failure |
| Structured output validation failed | Retry up to 2 times; if exhausted, log AI_GENERATION_FAILED, serve stale | No partial row written on validation failure |
| Concurrent force-refresh | Exactly one new row created; losing request receives existing row | Idempotency key `(student_id, insight_type, date_period, prompt_version, version_number)` |

### 10.4 Report Generation Recovery

| Failure scenario | Recovery approach | Idempotency guarantee |
|---|---|---|
| REPORT_GENERATING fails mid-computation | Row remains in REPORT_GENERATING; re-triggering generation retries from REPORT_PENDING via new idempotency key check | Idempotency key in `processed_events` |
| `report_audit_log` write fails | Generation rolled back; row returns to prior state | Audit log entry is a prerequisite, not a side effect |
| No finalized snapshots for target month | Report generation returns `NOT_AVAILABLE`; no partial report created | No warehouse row created for failed month |
| Fingerprint divergence at regeneration | `POTENTIALLY_DIVERGENT` flag set; SEVERITY: MEDIUM alert raised; regeneration continues | Divergence is an audit finding, not a blocker |

### 10.5 Ingestion Recovery

| Failure scenario | Recovery approach | Idempotency guarantee |
|---|---|---|
| GHL webhook delivery failure | GHL retries delivery; platform dedup key prevents duplicate timeline event | Event idempotency key in `processed_events` |
| Timeline event write fails | Event is not written; GHL webhook returns non-200; GHL retries | Retry-safe: dedup key catches re-delivery |
| SQL Server lifecycle event missed | Detected on next sync comparison; event recorded with original attribution_timestamp from SQL Server data | Attribution timestamp = SQL Server source time |

### 10.6 Compliance Interruption Handling

| Failure scenario | Recovery approach | Governance implication |
|---|---|---|
| IN_EXECUTION fails mid-deletion | PARTIAL_COMPLETION_CHECKPOINT entry written; workflow remains in IN_EXECUTION | Manual triage required; automated resume not permitted |
| POST_ACTION audit write fails | Incident raised; DBA manually inserts POST_ACTION entry after verification | Failure to write post-action entry is an incident, not a warning |
| Compliance pathway SA credentials unavailable | Compliance workflow blocked until credentials restored | No bypass; pre-action gate requires SA credentials to be valid |
| PRE_ACTION audit entry absent | IN_EXECUTION transition blocked; GovernanceGateViolation raised; SEVERITY: CRITICAL | Hard gate; no bypass permitted under any circumstances |

---

## 11. DEPENDENCY GRAPH

---

```
SQL Server Ingestion Service
    │
    ├──── Unified Timeline Ingestion
    │         │
    │         └──── Snapshot Orchestration (DRAFT→VALIDATING)
    │
    ├──── Config Resolution Service (read path)
    │         │
    │         └──── Snapshot Orchestration (config binding at VALIDATING)
    │                   │
    │                   ├──── AI Enrichment Orchestration
    │                   │         │
    │                   │         └──── Snapshot Orchestration (FINALIZED boundary)
    │                   │                   │
    │                   │                   └──── Report Generation Service
    │                   │                             │
    │                   │                             ├──── Publication Workflows
    │                   │                             │         │
    │                   │                             │         └──── Historical Regeneration
    │                   │                             │
    │                   │                             └──── Compliance Workflow Service
    │                   │
    │                   └──── Observability Validation (Phase 10)
    │
    └──── Config Resolution Service (management plane)
              │
              └──── Snapshot Orchestration (VALIDATING config binding confirmed)

Operational Dashboards (reads from all services above)
    │
    └──── Production Governance Readiness (Phase 12)
```

---

## 12. ARCHITECTURE-PRESERVATION RULES

---

The following rules are binding on all implementation work. They cannot be waived by scope tier or implementation urgency.

### 12.1 Immutability Rules

* FINALIZED snapshot rows may not be updated or deleted by any application service account except compliance pathway (column-level `status` only)
* REPORT_PUBLISHED report rows may not be updated or deleted by any application service account
* `compliance_audit` rows may not be updated or deleted by any account
* Governance transitions are one-way: FINALIZED, REPORT_PUBLISHED, config SUPERSEDED, and compliance COMPLETED are terminal states

### 12.2 Authority Rules

* SQL Server is read-only; no write of any kind from any code path (FAD-5)
* Report generation reads from warehouse schema only; no SQL Server or `student_trigger_data` queries during generation or regeneration (FAD-2)
* AI text in a finalized snapshot is a physical copy; no AI provider call during historical operations (FAD-1)

### 12.3 Attribution Rules

* `origin_source` and `origin_authority` are immutable on all timeline events after insert
* `attribution_timestamp` reflects the originating event time, not the processing time
* AI attribution metadata (`prompt_version`, `model_used`, `generated_at`) is immutable after AI_GENERATED state
* Config version reference in snapshot (`fingerprint_config_registry_version`) is immutable after VALIDATING

### 12.4 Lineage Rules

* Historical regeneration always creates a new lineage version; it never modifies an existing REPORT_PUBLISHED row
* Config version rollback is forbidden; creating a new version with prior values is the correct path
* Replay ingestion always carries `execution_type: replay` and `causation_id` pointing to the original job

### 12.5 Observability Rules

* PII must not appear in any log entry: email → `***@***`, phone → `***`, name → `[REDACTED]`, raw UserID → opaque hash only
* AI insight content text must not appear in any log entry; metadata only
* Observability systems must not store student data as a searchable corpus (telemetry minimization)

---

## 13. UNRESOLVED IMPLEMENTATION CONCERNS

---

These concerns must be resolved before production go-live. They are documented here and in the relevant spec files.

### Blocking Production Go-Live

| ID | Concern | Severity | Blocking what |
|---|---|---|---|
| US-1 | Authentication mechanism not specified — JWT vs. session vs. API key | HIGH | Multi-user LIVE deployment |
| US-2 | SQL Server read-only boundary must be verified at SQL Server RBAC level, not just application convention | HIGH | FAD-5 production verification |
| UO-1 | Log aggregation platform not specified; DPA verification required before PII flows through log pipeline | HIGH | LIVE execution with PII data |
| UO-2 | Distributed scheduler coordination strategy not specified — APScheduler in-memory job store cannot coordinate across horizontal instances | HIGH | Horizontal deployment of scheduler |

### Blocking STANDARD Tier

| ID | Concern | Severity | Blocking what |
|---|---|---|---|
| UO-3 | Student opaque ID hashing scheme not defined — raw UserID must never appear in logs | MEDIUM | Observability compliance |
| UO-4 | Alert delivery mechanism not specified (email, PagerDuty, Slack) | MEDIUM | Operational alert response |
| US-5 | Compliance audit export credential model not specified | MEDIUM | Compliance workflow STANDARD tier |
| US-6 | GHL webhook signature verification not specified | MEDIUM | GHL ingestion security |

### Deferred (Non-Blocking for STANDARD)

| ID | Concern | Severity | Notes |
|---|---|---|---|
| US-3 | FERPA obligations for aggregate reports after student deletion | MEDIUM | Legal/Compliance decision required |
| US-4 | AI provider DPA for FERPA compliance | MEDIUM | Confirm no AI provider training on student data |
| UO-5 | SIEM forwarding decision for structured log stream | MEDIUM | Security/Compliance decision |
| UO-6 | Causation ID propagation across async job boundaries | MEDIUM | Verification required before Phase 10 |
| US-7 | Row-level security for super mentor | LOW | Blocked by open assumption on supervision graph |
| UO-7 | Governance dashboard access control at API layer | LOW | Dashboard implementation detail |

---

## 14. DOWNSTREAM IMPLICATIONS

---

### For Service Implementation

| Service | Implementation implication |
|---|---|
| Snapshot orchestration | Two sub-phases required: DRAFT→VALIDATING (no AI dependency) and VALIDATING→FINALIZED (AI_REVIEWED dependency); cannot be built as a single monolithic job |
| AI enrichment | Must produce AI_REVIEWED state before snapshot finalization is activated; build order is AI-first, finalization-second |
| Report generation | Must enforce FAD-2 at the service layer (SQL Server query ban during generation); implement as an assertion or architectural constraint, not a guideline |
| Compliance workflow | Must be the last service built; scope manifest accuracy requires all other data-producing services to be operational |

### For Orchestration

| Concern | Implication |
|---|---|
| APScheduler in-memory job store | Cannot coordinate across horizontal instances; UO-2 must be resolved before horizontal deployment |
| Month-end snapshot batch | Must emit per-student progress logs; must be resumable from last successful student without full rerun |
| Report generation | Must be triggerable both by scheduler and by operator API; both paths must be idempotent |
| AI enrichment in batch context | Concurrent AI generation for an entire cohort must respect rate limits; causation_id must flow from the parent snapshot job |

### For Operations

| Concern | Implication |
|---|---|
| CRITICAL alerts | Require 15-minute response time; alert delivery mechanism (UO-4) must be resolved before LIVE |
| Compliance workflow | Requires a designated compliance authority before any IN_EXECUTION transition; operational staffing assumption |
| SHADOW mode monitoring | SHADOW execution produces full logs; operations team must monitor SHADOW runs before LIVE activation |
| Governance dashboard | Required before LIVE mode to provide operators visibility into governance boundary crossings |

### For Deployment

| Concern | Implication |
|---|---|
| Migration 0002 GRANT statements | Must be in the migration file; cannot be applied as separate operational steps |
| Config V1 seed | Must be transactional in migration 0003; deployment without V1 ACTIVE violates DATA-INVARIANT-4 |
| Three-SA credentials | Must be provisioned and verified before deployment; health endpoint must report SA connectivity |
| EXECUTION_MODE | Environment variable; must default to SHADOW; LIVE requires explicit Phase 12 authorization |

### For Support Workflows

| Concern | Implication |
|---|---|
| Compliance workflow support | Support team must not have direct access to compliance_audit schema; compliance_reviewer role via API is the access path |
| Snapshot query | Historical snapshots are accessible via read API; no direct warehouse schema access for support teams |
| Fingerprint divergence | When POTENTIALLY_DIVERGENT flag appears, support team escalates to operator for governance dashboard review |
| Stale AI insight | `stale: true` flag in API response is expected behavior during AI provider outages; support team should not treat it as a system error |

---

## 15. ACCEPTANCE CRITERIA

---

**AC-1 — Architecture-Preserving Rollout**
Given all services implemented in the canonical order defined in Section 5, when the first production execution runs, then all seven platform invariants (INVARIANT-1 through INVARIANT-7, spec/03 §40) are verifiably enforced.

**AC-2 — Governance-Safe Implementation**
Given any phase from Phases 1–12 completed, when its exit criteria are reviewed, then all governance validation gates for that phase are met with concrete evidence (not assertions of intent).

**AC-3 — Reproducibility-Safe Execution**
Given a finalized snapshot for month M, when a report is generated or regenerated for month M in any subsequent month, then the output is identical to the original regardless of current AI model, prompt version, or config version.

**AC-4 — Replay-Safe Orchestration**
Given any service (sync, snapshot, AI generation, report generation), when that service is executed twice with the same inputs and the same correlation_id context, then the second execution produces no duplicate records and no additional side effects.

**AC-5 — Observability-First Readiness**
Given LIVE mode is enabled, when any governance boundary is crossed, then the operational log entry and the database audit record both exist, are correlated by `correlation_id`, and are produced within the same execution window.

**AC-6 — Governance Readiness as Final Milestone**
Given all 12 phases complete, when Phase 12 exit criteria are reviewed, then governance readiness is the explicit milestone confirmed — not dashboard availability or feature completeness.

---

## 16. REFERENCES

| Document | Role |
|---|---|
| `spec/01_requirements.md` | FADs, NFRs, scope behaviors, configuration thresholds |
| `spec/03_state_transition_rules.md` | State machines for all 6 lifecycle domains; INVARIANT-1 through INVARIANT-7 |
| `spec/04_idempotency_concurrency.md` | Idempotency keys; concurrency invariants; irreversible operations |
| `spec/05_external_integrations.md` | Integration philosophy; sync boundary; AI provider; GHL ingestion |
| `spec/06_observability_operations.md` | Universal log schema; governance transition entries; acceptance criteria |
| `spec/07_api_contracts.md` | API endpoints; governance-specific error codes; role-based access |
| `spec/08_data_model.md` | Conceptual data model; schema isolation; data invariants |
| `spec/09_security_privacy.md` | Three-SA model; RBAC; schema isolation; security acceptance criteria |
| `spec/09_warehouse_physical_architecture.md` | Physical storage; migration readiness; permission grants; data flows |
| `spec/10_pre_migration_storage_validation.md` | Pre-authoring validation; migration risk register |
| `alembic/versions/0002_warehouse_schema.py` | Warehouse and compliance_audit schema migration |
| `alembic/versions/0003_config_version_registry.py` | Config version registry with V1 seed |
| `execution/build_phases.md` | Phase-level objectives, components, validation checkpoints, exit criteria |
| `PROGRESS.md` | Authoritative record of delivered work |

---

## END OF FILE
