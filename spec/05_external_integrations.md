# spec/05_external_integrations.md

---

## LAYER 2 — SPECIFICATIONS (EXTERNAL INTEGRATIONS)

---

## 1. PURPOSE

This file defines the governed integration architecture for the Student Success Intelligence Platform (SSIP). It specifies how external systems — SQL Server, GHL (GoHighLevel), AI providers, and future integration surfaces — interact with the platform, what authority each system holds, and what guarantees the platform enforces across those boundaries.

This document governs:

* Authoritative-source boundaries and derivative system classification
* Synchronization semantics, attribution preservation, and replay-safety requirements
* Append-only ingestion expectations for governed historical data
* AI provider integration semantics and reproducibility isolation
* Orchestration sequencing expectations for snapshot generation and reporting
* Configuration registry consumption by integration consumers
* Event ingestion, timeline normalization, and attribution propagation
* Compliance and governance integration boundaries
* Cross-system failure classification and retry semantics
* Extensibility architecture for future integration surfaces

Canonical inputs: `spec/01_requirements.md`, `spec/03_state_transition_rules.md`, `spec/04_idempotency_concurrency.md`, `spec/07_api_contracts.md`, `spec/08_data_model.md`, `spec/09_warehouse_physical_architecture.md`, `spec/10_pre_migration_storage_validation.md`, `alembic/versions/0002_warehouse_schema.py`, `alembic/versions/0003_config_version_registry.py`.

---

## 2. INTEGRATION PHILOSOPHY

---

### 2.1 Governed Synchronization

All ingestion from external systems is subject to platform governance rules. External systems do not write to platform-owned tables directly. The platform controls all writes to its own schemas; external systems are data sources or execution targets, not data owners.

Synchronization moves data from an external authoritative source into a platform-owned derivative. The derivative can be updated by subsequent synchronizations; it does not confer write authority back to the external system.

---

### 2.2 Append-Only Ingestion

Data entering the `warehouse` and `compliance_audit` schemas is always append-only `INSERT`. No external system — and no platform service account other than the designated finalization account or compliance pathway account — may `UPDATE` or `DELETE` rows in these schemas.

Append-only ingestion is enforced at the database permission layer, not only at the application layer. Schema-level access controls are the final enforcement mechanism; application-layer guards are defense-in-depth.

---

### 2.3 Lineage-Preserving Integration

Every integration operation carries sufficient attribution to reconstruct the chain from external source to platform record. Required fields on all ingested events:

| Field | Description |
|---|---|
| `origin_source` | Where the data originated (`mirrored_sql_server`, `ghl_webhook`, `platform_generated`, etc.) |
| `origin_authority` | Authority class of the originating source (`sql_server_authoritative`, `platform_supplementary`) |
| `is_authoritative` | Whether this record governs eligibility decisions (`true` for SQL Server mirrored; `false` for all others) |
| `execution_mode` | `SHADOW` or `LIVE` at the time of ingestion |
| `correlation_id` | UUID v4 propagated from the triggering sync or webhook entry point |
| `attribution_timestamp` | When the event occurred in the source system (not ingestion time) |

ETL transforms that strip, overwrite, or fail to propagate these fields are specification violations.

---

### 2.4 Replay-Safe Ingestion

All ingestion pipelines must be safe to re-run. Delivering the same data batch twice produces no duplicate records and no additional side-effects. Replay safety is enforced by:

* Upsert semantics for SQL Server mirror (`INSERT ... ON CONFLICT DO UPDATE`)
* Deduplication via the `processed_events` table for event-based ingestion
* Unique constraints on `(student_id, origin_source, event_type, attribution_timestamp)` where applicable
* Idempotency keys on all cross-governance-boundary operations (per `spec/04_idempotency_concurrency.md`)

A replay that triggers any additional downstream side-effect (outreach, state transition, report generation) is a replay-safety defect.

---

### 2.5 Authoritative-Source Boundaries

SQL Server (`AI_ChatBot_TriggerData`) is the authoritative operational source for student academic state. When SQL Server-derived values and platform-supplementary values disagree for the same field, the SQL Server-derived value governs eligibility decisions. The platform-supplementary value is retained as context but never overrides authoritative state.

No platform logic rewrites authoritative-source data as platform-owned data without preserving origin attribution.

---

### 2.6 Reproducibility-Safe Synchronization

External data that contributes to snapshot finalization must be stable by content-lock time (`DRAFT → VALIDATING`). Live queries against external sources during finalization are prohibited.

The synchronization sequence is:
1. SQL Server sync completes → `student_trigger_data` current
2. AI enrichment completes → `ai_insights` at AI_REVIEWED state
3. Snapshot content lock → data is read from `student_trigger_data` and `ai_insights` and frozen in the snapshot
4. FINALIZED → data is committed immutably to `warehouse.student_snapshots`

Steps 1 and 2 involve external system interactions. Steps 3 and 4 are entirely platform-internal and read-only from the external perspective.

---

## 3. AUTHORITATIVE BOUNDARY MODEL

---

### 3.1 System Authority Classification

| System | Role | Authority Class | Direction | Platform Writes to It |
|---|---|---|---|---|
| SQL Server (`AI_ChatBot_TriggerData`) | Academic state source of truth | `sql_server_authoritative` | Read-only pull by platform | Never |
| GHL (GoHighLevel) | Communication execution | `platform_supplementary` | Platform → GHL (trigger); GHL → platform (webhooks) | Platform triggers GHL actions via API |
| AI Providers (Claude/OpenAI) | Augmentation service | `platform_supplementary` | Platform → AI (prompt); AI → platform (response) | Never (API calls only) |
| PostgreSQL `public` schema | Operational intelligence store | Platform-owned | Full read/write by application service account | N/A |
| PostgreSQL `warehouse` schema | Immutable historical archive | Platform-owned | INSERT-only by finalization service account | N/A |
| PostgreSQL `compliance_audit` schema | Governance-isolated audit | Platform-owned | INSERT-only by compliance pathway service account | N/A |

---

### 3.2 Authoritative vs Derivative Distinction

**Authoritative records** govern eligibility decisions. Fields derived from SQL Server `AI_ChatBot_TriggerData` — `HWsBehind`, `AvgEffRating`, `PerComp_Act`, `PaymentBalance`, `CurrentSection`, access state — govern cohort classification, risk scoring, and threshold evaluation. These carry `origin_authority = sql_server_authoritative` and `is_authoritative = true`.

**Derivative records** provide context and augmentation. GHL communication events, platform-generated notes, and AI-generated insights carry `origin_authority = platform_supplementary` and `is_authoritative = false`. They enrich the student timeline and inform operator decisions but do not govern academic eligibility.

**Conflict resolution:** When an authoritative and a derivative record exist for the same field and the same student, the authoritative record governs. Both records are retained; neither is deleted. The conflict is logged.

---

### 3.3 Operational vs Historical Ownership

| Layer | Operational Ownership | Historical Ownership |
|---|---|---|
| Student academic state | SQL Server owns source; platform owns the mirror | Platform owns immutable snapshots in `warehouse` |
| Communication events | GHL owns execution; platform owns the event log | Platform owns the append-only timeline records |
| AI insights | AI providers produce content; platform owns review/attribution | Platform owns physically copied AI text in snapshots |
| Configuration thresholds | Platform owns the config version registry | Platform owns every prior version permanently |
| Compliance records | Platform governs the workflow; `compliance_audit` is the truth | Platform owns compliance_audit records regardless of operational deletions |

---

### 3.4 Synchronization vs Mutation

**Synchronization** copies external state into a platform-owned derivative. The copy may be overwritten on subsequent syncs. The external system's state is not changed.

**Mutation** changes platform-owned state via state machine transitions. External systems do not trigger platform mutations directly; they provide inputs that the platform processes according to its own state machine rules.

**Mirrored events** are records of external state at a point in time. They do not claim the event "happened on the platform"; they record that the state was observed in the external source.

**Platform-owned events** carry `origin_source` set to a platform value (`platform_generated`, `platform_outreach`, etc.) and `origin_authority = platform_supplementary`. They supplement but never override mirrored-source records for eligibility decisions.

---

## 4. SQL SERVER INTEGRATION ARCHITECTURE

---

### 4.1 Extraction Domains

| Domain | Source Fields (SQL Server) | Platform Table | Sync Scope |
|---|---|---|---|
| Coursework engagement | `HWsBehind`, `AvgEffRating`, `CurrentSection`, `LastActivityDays`, `PerComp_Act` | `student_trigger_data` | Full row per sync |
| Payment tracking | `PaymentBalance`, `ClassFeesPaid`, payment plan fields | `student_trigger_data` | Full row per sync |
| Placement readiness | `CurrentSection` (launch/CAP patterns), placement pipeline signals | `student_trigger_data` | Full row per sync |
| Access history | Access state, revocation trigger, restoration events | `student_trigger_data` + timeline | Row + event recording |
| Enrollment state | `StudentStartDate`, `ClassStartDate`, cohort affiliation | `student_trigger_data` | Full row per sync |
| New signup / newcomer | `StudentStartDate`, `ClassStartDate`, days-since-signup calculation | `student_trigger_data` | Full row per sync |

Mentorship activity field mapping is unresolved (see UI-2 in §15).

---

### 4.2 Synchronization Philosophy

SQL Server is polled on demand via `POST /sync/mssql`. The platform does not maintain a persistent CDC connection.

Each sync cycle:
1. Opens a read-only MSSQL connection via pyodbc
2. Executes a `SELECT` against `AI_ChatBot_TriggerData`
3. Upserts results into `student_trigger_data` in PostgreSQL
4. Records a sync event with `sync_correlation_id` (UUID v4), row count, and timestamp
5. Closes the connection

The sync is idempotent. Running the same sync twice against unchanged SQL Server state produces identical `student_trigger_data` rows.

---

### 4.3 Incremental Extraction Expectations

| Scope | Behavior |
|---|---|
| MVP | Full-table extraction per invocation. All rows from `AI_ChatBot_TriggerData` are fetched on every sync. |
| STANDARD | Supports a `since_timestamp` parameter. Extraction is filtered to rows modified after the prior successful sync timestamp. |
| PRODUCTION | Incremental by default. Full-table sync available as a recovery option on explicit operator request. |

---

### 4.4 Attribution Preservation

Every row synced from SQL Server carries:

* `origin_source = mirrored_sql_server` on all derived platform records
* `sync_timestamp` on the `student_trigger_data` row — the time this copy was written
* `sync_correlation_id` propagated to all platform events generated from this sync cycle
* `is_authoritative = true` on timeline events derived from SQL Server mirror records

`origin_source` must not be overwritten from `mirrored_sql_server` to a platform value by any ETL transform, batch step, or enrichment process.

---

### 4.5 Replay Safety

* SQL Server sync is replay-safe. Re-running the sync for the same student set produces the same `student_trigger_data` state.
* No duplicate lifecycle events are generated from a sync replay. The `processed_events` table deduplicated by `(student_id, event_type, attribution_timestamp)` prevents duplicate downstream event creation.
* Replay of a sync that contributed to a FINALIZED snapshot produces no changes to the snapshot. The snapshot's content is locked at `DRAFT → VALIDATING` and is immutable thereafter.

---

### 4.6 Conflict Handling

When a SQL Server sync delivers a value that conflicts with a platform-supplementary estimate for the same field:

* The SQL Server value is applied to `student_trigger_data`
* The platform-supplementary estimate is retained as a separate record with `origin_authority = platform_supplementary`
* The conflict is logged with both values, the winning source, and `sync_correlation_id`
* Eligibility classifications use the SQL Server-derived value

---

### 4.7 Mirrored-Event Semantics

A mirrored event records that a state was observed in SQL Server at a point in time. It does not assert causality or event order. Mirrored events in the platform timeline carry `is_authoritative = true` and govern eligibility decisions.

When two platform timeline events for the same student action originate from different sources (one SQL Server, one GHL), both are preserved. The SQL Server record governs eligibility; the GHL record provides communication context.

---

### 4.8 Historical Snapshot Isolation

Once a snapshot is FINALIZED, the metric values it captured from `student_trigger_data` are immutable. Subsequent SQL Server syncs that update `student_trigger_data` do not affect any FINALIZED snapshot. Historical analytics must query `warehouse.student_snapshots`, not live `student_trigger_data` (FAD-2).

---

## 5. GHL / COMMUNICATION PROVIDER INTEGRATION

---

### 5.1 Provider Ownership Boundaries

GHL executes communication workflows. It does not own student records, academic state, or eligibility decisions. Platform intelligence determines when to trigger GHL; GHL delivers communication; GHL reports execution outcomes back via webhooks.

GHL has no write authority over:

* Cohort classification or risk scoring
* Snapshot content or finalization state
* Report publication state
* Config version thresholds
* Compliance workflow state

---

### 5.2 Communication Event Ingestion

Inbound GHL webhooks are ingested into platform-owned tables:

| Event Type | Target Table | Deduplication Key |
|---|---|---|
| Delivery confirmation | `ghl_messages` | `ghl_message_id` |
| Response event | `ghl_messages` | `ghl_message_id` |
| Campaign participation | `student_campaign_activity` | `(student_id, campaign_id, event_type, attribution_timestamp)` |
| Outreach outcome | `outreach_history` | `(user_id, checkpoint_type, contact_attempt)` |

All inbound GHL events are validated against a schema before storage. Malformed payloads are rejected and logged; they do not enter platform tables.

---

### 5.3 Attribution Preservation

All GHL-originated events carry:

* `origin_source = ghl_webhook`
* `origin_authority = platform_supplementary`
* `is_authoritative = false`
* `attribution_timestamp` = the event timestamp from the GHL payload (not the ingestion time)
* `ghl_message_id` preserved as the external deduplication anchor

These fields must be present on all GHL-derived records regardless of which processing step created the record.

---

### 5.4 Timeline Synchronization

GHL events are normalized and surfaced in the unified student timeline alongside SQL Server-mirrored events. Timeline ordering uses `attribution_timestamp` from the event payload. When a GHL event's timestamp conflicts with a SQL Server-mirrored event for the same student action, both records are preserved; the SQL Server record carries `is_authoritative = true`.

---

### 5.5 Deduplication Expectations

* GHL inbound webhooks: deduplicated by `ghl_message_id` via the `processed_events` table. A duplicate webhook is acknowledged (HTTP 200) and discarded without reprocessing.
* Campaign activity: deduplicated by `(student_id, campaign_id, event_type, attribution_timestamp)`.
* Outbound GHL triggers: deduplicated by the outreach domain idempotency key `(user_id, checkpoint_type, contact_attempt)`.

No GHL event may be silently dropped. Every deduplication result (new or duplicate) produces a `processed_events` entry.

---

### 5.6 Replay Handling

Replaying a GHL webhook batch produces no duplicate records. The `processed_events` table is the deduplication anchor. Re-delivery of the same webhook event is idempotent.

Replaying outbound GHL trigger logic is governed by the outreach domain idempotency key. A retry cycle that encounters an already-processed key exits cleanly; it does not re-trigger GHL.

---

### 5.7 Future Provider Extensibility

The communication integration architecture is provider-abstracted. New providers (Twilio, SendGrid, Vonage, Klaviyo) integrate via the same event ingestion contract:

* Inbound events carry `origin_source = [provider]_webhook`
* Provider-specific message IDs serve as `processed_events` deduplication keys
* Attribution fields (`origin_authority`, `is_authoritative`, `attribution_timestamp`) are populated at ingestion time
* No provider has write authority over platform eligibility state, snapshot state, or config versions
* Provider replacement is a configuration and service-layer change; no schema migration is required

---

## 6. AI PROVIDER INTEGRATION

---

### 6.1 Role Boundary

AI providers are augmentation services. They do not own student records, do not govern eligibility decisions, and do not participate in governance boundaries. AI provider output is treated as raw material that undergoes platform review before entering governed state (AI_REVIEWED).

No AI provider output enters a governance boundary — FINALIZED snapshot, REPORT_PUBLISHED — until it has reached AI_REVIEWED state via the platform's review workflow.

---

### 6.2 Integration Scope

| Capability | Input | Output |
|---|---|---|
| Risk summary | Student metrics, engagement signals | Free-text risk narrative |
| Progress summary | Coursework engagement, completion signals | Free-text progress narrative |
| Intervention recommendation | Risk signals, communication history | Structured recommendation text |
| Monthly narrative | Aggregated monthly metrics | Extended free-text narrative |
| Sentiment analysis | Communication transcript content | Sentiment classification |

---

### 6.3 Prompt Version Attribution

The prompt template version is captured at the moment the `AI_PENDING` record is created. The generation uses that captured version regardless of subsequent prompt template updates. This is enforced by binding `prompt_version` to the `AI_PENDING` record at creation time, before the AI provider call begins (per `spec/04_idempotency_concurrency.md` §17.3).

`prompt_version` is stored in `ai_insights.prompt_version` and is immutable after `AI_GENERATED`.

---

### 6.4 Model Version Attribution

The actual model used is recorded in `ai_insights.model_used` at `AI_GENERATED` state from the provider's response metadata — not from the configured model at job-start time. A provider that routes the same model name to different underlying models is treated as returning the same model identifier; the platform records what the API response reports.

`model_used` is immutable after `AI_GENERATED`.

---

### 6.5 Refresh Lineage

Force-refresh creates a new AI record with an incremented `version_number`. The prior `AI_REVIEWED` record transitions to `AI_REFRESH_REQUESTED`. The full version history is queryable; no prior version is deleted. Force-refresh lineage is visible via `GET /ai-insights/{user_id}/{insight_type}/history`.

---

### 6.6 Reproducibility Expectations

AI provider calls are non-deterministic. The same prompt with the same inputs may produce different text on different calls. Platform reproducibility guarantees are therefore not provided at the AI generation level.

Reproducibility is guaranteed at the snapshot and report levels by physical copy semantics (FAD-1):

* At `VALIDATING → FINALIZED`, the most recent `AI_REVIEWED` text is copied physically into `warehouse.snapshot_ai_narratives`
* All future report generations and historical regenerations read from that physical copy
* No AI provider call is made during report generation or historical regeneration
* Running the same report generation twice from the same FINALIZED snapshot produces identical output (CONC-INVARIANT-2)

---

### 6.7 Retry Semantics

| Scope | Behavior |
|---|---|
| MVP | One retry on failure; if still fails → `AI_GENERATION_FAILED` |
| STANDARD | Two retries with exponential backoff (e.g., 2s, 4s); max attempts = 3 |
| PRODUCTION | Two retries with exponential backoff; circuit breaker after N failures in a time window; max attempts = 3 |

Each retry creates a new AI provider call on the same `ai_insights` record. Partial output from a failed call is discarded; the record remains in `AI_GENERATING` until a complete valid response is received or retries are exhausted. Partial AI content must not be committed to `AI_GENERATED` state (per `spec/04_idempotency_concurrency.md` §17.5).

---

### 6.8 Failure Visibility

| Failure state | API surface | Behavior |
|---|---|---|
| `AI_GENERATION_FAILED` + prior `AI_REVIEWED` exists | `GET /ai-insights/{user_id}/{insight_type}` | Prior `AI_REVIEWED` served with `stale: true` |
| `AI_GENERATION_FAILED` + no prior `AI_REVIEWED` | `GET /ai-insights/{user_id}/{insight_type}` | Explicit `null` with `reason = AI_GENERATION_FAILED` |
| `AI_GENERATION_FAILED` at snapshot time | Snapshot | AI narrative field is null or populated from stale record with `ai_content_stale = true` flag |

`AI_GENERATION_FAILED` records are not served as current insight content. They are queryable for audit and diagnostic purposes via the history endpoint.

---

### 6.9 Frozen Snapshot Isolation

Once a snapshot is FINALIZED, the AI text in `warehouse.snapshot_ai_narratives` is completely isolated from the `ai_insights` lifecycle. The following operations on `ai_insights` do NOT modify frozen snapshot AI text:

* Force-refresh creating a new AI version
* Archival of prior AI versions
* Compliance deletion of `ai_insights` records

This is INVARIANT-3: `ai_insights` operations and snapshot AI text reads have no locking relationship. Report regeneration from snapshot data always produces identical output regardless of the current state of `ai_insights` records (per `spec/04_idempotency_concurrency.md` §17.7).

---

### 6.10 Provider Independence

The AI integration contract is provider-agnostic. The platform specifies prompt structures and output schemas; the AI provider is replaceable. Adding or replacing an AI provider requires:

* Updated model version identifier in configuration
* No schema migration required
* Historical `ai_insights` records retain their original `model_used` and `prompt_version` attribution

Replacing a provider does not affect any FINALIZED snapshot AI text; those are physical copies, not provider references.

---

## 7. SNAPSHOT GENERATION ORCHESTRATION

---

### 7.1 Conceptual Orchestration Sequence

The following is the logical sequencing for monthly snapshot generation. This is an orchestration boundary definition, not an implementation prescription.

```
Phase 0 — Preconditions
  SQL Server sync completed for all eligible students
  AI insights at AI_REVIEWED for all students (or stale handling defined)
  ACTIVE config version present in config_version_registry

Phase 1 — DRAFT Assembly
  For each eligible student:
    Read student_trigger_data (post-sync)
    Assemble draft metrics (cohort classification, risk scores, payment state)
    Classify against ACTIVE config version thresholds
    Create DRAFT snapshot record in public schema

Phase 2 — Content Lock (DRAFT → VALIDATING)
  For each DRAFT snapshot:
    Lock metric fields — no further changes permitted
    Capture ACTIVE config_version_id as fingerprint component
    Identify most recent AI_REVIEWED record per insight_type

Phase 3 — AI Enrichment
  For each VALIDATING snapshot:
    Read AI_REVIEWED text from ai_insights (physical read — no AI provider call)
    Copy text into snapshot row (or snapshot_ai_narratives companion row)
    If no AI_REVIEWED exists → NULL narrative; set ai_content_available = false
    If AI_REVIEWED exists but is stale → copy stale text; set ai_content_stale = true

Phase 4 — Fingerprint Computation
  Compute all 5 fingerprint components:
    schema_version, configuration_registry_version, ai_prompt_version,
    ai_model_version, report_template_version
  Unavailable components → recorded as UNKNOWN_V0; does not block finalization

Phase 5 — Finalization (VALIDATING → FINALIZED)
  Executed by finalization service account only
  INSERT into warehouse.student_snapshots (append-only)
  INSERT into warehouse.snapshot_ai_narratives (companion row)
  Idempotency check: reject if FINALIZED row already exists for (student_id, snapshot_month)
  Audit log entry written atomically with state transition

Phase 6 — Report Generation
  After all student snapshots FINALIZED for the cohort:
    Trigger report generation job
    Report reads from warehouse.student_snapshots exclusively (FAD-2)
    No SQL Server query; no AI provider call
    On completion: REPORT_GENERATED → (review) → REPORT_PUBLISHED
```

---

### 7.2 Orchestration Ownership

The orchestration scheduler (APScheduler or equivalent) owns trigger timing and sequencing decisions. The platform API and service layer own the actual state transitions. No external system has authority to directly insert rows into `warehouse.student_snapshots` or transition snapshots to FINALIZED; this is exclusively the finalization service account's responsibility, invoked by the platform scheduler.

External "run now" operator actions are expressed as API calls to platform-internal endpoints. They do not bypass the service layer or directly manipulate the warehouse schema.

---

### 7.3 Append-Only Guarantees in Orchestration

* Every FINALIZED snapshot is an `INSERT` into `warehouse.student_snapshots`; no `UPDATE` occurs
* Re-runs detect existing FINALIZED rows for `(student_id, snapshot_month)` and exit cleanly for those students
* No idempotency mechanism may produce a second FINALIZED row for the same `(student_id, snapshot_month)` pair
* Report publication produces a new row in `warehouse.monthly_reports`; no in-place update of a prior REPORT_PUBLISHED row

---

### 7.4 Replay Safety in Orchestration

| Scenario | Behavior |
|---|---|
| Batch re-run where some students already FINALIZED | FINALIZED students are skipped; un-finalized students continue |
| Batch re-run from DRAFT/VALIDATING checkpoint | Safe to resume; idempotency prevents duplicate content lock |
| Full batch re-run for a month with all students FINALIZED | All finalizations are no-ops; no new rows created |
| Scheduler double-fire within same window | Second fire detects in-progress or completed work; exits cleanly |

---

### 7.5 Failure Recovery Boundaries

| Failure | State after failure | Recovery path |
|---|---|---|
| DRAFT assembly fails mid-way | DRAFT incomplete | Resume from last checkpoint; retry |
| Content lock fails (DRAFT → VALIDATING) | DRAFT | Retry the transition |
| AI enrichment fails (AI read error) | VALIDATING | Proceed with NULL AI narrative; flag stale if applicable |
| Fingerprint computation fails (component unavailable) | VALIDATING | Record `UNKNOWN_V0`; proceed to finalization |
| Finalization write fails (DB error) | VALIDATING | Retry finalization; idempotency prevents duplicate FINALIZED |
| Hung job (no progress within SLA) | Last known state | Scheduler detects SLA breach; operator alert; human review |
| Report generation fails | REPORT_GENERATION_FAILED | Retry report generation (idempotent given same snapshot data) |

Partial execution of any phase leaves the system in a state safe to re-run. No failure path produces a corrupted FINALIZED snapshot or a partial warehouse write.

---

### 7.6 Historical Regeneration Boundary

Historical regeneration re-generates a report from a FINALIZED snapshot without contacting any external system:

* Reads `warehouse.student_snapshots` for metrics
* Reads `warehouse.snapshot_ai_narratives` for AI text (physical copy)
* Does NOT query `student_trigger_data`
* Does NOT query live `ai_insights`
* Does NOT call any AI provider
* Does NOT call SQL Server

This is the FAD-2 boundary. Same input → same output every time (CONC-INVARIANT-2). A regeneration that contacts an external system for content is a specification violation.

---

## 8. CONFIGURATION REGISTRY INTEGRATION

---

### 8.1 How Integration Consumers Read Config

All classification, scoring, and threshold evaluations during snapshot generation read from the `ACTIVE` record in `config_version_registry`. The ACTIVE version at content lock time (`DRAFT → VALIDATING`) is the authoritative config for that snapshot.

At content lock time, the integration consumer:
1. Queries `config_version_registry WHERE status = 'ACTIVE'` — returns exactly one row (enforced by partial unique index)
2. Captures the `version_id`, `version_number`, and all 24 threshold fields
3. Stores `version_id` as the `configuration_registry_version` fingerprint component on the snapshot
4. Applies thresholds from that row to classify the student

If no ACTIVE version exists (initial setup before V1 seed, or a gap in activation), snapshot generation must fail fast. Proceeding with implicit defaults is prohibited.

---

### 8.2 Historical Config Reference

Historical analysis requiring knowledge of thresholds at a past point in time queries `config_version_registry` by `version_number`. `SUPERSEDED` and `ARCHIVED` versions remain permanently queryable. No config version record is ever deleted by any application code.

This enables:
* Reproducing the exact classification logic that was active at a past snapshot's generation time
* Auditing threshold changes over time
* Explaining why a student was or was not classified into a cohort in a historical period

---

### 8.3 Prospective-Only Semantics for Integration Consumers

Configuration changes are always prospective. A new ACTIVE version affects only snapshot generation cycles that lock content after the activation completes. Integration consumers must not apply a new config version retrospectively to already-FINALIZED snapshots or in-progress VALIDATING snapshots.

If a config version is activated during a monthly batch run:
* Snapshots already in VALIDATING or FINALIZED carry the prior version in their fingerprint
* Snapshots not yet in VALIDATING pick up the new ACTIVE version at their content lock
* This produces different `configuration_registry_version` values within the same batch — this is expected behavior, not a concurrency defect (CONC-INVARIANT-4)

---

### 8.4 Exactly-One-ACTIVE Guarantee for Integration Consumers

The platform enforces exactly one ACTIVE version at all times via the partial unique index `((1)) WHERE status = 'ACTIVE'` on `config_version_registry`. This constraint is enforced at the database layer; no integration consumer or ETL process can bypass it.

Integration consumers must not implement fallback logic that assumes zero ACTIVE versions may exist in steady state. Zero ACTIVE versions is an initialization or incident state, not a normal runtime condition.

---

## 9. EVENT INGESTION AND TIMELINE INTEGRATION

---

### 9.1 Event Ingestion Architecture

All events — SQL Server mirrored, GHL webhook, platform-generated — are normalized into a unified event representation before storage in the platform's event log. Normalization is attribution-preserving: the normalized record carries the full set of attribution fields from §2.3 regardless of event origin.

Normalization does not modify event semantics. A SQL Server mirrored access-revocation event normalized into the timeline retains `origin_source = mirrored_sql_server` and `is_authoritative = true`. A GHL delivery confirmation normalized into the timeline retains `origin_source = ghl_webhook` and `is_authoritative = false`.

---

### 9.2 Timeline Normalization

The unified student timeline (`student_timeline_events`) is an append-only event log. Events from different sources are interleaved chronologically by `attribution_timestamp`.

| Field | Source |
|---|---|
| `attribution_timestamp` | Event occurrence time in the source system (not ingestion time) |
| `ingestion_timestamp` | When the event was written to the platform table |
| `origin_source` | Where the event originated |
| `origin_authority` | Authority class |
| `is_authoritative` | Whether this record governs eligibility |
| `execution_mode` | SHADOW or LIVE at ingestion time |
| `correlation_id` | UUID v4 from the sync or webhook entry point |

`attribution_timestamp` and `ingestion_timestamp` are both preserved. Timeline display uses `attribution_timestamp`; reconciliation uses the delta between the two.

---

### 9.3 Attribution Propagation Rules

* `correlation_id` is generated at the sync or webhook entry point and propagated through all downstream log entries, database writes, and derived records
* `origin_source` is set at ingestion and is immutable; no downstream transform overwrites it
* `is_authoritative` is set based on `origin_authority` at ingestion; it is not recalculated downstream

A log line missing `correlation_id`, `origin_source`, or `origin_authority` is an observability defect.

---

### 9.4 Replay-Safe Event Ingestion

| Deduplication mechanism | Applies to |
|---|---|
| `processed_events` table keyed on `event_id` | All webhook-delivered events |
| `INSERT ... ON CONFLICT DO NOTHING` on `(student_id, origin_source, event_type, attribution_timestamp)` | Timeline event deduplication |
| Upsert on `student_trigger_data` by student primary key | SQL Server sync deduplication |

Replaying any event batch produces no new records beyond those from the first delivery. Every deduplication result (new or duplicate) is logged; silent drops are prohibited.

---

### 9.5 Unified Timeline Expectations

The timeline API surfaces all event types in chronological order:

* SQL Server mirrored state changes (access, enrollment, coursework)
* GHL communication events (SMS, email, call, campaign)
* Platform outreach decisions and outcomes
* Snapshot lifecycle events (DRAFT created, FINALIZED, etc.)
* Report publication events
* Compliance workflow events (where authorized)

Conflicting events from different sources for the same action are both preserved; `is_authoritative` identifies the authoritative record.

---

### 9.6 Event Ordering Expectations

Out-of-order event arrival is expected. GHL webhooks may arrive after the corresponding SQL Server mirror has been updated. The platform stores events with their `attribution_timestamp` (occurrence time), not arrival order.

Out-of-order events do not trigger retroactive state machine transitions. They are stored as historical records. State machine transitions are driven by current-state reads, not event re-ordering.

---

### 9.7 Eventual Consistency Assumptions

The unified timeline is eventually consistent. Events may be ingested with up to [GHL webhook SLA: 5–30 minutes] lag relative to their actual occurrence. Snapshot content lock uses `student_trigger_data` as of the most recent completed sync; it does not wait for all GHL events to be ingested.

Historical timeline records remain queryable even after operational record deletion, subject to compliance survivability rules (`spec/04_idempotency_concurrency.md` §19.6).

---

## 10. COMPLIANCE AND GOVERNANCE INTEGRATION

---

### 10.1 Architecture Overview

Compliance and governance workflows are governance operations, not ordinary operational integrations. They operate through a dedicated compliance pathway service account with INSERT-only access to the `compliance_audit` schema. No standard application service account participates in compliance execution.

External compliance tooling (GDPR portals, legal case management systems) interacts with the platform exclusively via the compliance API (`spec/07_api_contracts.md` §13). External tools do not connect directly to any database schema.

---

### 10.2 Compliance Export Architecture

The compliance export endpoint (`GET /compliance/audit/export`) produces a self-contained structured document sourced entirely from the `compliance_audit` schema. The export does not depend on records in the `public` or `warehouse` schemas existing.

This means:
* Exports are producible after full GDPR deletion (operational records removed; compliance_audit survives)
* Exports do not require joining to `student_trigger_data` or `warehouse.student_snapshots`
* The compliance_audit schema is the sole source of truth for compliance export content

---

### 10.3 Audit Export Architecture

Compliance audit export content per workflow:

* Intake record (`COMPLIANCE_REQUEST_RECEIVED` event)
* Pre-action audit entry (must exist before `IN_EXECUTION` — hard gate)
* Scope manifest (captured at `APPROVED_FOR_ACTION`)
* Per-table execution records (created during `IN_EXECUTION`)
* Post-action audit entry (created after execution completes)
* Any correction records referencing prior entries

All entries are append-only; corrections create new records referencing prior ones. No entry is modified or deleted after creation.

---

### 10.4 Deletion Workflow Integration Boundaries

| Step | Actor | Service account |
|---|---|---|
| Request intake | Compliance reviewer (via API) | Standard application service account |
| Review and approval | Compliance reviewer (via API) | Standard application service account |
| Pre-action audit entry | Compliance pathway (API-mediated) | Compliance pathway service account |
| Scope manifest capture | Compliance pathway (API-mediated) | Compliance pathway service account |
| `IN_EXECUTION` execution | Compliance pathway (API-mediated) | Compliance pathway service account |
| Post-action audit entry | Compliance pathway (API-mediated) | Compliance pathway service account |

The hard gate: `APPROVED_FOR_ACTION → IN_EXECUTION` is blocked by the API if no pre-action audit entry exists in `compliance_audit` for the workflow. This check is atomic with the transition; a separate pre-check step is not sufficient.

---

### 10.5 Survivability Guarantees

Compliance audit records are independent of operational record existence. The `compliance_audit` schema has no FK dependencies on the `public` or `warehouse` schemas (per spec/09 §1.2 and spec/08 §2 schema separation rules). A full operational deletion of a student's records does not affect, cascade-delete, or make unqueryable any compliance_audit records for that student.

---

### 10.6 Governance Isolation Boundaries

Compliance workflows are isolated from all other platform operations:

* A compliance workflow cannot be triggered by outreach automation, the snapshot scheduler, or the report generation pipeline
* Compliance workflows are initiated exclusively by human actors with the `compliance_reviewer` role or higher
* A compliance execution in `IN_EXECUTION` does not pause or block concurrent snapshot generation, AI generation, or outreach execution for other students
* A compliance action on a published report annotation (`compliance_affected` flag) does not retroactively recalculate aggregate statistics (per spec/03 §37.4)

Execution mode (SHADOW / LIVE) does not gate compliance workflows. Compliance actions are governance events; they execute regardless of outreach execution mode.

---

## 11. FAILURE AND RETRY SEMANTICS

---

### 11.1 Partial Synchronization

A SQL Server sync that partially completes leaves `student_trigger_data` in a mixed-freshness state. Students synced before the failure have current data; students not yet synced retain prior-cycle data.

Recovery: re-run the sync for the full student set. Upsert semantics ensure idempotent re-sync. Partial sync data must not be used for snapshot content lock if the staleness policy (U-2, see §15) is violated.

---

### 11.2 Failure Classification Table

| Failure | Class | Retry Behavior |
|---|---|---|
| SQL Server connection timeout | Retryable | Exponential backoff; max 3 attempts |
| SQL Server authentication failure | Terminal | Alert; credentials rotation required |
| SQL Server schema mismatch | Terminal | Alert; human investigation; migration may be required |
| GHL webhook signature invalid | Terminal | Reject; log; do not store or retry |
| GHL API rate limit (outbound) | Retryable | Backoff per `Retry-After` header; max 5 attempts |
| GHL API server error (5xx) | Retryable | Exponential backoff; max 3 attempts |
| GHL API authentication failure | Terminal | Alert; key rotation required |
| AI provider timeout | Retryable | Exponential backoff; max 2 additional attempts (3 total) |
| AI provider content policy rejection | Terminal per generation | `AI_GENERATION_FAILED`; log rejection reason; no retry |
| AI partial output (schema mismatch) | Terminal per attempt | Discard; retry as new attempt |
| Snapshot fingerprint component unavailable | Non-blocking | Record `UNKNOWN_V0`; continue |
| Snapshot finalization duplicate detected | Non-retryable conflict | Existing FINALIZED preserved; second attempt exits cleanly |
| Report generation failure | Retryable | Retry from scratch; idempotent given same snapshot data |
| Compliance pre-action audit write failure | Incident | Block `IN_EXECUTION`; alert; human review immediately |
| Compliance post-action audit write failure | Incident | Emergency audit record; human review immediately |
| Config version zero-ACTIVE state | Incident | Block snapshot generation; alert; immediate resolution required |

---

### 11.3 Duplicate Ingestion Handling

| Scenario | Resolution |
|---|---|
| Duplicate GHL webhook delivery | Acknowledge (200); discard via `processed_events`; no record created |
| Duplicate SQL Server row in sync | Upsert; existing row updated; no duplicate row |
| Duplicate snapshot finalization attempt | Second rejected by idempotency check; first FINALIZED preserved |
| Duplicate AI generation request | Second rejected; in-flight generation completes normally |
| Duplicate compliance intake for same student | Second rejected; existing workflow preserved |

All duplicate detections are logged. Silent drops are not permitted; every suppressed duplicate produces an audit log entry.

---

### 11.4 Stale AI at Snapshot Time

If the most recent AI insight for a student is in `AI_GENERATION_FAILED` state at snapshot content lock time:

* If a prior `AI_REVIEWED` record exists: copy its text into the snapshot; set `ai_content_stale = true` in the snapshot row; record the stale source version_number
* If no `AI_REVIEWED` record exists: snapshot AI narrative fields are `NULL`; set `ai_content_available = false`; finalization continues (AI enrichment is not a finalization blocker)

Stale AI content in a FINALIZED snapshot is disclosed in the reproducibility fingerprint metadata and in the snapshot API response.

---

### 11.5 Provider Outage Handling

| Provider | Outage behavior |
|---|---|
| SQL Server | Sync cannot run; `student_trigger_data` reflects last successful sync; snapshot generation may proceed if within staleness policy (U-2) |
| GHL | Outbound communication blocked; outreach transitions to platform retry queue; no data corruption; in-flight state preserved |
| AI provider | AI generation deferred with exponential backoff; max retries exhausted → `AI_GENERATION_FAILED`; does not block snapshot finalization |

Provider outages do not corrupt platform state. The platform continues to serve all read operations (dashboards, reports, historical queries) regardless of external provider availability.

---

### 11.6 Reconciliation Expectations

| Reconciliation type | Trigger | Detection |
|---|---|---|
| SQL Server row count | After each sync cycle | `student_trigger_data` row count vs SQL Server active student count within tolerance |
| GHL delivery confirmation | Daily | Outreach records with no corresponding GHL delivery confirmation within SLA |
| AI insight coverage | Daily | Students with no `AI_REVIEWED` insight within TTL window — flagged for generation |
| Snapshot coverage | After batch | Students eligible for a month-end snapshot with no FINALIZED row — flagged for investigation |
| Compliance audit completeness | On demand | Workflows in terminal state with missing post-action audit entries |

---

### 11.7 Attribution Preservation During Retries

* SQL Server sync retry: uses the original `sync_correlation_id` from the first attempt; does not create a new attribution chain for already-synced students
* GHL webhook retry (re-delivery): uses the original `ghl_message_id`; `processed_events` deduplication prevents duplicate records
* AI generation retry: each retry attempt uses the same `ai_idempotency_key` on the existing `AI_PENDING` record; the retry creates a new provider call but not a new platform record; attribution fields captured at `AI_GENERATED` reflect the successful call's metadata

---

## 12. FUTURE INTEGRATION EXTENSIBILITY

---

### 12.1 Additional AI Providers

The AI integration contract is provider-agnostic. Adding a new AI provider or replacing the current one requires:

* Updated `model_version` identifier in config (no schema change)
* Updated prompt management configuration for the new provider's format requirements
* No migration to historical `ai_insights` records; they retain their original `model_used` attribution
* No change to snapshot AI text copies; they are physical copies tied to the version at finalization time

Multi-provider scenarios — different providers for different insight types — are supported by the per-record `model_used` field.

---

### 12.2 CRM Providers

GHL is the current CRM and communication execution layer. Future CRM providers integrate via the same communication event ingestion contract defined in §5. Core invariants:

* No CRM provider has write authority over platform eligibility state, snapshot state, config versions, or compliance records
* CRM provider replacement is a service-layer change; existing communication event records in platform tables are preserved with their original `origin_source` attribution

---

### 12.3 Communication Providers

Additional communication channels (Twilio, Vonage, SendGrid, RCS) integrate via:

* Outbound: platform API call to provider API
* Inbound: provider webhook → platform ingestion pipeline
* Attribution: `origin_source = [provider_slug]_webhook`; provider-specific message IDs mapped to `processed_events` keys

No additional communication provider changes the platform's event storage schema. The normalization pipeline handles provider-specific payload mapping.

---

### 12.4 Vector-Search and RAG Systems

Vector-search integration consumes platform intelligence data (AI insights, student summaries, snapshot narratives) to build retrieval indices for semantic search or retrieval-augmented generation.

Integration contract:

* Vector-search systems are **read-only consumers** of platform data; they do not write back to any platform-owned table
* AI narrative content in `warehouse.snapshot_ai_narratives` is the canonical stable input for vectorization; physical copy semantics ensure content stability
* Vectorization pipelines may read from both `public` (operational) and `warehouse` (historical) schemas with SELECT grants
* Index staleness is the vector system's concern; the platform provides stable, versioned content

---

### 12.5 Analytics Warehouses

External analytics warehouse export (Snowflake, BigQuery, Redshift, Databricks) is a read-only operation.

Integration contract:

* Export pipelines read from `warehouse.student_snapshots` and `warehouse.monthly_reports` exclusively (FAD-2 aligned)
* Attribution metadata — fingerprint, `config_version_id`, `model_used`, `prompt_version` — must be included in exports to preserve reproducibility context in the external warehouse
* Export pipelines do not modify any platform-owned tables
* Exports produce a point-in-time snapshot of the warehouse schema; they do not require locking or pausing platform operations

---

### 12.6 Compliance Export Systems

External compliance portals (OneTrust, TrustArc, or custom legal systems) integrate via the compliance API:

* External tools consume the `GET /compliance/audit/export` endpoint
* They do not connect directly to any database schema
* The export format is the integration contract; external systems adapt to it (per UI-7 in §15)
* Export access requires `compliance_reviewer` role; no compliance portal receives database credentials

---

## 13. ACCEPTANCE CRITERIA

---

### AC-1 — Replay-Safe Ingestion

**Given** a SQL Server sync batch is re-run for the same set of students
**When** the re-run completes
**Then** `student_trigger_data` rows for those students are identical to the first run; no additional lifecycle events, timeline entries, or state transitions are generated; no duplicate rows exist in any platform table

---

### AC-2 — Lineage Preservation

**Given** a SQL Server event is ingested and processed through snapshot generation
**When** the snapshot is FINALIZED
**Then** the snapshot fingerprint includes the `config_version_id` active at content lock time; the `sync_correlation_id` is present in the snapshot audit log; `origin_source = mirrored_sql_server` is present in all derived timeline events for that student-sync cycle

---

### AC-3 — Attribution Consistency

**Given** a GHL webhook event is ingested
**When** the event is stored and surfaced in the student timeline
**Then** `origin_source = ghl_webhook`, `origin_authority = platform_supplementary`, and `is_authoritative = false` are present on the stored record; the provider's message ID is preserved in `processed_events`; the event's `attribution_timestamp` reflects the GHL event occurrence time, not the platform ingestion time

---

### AC-4 — Reproducibility Preservation

**Given** a historical report regeneration is triggered for a FINALIZED snapshot
**When** the regeneration completes
**Then** AI narrative content is sourced exclusively from `warehouse.snapshot_ai_narratives` (physical copy); no SQL Server query is executed; no AI provider API call is made; running the same regeneration twice produces identical output

---

### AC-5 — Append-Only Guarantees

**Given** any number of SQL Server syncs, GHL webhook deliveries, or AI generation completions have executed
**When** the `warehouse` and `compliance_audit` schemas are inspected
**Then** no `UPDATE` or `DELETE` statement has executed against any row in either schema from any application service account; all rows are the result of `INSERT` operations only

---

### AC-6 — Authoritative-Boundary Preservation

**Given** a SQL Server sync updates `PerComp_Act` for a student
**When** the updated value is available in `student_trigger_data`
**Then** the next cohort classification run uses the SQL Server-derived value; any prior platform-supplementary estimate for the same field is superseded; the SQL Server-derived value carries `origin_source = mirrored_sql_server` in the audit log; the platform-supplementary estimate is retained as context, not deleted

---

### AC-7 — Governance Isolation

**Given** a compliance deletion workflow is in `IN_EXECUTION`
**When** the deletion proceeds for one student
**Then** no GHL outreach trigger is generated for that student; no snapshot finalization is triggered; no AI generation job is triggered; the compliance execution is performed exclusively by the compliance pathway service account; no other student's operations are affected

---

## 14. DOWNSTREAM IMPLICATIONS

---

### 14.1 Service Layer

| Service | Integration dependency |
|---|---|
| `app/services/sync.py` | SQL Server read via pyodbc; upsert `student_trigger_data`; emit sync events with `sync_correlation_id`; attribution fields set at ingestion |
| `app/services/snapshot.py` | Reads `student_trigger_data` (post-sync); reads `ai_insights` (AI_REVIEWED); assembles DRAFT; delegates FINALIZED INSERT to finalization service account; captures config_version at content lock |
| `app/services/ai_insights.py` | Calls AI provider API; captures `prompt_version` at record creation; stores `model_used` from provider response; manages retry with exponential backoff |
| `app/services/report.py` | Reads `warehouse.student_snapshots` and `warehouse.snapshot_ai_narratives` ONLY (FAD-2); zero SQL Server queries; zero AI provider calls |
| `app/services/config_registry.py` | Exposes `get_active_version()` for snapshot generation; enforces exactly-one-ACTIVE invariant; exposes historical version lookup for audit |
| `app/services/compliance.py` | All writes via compliance pathway service account; reads from `compliance_audit` schema for export; no cross-schema FK joins |
| `app/services/ghl_sync.py` | Receives and validates GHL webhooks; deduplicates via `processed_events`; normalizes to platform event schema with attribution fields |
| `app/services/timeline.py` | Aggregates events from multiple sources; normalizes attribution fields; preserves `attribution_timestamp` vs `ingestion_timestamp` delta |

---

### 14.2 Scheduler Jobs

| Scheduler job | Integration dependency |
|---|---|
| Monthly snapshot batch | SQL Server sync must be recent (U-2 policy); AI insights must be at AI_REVIEWED; config version must be ACTIVE |
| AI refresh scheduler | AI provider API; exponential backoff on failure; writes to `ai_insights` only; does not write to warehouse |
| SQL Server sync scheduler | pyodbc connection; MSSQL read-only credentials; upsert semantics |
| GHL campaign reconciliation | GHL read-only API; writes to `student_campaign_activity`; deduplication via `processed_events` |
| Orphaned job detection | Scans for REPORT_REGENERATION_REQUESTED and REGENERATION_REQUESTED states beyond SLA window; alerts operator |

---

### 14.3 ETL Jobs

| ETL job | Ingestion type | Attribution requirement |
|---|---|---|
| SQL Server → `student_trigger_data` | Upsert per student row | `origin_source = mirrored_sql_server`; `sync_correlation_id` |
| GHL webhook → `ghl_messages`, `student_campaign_activity` | Append per event | `origin_source = ghl_webhook`; `ghl_message_id` preserved |
| `warehouse` → analytics warehouse | Read-only export | Fingerprint metadata included; no write-back |

---

### 14.4 AI Orchestration

| Stage | External call | Platform write |
|---|---|---|
| AI generation (pre-governance) | AI provider API | `ai_insights` record (version-append) |
| AI physical copy at finalization | None (reads from `ai_insights`) | `warehouse.snapshot_ai_narratives` |
| AI at regeneration | None (reads from snapshot row) | No write; report rendering only |

---

### 14.5 Observability

Each integration surface must emit structured log events:

| Surface | Required log events |
|---|---|
| SQL Server sync | sync_start, sync_end, rows_fetched, rows_upserted, correlation_id, duration_ms, outcome |
| GHL webhook | event_received, dedup_result (new/duplicate), attribution_timestamp_delta_ms, event_type |
| AI generation | provider_call_start, provider_call_end, model_used, prompt_version, duration_ms, outcome, retry_count |
| Snapshot finalization | config_version_id_captured, fingerprint_components (per component: value or UNKNOWN_V0), ai_reviewed_available, ai_content_stale, outcome |
| Report generation | source_snapshot_id, source_fingerprint, generation_duration_ms, outcome |
| Compliance execution | workflow_id, action_type, tables_scoped, tables_completed, pre_action_audit_verified, outcome |

Missing required attribution fields in any log line are treated as observability defects, not acceptable omissions.

---

## 15. UNRESOLVED INTEGRATION CONCERNS

---

### UI-1 — SQL Server Connection Environment Compatibility (HIGH)

**Problem:** SQL Server ODBC connection parameters (driver string, server name, trusted connection vs credentials mode) are environment-specific. The pyodbc connection string for dev vs staging vs production has not been validated across all environments.

**Impact:** Blocks first production SQL Server sync. All downstream features (cohort classification, snapshot generation, outreach triggering) depend on a working sync.

**Owner:** Infrastructure + backend engineering.

---

### UI-2 — SQL Server Sync Recency Policy (HIGH)

**Problem:** No threshold defines how recent the last SQL Server sync must be for snapshot content lock to proceed. If `student_trigger_data` is 24 or 72 hours stale, should snapshot generation block, proceed with a staleness flag, or use a different behavior?

**Impact:** Blocks production snapshot generation scheduling. Without this policy, the batch runner cannot make a principled decision about whether to proceed or wait.

**Owner:** Operations + academic team.

---

### UI-3 — GHL Webhook Authentication (MEDIUM)

**Problem:** The mechanism for verifying GHL webhook signatures (HMAC, shared secret, IP allowlist) is not defined in the platform spec. Without signature verification, all inbound GHL payloads are treated as unverified.

**Impact:** Security exposure. Any actor that knows the webhook endpoint can inject fake communication events. Resolution required before PRODUCTION scope.

**Owner:** GHL integration developer + security.

---

### UI-4 — GHL API Rate Limits (MEDIUM)

**Problem:** The exact GHL API rate limits (per-minute, per-day, per-endpoint) are not documented in this spec. The retry strategy references "GHL Retry-After header" but GHL may not provide consistent rate limit headers.

**Impact:** Blocks hardening of the outbound GHL integration retry strategy. Aggressive retry without known limits risks GHL account throttling.

**Owner:** GHL integration developer.

---

### UI-5 — AI Provider API Key Rotation (MEDIUM)

**Problem:** No in-memory config reload path exists for AI provider API keys. Key rotation currently requires a service restart or redeploy to pick up new credentials from environment variables.

**Impact:** Key rotation causes brief service downtime for AI generation. Acceptable for MVP; not acceptable for PRODUCTION SLA.

**Owner:** Infrastructure.

---

### UI-6 — Analytics Warehouse Column Mapping (LOW)

**Problem:** The column mapping from `warehouse.student_snapshots` to external analytics warehouse target schemas is not defined. The fingerprint metadata inclusion strategy for external warehouses is unspecified.

**Impact:** Blocks external analytics warehouse integration. Does not block core platform operation.

**Owner:** Data team.

---

### UI-7 — Compliance Export Serialization Format (LOW)

**Problem:** The structured compliance export format (`GET /compliance/audit/export`) is defined conceptually but the exact serialization format (JSON, CSV, XML, NDJSON) for external portal consumption is unresolved.

**Impact:** Blocks external GDPR portal integration. Does not block internal platform compliance workflow.

**Owner:** Compliance team.

---

## 16. INTEGRATION INVARIANTS

---

* SQL Server is never written to from any platform service account — ever
* `warehouse` and `compliance_audit` schemas are never subject to `UPDATE` or `DELETE` from any application service account
* `origin_source` is never overwritten after ingestion by any transform or processing step
* Historical regeneration never contacts external systems — no SQL Server queries, no AI provider calls
* AI physical copy in `warehouse.snapshot_ai_narratives` is isolated from all subsequent `ai_insights` lifecycle events
* Config version changes are always prospective; historical snapshots always retain the config version active at their content lock time
* Compliance workflows are never triggered by automated platform processes; they are always initiated by authorized human actors
* Every duplicate detection event (webhook, sync, finalization, compliance intake) produces an audit log entry — no silent drops

---

## 17. SCOPE-SPECIFIC BEHAVIOR SUMMARY

---

### MVP

* Full-table SQL Server sync per invocation
* Basic GHL webhook ingestion with deduplication
* One AI provider; one retry on failure
* No signature verification on GHL webhooks
* No incremental sync; no circuit breaker
* Sync recency policy not enforced

---

### STANDARD

* Incremental SQL Server sync with `since_timestamp` parameter
* GHL webhook signature verification
* AI retry with exponential backoff (max 3 attempts)
* Reconciliation jobs for sync coverage and AI insight coverage
* Sync recency policy enforced at snapshot content lock

---

### PRODUCTION

* Full circuit breaker on AI provider and GHL API
* GHL rate-limit-aware retry with backoff
* In-memory config reload for AI provider API keys
* Automated orphaned-job detection and alerting
* Analytics warehouse export pipeline operational
* Full observability on all integration surfaces

---

## 18. REFERENCES

---

Canonical inputs:

* `spec/01_requirements.md` — System purpose, operational domains, cohort identification rules
* `spec/03_state_transition_rules.md` — All 6 lifecycle domain state machines; Event Attribution Standard §39; Cross-Domain Invariants §40–44
* `spec/04_idempotency_concurrency.md` — Idempotency keys per domain; CONC-INVARIANT-1 through CONC-INVARIANT-7; §17 AI Generation Idempotency; §20 Event Idempotency and Attribution
* `spec/07_api_contracts.md` — API contracts for sync, snapshot, report, AI insights, config version, compliance endpoints
* `spec/08_data_model.md` — Dual-database architecture; three-schema separation; data sources and authority levels
* `spec/09_warehouse_physical_architecture.md` — Physical boundary map; append-only enforcement; access control profiles
* `spec/10_pre_migration_storage_validation.md` — AI narrative storage design; TOAST validation; snapshot physicalization
* `alembic/versions/0002_warehouse_schema.py` — warehouse and compliance_audit schema DDL; access control grants
* `alembic/versions/0003_config_version_registry.py` — config_version_registry DDL; exactly-one-ACTIVE partial unique index; V1 seed

---

## END OF FILE
