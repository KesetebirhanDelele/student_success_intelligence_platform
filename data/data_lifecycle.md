# data/data_lifecycle.md

---

## LAYER 10 — DATA LIFECYCLE & GOVERNANCE

---

> **Version note:** This file was completely rewritten on 2026-05-27 to reflect the finalized governance-safe orchestration architecture established in `spec/01_requirements.md` through `spec/10_pre_migration_storage_validation.md`, the warehouse physical architecture, the Config V2 governance model, the alembic migration contracts, and all seven governance-safe runtime contracts. The previous version described MVP-era mutable data governance guidance: a simplistic three-category data model (Source Data / System Data / Derived Data), mutable "system-owned" data semantics with no immutability constraints, SQL Server described as "Primary system data" storage type implying write authority, hardcoded retention periods (12 months / 6–12 months / 90 days) with no Config V2 governance reference, scope-specific behavior (MVP: minimal tracking / STANDARD: defined retention / PRODUCTION: full lifecycle enforcement) implying governance is incrementally acquired, weak deletion semantics ("deletion must be explicit / must be logged / must not break referential integrity") with no compliance pathway requirement, no FINALIZED immutability, no append-only governance, no replay-safe lineage semantics, no warehouse/compliance schema isolation, no attribution continuity requirements, and acceptance criteria that validated only "required fields present" and "change is logged." That architecture is incompatible with the governance-safe orchestration model. Data governance is no longer generic storage management. It is immutable-lineage governance — append-only historical governance, replay-safe lineage governance, warehouse/compliance survivability governance, and attribution continuity governance.

---

## 1. PURPOSE

---

### 1.1 What This Document Defines

This file defines the **governance-safe data lineage architecture** for the Student Success Intelligence Platform (SSIP). It governs:

* How data is classified by governance authority, mutability model, and lineage class
* How immutable-lineage guarantees are enforced across operational, warehouse, and compliance schemas
* How append-only governance applies across all audit and historical domains
* How replay-safe lineage is maintained — replay artifacts cannot overwrite LIVE lineage
* How Config V2 governs all data lifecycle parameters — no hardcoded thresholds
* How warehouse and compliance schemas are physically isolated from operational data
* How attribution continuity is enforced on every governance-quality record
* How deletion and retention are governed through the compliance pathway, not generic cleanup

### 1.2 What This Document Does NOT Define

* Physical DDL, SQL, or migration code — see `alembic/versions/`
* ORM model field definitions — see `app/models.py`
* Retention period numeric values — these are Config V2-governed parameters, not constants defined here
* API request/response shapes — see `spec/07_api_contracts.md`
* State transition rules — see `spec/03_state_transition_rules.md`
* Idempotency and concurrency rules — see `spec/04_idempotency_concurrency.md`
* Warehouse physical column design — see `spec/09_warehouse_physical_architecture.md`
* Pre-migration validation requirements — see `spec/10_pre_migration_storage_validation.md`

### 1.3 Governance Purpose of Data Classification

Data classification in SSIP is not a labeling exercise. It determines:

* Whether a record is mutable, append-only, or immutable
* Which service account holds write authority for each schema
* What replay behavior the record participates in
* What compliance pathway is required before deletion is lawful
* What attribution fields are mandatory
* What survival guarantees apply after operational deletion

Governance architecture is invariant across all environments. Environments differ operationally — they do not differ in data governance semantics.

---

## 2. DATA CLASSIFICATION MODEL

---

### 2.1 Governance-Safe Lineage Classes

Platform data is classified into eight lineage classes. Each class defines ownership, mutability model, retention behavior, replay behavior, and auditability requirements.

| Lineage class | Schema | Origin | Mutability | Replay behavior | Auditability |
|---|---|---|---|---|---|
| `sql_server_authoritative` | SQL Server (external) | `AI_ChatBot_TriggerData` | Read-only — platform never writes | Not replayed; synced on demand | SQL Server is authoritative; platform mirror is derivative |
| `platform_operational` | `public` | Platform-generated outreach, state machine, notes, insights | Mutable via governed state transitions | Replay uses warehouse snapshots, not live operational data | Every mutation carries attribution fields |
| `append_only_governance` | `public` | `outreach_history`, `state_transition_log`, `student_timeline_events`, `processed_events` | INSERT-only — no UPDATE or DELETE | Replay reads these records; never overwrites | Every row is permanent; no modification pathway |
| `immutable_historical` | `warehouse` | `student_snapshots`, `monthly_reports`, `snapshot_ai_narratives`, `report_audit_log` | Append-only after INSERT; FINALIZED rows are unconditionally immutable | Replay sources from these; never writes to these outside REGENERATION lineage | FINALIZED immutability enforced at schema permission layer |
| `compliance_survivability` | `compliance_audit` | `deletion_log`, `scope_manifests`, audit records | Append-only always — no UPDATE or DELETE from any account | Not replayed — compliance records survive all operational actions | Permanent; survives operational deletion; compliance_pathway_user account only |
| `provider_supplementary` | `public` | `ghl_messages`, `student_campaign_activity` | Mutable cache — GHL is real-time source of truth | Replay does not re-dispatch to providers; provider cache reflects last known state | GHL origin_authority = `platform_supplementary` — not authoritative |
| `replay_generated` | `public` (tagged) | Orchestration replay outputs | Append-only INSERT with `execution_type = replay` tag; never overwrites LIVE records | Replay outputs are permanently attributed as replay; never converted to LIVE lineage | Full attribution mandatory: `correlation_id`, `causation_id`, `execution_type = replay`, `governance_scope = REPLAY_ONLY` |
| `config_v2_lineage` | `public` | `config_version_registry` | Append-only rule values; governance metadata columns (status, superseded_by_version_id, deactivated_at) carry column-level UPDATE for `config_admin_user` only | Replay uses `historical_config_version_id` — never the current ACTIVE version | Permanent lineage; SUPERSEDED versions remain fully queryable |

---

### 2.2 SQL Server Authority Boundaries

SQL Server (`AI_ChatBot_TriggerData`) is the authoritative source for student academic and engagement data. The platform holds no write grants to SQL Server (FAD-5). Any write attempt produces `ArchitecturalViolation`.

The platform's `public.student_trigger_data` table is a synced mirror — `origin_authority = sql_server_authoritative`, `origin_source = mirrored_sql_server`. On field conflicts, SQL Server data governs. The mirror is not an authoritative record; SQL Server is.

Sync semantics: `INSERT ... ON CONFLICT DO UPDATE` (upsert). Running the same sync batch twice produces no duplicate records and no additional side-effects (replay-safe by construction, per `spec/04_idempotency_concurrency.md` §3.1).

---

### 2.3 Provider Supplementary Boundaries

GHL (GoHighLevel), Synthflow, SMS, and email providers are classified as `origin_authority = platform_supplementary`. They are delivery vehicles — not authority boundaries. Platform-owned tables are the authoritative record for all outreach state. Provider cache records (`ghl_messages`, `student_campaign_activity`) carry `origin_authority = platform_supplementary` and do not govern eligibility decisions.

---

## 3. MUTABILITY GOVERNANCE

---

### 3.1 Mutable Operational Domains

The following `public` schema tables are mutable through governed state transitions:

| Table | Mutability constraint | Terminal boundary |
|---|---|---|
| `student_trigger_data` | Upserted on sync — full field update per SQL Server source | No terminal state; reflects current SQL Server state |
| `student_outreach_tracking` | State machine transitions only — no direct field mutation | CLOSED is terminal; no transition out of CLOSED |
| `ai_insights` | Version-append — new row per insight generation; no in-place update | Attribution metadata immutable after `AI_GENERATED` state |
| `config_version_registry` | Rule values immutable after INSERT; governance metadata (status, superseded_by_version_id, deactivated_at) mutable by `config_admin_user` only | ACTIVE → SUPERSEDED only outbound transition; rollback is forbidden |
| `student_notes` | Operator-authored notes; mutable by original author within governance window | No terminal immutability — operator notes remain mutable unless compliance workflow initiated |
| `compliance_workflow` | Workflow state transitions only | Terminal states irreversible; pre-action audit is a hard gate before execution |

### 3.2 Append-Only Governance Domains

The following tables are INSERT-only. No UPDATE or DELETE is permitted from any application service account. Enforcement is at both the application layer and the schema permission layer.

| Table | Append-only guarantee | What happens on mutation attempt |
|---|---|---|
| `outreach_history` | One row per outreach attempt — never modified | Schema permission denied; `ArchitecturalViolation` surfaced |
| `state_transition_log` | One row per state transition — FAD-4 enforced | Schema permission denied; `ArchitecturalViolation` surfaced |
| `student_timeline_events` | One row per timeline event — FAD-4 enforced | Schema permission denied; `ArchitecturalViolation` surfaced |
| `processed_events` | Idempotency deduplication store — append-only | Schema permission denied |
| `warehouse.report_audit_log` | Audit entries for report generation and publication | Schema permission denied |
| `compliance_audit.deletion_log` | Compliance deletion audit trail | Schema permission denied; `compliance_pathway_user` INSERT-only |
| `compliance_audit.scope_manifests` | Compliance scope manifests — append-only by design (no `is_current` column — see `alembic/versions/0002_warehouse_schema.py`) | Schema permission denied |

### 3.3 Immutable FINALIZED Domains

The following records become unconditionally immutable upon reaching their terminal governance state. Immutability is enforced at the schema permission layer — not only at the application layer.

| Record type | Immutability trigger | Enforcement | Mutation attempt result |
|---|---|---|---|
| `warehouse.student_snapshots` (FINALIZED) | `lifecycle_state = FINALIZED` transition | `SELECT`-only for standard `app_service_user`; column-level `UPDATE (status)` for `compliance_pathway_user` exclusively (for `COMPLIANCE_DELETED` transition) | `IMMUTABLE_RECORD_VIOLATION` raised |
| `warehouse.snapshot_ai_narratives` | `allows_update = false` after FINALIZED snapshot — FAD-1, INV-6 | `SELECT`-only for all accounts after FINALIZED | `IMMUTABLE_RECORD_VIOLATION` raised; `allows_update = false` confirmed |
| `warehouse.monthly_reports` (REPORT_PUBLISHED) | `lifecycle_state = REPORT_PUBLISHED` transition | `SELECT`-only; no regeneration overwrites existing row — new `lineage_version` row created | In-place overwrite attempt raises schema permission error |
| Config Version (ACTIVE) | Rule field values locked at INSERT | No UPDATE privilege on rule columns for any role | Schema permission denied |

### 3.4 Regeneration Creates Lineage, Not Overwrite

Historical report regeneration does not overwrite `warehouse.monthly_reports` rows. It creates a new row with an incremented `lineage_version`, `execution_type = regeneration`, `sourced_from_warehouse = true`, and a fingerprint comparison result. The original `REPORT_PUBLISHED` row is never modified. Fingerprint comparison is logged at regeneration start: stored fingerprint versus current system fingerprint. Divergence → `POTENTIALLY_DIVERGENT` log warning emitted, even if regeneration proceeds.

---

## 4. STORAGE GOVERNANCE

---

### 4.1 Three-Schema PostgreSQL Architecture

PostgreSQL is divided into three physically isolated schemas with distinct service account access controls. This is FAD-6 (Three-schema privilege separation).

| Schema | Purpose | Mutability | Standard `app_service_user` access | Additional accounts |
|---|---|---|---|---|
| `public` | Operational data — all current state, outreach tracking, AI insights, config registry, idempotency store | Mutable via governed state transitions; append-only log tables | Full read/write (governed) | `config_admin_user` — limited UPDATE on `config_version_registry` governance metadata columns |
| `warehouse` | Immutable historical archive — finalized snapshots, published reports, AI narratives, report audit log | Append-only INSERT; no UPDATE or DELETE from `app_service_user` | SELECT-only | `finalization_service_user` — INSERT into warehouse tables; `compliance_pathway_user` — column-level UPDATE (status) on `student_snapshots` for COMPLIANCE_DELETED transition only |
| `compliance_audit` | Governance-isolated audit trail — deletion records, scope manifests, pre/post-action entries | Append-only always — no UPDATE or DELETE from any account | SELECT-only | `compliance_pathway_user` — INSERT-only |

The `warehouse` and `compliance_audit` schemas have no cross-schema FK dependencies. This ensures compliance audit records survive even if operational records are deleted. Warehouse data can be archived independently of operational state.

### 4.2 SQL Server Storage Authority

SQL Server is a read-only external source. It is not a platform storage tier. Platform services hold no write grants to SQL Server (FAD-5). All application state lives in PostgreSQL. SQL Server is accessed via `SELECT *` sync to avoid schema drift failures.

### 4.3 Schema-Level Access as Final Enforcement

Application-layer guards (service-level checks, ORM constraints) are defense-in-depth. Schema-level access controls are the **final enforcement mechanism**. A governance violation that bypasses application-layer guards will be caught at the schema permission layer. No service account combination can produce:

* An UPDATE to `warehouse.student_snapshots` rule fields (only `status` UPDATE is permitted for `compliance_pathway_user`)
* Any UPDATE or DELETE to `compliance_audit` tables
* A direct write to SQL Server
* An overwrite of `warehouse.snapshot_ai_narratives` after `allows_update = false`

### 4.4 Two-Table Snapshot Strategy

The warehouse uses a two-table design for finalized snapshots (per `spec/09_warehouse_physical_architecture.md` §3.2):

* `warehouse.student_snapshots` — compact metrics row (~400 bytes); indexed for analytical scan performance
* `warehouse.snapshot_ai_narratives` — 1:1 AI text companion (TOAST-eligible); foreign key to `student_snapshots`

The AI narrative table FK is to `student_snapshots`, NOT to `ai_insights`. The text is a physical point-in-time deep copy at FINALIZED time (FAD-1). No FK to `ai_insights` is safe — compliance deletion or cleanup of `ai_insights` would either violate the FK or cascade-delete the frozen copy.

---

## 5. REPLAY AND REGENERATION GOVERNANCE

---

### 5.1 Replay-Generated Records

Replay orchestration produces records that are permanently attributed as replay outputs. These records:

* Carry `execution_type = replay` on every governance-quality field
* Carry `governance_scope = REPLAY_ONLY` — never `LIVE` or `SHADOW_ONLY`
* Carry a new `correlation_id` with `causation_id` pointing to the original execution's `correlation_id`
* Carry `historical_config_version_id` — the Config Version that was ACTIVE at the original execution time; never the current ACTIVE version
* Produce `live_effects_produced = 0` — invariant; non-zero → CRITICAL governance alert (INV-4, AP-RT2)
* Are INSERT-only into `public` schema tables (never into `warehouse` schema)
* Cannot overwrite, backfill, or retroactively modify any LIVE lineage records

A replay execution that produces a non-zero `live_effects_produced` is a governance defect, not an edge case.

### 5.2 Replay Cannot Overwrite LIVE Lineage

Replay records are logically isolated from LIVE lineage at the data layer:

* Replay records in `outreach_history` carry `execution_type = replay` — never aggregated with `execution_type = original` records without explicit filter
* Replay records in `state_transition_log` carry `execution_type = replay` — state machine does not process replay transitions as LIVE transitions
* No replay execution path has INSERT authority into `warehouse` schema tables
* No replay execution can transition a LIVE outreach state machine record

### 5.3 Regeneration Lineage

Historical report regeneration differs from replay orchestration:

* Regeneration reads from `warehouse.student_snapshots` (FINALIZED only); `sourced_from_warehouse = true`
* Regeneration produces a new `warehouse.monthly_reports` row with `lineage_version` incremented and `execution_type = regeneration`
* The original `REPORT_PUBLISHED` row is never modified
* Fingerprint comparison at regeneration start: five-component fingerprint (schema_version, config_registry_version, ai_prompt_version, ai_model_version, report_template_version) compared between stored and current
* `fingerprint_comparison_outcome`: `IDENTICAL`, `POTENTIALLY_DIVERGENT`, or `COMPARISON_UNAVAILABLE`
* `POTENTIALLY_DIVERGENT` → warning log entry; regeneration may proceed; divergence is recorded, not suppressed

### 5.4 Replay-Safe Storage Guarantees

All storage operations must be safe to re-run. Delivering the same data batch twice produces no duplicate records and no additional side-effects. Replay safety is enforced by:

* Upsert semantics for SQL Server mirror (`INSERT ... ON CONFLICT DO UPDATE`)
* Deduplication via `processed_events` table for event-based ingestion
* Unique constraints on `(student_id, origin_source, event_type, attribution_timestamp)` where applicable
* Idempotency keys on all cross-governance-boundary operations (per `spec/04_idempotency_concurrency.md`)

A replay that triggers any additional downstream side-effect (outreach, state transition, report generation) is a replay-safety defect.

### 5.5 Replay Attribution Remains Permanently Queryable

Replay lineage chains are permanent. Replay records are never purged without compliance pathway authorization. The full replay chain — original `correlation_id`, replay `causation_id`, `historical_config_version_id`, `fingerprint_comparison_outcome` — remains queryable to support forensic reconstruction of any historical replay execution.

---

## 6. RETENTION AND DELETION GOVERNANCE

---

### 6.1 Governance-Safe Retention Architecture

Data retention is governed by Config V2 — not by hardcoded periods. No retention period, archive threshold, or purge schedule is a constant defined in this document or in implementation code. All retention parameters are resolved from the ACTIVE Config Version Registry at evaluation time (INV-7).

| Retention domain | Config V2 parameter group | Governance behavior |
|---|---|---|
| Operational outreach records | Group A | Governed by `outreach_retention_days` (resolved at evaluation time) |
| Append-only audit logs | Group A | `outreach_history`, `state_transition_log` — retention governed by Config V2; archive queryability guaranteed |
| Warehouse snapshot records | Permanent unless compliance deletion | FINALIZED snapshots are immutable; deletion requires compliance pathway |
| Compliance audit records | Permanent always | `compliance_audit` records survive all operational deletion; no retention expiry |
| AI insight records | Group A | Active and superseded insight versions; retention governed by Config V2 |
| Config Version Registry records | Permanent | All versions — ACTIVE, SUPERSEDED, DRAFT — remain permanently queryable for historical attribution |

### 6.2 Immutable FINALIZED Retention

`warehouse.student_snapshots` records with `lifecycle_state = FINALIZED` are unconditionally retained. Deletion of a FINALIZED snapshot requires:

1. Compliance workflow initiation through the compliance pathway (`compliance_audit` schema)
2. Pre-action audit entry written before execution begins (hard gate)
3. `compliance_pathway_user` account with column-level `UPDATE (status)` privilege — the only account permitted
4. Transition to `lifecycle_state = COMPLIANCE_DELETED` (not physical row deletion)
5. Post-action audit entry written after execution completes

Physical deletion of a FINALIZED snapshot row is not permitted from any service account. The compliance pathway produces a status transition to `COMPLIANCE_DELETED`, not a DELETE statement.

### 6.3 Compliance Deletion Survivability

Records in `compliance_audit.deletion_log` survive all operational actions, including the deletion of the operational records they describe. This is guaranteed by the absence of cross-schema FK dependencies:

* `compliance_audit` schema has no FK references to `public` or `warehouse` schemas
* An operational record deletion does not cascade to `compliance_audit`
* The compliance audit trail remains queryable even when the associated operational records no longer exist

### 6.4 Append-Only Audit Log Retention

`student_timeline_events`, `state_transition_log`, and `outreach_history` are append-only (FAD-4). These records are not subject to routine deletion. If Config V2-governed retention windows result in archival of these records, the archive must:

* Remain queryable — archive is not purge
* Retain all attribution fields (`correlation_id`, `execution_mode`, `execution_type`, `config_version_id`)
* Preserve the append-only character — no modification during archival

### 6.5 Deletion Prohibition Domains

The following records have no deletion pathway under any circumstances:

| Record type | Why deletion is prohibited |
|---|---|
| `compliance_audit.deletion_log` | Compliance trail must survive the records it describes |
| `compliance_audit.scope_manifests` | Append-only by schema design; no `is_current` flag requiring UPDATE |
| `warehouse.snapshot_ai_narratives` (FINALIZED) | FAD-1 frozen AI copy; `allows_update = false` is permanent |
| `config_version_registry` (any version) | Historical config attribution for replay; SUPERSEDED versions must remain queryable |
| `warehouse.report_audit_log` | Permanent audit record for all report generation and publication events |

### 6.6 Weak Deletion Semantics Are Prohibited

The MVP-era rule "deletion must be explicit / must be logged / must not break referential integrity" is insufficient governance. In the governance-safe data model:

* Deletion is never a generic operation — it is a compliance pathway event or an explicit Config V2-governed archival action
* No operational service account holds DELETE privileges on `warehouse` or `compliance_audit` schemas
* No deletion pathway exists for FINALIZED records without compliance workflow authorization and audit survivability
* Deletion of append-only records is a schema permission violation, not a process violation — the schema enforces it

---

## 7. CONFIG V2 DATA GOVERNANCE

---

### 7.1 Config Version Lineage Permanence

Every Config Version record in `public.config_version_registry` is permanent. SUPERSEDED versions are never deleted. This is required because:

* Finalized snapshots carry `fingerprint_config_registry_version` referencing the Config Version that governed their classification
* A future auditor must be able to retrieve the exact rule set that governed any historical snapshot
* Replay uses `historical_config_version_id` — the Config Version ACTIVE at original execution; deleting that version would break historical reproduction

### 7.2 ACTIVE Version Visibility

Exactly one Config Version is ACTIVE at all times (INV-2). This is physically enforced at the database layer via a partial unique index on `config_version_registry WHERE status = 'ACTIVE'`. Attempting to INSERT a second ACTIVE row raises a unique violation before any application-layer logic can be bypassed (DATA-INVARIANT-4).

### 7.3 Supersession Lineage

Config Version lifecycle produces a permanent supersession chain:

1. Current ACTIVE version: `status = ACTIVE`
2. Activation transaction: ACTIVE row → `status = SUPERSEDED`, `superseded_by_version_id = <new_id>`, `deactivated_at = now()`; new version row → `status = ACTIVE`
3. The supersession chain is append-only — no version is deleted, no `superseded_by_version_id` is overwritten
4. Rollback to a prior version is accomplished by creating a new version record that copies prior values — not by restoring the superseded record (INV-3, FAD-3)

### 7.4 Replay Config Resolution

Replay orchestration always uses `historical_config_version_id` — the Config Version ID that was ACTIVE at the time of the original execution. Replay never uses the current ACTIVE Config Version. This ensures historical simulation uses historically-accurate governance parameters, and current Config Version changes do not alter replay outcomes.

### 7.5 Prospective-Only Activation

Config Version activation is prospective-only (INV-3, FAD-3). A version change affects future classification runs only. Historical snapshots retain their original `fingerprint_config_registry_version` attribution regardless of how many subsequent versions are created. No backdated activation is permitted — the database layer enforces this via the partial unique index (only one ACTIVE row possible at any moment).

---

## 8. ATTRIBUTION GOVERNANCE

---

### 8.1 Attribution Fields Are Mandatory

Every governance-quality record carries the following attribution fields. Null attribution fields surface `ATTRIBUTION_INCOMPLETE` — they are never silently accepted (INV-5).

| Field | Purpose | Null behavior |
|---|---|---|
| `correlation_id` | UUID v4 binding all records from a single request or job to one traceable chain | `ATTRIBUTION_INCOMPLETE` alert |
| `causation_id` | (Where applicable) UUID binding this record to the upstream event that caused it — enables multi-hop lineage reconstruction | Required on replay records; optional on original records |
| `execution_type` | `original`, `replay`, or `regeneration` — distinguishes LIVE lineage from replay and regeneration | `ATTRIBUTION_INCOMPLETE` alert |
| `execution_mode` | `SHADOW`, `LIVE`, or `REPLAY` — the execution mode at record creation time | `ATTRIBUTION_INCOMPLETE` alert |
| `origin_source` | Where the data originated (`mirrored_sql_server`, `ghl_webhook`, `platform_generated`, etc.) | `ATTRIBUTION_INCOMPLETE` alert |
| `origin_authority` | Authority class (`sql_server_authoritative`, `platform_supplementary`) | `ATTRIBUTION_INCOMPLETE` alert |
| `config_version_id` | The Config Version Registry ID governing this record's orchestration context | `ATTRIBUTION_INCOMPLETE` alert |
| `attribution_timestamp` | When the event occurred in the source system (not ingestion time) | `ATTRIBUTION_INCOMPLETE` alert |

### 8.2 Attribution Is Permanent

Attribution fields are never overwritten after record creation. They are part of the immutable lineage chain. An ETL transform, sync operation, or migration that strips, overwrites, or fails to propagate attribution fields is a specification violation.

### 8.3 Replay Attribution Remains Queryable

Replay record attribution (`execution_type = replay`, `causation_id → original correlation_id`, `historical_config_version_id`) is never removed, suppressed, or converted to LIVE attribution. The full replay chain remains queryable for forensic reconstruction.

### 8.4 Fingerprint Lineage

Finalized snapshots carry a five-component fingerprint for historical reproducibility:

| Fingerprint component | Field | Purpose |
|---|---|---|
| Schema version | `fingerprint_schema_version` | PostgreSQL schema version at FINALIZED time |
| Config registry version | `fingerprint_config_registry_version` | Config Version ID governing classification |
| AI prompt version | `fingerprint_ai_prompt_version` | Prompt version used for AI narrative generation |
| AI model version | `fingerprint_ai_model_version` | LLM model version used |
| Report template version | `fingerprint_report_template_version` | Report template version at publication |

`UNKNOWN_V0` in any fingerprint component surfaces an audit-gap indicator — it means the version was not captured at FINALIZED time. This is an observability defect for records generated before fingerprint tracking was implemented, not a permission to omit fingerprint fields on new records.

### 8.5 Observability Telemetry Attribution

Every telemetry event that crosses a data lineage boundary carries the full lineage context (per `spec/06_observability_operations.md` §1.3):

* `origin_source`, `origin_authority`, `correlation_id`, `causation_id` (where applicable), `attribution_timestamp`
* Governance-quality log entries (crossing a governance boundary) carry all five fingerprint components where applicable
* A governance boundary crossed without a corresponding governance-quality log entry is an observability defect

---

## 9. GOVERNANCE INVARIANTS

---

### 9.1 Governance Invariants (INV-1 through INV-7)

All invariants apply in all environments and all execution modes. No environment (LOCAL/STAGING/PRODUCTION) and no execution mode (SHADOW/LIVE/REPLAY/REGENERATION/DEGRADED/MAINTENANCE) relaxes any invariant.

| Invariant | Rule | Data-layer enforcement |
|---|---|---|
| INV-1 | FINALIZED snapshot is immutable — no update, overwrite, or deletion | `warehouse` schema `SELECT`-only for `app_service_user`; only `compliance_pathway_user` holds column-level `UPDATE (status)` for COMPLIANCE_DELETED transition |
| INV-2 | Exactly one Config Version is ACTIVE at all times | Partial unique index on `config_version_registry ((1)) WHERE status = 'ACTIVE'` — DB-enforced |
| INV-3 (FAD-3) | Config Version activation is prospective-only — no backdated activation | Partial unique index ensures only one ACTIVE row; activation transaction marks previous SUPERSEDED before INSERT |
| INV-4 (AP-RT2) | No LIVE effects from replay — `live_effects_produced = 0` on all replay outputs | Replay records carry `execution_type = replay`; no replay execution path has INSERT authority into provider-dispatch tables |
| INV-5 | Attribution continuity — `correlation_id`, `execution_mode`, `execution_type` mandatory on every governance-quality record | `ATTRIBUTION_INCOMPLETE` surfaced on null fields; never silently accepted |
| INV-6 (FAD-1) | FINALIZED_COPY AI narrative immutability — `allows_update = false` after FINALIZED state | `warehouse.snapshot_ai_narratives` is `SELECT`-only after INSERT; `allows_update = false` is permanent |
| INV-7 | No hardcoded thresholds — all orchestration parameters governed by Config Version Registry | No retention period, retry ceiling, concurrency limit, or timing window is a constant in this document or implementation code |

### 9.2 Foundational Architecture Decisions (FAD-1 through FAD-6)

| FAD | Decision | Data-layer implication |
|---|---|---|
| FAD-1 | Frozen AI copy — AI narrative is deep-copied at snapshot FINALIZED time and remains immutable | `snapshot_ai_narratives` FK to `student_snapshots` (not `ai_insights`); physical copy at FINALIZED; `allows_update = false` permanent |
| FAD-2 | Snapshot-centric historical — all longitudinal analysis uses warehouse snapshots, not live operational data | Replay and regeneration read `warehouse` schema; no longitudinal query against `public` operational tables |
| FAD-3 | Prospective-only config activation — no retroactive config version changes | Partial unique index enforcement; `historical_config_version_id` used for replay; no backdating pathway |
| FAD-4 | Append-only audit log — `student_timeline_events` and `state_transition_log` are append-only; no deletions | Schema permission: INSERT-only for these tables; UPDATE/DELETE returns schema permission error |
| FAD-5 | SQL Server read-only boundary — no write grants provisioned; write attempt produces `ArchitecturalViolation` | No write grants exist in SQL Server connection; sync uses SELECT-only connection |
| FAD-6 | Three-schema privilege separation — `public`, `warehouse`, `compliance_audit` with distinct service accounts | `app_service_user`, `finalization_service_user`, `compliance_pathway_user`, `config_admin_user` — each scoped to minimum required privilege |

### 9.3 Append-Only Data Invariants

Per `spec/08_data_model.md` DATA-INVARIANT definitions:

| Domain | Append-only guarantee | Violation consequence |
|---|---|---|
| `outreach_history` | One row per attempt — no UPDATE/DELETE | Schema permission error; `ArchitecturalViolation` surfaced |
| `state_transition_log` | One row per transition — no UPDATE/DELETE | Schema permission error; `ArchitecturalViolation` surfaced |
| `student_timeline_events` | One row per event — no UPDATE/DELETE | Schema permission error; `ArchitecturalViolation` surfaced |
| `warehouse.report_audit_log` | One row per report audit event — no UPDATE/DELETE | Schema permission error |
| `compliance_audit.*` | All tables append-only — no UPDATE/DELETE from any account | Schema permission error |

---

## 10. ACCEPTANCE CRITERIA

---

### Case 1 — Governance Invariant Universality

**Given** any data operation in any environment (LOCAL/STAGING/PRODUCTION) in any execution mode (SHADOW/LIVE/REPLAY/REGENERATION)
**When** the operation would violate INV-1 through INV-7 or FAD-1 through FAD-6
**Then** the violation is rejected; the governance invariant applies without relaxation; no environment-specific override exists

---

### Case 2 — FINALIZED Immutability Enforcement

**Given** a `warehouse.student_snapshots` record with `lifecycle_state = FINALIZED`
**When** any service (other than `compliance_pathway_user` targeting the `status` column) attempts an UPDATE or DELETE
**Then** `IMMUTABLE_RECORD_VIOLATION` is raised; the operation is rejected at the schema permission layer; no silent acceptance occurs (INV-1)

---

### Case 3 — FINALIZED_COPY AI Narrative Immutability

**Given** a `warehouse.snapshot_ai_narratives` record with `allows_update = false`
**When** any account attempts an UPDATE
**Then** the operation is rejected at the schema permission layer; `IMMUTABLE_RECORD_VIOLATION` raised; `allows_update = false` is permanent (INV-6, FAD-1)

---

### Case 4 — Replay Live-Effects Prohibition

**Given** a replay orchestration execution
**When** the execution completes
**Then** `live_effects_produced = 0`; all output records carry `execution_type = replay`; `governance_scope = REPLAY_ONLY`; `historical_config_version_id` used; no LIVE provider dispatch occurred; non-zero `live_effects_produced` → CRITICAL governance alert (INV-4, AP-RT2)

---

### Case 5 — Attribution Continuity in All Environments

**Given** any governance-quality record created in any environment or execution mode
**When** `correlation_id`, `execution_mode`, or `execution_type` is null
**Then** `ATTRIBUTION_INCOMPLETE` is surfaced; the record is not silently accepted as complete; no environment suppresses this check (INV-5)

---

### Case 6 — Config V2 Parameter Resolution

**Given** any orchestration operation requiring a retention period, retry ceiling, concurrency limit, or timing window
**When** the parameter is evaluated
**Then** the value resolves from the ACTIVE Config Version Registry at evaluation time; no hardcoded constant is substituted; no environment-specific override is permitted (INV-7)

---

### Case 7 — Append-Only Audit Log Enforcement

**Given** `outreach_history`, `state_transition_log`, `student_timeline_events`, or any `compliance_audit` table
**When** any service attempts an UPDATE or DELETE
**Then** the operation is rejected at the schema permission layer; the append-only character of the table is permanent (FAD-4)

---

### Case 8 — Compliance Deletion Survivability

**Given** an operational record is deleted or compliance-deleted
**When** the corresponding `compliance_audit.deletion_log` entry is queried
**Then** the audit entry survives; it is not cascade-deleted; the compliance trail is permanent regardless of the operational record's status

---

### Case 9 — Replay Cannot Overwrite LIVE Lineage

**Given** a replay execution that produces `outreach_history` or `state_transition_log` entries
**When** those entries are queried alongside LIVE entries
**Then** replay entries carry `execution_type = replay`; they are distinguishable from LIVE entries; no replay entry is returned as a LIVE record without explicit filter removal; the LIVE lineage is not modified

---

### Case 10 — SQL Server Read-Only Boundary

**Given** any platform service accessing SQL Server
**When** a write operation is attempted
**Then** `ArchitecturalViolation` is produced; no write grants exist; the SQL Server remains read-only authoritative (FAD-5)

---

## 11. REFERENCES

---

| Document | Governance relationship |
|---|---|
| `spec/01_requirements.md` | Platform purpose, 10 operational domains, FAD-1–FAD-6, NFRs |
| `spec/03_state_transition_rules.md` | State lifecycle domains — governance boundaries (FINALIZED, REPORT_PUBLISHED, CLOSED) |
| `spec/04_idempotency_concurrency.md` | Idempotency and replay-safety rules across all lifecycle domains |
| `spec/05_external_integrations.md` | Integration philosophy — append-only ingestion, lineage-preserving integration, SQL Server authority |
| `spec/06_observability_operations.md` | Two-category telemetry, governance-aware observability, lineage-aware telemetry, replay observability |
| `spec/08_data_model.md` | Entity definitions, three-schema architecture, data class table, source data ownership |
| `spec/09_warehouse_physical_architecture.md` | Physical column design, two-table snapshot strategy, service account model |
| `spec/10_pre_migration_storage_validation.md` | Pre-migration validation requirements — CRITICAL corrections to `is_current` and compliance DELETE |
| `runtime/system_loop.md` | Six execution modes — governance semantics for SHADOW, LIVE, REPLAY, REGENERATION, DEGRADED, MAINTENANCE |
| `failure/failure_playbook.md` | Canonical resilience contract — AP-FP7 (immutable lineage corruption prohibition), AP-FP2 (replay LIVE recovery prohibition) |
| `meta/project_classification.md` | Execution mode classification, governance invariant universality, deployment-stage governance |
| `ux/user_experience.md` | UX governance contract — immutable lineage display constraints, FINALIZED artifact display rules |
| `alembic/versions/0002_warehouse_schema.py` | Physical warehouse and compliance_audit schema creation — two-table snapshot, service account GRANTs |
| `alembic/versions/0003_config_version_registry.py` | Config Version Registry — exactly-one-ACTIVE enforcement, append-only lineage, prospective activation |
| `tests/test_shadow_safety.py` | SHADOW containment, replay isolation, attribution continuity, provider containment — 74 certified tests |
| `tests/test_dashboard.py` | Observability governance, immutable-lineage visibility, replay observability — 87 certified tests |

---

## END OF FILE
