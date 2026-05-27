# evolution/versioning_strategy.md

---

## LAYER 11 — EVOLUTION & LINEAGE STRATEGY

---

> **Version note:** This file was completely rewritten on 2026-05-27 to reflect the finalized governance-safe evolution and lineage strategy aligned with the governed historical intelligence platform architecture. The previous version described traditional software versioning guidance: MAJOR.MINOR.PATCH semantic versioning with breaking/minor/patch classification, reversible database migration rules ("Must be reversible"), feature flags for evolution control ("ENABLE_NEW_DECISION_RULE = true/false"), rollback steps ("Revert to previous version", "Restore previous state if needed"), MVP/STANDARD/PRODUCTION deployment tier progression implying governance is incrementally acquired, and no replay lineage semantics, no Config V2 governance, no attribution requirements, no certification gates, no immutable historical version semantics. That architecture is incompatible with the governance-safe orchestration model. Evolution is no longer software upgrade management. It is governance-safe append-only lineage progression.

---

## 1. PURPOSE

---

### 1.1 What This Document Defines

This document defines the **governance-safe evolution and lineage strategy** for the Student Success Intelligence Platform (SSIP). It governs:

* How platform versions evolve through append-only supersession, not in-place overwrite
* What lineage classification governs each version artifact's mutability, replay behavior, and attribution requirements
* How Config V2 supersession governance enforces the exactly-one-ACTIVE invariant through deployment history
* How replay safely resolves historical version lineage without reinterpreting it
* How regenerated artifacts preserve original lineage without overwriting it
* How deployment evolution is governed by certification gates, not tier-based capability exposure
* What governance invariants apply to every evolution event across all deployment stages

### 1.2 What This Document Does NOT Define

* Physical database migration code — see `alembic/versions/`
* Deployment scripts, CI/CD pipeline configuration, or container orchestration
* Package management, dependency resolution, or build tooling
* Runtime service configuration beyond governance mode attribution
* State transition rules — see `spec/03_state_transition_rules.md`
* Config Version rule parameter values — see `spec/01_requirements.md §12` and Config Version Registry
* Idempotency and concurrency rules — see `spec/04_idempotency_concurrency.md`

### 1.3 Governance Purpose of Version Classification

Version classification determines:

* **Mutability** — which version artifacts can be updated and which are permanently immutable
* **Supersession semantics** — how new versions replace active versions without destroying historical lineage
* **Replay behavior** — which historical version is resolved for replay orchestration
* **Attribution requirements** — what lineage fields every version event must carry
* **Certification gates** — what validation must complete before a deployment stage advances
* **Rollback constraints** — which rollback semantics are prohibited by FAD-3 and append-only architecture

---

## 2. VERSION CLASSIFICATION MODEL

---

### 2.1 Governance-Safe Version Lineage Classes

Each version artifact in the platform belongs to exactly one lineage class. Classification governs mutability, supersession behavior, replay resolution, and attribution requirements.

| Lineage class | Location | Examples | Mutability | Replay resolution | Supersession semantics |
|---|---|---|---|---|---|
| `schema_lineage` | `alembic/versions/` | Migration revision history | Append-only; no revision modification after execution | Replay uses snapshot-time schema fingerprint (`fingerprint_schema_version`) | New revision; prior revision permanent |
| `config_v2_lineage` | `public.config_version_registry` | Config Version Registry rows | Rule values immutable after INSERT; governance metadata UPDATE for `config_admin_user` only | Replay resolves `historical_config_version_id`; never current ACTIVE | New ACTIVE row; prior ACTIVE → SUPERSEDED (append-only chain) |
| `runtime_lineage` | `runtime/`, `spec/` | `system_loop.md`, `scheduler_design.md` | Document revisions forward-only; prior content preserved in version history | Runtime version attributed in correlation_id context at execution time | Forward-only; version note records prior state summary |
| `replay_lineage` | `public` schema (tagged) | Replay-generated orchestration records | Append-only INSERT with `execution_type = replay`; never overwrites LIVE records | Historical record permanent; `causation_id → original correlation_id` | Cannot be converted to LIVE lineage |
| `regeneration_lineage` | `warehouse.monthly_reports` | Regenerated report rows | New `lineage_version` row; original `REPORT_PUBLISHED` row immutable | Reads FINALIZED warehouse snapshots only; never live operational data (FAD-2) | Lineage increment; original artifact permanent |
| `directive_lineage` | `directives/`, `spec/`, `runtime/`, `ux/`, `failure/` | All governance contract documents | Document revisions forward-only; version notes preserve prior state | Directive version attributed in observability context | Forward-only; version notes document superseded content summary |
| `governance_certification_lineage` | `execution/build_phases.md`, certification records | Phase gate outcomes | Certification records append; failed gate results permanent | Certification outcome attributed in deployment records | Cumulative; prior phase certifications never revoked |
| `operational_deployment_lineage` | Runtime deployment records | SHADOW→LIVE transition records, activation records | Append-only deployment records; `activation_record_present` flag permanent | Deployment mode attributed in every record via `execution_mode` | Mode transitions recorded; prior mode records permanent |

### 2.2 Prohibited Version Semantics

The following version semantics violate governance invariants and are explicitly prohibited:

| Prohibited semantic | Governance violation | Required replacement |
|---|---|---|
| In-place overwrite of a deployed version | Destroys lineage auditability | Append-only supersession; prior version permanently queryable |
| Reverting SUPERSEDED Config Version to ACTIVE | Violates FAD-3 (prospective-only activation) | Create new version record copying prior rule values |
| Modifying `historical_config_version_id` on a finalized snapshot | Violates INV-1, FAD-3 | Attribution is permanent; no post-hoc modification |
| Deleting historical Alembic revision | Violates append-only evolution | Revisions are permanent; migration issues are resolved by additive corrections |
| Rolling back warehouse schema past existing FINALIZED records | Violates INV-1 (FINALIZED immutability) | Schema evolution is forward-only once governance-sensitive data exists |
| Feature flags governing governance invariant behavior | Violates INV-1–INV-7 universality | Governance invariants apply unconditionally in all environments and modes |

---

## 3. APPEND-ONLY EVOLUTION GOVERNANCE

---

### 3.1 Append-Only Evolution Principle

Platform evolution is governed by append-only semantics at every lineage layer:

* Versions are **never overwritten** — a new version is created; the prior version becomes permanently queryable as a historical lineage record
* Supersession **replaces** overwrite — when a Config Version, schema revision, or governance contract changes, the prior version transitions to SUPERSEDED status (not deleted or modified)
* Historical versions are **permanently queryable** — every SUPERSEDED Config Version, every historical schema revision, and every prior directive version remains attributable and queryable
* Append-only enforcement is **schema-enforced**, not application-layer-only — INSERT-only privilege on `warehouse` and `compliance_audit` schemas; governance metadata UPDATE privilege is column-level and account-scoped

### 3.2 Schema Lineage Append-Only Governance

Database schema evolution follows append-only lineage through Alembic revision history:

* Each Alembic revision is a permanent record — revisions are never deleted or modified after execution
* Schema changes are **additive by default** — dropping columns or tables containing governance-sensitive records requires pre-migration validation per `spec/10_pre_migration_storage_validation.md`
* The warehouse and compliance_audit schemas receive **no UPDATE/DELETE privileges** from standard application accounts — schema evolution must preserve this model; new warehouse or compliance_audit tables added in future migrations must include explicit GRANT statements (grants do not inherit automatically — alembic/0002 architectural note)
* Append-only tables (`warehouse.*`, `compliance_audit.*`, `public.outreach_history`, `public.state_transition_log`, `public.student_timeline_events`, `public.processed_events`) must never receive an Alembic migration that adds UPDATE or DELETE permissions to any account

### 3.3 Supersession Lineage

Supersession is the governance-safe mechanism for replacing an active version:

| Version type | Supersession mechanism | Historical record behavior |
|---|---|---|
| Config Version | `status = 'SUPERSEDED'` + `superseded_by_version_id` + `deactivated_at` set atomically in same transaction as new ACTIVE row INSERT | SUPERSEDED row permanent; required for `fingerprint_config_registry_version` attribution and replay resolution |
| Schema revision | New Alembic revision with forward-only migration; prior revision permanent in history | Prior revision permanent; `down()` migration must not violate warehouse or compliance_audit data integrity |
| Governance contract documents | Version note records prior state summary; document updated forward-only | Prior state documented in version note; not deleted |
| Deployment mode | SHADOW → LIVE transition recorded with `activation_record_present = true`; prior SHADOW records permanent | All SHADOW records remain queryable; SHADOW→LIVE transition is the forward event |

### 3.4 Immutable Historical Versions

Once a version event creates an immutable artifact, that artifact is permanently immutable:

| Immutable artifact | Immutability condition | Enforcement |
|---|---|---|
| `warehouse.student_snapshots` row | `lifecycle_state = FINALIZED` | Schema-level SELECT-only for `app_service_user`; `IMMUTABLE_RECORD_VIOLATION` on mutation attempt |
| `warehouse.snapshot_ai_narratives` row | `allows_update = false` set at FINALIZED time (FAD-1, INV-6) | Schema permission enforcement; `IMMUTABLE_RECORD_VIOLATION` on update attempt |
| `warehouse.monthly_reports` row | `lifecycle_state = REPORT_PUBLISHED` | SELECT-only; new `lineage_version` row on regeneration — no in-place modification |
| Config Version rule columns | Rule values locked at INSERT | No UPDATE privilege on rule columns for any role; governance metadata columns only |
| `compliance_audit.*` rows | Append-only always | No UPDATE or DELETE from any account; schema permission enforcement |

---

## 4. CONFIG V2 EVOLUTION GOVERNANCE

---

### 4.1 Config Version Lineage Permanence

The Config Version Registry (`public.config_version_registry`) is the governance-controlled, append-only record of every change to configurable operational rules:

* Every Config Version record is **permanent** — SUPERSEDED versions are never deleted; they are the historical anchor for `fingerprint_config_registry_version` attribution on finalized snapshots
* A future auditor can look up any historical `fingerprint_config_registry_version` and retrieve the exact rule set that governed the snapshot's classification at that time
* The Config Version Registry is the authoritative source for replay config resolution — replay always uses `historical_config_version_id`, never the current ACTIVE version

### 4.2 Exactly-One-ACTIVE Invariant

The EXACTLY-ONE-ACTIVE invariant (INV-2, DATA-INVARIANT-4) is physically enforced at the database layer:

```sql
CREATE UNIQUE INDEX uq_cvr_active_singleton
ON config_version_registry ((1))
WHERE status = 'ACTIVE'
```

* PostgreSQL evaluates the constant expression `(1)` for every row where `status = 'ACTIVE'` — one ACTIVE row yields one index entry; two ACTIVE rows violate the unique constraint before any application logic executes
* The activation transaction must mark the current ACTIVE row as SUPERSEDED before inserting the new ACTIVE row — atomically in a single BEGIN/COMMIT block
* This invariant is **DB-enforced**, not application-enforced — application-layer guards are defense-in-depth; the index is the final enforcement mechanism
* Schema migrations must never drop or disable `uq_cvr_active_singleton`

### 4.3 Supersession Lineage Governance

Config Version supersession is append-only and forward-only:

* Version activation: `ACTIVE → SUPERSEDED` + `superseded_by_version_id = <new_id>` + `deactivated_at = now()` in the same transaction as INSERT of new ACTIVE row
* Version "rollback": accomplished by creating a **new version record** that copies the rule values of the prior version — never by restoring the SUPERSEDED record to ACTIVE status (INV-3, FAD-3)
* Supersession chain: the full chain from V1 to current ACTIVE version is permanently queryable via `superseded_by_version_id` FK traversal
* No version may be inserted with a `created_at` or `effective_from` timestamp earlier than the currently ACTIVE version — prospective-only activation enforced at application layer and audit-verified

### 4.4 Replay Config Resolution

* Replay orchestration always resolves `historical_config_version_id` for classification decisions — the config version that was ACTIVE at the original execution time, not the current ACTIVE version
* Using current ACTIVE config for replay is a lineage violation — it would reinterpret historical decisions under current rules, violating reproducibility guarantees
* SUPERSEDED versions must remain queryable permanently — replay depends on this guarantee; deletion of a SUPERSEDED version is prohibited
* `COMPARISON_UNAVAILABLE` is emitted when the historical config version record is missing — current ACTIVE is never silently substituted

### 4.5 Prospective-Only Activation

* Config Version activation affects future classification runs only — historical snapshots retain their original `fingerprint_config_registry_version` regardless of subsequent version changes (FAD-3)
* No backdating pathway exists — `effective_from` cannot be set earlier than `now()` at activation time
* Restoring a SUPERSEDED version to ACTIVE is an `ArchitecturalViolation` — the correct path is creating a new version with prior values

---

## 5. REPLAY AND REGENERATION EVOLUTION GOVERNANCE

---

### 5.1 Replay Lineage Resolution

Replay orchestration must resolve historical lineage, not reinterpret it:

| Attribution field | Replay resolution | Violation behavior |
|---|---|---|
| `historical_config_version_id` | Config version ACTIVE at original execution time | `COMPARISON_UNAVAILABLE` if version missing; never substituted with current ACTIVE |
| `execution_type` | `replay` (never `original`) | `ATTRIBUTION_INCOMPLETE` alert if absent |
| `governance_scope` | `REPLAY_ONLY` | Replay records cannot enter LIVE provider paths |
| `causation_id` | Original correlation_id of the triggering LIVE execution | Multi-hop lineage chain preserved |
| `live_effects_produced` | `0` (invariant — non-zero → CRITICAL governance alert) | INV-4, AP-RT2 enforcement |
| `fingerprint_schema_version` | Schema version at replay time (comparison, not override) | `POTENTIALLY_DIVERGENT` logged if mismatched from stored fingerprint |

Replay cannot reinterpret historical lineage. If the current system fingerprint diverges from the stored fingerprint, the divergence is **logged and flagged** (`POTENTIALLY_DIVERGENT`), but the historical fingerprint is never overwritten.

### 5.2 Regeneration Lineage Continuity

Report regeneration creates new lineage, never overwrites original lineage:

* Regeneration reads `warehouse.student_snapshots` rows with `lifecycle_state = FINALIZED` only — never live operational data (FAD-2)
* A new `warehouse.monthly_reports` row is created with `lineage_version` incremented by 1, `execution_type = regeneration`, `sourced_from_warehouse = true`
* The original `REPORT_PUBLISHED` row is **never modified** — it is permanently immutable
* Fingerprint comparison is logged: five-component fingerprint from the new execution versus the fingerprint stored in the original report row
  * `IDENTICAL` — regeneration produced the same output as the original
  * `POTENTIALLY_DIVERGENT` — at least one fingerprint component differs; warning logged with differing components named
  * `COMPARISON_UNAVAILABLE` — original fingerprint record is missing; audit gap indicator logged
* A `POTENTIALLY_DIVERGENT` outcome does not block regeneration but produces a governance warning requiring Governance Administrator acknowledgement

### 5.3 Five-Component Fingerprint Preservation

The snapshot reproducibility fingerprint is preserved across all evolution events:

| Component | Field name | Permanently queryable | `UNKNOWN_V0` meaning |
|---|---|---|---|
| Schema version | `fingerprint_schema_version` | Yes — Alembic revision ID | Audit gap; schema version was not recorded at finalization time |
| Config registry version | `fingerprint_config_registry_version` | Yes — Config Version Registry ID | Audit gap; config version was not captured |
| AI prompt version | `fingerprint_ai_prompt_version` | Yes — prompt template version | Audit gap; prompt version was not captured |
| AI model version | `fingerprint_ai_model_version` | Yes — model identifier string | Audit gap; model version was not captured |
| Report template version | `fingerprint_report_template_version` | Yes — template version identifier | Audit gap; template version was not captured |

`UNKNOWN_V0` on any component is an **audit-gap indicator** — not a permission to omit the component from future records, and not a default value for replay resolution. `UNKNOWN_V0` must be logged as a governance warning when encountered during regeneration or replay.

### 5.4 Replay-Safe Deployment Behavior

* Deployment to SHADOW mode does not trigger replay of historical LIVE records — SHADOW is a forward-only operational mode for new execution cycles
* Replay executions are explicitly initiated; they are not triggered by deployment events
* Replay records in `public.outreach_history` and `public.state_transition_log` carry `execution_type = replay` and are permanently distinguishable from LIVE records — no deployment or migration event may strip or overwrite these attribution fields
* No replay execution path holds INSERT authority into the `warehouse` schema — replay outputs are contained to `public` schema with `governance_scope = REPLAY_ONLY`

---

## 6. DEPLOYMENT EVOLUTION GOVERNANCE

---

### 6.1 Governance-First Deployment Sequencing

Deployment evolution is governed by certification gates, not tier-based capability exposure:

* The MVP/STANDARD/PRODUCTION tier model is **deprecated** — it implied governance was incrementally acquired across tiers, which contradicts INV-1–INV-7 universality
* All deployments begin in **SHADOW mode** — outbound provider calls are suppressed; governance-sensitive operations are certified before LIVE promotion
* Governance architecture does not downgrade — once INV-1–INV-7 and FAD-1–FAD-6 are deployed, no subsequent release may introduce code that violates these invariants

### 6.2 Deployment Maturity Classification

| Stage | Governance mode | Outbound effects | Certification requirement |
|---|---|---|---|
| DEVELOPMENT | SHADOW | None | Local governance validation; no production-grade certification required |
| STAGING | SHADOW | None | Governance certification suite passes; Phase 1–8 dependencies validated |
| PRE-PRODUCTION | SHADOW | None | All Phase 1–11 checkpoints complete; test suite passes; no invariant violations |
| PRODUCTION (SHADOW) | SHADOW | None | Phase 12 readiness validated; Governance Administrator review complete |
| PRODUCTION (LIVE) | LIVE | Governed provider delegation | Phase 12 certification complete; `activation_record_present = true`; Governance Administrator explicit acknowledgement |

SHADOW mode is a **mandatory operational tier**, not a debugging convenience. The SHADOW → LIVE transition requires:
* `activation_record_present = true` in Config Version Registry
* Governance Administrator authorization — this transition cannot be automated (AP-RT7)
* Explicit acknowledgement checkbox confirming Phase 12 certification completion
* No automated service or deployment script may trigger this transition

### 6.3 Rollback Governance Constraints

Rollback semantics in the governance-safe architecture are constrained by append-only invariants:

| Rollback type | Permitted | Governance constraint |
|---|---|---|
| Application service code rollback | Permitted with care | Must not create state where governance-sensitive records exist without required attribution fields; INV-5 enforced on all records written by reverted code |
| Config Version "rollback" | Prohibited as restore-to-SUPERSEDED | Create a new version record with prior rule values (FAD-3); SUPERSEDED records are never restored to ACTIVE |
| Schema migration `down()` | Constrained | Prohibited if warehouse or compliance_audit records exist in tables that `down()` would drop or truncate; `spec/10_pre_migration_storage_validation.md` validation required |
| Governance architecture rollback | Prohibited | INV-1–INV-7 and FAD-1–FAD-6 are permanently deployed; no release may introduce code that violates them |
| LIVE → SHADOW mode transition | Permitted by Governance Administrator only | Transition recorded with full attribution; LIVE records are not invalidated; mode transition is forward-lineage, not rollback |

### 6.4 Forward-Only Governance Architecture

* Once governance infrastructure (three-schema isolation, service accounts, Config Version Registry, attribution fields, append-only enforcement) is deployed, no subsequent migration may remove or weaken it
* New migrations that add tables to `warehouse` or `compliance_audit` must include explicit GRANT statements — INSERT-only for designated service accounts; SELECT-only for standard account
* No migration may add UPDATE or DELETE privileges to append-only tables
* No migration may drop the `uq_cvr_active_singleton` partial unique index enforcing exactly-one-ACTIVE
* No migration may introduce FK dependencies from `compliance_audit` or `warehouse` to `public` tables — cross-schema FK independence preserves compliance audit survivability

---

## 7. GOVERNANCE CERTIFICATION GATES

---

### 7.1 Certification-Gated Promotion

Platform deployment advances through certification gates, not calendar-based releases or feature toggles. Each gate must be satisfied before the next deployment stage can proceed:

| Certification domain | Gate type | Canonical test reference | Phase dependency |
|---|---|---|---|
| SHADOW containment | SVL-1–SVL-3: no outbound HTTP in SHADOW; `outbound_suppressed = true`; `live_effects_produced = 0` | `tests/test_shadow_safety.py` | Phase 6 |
| Replay isolation | ROS-1–ROS-2, INV-4, AP-RT2: replay records carry `execution_type = replay`; `live_effects_produced = 0` | `tests/test_shadow_safety.py` | Phase 7 |
| Immutable-lineage | INV-1, INV-6, FAD-1: FINALIZED mutation raises `IMMUTABLE_RECORD_VIOLATION`; `allows_update = false` permanent | `tests/test_shadow_safety.py` | Phase 8 |
| Attribution continuity | INV-5: null attribution fields raise `ATTRIBUTION_INCOMPLETE`; never silently accepted | `tests/test_shadow_safety.py` | Phase 8 |
| Observability | ROG-1–ROG-7: replay observability; governance transitions visible; correlation propagation | `tests/test_dashboard.py` | Phase 9 |
| Resilience | AP-FP1–AP-FP8: failure classification; no silent swallowing; dead-letter handling | `failure/failure_playbook.md` | Phase 10 |
| Synchronization | SQL Server read-only boundary; dedup gate; origin authority attribution | `tests/test_sync.py` | Phase 5 |
| Config V2 governance | INV-2, INV-7: exactly-one-ACTIVE enforced; no hardcoded threshold substitution | `tests/test_shadow_safety.py` | Phase 4 |
| Priority engine | Work queue governance; source router; batch preview | `tests/test_work_queue.py` | Phase 5 |
| SHADOW→LIVE transition | CV2-4, AP-RT7: transition governance; Governance Administrator only; no automated trigger | `tests/test_shadow_safety.py` | Phase 12 |

### 7.2 Failed Certification Blocks Promotion

* A failed certification gate **blocks deployment stage promotion** — the deployment stage may not advance until the gate is satisfied
* Failed gate results are **permanent governance records** — not overwritten by subsequent passing results; both passing and failing outcomes are retained in deployment history
* Governance certification outcomes carry `correlation_id`, `execution_type = certification`, `attribution_timestamp` — they are attributed lineage events, not disposable pass/fail indicators

### 7.3 Replay Certification

Replay certification requires:
* `execution_type = replay` on all replay-generated records
* `governance_scope = REPLAY_ONLY` on all replay orchestration intents
* `live_effects_produced = 0` invariant enforced — any non-zero value triggers a CRITICAL governance alert (INV-4, AP-RT2)
* `historical_config_version_id` resolves to the correct version that was ACTIVE at original execution time — current ACTIVE is never substituted
* Replay records are permanently distinguishable from LIVE records in `outreach_history`, `state_transition_log`, and `student_timeline_events`

### 7.4 Immutable-Lineage Certification

Immutable-lineage certification requires:
* FINALIZED snapshot mutation raises `IMMUTABLE_RECORD_VIOLATION` at schema permission layer, not only application layer
* `warehouse.snapshot_ai_narratives` with `allows_update = false` raises `IMMUTABLE_RECORD_VIOLATION` on any update attempt (FAD-1, INV-6)
* `warehouse.monthly_reports` with `lifecycle_state = REPORT_PUBLISHED` has no in-place overwrite path — regeneration creates a new row with incremented `lineage_version`
* Config Version rule columns have no UPDATE privilege for any role

---

## 8. ATTRIBUTION GOVERNANCE

---

### 8.1 Mandatory Attribution Fields for Version Lineage Events

Every version lineage event — schema migration execution, Config Version activation, deployment mode transition, replay execution, regeneration execution — must carry the following attribution fields:

| Field | Type | Required on | Null behavior |
|---|---|---|---|
| `correlation_id` | UUID v4 | All lineage events | `ATTRIBUTION_INCOMPLETE` alert; never silently accepted |
| `causation_id` | UUID v4 | Replay and regeneration events | Required on replay; optional on original execution |
| `execution_type` | `original` / `replay` / `regeneration` / `certification` | All lineage events | `ATTRIBUTION_INCOMPLETE` alert |
| `execution_mode` | `SHADOW` / `LIVE` / `REPLAY` | All lineage events | `ATTRIBUTION_INCOMPLETE` alert |
| `origin_source` | `platform_generated`, `governance_admin_action`, `migration_execution`, etc. | All lineage events | `ATTRIBUTION_INCOMPLETE` alert |
| `origin_authority` | `sql_server_authoritative` / `platform_supplementary` | All data ingestion events | `ATTRIBUTION_INCOMPLETE` alert |
| `config_version_id` | Config Version Registry ID | All orchestration lineage events | `ATTRIBUTION_INCOMPLETE` alert |
| `attribution_timestamp` | Source event time (not ingestion time) | All lineage events | `ATTRIBUTION_INCOMPLETE` alert |

Attribution is **permanent** — version lineage events carry attribution fields that are never overwritten by subsequent version changes. ETL, migration, or application code that strips attribution fields from existing records is a specification violation.

### 8.2 Version Lineage Attribution Permanence

| Version artifact | Attribution permanence | AP-FP7 recovery restriction |
|---|---|---|
| Schema migration execution record | Revision ID, execution timestamp, author permanent | No migration may retroactively overwrite attribution |
| Config Version activation record | `created_at`, `created_by`, `activation_record_present`, prior ACTIVE's `deactivated_at` permanent | SUPERSEDED record attribution never removed |
| Deployment mode transition record | `activation_record_present`, governance admin identifier, acknowledgement timestamp permanent | No automated service may produce this record |
| Replay execution lineage | `causation_id → original correlation_id`, `historical_config_version_id` permanent | Replay chain never purged without compliance pathway |
| Regeneration execution lineage | `lineage_version`, `sourced_from_warehouse`, fingerprint comparison outcome permanent | Original report row attribution never modified |

AP-FP7 applies to evolution lineage: no recovery action may overwrite, backfill, or retroactively modify attribution records in `student_timeline_events`, `state_transition_log`, `warehouse.student_snapshots`, `warehouse.snapshot_ai_narratives`, or `warehouse.monthly_reports`.

### 8.3 Deployment Lineage Attribution

Deployment lineage — the record of when each deployment stage was promoted and under what governance authorization — is permanently attributed:

* SHADOW → LIVE transitions carry: `activation_record_present = true`, Governance Administrator identifier, explicit acknowledgement evidence, Config Version ID at transition time
* Deployment mode is attributed on every record written after the transition — `execution_mode` field is mandatory on all records (INV-5)
* Records written in SHADOW mode carry `execution_mode = SHADOW` and `governance_scope = SHADOW_ONLY` permanently — this attribution is never reinterpreted as LIVE execution after a subsequent mode transition

---

## 9. GOVERNANCE INVARIANTS

---

### 9.1 INV-1 through INV-7 — Evolution-Layer Enforcement

All seven governance invariants apply to evolution and lineage events without relaxation. No deployment stage, certification gate result, or version change may weaken them.

| Invariant | Rule | Evolution-layer enforcement |
|---|---|---|
| INV-1 | FINALIZED snapshot is immutable — no update, overwrite, or deletion | Schema migrations must never add UPDATE/DELETE privileges to `warehouse.student_snapshots` for any account except `compliance_pathway_user` column-level UPDATE (status) for COMPLIANCE_DELETED |
| INV-2 | Exactly one Config Version ACTIVE at all times | `uq_cvr_active_singleton` partial unique index must be preserved by all migrations; activation transaction must atomically SUPERSEDE prior before INSERT of new ACTIVE row |
| INV-3 (FAD-3) | Config Version activation is prospective-only — no backdating | "Rollback" creates a new version record; no SUPERSEDED restore pathway; prospective `effective_from` enforced |
| INV-4 (AP-RT2) | No LIVE effects from replay — `live_effects_produced = 0` on all replay outputs | Replay attribution fields (`execution_type = replay`, `governance_scope = REPLAY_ONLY`) are permanent; no migration may strip them; non-zero `live_effects_produced` triggers CRITICAL governance alert |
| INV-5 | Attribution continuity — `correlation_id`, `execution_mode`, `execution_type` mandatory | All records written by any deployment stage must carry attribution fields; `ATTRIBUTION_INCOMPLETE` on null; migration must not drop attribution columns |
| INV-6 (FAD-1) | FINALIZED_COPY AI narrative immutability — `allows_update = false` after FINALIZED state | `warehouse.snapshot_ai_narratives` schema permissions permanently enforce SELECT-only after `allows_update = false`; migration must not add UPDATE privilege |
| INV-7 | No hardcoded thresholds — all orchestration parameters governed by Config Version Registry | No migration, directive, or deployment configuration may introduce hardcoded constants substituting Config V2-governed parameters |

### 9.2 FAD-1 through FAD-6 — Evolution-Layer Implications

| FAD | Decision | Evolution-layer implication |
|---|---|---|
| FAD-1 | Frozen AI copy — AI narrative deep-copied at FINALIZED time | `snapshot_ai_narratives` FK is to `student_snapshots`, not `ai_insights`; schema evolution must preserve this FK model; migration must not add cascade-delete from `ai_insights` to `snapshot_ai_narratives` |
| FAD-2 | Snapshot-centric historical — all longitudinal analysis uses warehouse snapshots | Schema evolution must never create a pathway for report generation from live operational data; warehouse schema is the required source for all historical reporting |
| FAD-3 | Prospective-only config activation — no retroactive config changes | Config Version supersession is always forward-only; no migration may add a backdating mechanism; rollback = new version with prior values |
| FAD-4 | Append-only audit log — `student_timeline_events`, `state_transition_log` are append-only | Schema evolution must never add UPDATE/DELETE privileges to append-only tables; every table added to `compliance_audit` is INSERT-only by schema permission |
| FAD-5 | SQL Server read-only boundary — no write grants provisioned | Schema evolution introduces no write capability to SQL Server connection; any write attempt produces `ArchitecturalViolation` |
| FAD-6 | Three-schema privilege separation | Schema evolution preserves `public` / `warehouse` / `compliance_audit` schema model with distinct service accounts; no new account may receive warehouse UPDATE/DELETE or compliance_audit UPDATE/DELETE privileges |

### 9.3 Append-Only Evolution Invariants

| Domain | Append-only guarantee | Violation consequence |
|---|---|---|
| `warehouse.student_snapshots` | INSERT-only except `compliance_pathway_user` column-level UPDATE (status) | Schema permission error; `IMMUTABLE_RECORD_VIOLATION` |
| `warehouse.snapshot_ai_narratives` | INSERT-only; SELECT-only after `allows_update = false` | Schema permission error; `IMMUTABLE_RECORD_VIOLATION` |
| `warehouse.monthly_reports` | INSERT-only; SELECT-only after REPORT_PUBLISHED | Schema permission error; regeneration creates new row |
| `warehouse.report_audit_log` | INSERT-only always | `ArchitecturalViolation` |
| `compliance_audit.*` | INSERT-only always; no UPDATE or DELETE from any account | Schema permission error; always |
| `public.outreach_history` | INSERT-only | `ArchitecturalViolation` on UPDATE/DELETE |
| `public.state_transition_log` | INSERT-only | `ArchitecturalViolation` on UPDATE/DELETE |
| `public.student_timeline_events` | INSERT-only | `ArchitecturalViolation` on UPDATE/DELETE |
| `public.processed_events` | INSERT-only (dedup gate) | `ArchitecturalViolation` on UPDATE/DELETE |
| `public.config_version_registry` (rule columns) | INSERT-only on rule columns; governance metadata UPDATE by `config_admin_user` only | Schema permission denied on rule column UPDATE |

---

## 10. ACCEPTANCE CRITERIA

---

### Case 1 — Append-Only Evolution Enforcement

**Given** any version artifact in the platform  
**When** a new version is created  
**Then** the prior version is preserved as a permanently queryable historical lineage record with SUPERSEDED status; no version artifact is deleted or overwritten

---

### Case 2 — Config V2 Exactly-One-ACTIVE Invariant

**Given** an activation transaction creating a new ACTIVE Config Version  
**When** the transaction executes  
**Then** the prior ACTIVE row transitions to SUPERSEDED atomically; at no point do two rows hold `status = 'ACTIVE'`; DB-level partial unique index (`uq_cvr_active_singleton`) enforces this before any application logic can be bypassed (INV-2)

---

### Case 3 — Replay Config Resolution

**Given** a replay execution initiated against a historical record  
**When** the replay resolves Config Version  
**Then** `historical_config_version_id` is used — the version that was ACTIVE at original execution time; the current ACTIVE version is never substituted; `COMPARISON_UNAVAILABLE` is emitted if the historical version record is missing

---

### Case 4 — Immutable Historical Versions

**Given** `warehouse.student_snapshots` row with `lifecycle_state = FINALIZED`  
**When** any application-layer operation attempts mutation  
**Then** schema permission enforcement raises `IMMUTABLE_RECORD_VIOLATION`; no update pathway exists for `app_service_user`; `compliance_pathway_user` column-level UPDATE (status) is the sole exception for COMPLIANCE_DELETED transition (INV-1)

---

### Case 5 — Certification-Gated Promotion

**Given** a deployment attempting SHADOW → LIVE mode transition  
**When** Phase 12 certification is not complete  
**Then** the transition is blocked; `activation_record_present` must be `true` in Config Version Registry; Governance Administrator explicit authorization is required; no automated service may trigger this transition (AP-RT7)

---

### Case 6 — Attribution Continuity

**Given** any version lineage event (migration execution, Config Version activation, replay execution, regeneration execution, deployment transition)  
**When** the event is recorded  
**Then** all mandatory attribution fields are populated; null fields raise `ATTRIBUTION_INCOMPLETE`; attribution is permanent and never overwritten by subsequent version changes (INV-5)

---

### Case 7 — Config Version Rollback Prohibition

**Given** an operator requesting "rollback" to a prior Config Version  
**When** the rollback is executed  
**Then** a **new** Config Version record is created copying the prior version's rule values; the SUPERSEDED record is not restored to ACTIVE; `effective_from` is set to `now()` (FAD-3, INV-3)

---

### Case 8 — Governance Architecture Non-Downgrade

**Given** any schema migration or application deployment  
**When** applied  
**Then** no migration removes the `uq_cvr_active_singleton` index; no migration adds UPDATE/DELETE to append-only tables; no migration introduces cross-schema FK dependencies from `compliance_audit` to `public`; no migration weakens the three-schema service account privilege model

---

### Case 9 — Fingerprint Preservation

**Given** a regenerated `warehouse.monthly_reports` row  
**When** fingerprint comparison executes  
**Then** all five fingerprint components from the new execution are compared to the stored original fingerprint; `IDENTICAL` / `POTENTIALLY_DIVERGENT` / `COMPARISON_UNAVAILABLE` outcome is logged; `POTENTIALLY_DIVERGENT` produces a governance warning; original fingerprint is never overwritten

---

### Case 10 — Replay Cannot Overwrite LIVE Lineage

**Given** a replay execution producing records in `public.outreach_history` and `public.state_transition_log`  
**When** replay records are written  
**Then** all records carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`; no replay execution path holds INSERT authority into the `warehouse` schema; no LIVE record is modified by replay execution (INV-4, AP-RT2)

---

## 11. REFERENCES

---

This document inherits governance contracts from the following canonical sources. Where this document conflicts with a referenced canonical source, the canonical source governs.

| Document | Governance contract |
|---|---|
| `spec/01_requirements.md` | Platform purpose, 10 operational domains, 6 FADs, NFRs, Config Version Registry governance (§12) |
| `spec/03_state_transition_rules.md` | Valid/invalid transitions, INV-1–INV-7, governance boundaries across all lifecycle domains |
| `spec/04_idempotency_concurrency.md` | Idempotency model, concurrency governance, regeneration lineage (new `lineage_version`) |
| `spec/05_external_integrations.md` | Append-only ingestion, lineage-preserving integration, attribution propagation |
| `spec/06_observability_operations.md` | Two-category telemetry, governance-aware observability, replay observability (§1.5) |
| `spec/08_data_model.md` | Warehouse entity model, three-schema architecture, lineage attribution fields |
| `spec/09_warehouse_physical_architecture.md` | Physical warehouse design, two-table snapshot strategy, service account model |
| `data/data_lifecycle.md` | Data lineage classes, mutability governance, retention governance, attribution fields |
| `meta/project_classification.md` | Execution-mode governance, environment classification, deployment-stage governance |
| `runtime/system_loop.md` | Six canonical runtime modes, SHADOW/LIVE governance, AP-RT7 transition governance |
| `failure/failure_playbook.md` | AP-FP1–AP-FP8, AP-FP7 recovery action prohibition on append-only records |
| `execution/build_phases.md` | Governance-first phase architecture, 12-phase certification dependency map, exit criteria |
| `execution/implementation_plan.md` | Service implementation order, governance blocker analysis, SHADOW→LIVE rollout model |
| `alembic/versions/0002_warehouse_schema.py` | Warehouse/compliance_audit schema, service accounts, GRANT model, two-table snapshot strategy |
| `alembic/versions/0003_config_version_registry.py` | Config Version Registry, exactly-one-ACTIVE index, supersession lineage, prospective-only activation |
| `tests/test_shadow_safety.py` | SHADOW containment (SVL-1–3), replay isolation (ROS-1–2, INV-4, AP-RT2), attribution continuity (74 tests) |
| `tests/test_dashboard.py` | Observability governance, replay observability (ROG-1–7), governance transition visibility (87 tests) |

---

## END OF FILE
