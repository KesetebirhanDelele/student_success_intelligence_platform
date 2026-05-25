# spec/09_warehouse_physical_architecture.md

---

## LAYER 2 — SPECIFICATIONS (PHYSICAL WAREHOUSE ARCHITECTURE)

---

## 1. PHYSICAL ARCHITECTURE OVERVIEW

---

### 1.1 Purpose and Scope

This document translates the conceptual data model in `spec/08_data_model.md` into a concrete physical storage architecture that can be directly implemented via Alembic migrations. It defines table groupings, column strategy, append-only enforcement mechanisms, lineage storage patterns, and the exact physical boundaries of each schema domain. No SQL DDL, ORM code, or migration code appears in this document.

### 1.2 Three-Schema Physical Boundary Map

PostgreSQL is divided into three physically isolated schema domains with distinct access control profiles, mutability guarantees, and lifecycle semantics.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  SQL Server (READ-ONLY)                                                  │
│  AI_ChatBot_TriggerData — authoritative source for student academic state│
└──────────────────────────────┬──────────────────────────────────────────┘
                               │  sync (POST /sync/mssql)
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PostgreSQL — public schema (Operational)                                │
│  Full READ+WRITE for standard application service account               │
│                                                                          │
│  student_trigger_data       (SQL Server mirror — mutable on sync)        │
│  student_outreach_tracking  (outreach state machine)                     │
│  outreach_history           (append-only outreach log)                   │
│  state_transition_log       (append-only transition log)                 │
│  student_notes              (mutable operator notes)                     │
│  ai_insights                (versioned AI output)                        │
│  ghl_messages               (GHL message cache)                          │
│  student_campaign_activity  (append-only campaign log)                   │
│  student_quick_action_log   (append-only action audit)                   │
│  processed_events           (idempotency store)                          │
│  config_version_registry    (governance version records) [0003]          │
│  snapshot_draft_queue       (draft lifecycle tracking)  [0006]           │
└──────────────────────────────┬──────────────────────────────────────────┘
       FINALIZED ────────────► │  finalization service account (INSERT only)
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PostgreSQL — warehouse schema (Immutable Historical Archive)            │
│  SELECT-only for standard application service account                   │
│  INSERT-only for finalization service account                           │
│  No UPDATE or DELETE permitted from any application account             │
│                                                                          │
│  warehouse.student_snapshots       (one row per student per month)       │
│  warehouse.snapshot_ai_narratives  (1:1 companion — AI text physical    │
│                                     copy; separate for row compactness)  │
│  warehouse.monthly_reports         (one row per publication/lineage)     │
│  warehouse.report_audit_log        (append-only lifecycle events)        │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │  compliance pathway account (restricted)
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PostgreSQL — compliance_audit schema (Governance-Isolated)              │
│  SELECT-only for standard application service account                   │
│  INSERT-only for compliance pathway service account                     │
│  No UPDATE or DELETE from any account — ever                            │
│  No FK dependencies on public or warehouse schemas                      │
│                                                                          │
│  compliance_audit.deletion_log     (pre/post audit entries — permanent) │
│  compliance_audit.scope_manifests  (captured at APPROVED_FOR_ACTION)    │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.3 Append-Only Enforcement Strategy

Append-only semantics are enforced at two independent layers:

| Layer | Mechanism | Applies to |
|---|---|---|
| Database permission layer | Standard service account has SELECT-only on `warehouse` and `compliance_audit`; no UPDATE or DELETE grants | `warehouse`, `compliance_audit` |
| Application state machine layer | FINALIZED, REPORT_PUBLISHED, ACTIVE→SUPERSEDED transitions are one-way with no reversal code path | All governance boundaries |
| Public schema append-only tables | Application layer convention; no DB-level enforcement needed — tables are designed as audit logs, not mutable entities | `outreach_history`, `state_transition_log`, `student_campaign_activity`, `student_quick_action_log` |

The database-level enforcement is the hard guarantee. The application-layer convention is defense in depth.

### 1.4 Immutable History Enforcement Strategy

A finalized snapshot or published report cannot be mutated even if the application code contains a bug that attempts an UPDATE. The enforcement sequence is:

1. Standard service account: `GRANT SELECT ON ALL TABLES IN SCHEMA warehouse` — no INSERT, UPDATE, DELETE grants
2. Finalization service account: `GRANT INSERT ON warehouse.student_snapshots, warehouse.snapshot_ai_narratives, warehouse.monthly_reports, warehouse.report_audit_log` — no UPDATE, DELETE grants
3. Application code never calls `warehouse.finalization_account` functions directly; the finalization path is a dedicated service boundary

This means an accidental UPDATE in application code fails at the database layer, not the application layer. The error surfaces as a PostgreSQL `insufficient_privilege` error, not a silent no-op.

### 1.5 Regeneration Lineage Strategy

Regeneration never overwrites. Each regeneration produces a new row in `warehouse.monthly_reports` with:
- `lineage_version` = prior version + 1
- `parent_report_id` = the previous REPORT_PUBLISHED row's ID
- `source_snapshot_fingerprint` = fingerprint of the source snapshot at regeneration job start
- `POTENTIALLY_DIVERGENT` flag = true if source fingerprint differs from original publication fingerprint

The original REPORT_PUBLISHED row is never touched. Both rows are independently queryable.

### 1.6 Publication Lineage Strategy

A report's complete publication history is a linked list:

```
monthly_reports row (lineage_version=1, parent_report_id=NULL)
    ↓ parent_report_id
monthly_reports row (lineage_version=2, parent_report_id=row_1_id)
    ↓ parent_report_id
monthly_reports row (lineage_version=3, parent_report_id=row_2_id)
```

The current publication for a `(cohort_id, report_month)` is the row with the highest `lineage_version` in REPORT_PUBLISHED state. All prior lineage members are preserved. No publication row is ever deleted by the application.

---

## 2. PHYSICAL ENTITY GROUPING STRATEGY

---

Nine physical storage domains, each with a defined purpose, mutability contract, and access profile.

### Domain 1 — SQL Server Mirror (Operational Intelligence Source)

| Property | Value |
|---|---|
| Schema | `public` |
| Primary table | `student_trigger_data` |
| Purpose | Current operational state of all students; powers lifecycle tabs, segmentation, eligibility, and snapshot generation |
| Mutability | Upserted on every `POST /sync/mssql` call; full replacement of all mirror columns per student |
| Retention | Operational window; no historical retention — historical state is captured in warehouse snapshots |
| Ownership | Platform (derivative; SQL Server is the authority) |
| Access | Standard service account: READ+WRITE |

### Domain 2 — Outreach State Machine (Operational Audit)

| Property | Value |
|---|---|
| Schema | `public` |
| Tables | `student_outreach_tracking`, `outreach_history`, `state_transition_log` |
| Purpose | Records every outreach action, state transition, and current outreach state per student |
| Mutability | `student_outreach_tracking`: mutable state machine; `outreach_history` and `state_transition_log`: append-only |
| Retention | Indefinite; these are the authoritative outreach history records |
| Ownership | Platform |
| Access | Standard service account: READ+WRITE |

### Domain 3 — Communication Telemetry (Unified Timeline Source)

| Property | Value |
|---|---|
| Schema | `public` |
| Tables | `ghl_messages`, `student_campaign_activity`, `student_quick_action_log` |
| Purpose | Provides the raw events that feed the unified communication timeline |
| Mutability | Append-only on record; no updates to existing records |
| Retention | `ghl_messages`: idempotent cache, replaced on re-sync; `student_campaign_activity` and `student_quick_action_log`: indefinite |
| Ownership | Platform |
| Access | Standard service account: READ+WRITE |

### Domain 4 — Monthly Snapshots (Historical Archive)

| Property | Value |
|---|---|
| Schema | `warehouse` |
| Tables | `warehouse.student_snapshots`, `warehouse.snapshot_ai_narratives` |
| Purpose | Immutable point-in-time state of every student at each month-end; primary source for all historical analytics and report generation |
| Mutability | Append-only after FINALIZED; no UPDATE or DELETE from any application account |
| Retention | Indefinite until compliance deletion (U-9 to be resolved before first production snapshot) |
| Ownership | Platform |
| Access | Standard: SELECT-only; Finalization service: INSERT-only; Compliance pathway: SELECT-only |

### Domain 5 — Report Publication (Historical Archive)

| Property | Value |
|---|---|
| Schema | `warehouse` |
| Tables | `warehouse.monthly_reports`, `warehouse.report_audit_log` |
| Purpose | Immutable record of every published and regenerated report, with full lineage and source attribution |
| Mutability | Append-only after REPORT_PUBLISHED; regeneration creates new rows, never modifies existing |
| Retention | Indefinite |
| Ownership | Platform |
| Access | Standard: SELECT-only; Finalization service: INSERT-only |

### Domain 6 — AI Insight Lineage (Operational Intelligence)

| Property | Value |
|---|---|
| Schema | `public` |
| Tables | `ai_insights` |
| Purpose | Live, versioned AI-generated insights per student; powers dashboard AI panels and provides source for snapshot AI copy at finalization time |
| Mutability | Version-append: each force-refresh creates a new record; no in-place mutation of any version |
| Retention | All versions retained indefinitely; never deleted |
| Ownership | Platform |
| Access | Standard service account: READ+WRITE |

### Domain 7 — Configuration Version Registry (Governance)

| Property | Value |
|---|---|
| Schema | `public` |
| Tables | `config_version_registry` |
| Purpose | Governs which classification thresholds, scoring formulas, and behavioral parameters are active; provides the `configuration_registry_version` component of the reproducibility fingerprint |
| Mutability | Append-only: each version record is immutable once created; activation state changes are recorded as column updates on the same row (status field only) |
| Retention | Indefinite; all versions retained for audit |
| Ownership | Platform |
| Access | Standard service account: READ + restricted WRITE (status column only via dedicated service function) |

**Note on config version mutability:** The `status` column on a config version record changes (DRAFT → UNDER_REVIEW → APPROVED → ACTIVE → SUPERSEDED). This is the only mutable column; all threshold values and metadata are immutable once created. This is acceptable because it represents governance state progression, not data mutation. The activation lineage is queryable from the `activated_at` and `superseded_at` timestamps on each row.

### Domain 8 — Event Timeline Storage (Operational Log)

| Property | Value |
|---|---|
| Schema | `public` |
| Tables | `student_timeline_events` (new — migration 0006 or standalone) |
| Purpose | Unified append-only event log for all non-compliance timeline events; normalized display source for unified timeline rendering |
| Mutability | Append-only always |
| Retention | Indefinite |
| Ownership | Platform |
| Access | Standard service account: READ+INSERT (no UPDATE/DELETE) |

See Section 5 for the detailed event storage strategy and hybrid approach.

### Domain 9 — Compliance Audit (Governance-Isolated)

| Property | Value |
|---|---|
| Schema | `compliance_audit` |
| Tables | `compliance_audit.deletion_log`, `compliance_audit.scope_manifests` |
| Purpose | Governance-isolated, permanent audit trail for all deletion and anonymization operations; survives operational deletions |
| Mutability | Append-only always; no deletion ever permitted |
| Retention | Permanent — not subject to any data retention policy |
| Ownership | Platform (compliance pathway only) |
| Access | Standard: SELECT-only; Compliance pathway: INSERT-only |

---

## 3. SNAPSHOT STORAGE STRATEGY

---

### 3.1 Snapshot Granularity

One finalized snapshot row per `(student_id, snapshot_month)`. The combination is a unique business key. Uniqueness is enforced at the application layer before finalization write; no duplicate FINALIZED snapshot can exist for the same `(student_id, snapshot_month)`.

Draft snapshots (before FINALIZED) live in the `public` schema snapshot draft queue table. Only FINALIZED snapshots are written to `warehouse.student_snapshots`.

### 3.2 Two-Table Physical Strategy for Snapshot Storage

**Decision: Two warehouse tables in a 1:1 physical relationship.**

The snapshot is physically split into:

1. `warehouse.student_snapshots` — the metrics row (compact, queryable for analytics)
2. `warehouse.snapshot_ai_narratives` — the AI text companion (large text blobs, isolated from analytical queries)

**Rationale:**

Monthly snapshot rows contain up to five AI narrative fields (risk_summary_text, progress_summary_text, monthly_narrative_text, intervention_recommendation_text, trend_interpretation_text). Each field may hold 200–1,000+ words. With 2,000+ students and 36+ months of history, inline storage inflates every analytical query with text column data even when text is not needed. Separating the text into a companion table:

- Keeps the main snapshot row compact for aggregations, trend analysis, and cohort statistics
- Preserves full FAD-1 compliance: physical copy semantics, no FK to `ai_insights`, immune to future AI operations
- Maintains identical immutability semantics (companion table is also in `warehouse` schema, SELECT-only for standard account)
- Enables embedding generation from narrative text without loading full metric rows

The companion table has a FK to `warehouse.student_snapshots.id` (NOT to `ai_insights`). This FK enforces referential integrity within the warehouse schema while keeping the isolation boundary intact.

**This is NOT reference semantics (FAD-1 compliance confirmed):** The AI text in `warehouse.snapshot_ai_narratives` is a physical point-in-time copy written at finalization. Future operations on `ai_insights` (force-refresh, model change, new generation) have zero effect on any row in `warehouse.snapshot_ai_narratives`. Regeneration reads from `warehouse.snapshot_ai_narratives` directly — never from `ai_insights`.

**Recommendation: Benchmark before finalizing.** Before authoring `0002_warehouse_schema.py`, measure representative AI narrative lengths across all five types using current `ai_insights` content. If the median total narrative payload per student is under 8 KB, the inline single-table approach remains viable and simpler. If the median exceeds 8 KB or p95 exceeds 20 KB, the two-table approach is the correct physical choice. The two-table approach is the safe default for a system targeting 36+ months of history at 2,000+ students.

### 3.3 warehouse.student_snapshots — Column Groupings

The main snapshot row is organized into six logical column groups:

**Identity and Lifecycle (required)**
- `id` — surrogate PK
- `student_id` — SQL Server UserID at snapshot time (physical copy; no FK to student_trigger_data)
- `snapshot_month` — the month this snapshot covers (DATE, first day of month)
- `status` — FINALIZED | REGENERATION_REQUESTED | COMPLIANCE_HOLD | COMPLIANCE_DELETED
- `lineage_version` — 1 for original; incremented on regeneration
- `parent_snapshot_id` — NULL for original; references prior lineage member on regeneration
- `POTENTIALLY_DIVERGENT` — boolean; true when regeneration source fingerprint differs from original
- `finalized_at` — when FINALIZED state was reached
- `correlation_id` — UUID v4 from the finalization job that created this row

**SQL Server Metric Columns (physical copy at snapshot_month cutoff)**
All columns from `student_trigger_data` as they existed at sync time. These are physical copies — not live references. Column names match `student_trigger_data` with a `ss_` prefix to distinguish them from live mirror columns during joins.

**Derived Metrics (computed at finalization)**
- `segment_classification` — NEWCOMERS | CAP_HOPEFULS | LAUNCH_HOPEFULS | PLACEMENT_HOPEFULS | HYPER_ACTIVE
- `payment_risk_label` — CLEAR | MEDIUM | HIGH
- `hw_risk_score` — ON_TRACK | AT_RISK | CRITICAL
- `actual_balance` — bundle-corrected balance computed at finalization
- `is_bundle_deal` — boolean
- `weeks_in_program` — computed at finalization
- `days_since_last_submission` — computed at finalization

**Communication Summary (computed at finalization from append-only operational tables)**
- `total_outreach_attempts`
- `total_responses`
- `last_contact_date`
- `days_since_last_contact`
- `channel_breakdown_json` — JSONB: `{CALL: N, SMS: N, EMAIL: N}`

**Reproducibility Fingerprint (all 5 components — immutable after FINALIZED)**
- `fingerprint_schema_version` — TEXT, Alembic revision active at finalization
- `fingerprint_config_registry_version` — TEXT, config version ID active at DRAFT→VALIDATING
- `fingerprint_report_template_version` — TEXT, report template version active at snapshot time
- `fingerprint_ai_versions_json` — JSONB, per-type map: `{"risk_summary": {"prompt": "v1.2", "model": "claude-sonnet-4-6"}, ...}`
- `fingerprint_computed_at` — TIMESTAMPTZ, when fingerprint was locked (at FINALIZED transition)

Using individual scalar columns for three fingerprint components (schema_version, config_registry_version, report_template_version) allows direct equality filtering without JSON path queries — important for fingerprint mismatch detection and audit queries. The per-type AI version map remains JSONB because the set of insight types may expand without schema change.

**Metadata**
- `created_at` — when the DRAFT snapshot was created
- `execution_mode` — SHADOW | LIVE
- `generated_by` — service account or job identifier

### 3.4 warehouse.snapshot_ai_narratives — Column Groupings

This is the 1:1 AI text companion to the main snapshot row.

- `id` — surrogate PK
- `snapshot_id` — FK to `warehouse.student_snapshots.id`; NOT NULL; NOT to `ai_insights`
- `risk_summary_text` — TEXT; physical copy; NULL if AI_REVIEWED did not exist at finalization
- `progress_summary_text` — TEXT; physical copy; NULL if absent at finalization
- `monthly_narrative_text` — TEXT; physical copy; NULL if absent
- `intervention_recommendation_text` — TEXT; physical copy; NULL if absent
- `trend_interpretation_text` — TEXT; physical copy; NULL if absent
- `copied_at` — TIMESTAMPTZ; when the AI text was copied (= finalization time)
- `ai_source_insight_id_hint` — INTEGER; non-FK advisory reference to the `ai_insights.id` that was copied; no FK constraint; used for audit trail only (answers "which insight record was the source?"); the hint becomes stale if the `ai_insights` record is deleted — this is acceptable because the text is a physical copy

### 3.5 Snapshot Lineage Relationships

```
warehouse.student_snapshots (lineage_version=1, parent_snapshot_id=NULL)
    ↑ referenced by parent_snapshot_id
warehouse.student_snapshots (lineage_version=2, parent_snapshot_id=row_1_id)
    ↑ referenced by parent_snapshot_id
warehouse.student_snapshots (lineage_version=3, parent_snapshot_id=row_2_id)
```

Querying the full lineage for a `(student_id, snapshot_month)` traverses `parent_snapshot_id` from the current row backwards to lineage_version=1. All lineage members are preserved. No deletion of prior lineage members.

### 3.6 Reproducibility Invariant Under Physical Strategy

Given the two-table design, reproducibility is maintained as follows:

| Concern | Physical guarantee |
|---|---|
| Same snapshot → same report output | Main row metrics + AI text companion are both immutable after FINALIZED; report generation reads from both |
| AI change after finalization | `snapshot_ai_narratives` is in `warehouse` schema; no UPDATE path exists; physically immune |
| Regeneration reads correct AI content | Regeneration job reads from `warehouse.snapshot_ai_narratives`, never from `ai_insights`; text is unchanged since finalization |
| Fingerprint locked | `fingerprint_*` columns are immutable after FINALIZED (warehouse schema permission enforcement) |

---

## 4. REPORT ARTIFACT STORAGE STRATEGY

---

### 4.1 warehouse.monthly_reports — Column Groupings

**Identity and Lineage**
- `id` — surrogate PK
- `cohort_id` — the cohort this report covers (maps to a `ClassName` or cohort identifier)
- `report_month` — DATE (first day of month)
- `template_version` — version of the report template used
- `lineage_version` — 1 for original publication; incremented on regeneration
- `parent_report_id` — NULL for lineage_version=1; FK to prior lineage member
- `status` — REPORT_PENDING | REPORT_GENERATING | REPORT_GENERATED | REPORT_REVIEW_PENDING | REPORT_APPROVED | REPORT_PUBLISHED | REPORT_GENERATION_FAILED | REPORT_REJECTED
- `POTENTIALLY_DIVERGENT` — boolean; true when regeneration source fingerprint differs from original

**Source Attribution (FAD-2)**
- `source_snapshot_fingerprint_json` — JSONB; the collective fingerprint of all source snapshots at job creation time
- `report_idempotency_key` — TEXT; deterministic key for this exact `(cohort_id, report_month, template_version, lineage_version)` combination; prevents duplicate generation jobs

**Rendered Content**
- `report_content_json` — JSONB; the structured report payload (metrics, AI narratives, cohort statistics, trend interpretation, placement pipeline status); self-contained for PDF rendering
- `aggregate_stats_json` — JSONB; pre-computed cohort-level statistics (engagement rate, payment compliance rate, hw risk rate, placement count)

**Metadata**
- `generated_at` — TIMESTAMPTZ; when report generation completed
- `published_at` — TIMESTAMPTZ; when REPORT_PUBLISHED state was reached
- `generated_by` — service or operator identifier
- `correlation_id` — UUID v4 from the generation job
- `execution_mode` — SHADOW | LIVE

**On inline JSONB for report content:** The structured report payload (report_content_json) is stored as JSONB in the monthly_reports row for the initial implementation. This is acceptable because:

- Monthly reports are queried per `(cohort_id, report_month)` — one row at a time, not in aggregate scans
- JSONB enables partial extraction of specific sections without loading the full payload in most query patterns
- PostgreSQL handles JSONB compression efficiently for large documents

Future evolution path: if report content payloads exceed ~1 MB or if object storage is introduced for PDF rendering, the content can be migrated to an external blob store with a signed URL reference in `report_content_url`. The schema accommodates this without a breaking change by adding the URL column and deprecating the JSONB column.

### 4.2 warehouse.report_audit_log — Column Groupings

Append-only log of every lifecycle event for every report.

- `id` — surrogate PK
- `report_id` — FK to `warehouse.monthly_reports.id`
- `event_type` — `GenerationJobCreated | GenerationCompleted | PublicationCommitted | RegenerationRequested | PotentiallyDivergentFlagged | GenerationFailed`
- `report_idempotency_key` — denormalized copy from the report row (enables audit queries without join)
- `source_snapshot_fingerprint_json` — JSONB; fingerprint at event time
- `event_details_json` — JSONB; event-type-specific context
- `correlation_id` — UUID v4
- `actor` — service or operator identifier
- `created_at` — TIMESTAMPTZ

### 4.3 Report Immutability Under Regeneration

| Scenario | Behavior |
|---|---|
| First publication | `lineage_version=1`, `parent_report_id=NULL`, `POTENTIALLY_DIVERGENT=false` |
| Regeneration (same fingerprint) | New row; `lineage_version=2`; `parent_report_id=row_1_id`; `POTENTIALLY_DIVERGENT=false` |
| Regeneration (different fingerprint) | New row; `lineage_version=2`; `POTENTIALLY_DIVERGENT=true`; audit entry with both fingerprints |
| In-place update | **Not possible** — warehouse schema is SELECT-only for standard account; finalization account has INSERT-only |

The current publication for a `(cohort_id, report_month)` is always the row with `status = REPORT_PUBLISHED AND lineage_version = (SELECT MAX(lineage_version) FROM warehouse.monthly_reports WHERE cohort_id = X AND report_month = Y AND status = 'REPORT_PUBLISHED')`.

---

## 5. EVENT TIMELINE STORAGE STRATEGY

---

### 5.1 Unified vs. Segmented — Decision: Hybrid

A fully unified single-table approach (one table, all event types, polymorphic JSONB detail) and a fully segmented approach (one table per event type) both have drawbacks at the scale and diversity of SSIP's event model. The recommended hybrid:

| Event category | Physical storage | Schema |
|---|---|---|
| Operational and communication events (CommunicationEvent, AccessHistoryEvent, AILifecycleEvent, SnapshotLifecycleEvent, ConfigLifecycleEvent) | `public.student_timeline_events` — unified table with `event_type` discriminator + `detail_json` JSONB | `public` |
| Report lifecycle events | `warehouse.report_audit_log` — already defined in Section 4.2 | `warehouse` |
| Compliance lifecycle events | `compliance_audit.deletion_log` — governance-isolated | `compliance_audit` |

**Rationale for unified operational events table:** The five operational event types share identical attribution fields (correlation_id, attribution_timestamp, origin_source, origin_authority, execution_mode). They are all rendered in the same unified timeline view. A single table with a discriminator enables the timeline query to be a single scan rather than a UNION across five tables. Event-type-specific data lives in `detail_json` — not in typed columns — keeping the physical schema stable as new event subtypes are introduced.

### 5.2 public.student_timeline_events — Column Strategy

**Universal Attribution Fields (present on every row — NOT in detail_json)**

These fields are in top-level columns because they are used in WHERE clauses, ORDER BY, and aggregations.

- `id` — surrogate PK
- `student_id` — INTEGER; SQL Server UserID
- `event_type` — VARCHAR; stable discriminator: `CommunicationEvent | AccessHistoryEvent | AILifecycleEvent | SnapshotLifecycleEvent | ConfigLifecycleEvent`
- `event_subtype` — VARCHAR; e.g., `OutreachAttempt | OperatorLoggedActivity | GHLMessageCached | DraftCreated | FinalizationCompleted | ...`
- `attribution_timestamp` — TIMESTAMPTZ; when the event occurred (NOT when logged)
- `origin_source` — VARCHAR: `mirrored_sql_server | operator | system | ghl_sync | compliance_pathway`
- `origin_authority` — VARCHAR: `sql_server_authoritative | platform_supplementary | platform_owned`
- `execution_mode` — VARCHAR: `SHADOW | LIVE`
- `correlation_id` — UUID; the request correlation ID that produced this event
- `is_authoritative` — BOOLEAN; true for `origin_authority = sql_server_authoritative`

**Content**
- `display_label` — VARCHAR; human-readable event label for timeline rendering (denormalized to avoid runtime label computation)
- `channel` — VARCHAR NULL; `SMS | EMAIL | CALL | CAMPAIGN | NOTE | AI_SUMMARY | NULL` (NULL for non-communication events)
- `detail_json` — JSONB; event-type-specific context; nullable (some events have no detail beyond top-level fields)

**Metadata**
- `created_at` — TIMESTAMPTZ; when this row was inserted (differs from `attribution_timestamp` for mirrored SQL Server events)

### 5.3 SQL Server Event Distinguishability (FAD-5)

SQL Server-mirrored access events are distinguished from platform-originated events by:

- `origin_source = 'mirrored_sql_server'`
- `origin_authority = 'sql_server_authoritative'`
- `is_authoritative = true`

On conflict (same `(student_id, event_type, attribution_timestamp)` with different `origin_source`):
- Both rows are retained (append-only)
- The conflict is logged in `detail_json` with a `conflict_detected` flag and `conflicting_correlation_id`
- The `is_authoritative` field identifies which row governs for operational decisions
- No row is deleted or overwritten

### 5.4 Replay Safety

The event table is idempotency-safe because:
- Events are identified by `(student_id, event_subtype, attribution_timestamp, origin_source)` for deduplication checks
- The `processed_events` idempotency store in `public` schema gates event writes using an event-specific idempotency key
- Replay of the same event produces a no-op (idempotency key exists); the original row is not duplicated

### 5.5 Correlation ID Strategy

Every event row carries a `correlation_id` generated at the entry point of the request or job that triggered the event. The correlation ID flows through:

- The HTTP request header (`X-Correlation-ID`)
- The job payload (for scheduled jobs)
- All downstream log entries in the application
- The database rows written during the request lifetime

This means any event can be traced back to the originating request by filtering `correlation_id` across all tables, log streams, and external API calls.

---

## 6. CONFIGURATION VERSION STORAGE STRATEGY

---

### 6.1 public.config_version_registry — Column Strategy

**Identity and Lifecycle**
- `id` — surrogate PK
- `version_number` — INTEGER; monotonically increasing; seed V1 = 1
- `status` — VARCHAR: `DRAFT | UNDER_REVIEW | APPROVED | ACTIVE | SUPERSEDED | REJECTED`
- `effective_from` — TIMESTAMPTZ; when this version became ACTIVE (NULL until activation)
- `activated_at` — TIMESTAMPTZ; alias for effective_from (explicit for query clarity)
- `superseded_at` — TIMESTAMPTZ; when this version was superseded (NULL until superseded)
- `prior_version_id` — FK to `config_version_registry.id`; NULL for V1

**Governance Metadata**
- `change_rationale` — TEXT NOT NULL; required description of why this version was created
- `proposed_by` — VARCHAR; identity of the operator who drafted this version
- `approved_by` — VARCHAR NULL; identity of the reviewer who approved it
- `activated_by` — VARCHAR NULL; identity who activated it

**Rule Set (one column per configurable rule — all from spec/01 Sections 12.1–12.7)**

Cohort Identification:
- `cap_hopeful_min_percomp` — DOUBLE PRECISION; default 0.30
- `launch_hopeful_min_percomp` — DOUBLE PRECISION; default 0.59
- `cap_section_exclusion_patterns_json` — JSONB; default `["%launch%", "%CAP%"]`
- `launch_section_inclusion_pattern` — VARCHAR; default `%CAP%`
- `placement_section_inclusion_pattern` — VARCHAR; default `%launch%`

Homework Risk:
- `hw_at_risk_min_behind` — INTEGER; default 1
- `hw_at_risk_max_eff_rating` — DOUBLE PRECISION; default 3.0
- `hw_critical_min_behind` — INTEGER; default 3
- `hw_critical_max_eff_rating` — DOUBLE PRECISION; default 2.0

Payment Risk:
- `payment_medium_threshold` — DOUBLE PRECISION; default 0.01
- `payment_high_threshold` — DOUBLE PRECISION; default 1000.00

Priority Scoring:
- `priority_hw_weight` — INTEGER; default 10
- `priority_hw_cap` — INTEGER; default 50
- `priority_eff_weight` — INTEGER; default 7
- `priority_eff_cap` — INTEGER; default 35
- `priority_inactivity_weight` — INTEGER; default 2
- `priority_inactivity_cap` — INTEGER; default 50

Scheduling:
- `ai_insight_ttl_hours` — INTEGER; default 24
- `outreach_retry_window_days` — INTEGER; default 3
- `placement_inactivity_alert_days` — INTEGER; default 7
- `access_revocation_alert_hours` — INTEGER; default 48

**Metadata**
- `rule_set_snapshot_json` — JSONB; complete snapshot of all rule values at this version (for one-shot reproducibility audit without joining against individual columns)
- `created_at` — TIMESTAMPTZ

### 6.2 Exactly-One-ACTIVE Invariant Enforcement

Physical enforcement strategy: a partial unique index on `(status)` WHERE `status = 'ACTIVE'` ensures at most one ACTIVE row exists at the database layer. The application enforces the invariant via the atomic swap:

```
BEGIN TRANSACTION
  UPDATE config_version_registry SET status = 'SUPERSEDED', superseded_at = now() WHERE status = 'ACTIVE'
  UPDATE config_version_registry SET status = 'ACTIVE', activated_at = now() WHERE id = new_version_id AND status = 'APPROVED'
COMMIT
```

The partial unique index catches any double-ACTIVE scenario even if the transaction logic has a bug. Zero-ACTIVE windows are impossible within the transaction because the old version is only superseded after the new version is atomically activated in the same transaction.

### 6.3 Activation Lineage Query

The full activation history is queryable from the config_version_registry table itself:

```
For a given snapshot_month:
  SELECT * FROM config_version_registry
  WHERE activated_at <= snapshot_month_cutoff
    AND (superseded_at IS NULL OR superseded_at > snapshot_month_cutoff)
  ORDER BY version_number DESC
  LIMIT 1
```

This query returns exactly one row — the config version that was ACTIVE at the snapshot_month cutoff. No separate activation lineage table is needed; the timestamps on each version record provide the lineage.

### 6.4 Snapshot Config Version Reference

The binding of a snapshot to its config version is captured as:

- `fingerprint_config_registry_version` column on `warehouse.student_snapshots` (TEXT; the `version_number` as a string, stored at DRAFT→VALIDATING transition)
- The corresponding row in `public.config_version_registry` is the reference record

The binding is a logical reference (stored as a text version number), not a physical FK. This is intentional: compliance deletion or future config registry evolution cannot break the snapshot fingerprint via FK cascade.

---

## 7. COMPLIANCE AUDIT STORAGE STRATEGY

---

### 7.1 Isolation Architecture

The `compliance_audit` schema is physically isolated:
- No FK constraints pointing to `public` or `warehouse` tables
- No FK constraints from `public` or `warehouse` tables pointing to `compliance_audit`
- Standard application service account: SELECT-only
- Compliance pathway service account: INSERT-only (no UPDATE, DELETE)
- DBA account: full access for emergency auditor exports only

All writes to `compliance_audit` tables are made exclusively through the compliance pathway service boundary. Direct database writes by the application are prohibited.

### 7.2 compliance_audit.deletion_log — Column Strategy

This single table stores both PRE_ACTION and POST_ACTION audit entries. The `entry_type` discriminator distinguishes them. The pre-action entry must exist before IN_EXECUTION begins (hard gate enforced at application layer).

**Identity**
- `id` — surrogate PK
- `workflow_id` — UUID; unique per compliance workflow instance; shared across PRE_ACTION and POST_ACTION entries for the same workflow
- `sequence_number` — INTEGER; ordering within a workflow (PRE_ACTION = 1, POST_ACTION = 2+)
- `entry_type` — VARCHAR: `PRE_ACTION | POST_ACTION | PARTIAL_COMPLETION_CHECKPOINT`

**Student Scope**
- `student_id` — INTEGER; SQL Server UserID; NOT NULL; no FK (survives student_trigger_data deletion)
- `action_type` — VARCHAR: `GDPR_DELETION | FERPA_REMOVAL | ANONYMIZATION_REQUEST | INTERNAL_COMPLIANCE`

**Authorization Chain**
- `authorization_timestamp` — TIMESTAMPTZ; when authorization was granted
- `authorized_by` — VARCHAR; identity of the approving compliance authority
- `executed_by` — VARCHAR; identity of the operator executing the action
- `audit_rationale` — TEXT NOT NULL; legal or compliance basis

**Scope Manifest**
- `scope_manifest_id` — UUID; references the scope manifest captured at APPROVED_FOR_ACTION
- `affected_tables_json` — JSONB; list of all tables from which records are removed or anonymized: `[{table: "warehouse.student_snapshots", record_count: N, action: "DELETE"}, ...]`
- `affected_record_count` — INTEGER; total records across all tables

**Execution Details**
- `execution_details_json` — JSONB; per-table completion status, error details for partial failures
- `outcome` — VARCHAR NULL: `COMPLETED_DELETED | COMPLETED_ANONYMIZED | PARTIALLY_COMPLETED | IN_PROGRESS`

**Metadata**
- `correlation_id` — UUID
- `created_at` — TIMESTAMPTZ; immutable

### 7.3 compliance_audit.scope_manifests — Column Strategy

The scope manifest captures the complete set of records in scope at APPROVED_FOR_ACTION time. It must be current at IN_EXECUTION time.

- `id` — surrogate PK
- `manifest_id` — UUID; referenced by `deletion_log.scope_manifest_id`
- `workflow_id` — UUID; matches the workflow
- `student_id` — INTEGER; no FK
- `captured_at` — TIMESTAMPTZ; when the manifest was built
- `manifest_version` — INTEGER; incremented if manifest is refreshed before execution
- `tables_in_scope_json` — JSONB; full table-by-table enumeration with record IDs or query predicates
- `created_at` — TIMESTAMPTZ

**Note:** `is_current` was removed. The compliance_audit schema is INSERT-only; an UPDATE to flip is_current=false on older manifests would require UPDATE privilege, violating the append-only invariant. The current manifest for a workflow is always `SELECT ... WHERE workflow_id = X ORDER BY manifest_version DESC LIMIT 1`. No UPDATE operations are required.

### 7.4 Survivability Guarantees

| Operational deletion scenario | Compliance audit survivability |
|---|---|
| `student_trigger_data` rows deleted | `deletion_log.student_id` is a plain INTEGER — no FK cascade; audit row survives |
| `warehouse.student_snapshots` rows COMPLIANCE_DELETED | `deletion_log` has no FK to warehouse schema; audit row survives |
| `ai_insights` rows deleted | No FK from compliance tables to ai_insights; unaffected |
| Entire `public` schema dropped | `compliance_audit` schema is physically separate; unaffected |

### 7.5 Audit Exportability Requirements

The `compliance_audit` schema must support read-only export for compliance auditors without granting them broader database access. Required export capabilities:

- Row-level SELECT on `deletion_log` filtered by `student_id` or `workflow_id` or date range
- Full `scope_manifests` for a given `workflow_id`
- Export format: structured JSON (NDJSON or JSON array); PDF rendering is a derived layer

The compliance pathway service account or a dedicated read-only auditor account may be granted SELECT on `compliance_audit` schema for export purposes. No other access is granted.

---

## 8. INDEXING AND QUERY STRATEGY

---

This section defines **conceptual indexing categories** — the categories of indexes needed and why. Physical index definitions (column lists, partial conditions, covering columns) are deferred to the Alembic migration files.

### 8.1 Expected Query Pattern Categories

| Query pattern | Frequency | Performance requirement |
|---|---|---|
| Current student state lookup (dashboard, tab views) | Very high | p95 ≤ 200ms; primary key or UserID equality |
| Outreach eligibility scan (daily scheduler) | Daily, full table | Full scan acceptable; composite index on active+checkpoint type |
| Monthly snapshot for a specific student | High (report generation, historical view) | `(student_id, snapshot_month)` lookup; near-instant |
| All snapshots for a cohort in a month | High (cohort report generation) | `(cohort or ClassName, snapshot_month)` range scan |
| Multi-month trend for a student | Medium (analytics, dashboard history tab) | `(student_id) ORDER BY snapshot_month` scan; indexed on student_id |
| AI insight latest version for a student | High | `(student_id, insight_type) ORDER BY version_number DESC LIMIT 1` |
| Config version active at a date | Low frequency, high criticality | `(status='ACTIVE')` or date range on `activated_at/superseded_at` |
| Event timeline for a student | High (unified timeline view) | `(student_id) ORDER BY attribution_timestamp DESC` |
| Report for a cohort+month | Medium | `(cohort_id, report_month) ORDER BY lineage_version DESC` |
| Compliance audit for a student | Very low frequency, high importance | `(student_id)` on deletion_log |

### 8.2 Index Strategy Categories

**Primary key indexes** — surrogate `id` columns on all tables. Standard PostgreSQL behavior.

**Business key unique indexes** — enforce uniqueness at the DB layer for:
- `student_trigger_data`: UNIQUE `(UserID)`
- `warehouse.student_snapshots`: UNIQUE `(student_id, snapshot_month)` WHERE `status = 'FINALIZED'` — partial unique index prevents duplicates only among finalized rows (draft duplicates are acceptable during the two-phase process)
- `config_version_registry`: partial unique index WHERE `status = 'ACTIVE'` — enforces exactly-one-ACTIVE invariant
- `warehouse.monthly_reports`: UNIQUE `(cohort_id, report_month, lineage_version)` WHERE `status = 'REPORT_PUBLISHED'`

**Idempotency key indexes** — covering the idempotency keys for all idempotent operations:
- `processed_events.idempotency_key` — UNIQUE
- `warehouse.monthly_reports.report_idempotency_key` — UNIQUE

**State filtering indexes** — composite indexes for scheduler and eligibility queries:
- `student_trigger_data`: index on `(ActiveStatus, UserID)` for active-student scans
- `ai_insights`: index on `(user_id, insight_type, status)` for current-version lookups
- `outreach_history`: index on `(user_id, checkpoint_type, attempt_number)` for dedup

**Timeline query indexes** — for the unified timeline rendering:
- `student_timeline_events`: index on `(student_id, attribution_timestamp DESC)` for per-student ordered timeline

**Warehouse analytics indexes** — for snapshot analytics and report generation:
- `warehouse.student_snapshots`: index on `(student_id, snapshot_month)` — primary analytical access pattern
- `warehouse.student_snapshots`: index on `(snapshot_month, segment_classification)` — cohort report aggregations
- `warehouse.monthly_reports`: index on `(cohort_id, report_month, status)` — report lookup

### 8.3 Partitioning Candidates

The `warehouse.student_snapshots` table grows indefinitely at O(students × months). At 2,000 students × 36 months = 72,000 rows — this is small by PostgreSQL standards and does not require immediate partitioning. However, the table design should be **partition-ready**:

- The natural partition key is `snapshot_month` (range partitioning by year or quarter)
- The physical schema must not include any construct that prevents future declarative partitioning
- At 36 months × 10,000 students (future scale), partition-by-range on `snapshot_month` becomes beneficial

`student_timeline_events` is the highest-volume append-only table. At O(events × students × time), this table is the primary partitioning candidate as the system scales. The natural partition key is `attribution_timestamp` (range by month or quarter).

### 8.4 Archival Candidates

| Table | When archival applies | Archival approach |
|---|---|---|
| `processed_events` | After idempotency window expires (e.g., >90 days) | Delete expired rows; no compliance implications |
| `student_trigger_data` | Never — it's an operational mirror, not historical | N/A |
| `warehouse.student_snapshots` | Only via compliance pathway (U-9) | Compliance deletion; no archival to cold storage in initial design |
| `student_timeline_events` | After configured retention window (operational only) | Old events can be archived to cold storage; compliance events are in a separate schema |
| `ghl_messages` | After GHL lookback window | Bulk delete of messages older than retention window |

---

## 9. STORAGE EVOLUTION STRATEGY

---

### 9.1 Horizontal Scaling Path

The current architecture is single-node PostgreSQL. The append-only design of `warehouse` and `compliance_audit` schemas provides a natural future path to:

- **Read replicas:** The warehouse schema (SELECT-only for standard accounts) is fully replicated to read replicas; all historical analytics and report queries can be served from a replica without touching the primary
- **Logical replication to analytics backends:** The warehouse schema's append-only semantics make it a clean source for logical replication to a dedicated analytics warehouse (e.g., BigQuery, Redshift) — no change data capture complexity; every row is an INSERT
- **Schema-level archival separation:** The three-schema design can be mapped to three separate PostgreSQL instances in a future architecture without application code changes — only connection strings change

### 9.2 Archive Strategy

| Domain | Archive approach | Trigger |
|---|---|---|
| Warehouse snapshots | No archival to cold storage — retained in-database; compliance deletion is the only removal path | U-9 resolution |
| Warehouse reports | Same as snapshots | U-9 resolution |
| Compliance audit | Never archived — permanent in-database retention | Not applicable |
| Operational timeline events | Cold archival to object storage (S3-compatible) after retention window; application serves from DB within window, from archive outside window | Defined by retention policy (U-9 or separate operational policy) |
| `processed_events` | Periodic cleanup of expired idempotency records (>90 days) | Automated scheduled cleanup job |

### 9.3 Long-Term Retention

The warehouse schema is designed to retain 36+ months of snapshots without query degradation at the target scale of 2,000+ students. Beyond 36 months at 10,000+ students, the following path is available:

1. Add range partitioning on `snapshot_month` to `warehouse.student_snapshots` (non-breaking DDL addition)
2. Migrate cold partitions (>24 months) to tablespaces on slower storage
3. Analytical queries spanning >24 months operate on partitioned table with partition pruning

### 9.4 AI Artifact Growth Management

`warehouse.snapshot_ai_narratives` grows at O(students × months × narrative_types). At 2,000 students × 36 months × 5 narrative types = 360,000 rows of text. PostgreSQL TOAST handles large text values efficiently (values >2 KB are stored out-of-line), so growth is manageable.

Future evolution for AI artifact management:

- **Embedding generation:** `FrozenSnapshotNarrative` text is the authoritative source for student history embeddings. A future `warehouse.snapshot_embeddings` table (snapshot_id, embedding_model_version, embedding_vector) can be added without modifying `snapshot_ai_narratives`
- **AI provider changes:** `fingerprint_ai_versions_json` records which model/prompt produced each narrative; historical narratives remain attributable regardless of future provider changes
- **Vector search (RAG):** Adding a `vector` extension and `snapshot_embeddings` table is non-breaking; existing tables are unchanged

### 9.5 Event Volume Growth Management

`student_timeline_events` is the highest-growth operational table. Management strategy:

- At current scale (100–500 students): no management needed
- At 2,000 students: add composite index and monitor query latency
- At 5,000+ students: evaluate range partitioning on `attribution_timestamp`
- At 10,000+ students: evaluate logical replication to dedicated event store (e.g., TimescaleDB or Kafka + consumer)

The event attribution fields (origin_source, origin_authority) are stable top-level columns, enabling migration to any time-series store without losing attribution semantics.

---

## 10. DATA FLOW AND SYNCHRONIZATION

---

### 10.1 SQL Server → PostgreSQL Sync Boundary

```
SQL Server.AI_ChatBot_TriggerData
    │
    │  SELECT * (no write; schema-drift-tolerant)
    │  Called via POST /sync/mssql
    ▼
UPSERT INTO public.student_trigger_data ON CONFLICT (UserID) DO UPDATE
    │
    │  All mapped columns updated in place
    │  Unmapped SQL Server columns: silently ignored
    │  New columns in SQL Server: detected as schema drift; logged; existing columns sync normally
    │  synced_at updated on every upsert
    ▼
public.student_trigger_data (current mirror state)
```

**Sync boundary properties:**
- One-directional: PostgreSQL never writes back to SQL Server
- Idempotent: calling sync N times produces the same mirror state
- Partial-sync-safe: a partial sync (SQL Server unreachable mid-run) does not corrupt already-upserted rows

### 10.2 Snapshot Generation Data Flow

```
APScheduler (month-end trigger)
    │
    │  1. CREATE DRAFT snapshot row in public.snapshot_draft_queue
    │     Idempotency key: (student_id, snapshot_month, 'DRAFT')
    ▼
public.snapshot_draft_queue (DRAFT)
    │
    │  2. For each DRAFT snapshot:
    │     - Pull all fields from public.student_trigger_data (current mirror state)
    │     - Compute derived metrics (segment, payment risk, hw risk, actual_balance)
    │     - Pull communication summary from outreach_history + student_campaign_activity
    │     - Pull placement summary from segmentation logic
    │     - Read active config version from config_version_registry
    │     - Lock config_version reference (fingerprint_config_registry_version)
    ▼
public.snapshot_draft_queue (VALIDATING)
    │
    │  3. VALIDATING → FINALIZED:
    │     - Compute reproducibility fingerprint (all 5 components)
    │     - Copy AI_REVIEWED text from ai_insights for each insight type
    │     - Perform snapshot row insert into warehouse.student_snapshots (finalization account)
    │     - Perform AI narrative insert into warehouse.snapshot_ai_narratives (finalization account)
    │     - Mark draft queue row as FINALIZED
    │     - Emit SnapshotLifecycleEvent (FinalizationCompleted) to student_timeline_events
    ▼
warehouse.student_snapshots (FINALIZED)
warehouse.snapshot_ai_narratives (companion row, copied at same time)
```

**Key invariants in this flow:**
- Step 2 is idempotent: VALIDATING snapshots can be re-processed from SQL Server mirror without data loss
- Step 3 is atomic: both the snapshot row and the AI narrative companion row are written in a single transaction (finalization account)
- If Step 3 fails: the draft queue row remains in VALIDATING; the job can resume at Step 3 without data corruption
- After Step 3 completes: no UPDATE is possible on either warehouse row

### 10.3 Report Generation Data Flow

```
Report generation job (POST /reports/generate or monthly scheduler)
    │
    │  1. Compute report_idempotency_key = hash(cohort_id, report_month, template_version, lineage_version)
    │     Check processed_events for this key
    │     If exists: return existing report_id (idempotent)
    ▼
warehouse.monthly_reports (REPORT_PENDING row inserted by finalization account)
    │
    │  2. Read all FINALIZED snapshots for (cohort_id, report_month) from warehouse.student_snapshots
    │     Read AI narrative text from warehouse.snapshot_ai_narratives
    │     Capture source_snapshot_fingerprint_json at this moment
    │     NOTE: Zero SQL Server queries at this step (FAD-2)
    ▼
warehouse.monthly_reports (REPORT_GENERATING)
    │
    │  3. Compute aggregate statistics from snapshot metrics
    │     Assemble report_content_json (metrics + AI narratives from physical copies)
    │     Apply report template version
    ▼
warehouse.monthly_reports (REPORT_GENERATED → REPORT_REVIEW_PENDING)
    │
    │  4. Review (operator approval or auto-approval policy)
    ▼
warehouse.monthly_reports (REPORT_APPROVED → REPORT_PUBLISHED)
    │
    │  5. Emit ReportLifecycleEvent (PublicationCommitted) to warehouse.report_audit_log
```

### 10.4 Historical Regeneration Data Flow

```
Operator: POST /reports/{cohort_id}/{report_month}/regenerate
    │
    │  1. Fetch latest REPORT_PUBLISHED row (lineage_version = N)
    │     Compute new lineage_version = N + 1
    │     Compute new report_idempotency_key
    │     Insert new REPORT_PENDING row with parent_report_id = original row id
    ▼
warehouse.monthly_reports (new row, lineage_version = N+1, REPORT_PENDING)
    │
    │  2. Read warehouse.student_snapshots and warehouse.snapshot_ai_narratives
    │     (same data source as original generation — FAD-2 guaranteed)
    │     NOTE: source snapshot fingerprint captured NOW
    │     Compare to original publication fingerprint
    │     If different: set POTENTIALLY_DIVERGENT = true; log both fingerprints
    ▼
    │  3. Follow same generation steps as Section 10.3 steps 3–5
    │     Original REPORT_PUBLISHED row (lineage_version = N) is NEVER modified
    ▼
warehouse.monthly_reports (new row REPORT_PUBLISHED, lineage_version = N+1)
warehouse.monthly_reports (original row REPORT_PUBLISHED, lineage_version = N — unchanged)
```

### 10.5 AI Enrichment Flow

```
AI insight generation job (daily or on-demand)
    │
    │  1. Check idempotency: (student_id, insight_type, date_period, prompt_version) in processed_events
    │     If exists and within TTL: return cached ai_insights row
    ▼
ai_insights (AI_PENDING row inserted)
    │
    │  2. Build non-PII prompt from student_trigger_data fields (anonymized metrics only)
    │     Submit to LLM provider
    ▼
ai_insights (AI_GENERATING)
    │
    │  3. Validate structured output against declared schema
    │     If invalid: retry (max 2 times); if exhausted → AI_GENERATION_FAILED; serve stale insight
    ▼
ai_insights (AI_GENERATED — attribution metadata locked: prompt_version, model_used, generated_at)
    │
    │  4. Review step (AI_REVIEW_PENDING → AI_REVIEWED)
    │     content_text locked at AI_REVIEWED
    ▼
ai_insights (AI_REVIEWED — active version)
    │
    │  ← SNAPSHOT COPY BOUNDARY: text is copied from here into warehouse.snapshot_ai_narratives at finalization
    │    After copy, further changes to ai_insights have ZERO effect on the snapshot copy
```

### 10.6 Compliance Annotation Flow

```
Compliance request intake
    │
    │  1. ComplianceWorkflowRecord created in public schema (REQUESTED)
    │     At most one active workflow per student — duplicate rejected
    ▼
    │  2. APPROVED_FOR_ACTION: capture ComplianceScopeManifest
    │     Insert into compliance_audit.scope_manifests (compliance pathway account)
    │     Manifest lists all tables + record IDs in scope for this student
    ▼
    │  3. Before IN_EXECUTION: verify pre-action audit entry exists in compliance_audit.deletion_log
    │     If absent: BLOCK transition; raise incident
    │     (The pre-action entry is the hard gate from FAD-4)
    ▼
    │  4. IN_EXECUTION: delete/anonymize records per scope manifest
    │     Per-table completion logged in compliance_audit.deletion_log (PARTIAL_COMPLETION_CHECKPOINT entries)
    │     warehouse.student_snapshots rows: set status = COMPLIANCE_DELETED (finalization account)
    ▼
    │  5. Post-action: insert POST_ACTION entry in compliance_audit.deletion_log
    │     Failure to write post-action entry = incident (not a warning)
    ▼
ComplianceWorkflowRecord (COMPLETED_DELETED or COMPLETED_ANONYMIZED)
```

---

## 11. MIGRATION PLANNING READINESS

---

### 11.1 Migration Readiness Assessment

| Migration | File | Readiness | Assessment |
|---|---|---|---|
| 0002 | `0002_warehouse_schema.py` | **READY — begin now** | All architecture decisions resolved (FAD-1 through FAD-6). Schema design complete per Sections 3–4. Two-table snapshot strategy requires benchmarking before column type finalization, but does not block the migration start. |
| 0003 | `0003_config_version_registry.py` | **READY — begin concurrently** | Config version schema is fully specified. Seed V1 values are defined in spec/01 Section 12. No blockers. |
| 0004 | `0004_compliance_schema.py` | **SUBSUMED by 0002 — see Note** | FAD-4 mandates compliance_audit schema is created in the same migration as warehouse schema (spec/01 Section 13, FAD-4 implementation implications). The spec/08 migration table lists 0004 separately, creating an inconsistency. Recommended resolution below. |

**Inconsistency Resolution — spec/08 migration table vs. FAD-4:**

spec/08 Section 8 lists `compliance_audit` schema as migration 0004. spec/01 Section 13 (FAD-4) states: "compliance_audit schema must be created in the same Alembic migration as the warehouse schema." These conflict.

**Recommended resolution:** Migration 0002 covers both schemas as FAD-4 requires. Migration 0004 is either retired or repurposed as a future compliance schema extension migration (additional tables when compliance pathway is implemented in PRODUCTION tier). The migration numbering in spec/08 should be updated when 0002 is authored to reflect this.

### 11.2 Pre-Migration Benchmarking Requirement

**REQUIRED before finalizing 0002 column types:**

Per spec/01 Section 14.3 risk register: "AI text volume in snapshots (FAD-1 physical copy) — evaluate a linked AI snapshot content table if row size exceeds acceptable threshold."

Benchmark action before writing 0002:
1. Query `SELECT insight_type, MAX(length(content)), AVG(length(content)), percentile_cont(0.95) WITHIN GROUP (ORDER BY length(content)) FROM ai_insights GROUP BY insight_type` against the current PostgreSQL instance
2. If p95 total narrative payload per student (all types combined) < 8 KB: inline single-table approach is also viable
3. If p95 exceeds 8 KB or MAX exceeds 20 KB: two-table approach (Section 3.2) is the correct physical choice

The two-table approach described in Section 3.2 is the recommended default. If benchmarking shows content is small, a simplified single-table approach remains an option, but the two-table approach is the safer long-term design.

### 11.3 Remaining Blockers

**Schema blockers:** None. All FAD-1 through FAD-6 are resolved. All schema design decisions in Sections 3–7 are specified. Migration authoring can begin.

**Go-live blockers (do NOT block schema authoring):**

| Item | Severity | What it blocks |
|---|---|---|
| U-9: snapshot retention policy | HIGH | First production snapshot finalization; does NOT block schema creation |
| U-4: month-end cutoff definition | HIGH | Snapshot scheduler go-live; does NOT block schema creation |
| Compliance scope manifest completeness | MEDIUM | Compliance pathway go-live; does NOT block deletion_log schema |
| Finalization service account credentials | HIGH | Running the finalization service against warehouse schema | 
| Compliance pathway service account credentials | HIGH | Running compliance operations |

### 11.4 Implementation-Sensitive Areas

These are areas where the physical implementation requires care beyond what a standard migration would include:

**Warehouse schema permissions (critical):**
The migration that creates `warehouse` and `compliance_audit` schemas must ALSO execute the GRANT statements that establish the access control profile:
- REVOKE all public grants on warehouse schema
- GRANT SELECT on warehouse schema to application service account
- GRANT INSERT on specific warehouse tables to finalization service account
- REVOKE all public grants on compliance_audit schema
- GRANT SELECT on compliance_audit schema to application service account
- GRANT INSERT on compliance_audit tables to compliance pathway service account

These GRANT statements are part of the schema definition, not separate operational steps. They must be in the migration file.

**Additional GRANT required (compliance deletion path):**
The compliance pathway account must be able to set `status = 'COMPLIANCE_DELETED'` on `warehouse.student_snapshots` rows during compliance deletion workflows. This requires a column-level UPDATE grant — the only UPDATE grant on any warehouse table:

```
GRANT UPDATE (status) ON warehouse.student_snapshots TO compliance_pathway_user;
```

This is the sole exception to the warehouse INSERT-only model. The compliance pathway account has UPDATE privilege on the `status` column only, not on any other column. This grant must appear in the 0002 GRANT block alongside the INSERT grants.

**Config version seed (critical):**
Migration 0003 must include a seed INSERT for V1 with `status = 'ACTIVE'` and all threshold values from spec/01 Section 12. A deployment with no ACTIVE config version violates DATA-INVARIANT-4.

**Partial unique indexes (correctness):**
- `warehouse.student_snapshots`: `UNIQUE (student_id, snapshot_month) WHERE status = 'FINALIZED'` — partial, not full unique
- `config_version_registry`: `UNIQUE (version_number)` full + `UNIQUE (1) WHERE status = 'ACTIVE'` partial (enforces exactly-one-ACTIVE)

**Transaction safety for config activation (correctness):**
The atomic swap for config activation (old → SUPERSEDED, new → ACTIVE) must execute in a single transaction. This is an application-layer concern but must be documented as a migration-adjacent constraint.

### 11.5 Recommended Migration Sequencing

```
0001_baseline.py           (DEPLOYED — public schema, Phase 5 tables)
        │
        ├──── 0002_warehouse_schema.py     (BEGIN NOW)
        │         warehouse + compliance_audit schemas
        │         warehouse.student_snapshots
        │         warehouse.snapshot_ai_narratives
        │         warehouse.monthly_reports
        │         warehouse.report_audit_log
        │         compliance_audit.deletion_log
        │         compliance_audit.scope_manifests
        │         All schema-level permission GRANTs
        │
        └──── 0003_config_version_registry.py  (BEGIN CONCURRENTLY WITH 0002)
                  public.config_version_registry
                  Seed V1 INSERT with all Section 12 defaults
                  Partial unique index WHERE status='ACTIVE'

0004_snapshot_lifecycle_public.py  (AFTER 0002 + 0003)
          public.snapshot_draft_queue  (draft lifecycle tracking)
          public.student_timeline_events  (unified event log)

0005_ai_insights_versioning.py  (AFTER 0002)
          ADD COLUMNS to ai_insights: version_number, prompt_version, model_version, ai_idempotency_key
          (See spec/08 Section 8 for existing plan)

0006_report_generation.py  (AFTER 0002 + 0003 + 0004)
          Any additional tables required for report generation service
          (Deferred until app/services/snapshot.py design is complete)
```

---

## 12. OUTPUT — SUMMARY AND SEQUENCING

---

### 12.1 Physical Architecture Summary

| Decision | Recommendation |
|---|---|
| Snapshot AI text storage | Two-table strategy: `warehouse.student_snapshots` (metrics) + `warehouse.snapshot_ai_narratives` (text) — 1:1 companion; physical copy semantics preserved (FAD-1) |
| Reproducibility fingerprint columns | Mixed: 3 scalar TEXT columns for queryable components + 1 JSONB for per-type AI version map |
| Report content storage | JSONB inline in `warehouse.monthly_reports` for initial implementation; future evolution to object storage when row size warrants |
| Event storage | Hybrid: unified `public.student_timeline_events` for operational events; `warehouse.report_audit_log` for report lifecycle; `compliance_audit.deletion_log` for compliance events |
| Config version activation | Partial unique index WHERE status='ACTIVE' + application-layer atomic swap |
| Compliance schema | Included in 0002 per FAD-4; no FK dependencies on other schemas; INSERT-only for compliance pathway account |
| Append-only enforcement | DB-level permission grants (not application-only); described in Section 11.4 |

### 12.2 Schema Boundary Recommendations

| Schema | Contents | Write path | Query path |
|---|---|---|---|
| `public` | All mutable operational state; AI insights; draft snapshots; config registry | Standard application service account | Standard application service account |
| `warehouse` | Finalized snapshots + AI narratives; published reports + audit log | Finalization service account (INSERT only) | Standard application service account (SELECT) |
| `compliance_audit` | Deletion log; scope manifests | Compliance pathway service account (INSERT only) | Standard application service account (SELECT); auditor read-only account |

### 12.3 Recommended Implementation Sequence

| Step | Work | Dependency |
|---|---|---|
| **Step 1** | Benchmark AI narrative lengths (pre-migration validation) | None — do first |
| **Step 2** | Author `0002_warehouse_schema.py` (warehouse + compliance_audit schemas + all GRANTs) | After Step 1 |
| **Step 2 concurrent** | Author `0003_config_version_registry.py` (config registry + V1 seed) | Independent of 0002 |
| **Step 3** | Deploy 0002 + 0003 to dev environment; verify permission model | After Step 2 |
| **Step 4** | Author `0004_snapshot_lifecycle_public.py` (draft queue + timeline events) | After 0002 deployed |
| **Step 5** | Author `0005_ai_insights_versioning.py` (add version/attribution columns to ai_insights) | After 0002 deployed |
| **Step 6** | Design `app/services/snapshot.py` (draft→finalized two-phase) | After Steps 3–5 |
| **Step 7** | Design `app/services/config_registry.py` (get_active_version, create_version) | After 0003 deployed |
| **Step 8** | Design compliance pathway service (pre-action gate, scope manifest) | After 0002 deployed; before Step 3 production go-live |

### 12.4 Service Layer Sequencing

| Service | After which migrations | Purpose |
|---|---|---|
| `app/services/config_registry.py` | 0003 | get_active_version(), create_version(), atomic_activate() |
| `app/services/snapshot.py` | 0002 + 0003 + 0004 | draft_create(), validate(), finalize() — two-phase; fingerprint computation |
| `app/services/report_generation.py` | 0002 + snapshot service | generate_report(), publish(), regenerate() |
| `app/services/compliance.py` | 0002 + compliance pathway account | intake(), approve(), execute(), audit_export() |
| `app/services/ai_insights.py` (extend) | 0005 | add versioning, idempotency key, force_refresh() |

### 12.5 Open Items for Migration Authors

The following items require resolution before or during migration authoring:

| Item | Urgency | Who resolves | Impact on migration |
|---|---|---|---|
| Benchmark AI narrative lengths | HIGH — before writing 0002 | Engineering (query existing ai_insights) | Determines single-table vs. two-table snapshot strategy |
| Finalization service account name | HIGH | DBA / DevOps | Required for GRANT statements in 0002 |
| Compliance pathway service account name | HIGH | DBA / DevOps | Required for GRANT statements in 0002 |
| Confirm 0004 retirement or repurpose | LOW | Architecture decision | Prevents confusing duplicate compliance migration |
| U-9 snapshot retention policy | HIGH (but does NOT block 0002) | Legal/Compliance | Determines whether a soft-delete column is needed in warehouse schema |

### 12.6 Scaling Considerations

| Concern | Current design | Future evolution trigger |
|---|---|---|
| Snapshot table size | Append-only rows; TOAST handles AI text; manageable at 2K students × 36 months | Partition on `snapshot_month` when table exceeds 500K rows |
| Report table size | One row per publication per cohort per month; small | Evaluate content offload to object storage at >10K cohort-months |
| Event table size | High volume; indexed on `(student_id, attribution_timestamp)` | Partition on `attribution_timestamp` at >10M rows |
| Compliance audit size | Very low volume; permanent retention | No growth concern; permanent in-database |
| Config registry size | One row per change; very low volume | No scaling concern |

---

## REFERENCES

---

### Canonical Sources for This Document

* `spec/01_requirements.md` — FAD-1 through FAD-6 (Section 13), open assumptions (Section 11.2), dependency sequencing (Section 14.2), risk register (Section 14.3)
* `spec/03_state_transition_rules.md` — State enums for all 6 lifecycle domains
* `spec/04_idempotency_concurrency.md` — Idempotency key patterns, concurrency invariants
* `spec/08_data_model.md` — Conceptual entity definitions (Sections 13–26), schema ownership (Section 13), cross-domain invariants (Section 22)

### Governed By

* `alembic/versions/0002_warehouse_schema.py` — Primary output of this architecture plan (pending authoring)
* `alembic/versions/0003_config_version_registry.py` — Secondary output (pending authoring)
* `app/services/snapshot.py` — Finalization service (pending design)
* `app/services/config_registry.py` — Config version service (pending design)
* `app/services/compliance.py` — Compliance pathway service (pending design)

---

## END OF FILE
