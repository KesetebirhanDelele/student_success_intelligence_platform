# spec/04_idempotency_concurrency.md

---

## LAYER 2 — SPECIFICATIONS (IDEMPOTENCY & CONCURRENCY)

---

## 1. PURPOSE

This file defines:

* Idempotency rules across all lifecycle domains
* Concurrency control mechanisms
* Duplicate prevention strategies
* Race condition handling
* Irreversible operation definitions and protections
* Replay safety and determinism expectations

The goal is to ensure:

* No duplicate outreach, snapshot finalization, report publication, or compliance action
* Safe retries and reprocessing in every domain
* Consistent behavior under parallel execution
* Immutable record protection for FINALIZED snapshots and REPORT_PUBLISHED reports
* Governance boundaries enforced at the concurrency layer

### Lifecycle Domains Covered

| Domain | Key Idempotency Concern | Governance Boundary |
|---|---|---|
| **Outreach** (Domain 1) | No duplicate outreach per (user_id, checkpoint_type, attempt) | CLOSED is terminal |
| **Snapshot** (Domain 2) | No duplicate FINALIZED snapshot per (student_id, snapshot_month) | FINALIZED is irreversible; the row is immutable after this state |
| **Monthly Report** (Domain 3) | No duplicate publication; regeneration creates new version lineage | REPORT_PUBLISHED is immutable; no in-place overwrite |
| **AI Insight** (Domain 4) | One in-flight generation per (student_id, insight_type, date_period) | Attribution metadata immutable after AI_GENERATED |
| **Config Version** (Domain 5) | Atomic activation; exactly one ACTIVE version; rollback forbidden | ACTIVE → SUPERSEDED only outbound transition |
| **Compliance Governance** (Domain 6) | One active workflow per student; pre-action audit is a hard gate | Terminal states are irreversible; audit records are append-only |

---

## 2. CORE PRINCIPLES

---

### 2.1 Idempotency First

* Repeated operations MUST NOT create duplicate effects
* Same request → same outcome
* Same input + same state → same persisted result; no first-run/second-run divergence

---

---

### 2.2 Concurrency Safety

* Parallel execution must not corrupt state
* Only one valid operation per entity per cycle
* Authoritative transition ownership: each state transition has exactly one owner; concurrent claims are resolved by the earliest-arriving write

---

---

### 2.3 Deterministic Conflict Resolution

* When conflicts occur → system must resolve predictably
* First valid write wins; subsequent conflicting writes are rejected, not silently dropped
* Every conflict produces an audit entry naming the winning and rejected actors

---

---

### 2.4 Platform Concurrency Philosophy

The platform contains six distinct workflow classes. Each has different concurrency expectations:

| Workflow class | Mutation model | Concurrency expectation | Replay model |
|---|---|---|---|
| Outreach workflows | Mutable state machine | Serialized per student per checkpoint | Idempotency key; second run blocked |
| Snapshot governance | Append-only once FINALIZED | Serialized finalization per (student_id, snapshot_month) | Idempotency check; second FINALIZED rejected |
| Report generation | Append-only on publish; new lineage on regenerate | Serialized publication per (cohort, month, version) | Regeneration creates NEW record; original preserved |
| AI generation | Version-append; prior versions archived | Serialized per (student_id, insight_type, date_period) for in-flight | New record on force-refresh; prior versioned |
| Config version activation | Atomic swap | Serialized activation globally | Rollback forbidden; new version required |
| Compliance workflows | Governance audit trail | Serialized per student; one active workflow | Each workflow uniquely identified; duplicate intake rejected |

**Append-only operational philosophy:** Once an entity crosses its governance boundary (FINALIZED, REPORT_PUBLISHED, ACTIVE config version), it becomes append-only from the application layer. No UPDATE or DELETE from application code is permitted. New content is expressed as new records — new versions or new regeneration lineage — not mutations.

**Replay safety:** A replay is safe when running the same operation twice produces the same final state without duplicate side-effects. Operations that cross governance boundaries are NOT replay-safe by design; they are irreversible. Operations before governance boundaries (DRAFT assembly, report generation, AI generation) are designed to be replay-safe.

**Determinism requirement:** Any operation whose output is used for reproducibility guarantees MUST produce deterministic output given identical inputs. Non-deterministic operations (live LLM calls) are isolated to the pre-governance-boundary phase; they are not permitted after a governance boundary is crossed.

---

---

### 2.5 Irreversible Operation Definitions

The following operations are explicitly irreversible. No retry, rollback, or replay may undo them:

| Operation | Domain | Why irreversible |
|---|---|---|
| `VALIDATING → FINALIZED` | Snapshot | AI text physically copied; fingerprint locked; immutability guarantee begins |
| `REPORT_APPROVED → REPORT_PUBLISHED` | Report | Publication boundary; report committed as authoritative record for that cohort-month |
| `APPROVED → ACTIVE` (config version) | Config Version | All subsequent runs use new version; prior is SUPERSEDED; no rollback path |
| `IN_EXECUTION → DELETED` | Compliance | Student records permanently removed |
| `IN_EXECUTION → ANONYMIZED` | Compliance | PII removed; original values are gone |
| `DRAFT → DISCARDED` | Snapshot | Draft discarded; no reinstatement path |
| `COMPLIANCE_HOLD → COMPLIANCE_DELETED` | Snapshot | Snapshot records removed via Compliance Pathway |

These operations require serialization, authorization, and pre-execution audit entries (where applicable). They are not subject to automatic retry.

---

---

## 3. IDEMPOTENCY DEFINITIONS

---

### Idempotent Operation

An operation where:

```plaintext
Same input + same state → same result (no duplication)
```

---

---

## 4. IDEMPOTENCY KEYS

---

### 4.1 Outreach Domain Key

```plaintext
idempotency_key = (user_id, checkpoint_type, contact_attempt)
```

Used for: outreach trigger, retry execution, webhook processing. Duplicate key → reject operation; log; do NOT retry.

---

---

### 4.2 Snapshot Domain Key

```plaintext
snapshot_idempotency_key = (student_id, snapshot_month)
```

**Scope:** Prevents duplicate FINALIZED snapshot rows for the same student-month. Checked at the `VALIDATING → FINALIZED` transition gate. If a FINALIZED row already exists for the pair, the second finalization attempt is rejected and the existing FINALIZED row is preserved unchanged.

**DRAFT behavior:** Multiple DRAFT snapshots for the same (student_id, snapshot_month) may coexist transiently during retry and resume flows. Only one may ever reach FINALIZED. The uniqueness constraint applies at the FINALIZED boundary, not at the DRAFT boundary.

**Regeneration:** Regeneration operations are keyed on (snapshot_id, regeneration_request_timestamp). Each regeneration request is a distinct lineage event, not a retry of the original finalization.

---

---

### 4.3 Report Domain Key

```plaintext
report_idempotency_key = (cohort_id, report_month, template_version, lineage_version)
```

**Scope:** Prevents duplicate REPORT_PUBLISHED records for the same cohort-month-template combination. The publication gate is checked at `REPORT_APPROVED → REPORT_PUBLISHED`.

**Regeneration:** Each operator-requested historical regeneration increments `lineage_version` and creates a new record; it is not a retry of the original generation.

---

---

### 4.4 AI Insight Domain Key

```plaintext
ai_idempotency_key = (student_id, insight_type, date_period, prompt_version, version_number)
```

**Scope:** Prevents duplicate AI insight records per tuple. Force-refresh creates a new record with an incremented `version_number`; it does NOT reuse the existing record's key.

**In-flight deduplication:** Before a new AI_PENDING record is created, the system checks for an existing record in (AI_PENDING, AI_GENERATING, AI_REVIEW_PENDING) for the same (student_id, insight_type, date_period). If one exists, the new request is rejected; the in-flight operation completes normally.

---

---

### 4.5 Config Version Domain Key

```plaintext
config_version_idempotency_key = (version_number, effective_from)
```

**Scope:** A version may be activated exactly once. The `APPROVED → ACTIVE` transition is a write-once operation on the version record. At most one pending activation is in flight at any time; activation is globally serialized.

---

---

### 4.6 Compliance Domain Key

```plaintext
compliance_idempotency_key = (student_id, action_type, request_timestamp)
```

**Scope:** A student may have at most one active (non-terminal) compliance workflow at a time. A new `COMPLIANCE_REQUEST_RECEIVED` is rejected if a non-terminal workflow already exists for the same student_id.

**Pre-action audit key:** `(student_id, action_type, workflow_id)` — uniquely identifies the pre-action audit entry. A second attempt to write the same entry is rejected.

---

---

### 4.7 Storage Requirement (All Domains)

* All idempotency keys are stored durably before the gated operation begins
* Duplicate key detection occurs at the storage layer before execution proceeds
* A detected duplicate key → reject the operation; log with domain, key, actor, attribution_timestamp
* No silent drops; every rejection is auditable

---

---

## 5. DUPLICATE PREVENTION RULES

---

### RULE 1 — OUTREACH TRIGGER

```plaintext id="8u3m8m"
IF idempotency_key exists → BLOCK execution
```

---

---

### RULE 2 — RETRY EXECUTION

```plaintext id="mrk0e1"
Same (user_id, attempt) must not execute twice
```

---

---

### RULE 3 — WEBHOOK EVENTS

```plaintext id="3rfv2q"
Same event_id must be processed once
```

---

---

## 6. CONCURRENCY CONTROL

---

### 6.1 Concurrency Limit

```plaintext id="4m1g4k"
MAX_CONCURRENT_EXECUTIONS = 50 (Production)
```

---

---

### 6.2 Execution Model

* Batch-based processing
* Queue-controlled execution

---

---

### 6.3 Locking Strategy

---

#### Per-User Lock

```plaintext id="1z6nyk"
Lock on user_id during processing
```

---

#### Purpose

* Prevent duplicate processing of same student

---

---

### 6.4 Global Scheduler Lock

```plaintext id="7kn3hv"
One scheduler run per execution window
```

---

---

## 7. RACE CONDITION HANDLING

---

### Scenario 1 — Duplicate Processing

---

**Given:**

* Same student picked by multiple workers

---

**Resolution:**

```plaintext id="l0xsh1"
First execution wins  
Others skipped
```

---

---

### Scenario 2 — Concurrent Retry + New Trigger

---

**Given:**

* Retry cycle and daily run overlap

---

**Resolution:**

* State-based validation prevents duplicate
* Idempotency key blocks duplication

---

---

### Scenario 3 — Webhook + Scheduler Conflict

---

**Given:**

* Webhook updates state during processing

---

**Resolution:**

* State check before execution
* Abort if state already advanced

---

---

## 8. IDEMPOTENT API DESIGN

---

### Requirement

All critical endpoints MUST support idempotency:

---

#### Applies To:

* POST /outreach/trigger
* POST /actions/manual
* POST /webhook/ghl-update

---

---

### Mechanism

* Accept idempotency key (header or payload)
* Store and validate

---

---

## 9. DATABASE ENFORCEMENT

---

### Unique Constraint

```sql id="tx8gk0"
UNIQUE (user_id, checkpoint_type, contact_attempt)
```

---

---

### Optional Event Table

```plaintext id="dr4e6y"
ProcessedEvents
  - event_id
  - user_id
  - timestamp
```

---

---

## 10. FAILURE HANDLING

---

### Duplicate Detection

---

**Behavior:**

1. Reject duplicate
2. Log event
3. Do NOT retry

---

---

### Lock Timeout

---

**Behavior:**

* Release lock
* Retry safely

---

---

### Partial Execution

---

**Behavior:**

* Resume safely
* Skip completed operations

---

---

## 11. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Minimal idempotency
* No strict concurrency control

---

---

### STANDARD

* Basic idempotency keys
* Limited concurrency control

---

---

### PRODUCTION

* Full idempotency enforcement
* Strict concurrency limits
* Locking + queue system
* Race condition handling

---

---

## 12. INVARIANTS

---

* No duplicate outreach per attempt
* No concurrent execution on same user
* All idempotent operations must be safe to retry
* State must remain consistent

---

---

## 13. ACCEPTANCE CRITERIA

---

### Case 1 — Duplicate Trigger

**Given** same idempotency key
**When** request repeated
**Then** second request blocked

---

---

### Case 2 — Concurrent Execution

**Given** parallel processing
**When** same user processed
**Then** only one succeeds

---

---

### Case 3 — Webhook Duplication

**Given** duplicate webhook
**When** processed
**Then** second ignored

---

---

### Case 4 — Retry Safety

**Given** retry triggered
**When** executed multiple times
**Then** no duplicate effect

---

---

## 14. REFERENCES

---

Depends on:

* spec/03_state_transition_rules.md
* spec/07_api_contracts.md
* runtime/system_loop.md
* runtime/scheduler_design.md
* failure/failure_playbook.md
* meta/project_classification.md

---

---

## 15. SNAPSHOT FINALIZATION IDEMPOTENCY

---

This section defines concurrency and idempotency protections specific to the Snapshot lifecycle domain (Domain 2 in spec/03_state_transition_rules.md).

---

### 15.1 Duplicate Snapshot Generation Protection

**Scenario:** The monthly scheduler fires twice for the same student (job restart, double-fire).

**Protection:** The idempotency key `(student_id, snapshot_month)` is checked at the `VALIDATING → FINALIZED` gate. If a FINALIZED record already exists for the pair, the second finalization attempt is rejected. The duplicate DRAFT is discarded. The existing FINALIZED snapshot is preserved without modification.

**DRAFT coexistence:** Multiple DRAFT snapshots for the same pair may exist transiently during retry flows. Only one may reach FINALIZED. The uniqueness guarantee applies at the FINALIZED boundary only.

---

### 15.2 Concurrent Finalization Attempt Handling

**Scenario:** Two workers attempt to finalize the same snapshot simultaneously (distributed job execution).

**Serialization requirement:** The `VALIDATING → FINALIZED` transition requires a serialized write. Only one writer can commit FINALIZED for a given `(student_id, snapshot_month)`. The second concurrent attempt observes the existing FINALIZED row and exits cleanly.

**Conflict resolution:** First valid writer wins. The rejected write is logged with: student_id, snapshot_month, rejecting_correlation_id, winning_correlation_id.

---

### 15.3 Regeneration Race Protection

**Scenario:** Multiple concurrent regeneration requests are submitted against the same FINALIZED snapshot.

**Protection:** Each regeneration request is a distinct lineage event keyed on `(snapshot_id, regeneration_request_timestamp)`. Concurrent requests do NOT mutate the snapshot. If a snapshot is already in REGENERATION_REQUESTED state when a second request arrives, the second is queued and processed after the first completes.

---

### 15.4 Content Freezing and Fingerprint Drift Prevention

**Scenario:** Snapshot content fields or AI insight data change between DRAFT assembly and finalization.

**Protection:** Snapshot content fields are locked at `DRAFT → VALIDATING`. The Reproducibility Fingerprint is computed from the locked content and is immutable at `VALIDATING → FINALIZED`. AI insight data that changes after `DRAFT → VALIDATING` does not affect what is frozen; the physical copy semantics apply at finalization only.

**Fingerprint components:** All five fingerprint components are captured atomically at finalization. Unavailable components are recorded as `UNKNOWN_V0`; this does not block finalization.

---

### 15.5 Stale Snapshot Update Protection

**Scenario:** A background process attempts to update a DRAFT snapshot after it has already been finalized by another path.

**Protection:** Any write to a snapshot row in FINALIZED, COMPLIANCE_HOLD, COMPLIANCE_DELETED, or DISCARDED state is rejected at the application layer. State validation precedes any content write; the writer must confirm the snapshot is still in a mutable state (DRAFT or VALIDATING) before updating fields.

---

### 15.6 Duplicate Compliance Action Protection

**Scenario:** Two compliance deletion requests arrive for the same FINALIZED snapshot.

**Protection:** The compliance workflow idempotency key (Section 4.6) enforces that at most one active non-terminal compliance workflow exists per student. A second intake request for the same student is rejected. The snapshot transitions to COMPLIANCE_HOLD exactly once; a second concurrent COMPLIANCE_HOLD attempt is rejected.

---

### 15.7 Snapshot Idempotency Classification

| Operation | Idempotency class | Safe to replay |
|---|---|---|
| DRAFT assembly | Replay-safe | Yes — new DRAFT replaces incomplete prior DRAFT |
| DRAFT → VALIDATING | Idempotent gate | Yes — second attempt is no-op if already VALIDATING |
| VALIDATING → FINALIZED | Serialized, once-only | No — second attempt rejected; first FINALIZED preserved |
| Regeneration request | Append-new-lineage | Yes — each request creates a new audit record |
| COMPLIANCE_HOLD entry | Serialized | Yes — already in COMPLIANCE_HOLD is a no-op for that transition |
| COMPLIANCE_DELETED | Once-only terminal | No — records are gone; no replay |

---

---

## 16. REPORT GENERATION CONCURRENCY

---

This section defines concurrency and idempotency protections specific to the Monthly Report lifecycle domain (Domain 3).

---

### 16.1 Duplicate Report Generation Job Prevention

**Scenario:** The report scheduler fires twice for the same cohort-month (APScheduler misconfiguration, job restart).

**Protection:** The idempotency key `(cohort_id, report_month, template_version, lineage_version)` is checked at `REPORT_PENDING → REPORT_GENERATING`. If a record in REPORT_GENERATING, REPORT_GENERATED, REPORT_REVIEW_PENDING, REPORT_APPROVED, or REPORT_PUBLISHED already exists for the same key, the duplicate job is rejected and exits cleanly.

---

### 16.2 Concurrent Publication Attempt Handling

**Scenario:** Two operator actions attempt to publish the same report simultaneously.

**Serialization requirement:** The `REPORT_APPROVED → REPORT_PUBLISHED` transition requires a serialized write. Only one writer can commit REPORT_PUBLISHED for a given `(cohort_id, report_month, lineage_version)`. The second concurrent attempt observes the existing REPORT_PUBLISHED row and exits. The conflict is logged as a duplicate publication attempt.

---

### 16.3 Regeneration Conflict Prevention

**Scenario:** A historical regeneration is requested while another regeneration for the same report is in progress.

**Protection:** A regeneration request is rejected if an existing record for the same (cohort_id, report_month, template_version) is currently in REPORT_REGENERATION_REQUESTED or REPORT_GENERATING state. The operator is notified that a regeneration is already in progress.

**Published report preservation:** The source REPORT_PUBLISHED record is never modified during regeneration. Regeneration operates on a NEW record; the published record is read-only throughout.

---

### 16.4 Stale Rendering Protection

**Scenario:** A long-running generation job reads snapshot data that changes during the job (e.g., compliance action on source snapshot).

**Protection:** The source_snapshot_id and source_snapshot_fingerprint are bound to the generation job at start time. If the source snapshot's fingerprint changes during generation, the mismatch is detected at output commit time and the job transitions to REPORT_GENERATION_FAILED.

**Historical regeneration:** Historical regeneration always uses physically stored snapshot data, not live table queries. Stale rendering is not applicable for historical regeneration.

---

### 16.5 Artifact Deduplication Semantics

Each report version is identified by `(cohort_id, report_month, template_version, lineage_version)`. Two records with the same tuple are duplicates; the second is rejected. A regenerated report is NOT a duplicate — it has a different `lineage_version`.

**POTENTIALLY_DIVERGENT flag:** Applied when a regenerated report's source snapshot fingerprint differs from the original publication's recorded fingerprint. This is a legitimate regeneration outcome, not a concurrency defect.

---

---

## 17. AI GENERATION IDEMPOTENCY

---

This section defines concurrency and idempotency protections specific to the AI Insight lifecycle domain (Domain 4).

---

### 17.1 Duplicate Generation Request Prevention

**Scenario:** The AI scheduler fires twice for the same (student_id, insight_type, date_period).

**Protection:** Before creating a new AI_PENDING record, the system checks for an existing record in (AI_PENDING, AI_GENERATING, AI_REVIEW_PENDING) for the same tuple. If one exists, the new request is rejected; the in-flight operation completes normally. If an AI_REVIEWED record exists within TTL and no force-refresh was requested, the scheduler does not trigger a new generation.

---

### 17.2 Concurrent Force-Refresh Handling

**Scenario:** Two operators simultaneously request force-refresh on the same AI_REVIEWED insight.

**Protection:** Force-refresh atomically transitions the existing AI_REVIEWED record to AI_REFRESH_REQUESTED. The first request succeeds; the second observes the record already in AI_REFRESH_REQUESTED and is rejected. The in-flight refresh is already in progress. Force-refresh creates exactly one NEW AI_PENDING record per event.

---

### 17.3 Prompt Version Capture and Stale Prompt Prevention

**Scenario:** The AI prompt template is updated while a generation job is in flight.

**Protection:** The `prompt_version` is captured at the moment the AI_PENDING record is created and is bound to that record immutably. The generation uses the prompt version captured at creation, regardless of any subsequent template update (Section 27.5 of spec/03_state_transition_rules.md). A force-refresh triggered after a prompt update creates a new record attributed to the new prompt version.

---

### 17.4 Model Version Attribution Consistency

The `model_used` field is set at AI_GENERATED state and is immutable. It reflects the actual LLM model that produced the output, not the model version in settings at job-start time. This attribution is final and cannot be changed after AI_GENERATED.

---

### 17.5 Partial Generation Failure Recovery

**Scenario:** An LLM call fails partway through generation (partial structured output, connection drop mid-stream).

**Recovery:** The AI record remains in AI_GENERATING. A retry creates a new LLM call on the same record. Partial output is discarded and not partially committed to the insight content fields. If all retries are exhausted, the record transitions to AI_GENERATION_FAILED.

**No partial AI content in AI_GENERATED state:** A record must not reach AI_GENERATED with partially populated output fields. The transition is gated by schema validation of the full output structure.

---

### 17.6 AI Serving State Semantics

**Current insight:** The most recently AI_REVIEWED record for a given (student_id, insight_type, date_period) is the current insight served to callers.

**Stale serving:**

* AI_GENERATION_FAILED + no prior AI_REVIEWED → no insight served (explicit null)
* AI_GENERATION_FAILED + prior AI_REVIEWED exists → prior record served with `stale: true` and `failure_timestamp`

**Archived versions:** AI_ARCHIVED records are not served as current insights but are fully queryable for audit, history, and reproducibility verification.

---

### 17.7 Finalized Snapshot AI Isolation Boundary

AI insight lifecycle events (force-refresh, archival, compliance deletion of ai_insights records) occurring concurrently with a report regeneration that reads snapshot AI text do NOT interfere. The report regeneration reads physically copied text from the snapshot row; it never reads from the ai_insights table. No locking relationship exists between ai_insights operations and snapshot AI text reads. Re-running snapshot regeneration from snapshot row data always produces the same output regardless of what has happened to the source ai_insights records.

---

---

## 18. CONFIGURATION VERSION GOVERNANCE CONCURRENCY

---

This section defines concurrency and idempotency protections for the Config Version lifecycle domain (Domain 5).

---

### 18.1 Simultaneous Activation Attempt Prevention

**Scenario:** Two administrators simultaneously attempt to activate different APPROVED configuration versions.

**Protection:** Config version activation is globally serialized. Only one `APPROVED → ACTIVE` transition may be in flight at any time. The first to commit succeeds; the second is rejected. The atomic swap invariant (never zero, never two ACTIVE versions) must hold at all times (Section 32.1 of spec/03_state_transition_rules.md).

**Collision logging:** The rejected activation is logged with: attempted_version_id, conflicting_version_id, actor_identity, attribution_timestamp. The operator is notified that another activation occurred first.

---

### 18.2 Duplicate Promotion Prevention

**Scenario:** A version record is promoted to APPROVED twice (operator double-clicks).

**Protection:** A version record may transition to APPROVED exactly once. The `UNDER_REVIEW → APPROVED` transition checks that the version is currently in UNDER_REVIEW. A second attempt against a version already in APPROVED is rejected. An attempt to activate an already-ACTIVE version is also rejected with a "version is already active" response.

---

### 18.3 Race Condition Around ACTIVE Status at Snapshot Finalization

**Scenario:** A snapshot generation job reads the ACTIVE config version at the same moment it is being superseded by a new activation.

**Protection:** The snapshot generation job captures the config version reference at `DRAFT → VALIDATING` (content lock time). That reference is bound to the snapshot regardless of subsequent activations. If the version transitions to SUPERSEDED between capture and finalization, the snapshot's fingerprint still records the captured version (now SUPERSEDED but fully queryable). No mid-run version switches occur for an in-flight snapshot.

---

### 18.4 Prospective-Only Enforcement

Configuration version changes never trigger retrospective processing. If a new version is activated during a monthly snapshot batch run, snapshots that have already locked content (VALIDATING or FINALIZED) retain their original version reference. Only snapshots not yet in VALIDATING state pick up the new version. This holds even if the batch runner is interrupted and resumed.

---

### 18.5 Rollback Prohibition (Concurrency Expression)

Rollback is the attempt to re-activate a SUPERSEDED version. The SUPERSEDED → ACTIVE transition is not valid in the state machine. Any code path that produces this transition is a defect; the system rejects it. If a configuration error is discovered post-activation, the only lawful path is: create a new PROPOSED record → full approval lifecycle → activate the new version, which supersedes the erroneous one.

---

---

## 19. COMPLIANCE-GOVERNED CONCURRENCY

---

This section defines concurrency and idempotency protections for the Compliance Governance domain (Domain 6).

---

### 19.1 Duplicate Deletion/Anonymization Request Prevention

**Scenario:** Two compliance requests arrive for the same student within a short window.

**Protection:** The intake gate checks for any existing non-terminal workflow for the same student_id. A duplicate is rejected; the intake log records both the accepted workflow_id and the rejected duplicate request details.

---

### 19.2 Concurrent Compliance Action Prevention

**Scenario:** Two compliance personnel simultaneously attempt to advance the same workflow to IN_EXECUTION.

**Protection:** The `APPROVED_FOR_ACTION → IN_EXECUTION` transition is serialized and gated. Only one actor may commit this transition. The second concurrent attempt observes the workflow already in IN_EXECUTION and is rejected. The pre-action audit entry, once written, is append-only; a second attempt to write the same entry is rejected by the unique key on the audit record.

---

### 19.3 Stale Approval Workflow Handling

**Scenario:** A compliance workflow is approved but the pre-action audit entry is delayed.

**Protection:** The `APPROVED_FOR_ACTION → IN_EXECUTION` gate does not time out; it blocks indefinitely until all preconditions are met. This is by design: compliance actions are governance events, not timed operations.

**Stale scope manifest:** If new finalized snapshots are created for the student during the delay between authorization and execution, the scope_manifest must be updated and re-authorized before IN_EXECUTION begins. A stale scope manifest is not a valid execution basis.

---

### 19.4 Conflicting Governance Action Prevention

**Scenario:** A compliance request arrives while a DRAFT snapshot for the same student is being assembled.

**Interaction:** A DRAFT snapshot that receives a compliance request is handled by `DRAFT → DISCARDED` (Section 17.4 of spec/03_state_transition_rules.md). The compliance workflow (Domain 6) governs FINALIZED records via COMPLIANCE_HOLD. A DRAFT → COMPLIANCE_HOLD transition is forbidden; DRAFTs are discarded directly.

---

### 19.5 Partial Execution Recovery

**Scenario:** A compliance deletion partially executes (some tables succeed, some fail mid-transaction).

**Recovery path:** `IN_EXECUTION → UNDER_REVIEW`. The partial execution is fully logged in compliance_audit: which tables were acted upon, which were not, row counts for both. The workflow re-enters review before any retry. Before retry execution resumes, the scope_manifest is updated to exclude already-completed tables, preventing double-deletion.

---

### 19.6 Audit Survivability Requirements

Compliance audit records are the survivability anchor for all compliance governance:

* **Pre-action entry** must exist before IN_EXECUTION begins — hard gate
* **Post-action entry** must be written after execution completes, even on crash-restart
* **Append-only** — no audit record is modified after creation; a correction creates a new record with a reference to the corrected record
* **Schema independence** — compliance_audit schema records must survive even if the operational records they document are deleted; the audit schema is never subject to operational deletions

**Failed post-action audit write:** Treated as an incident; recovery write required; human review of audit completeness required.

---

---

## 20. EVENT IDEMPOTENCY & ATTRIBUTION

---

### 20.1 Communication Events

**Idempotency key:** `(student_id, channel, message_template_id, outreach_attempt_id)`

**Deduplication:** Before any outbound communication dispatch (SHADOW or LIVE mode), the key is checked against the communication event log. A duplicate key rejects the dispatch and logs the suppression event.

**GHL inbound webhooks:** Deduplicated by `ghl_message_id`. A webhook event with a previously processed `ghl_message_id` is acknowledged (200 OK) and discarded without reprocessing.

---

### 20.2 Access History Events

**Idempotency:** SQL Server mirror events are deduplicated by `(user_id, event_type, event_timestamp)`. A mirror cycle that re-delivers an already-stored event produces a no-op (INSERT ... ON CONFLICT DO NOTHING semantics).

**Attribution preservation:** `origin_source = mirrored_sql_server` events must retain their attribution through any ETL or batch step. The origin must not be overwritten to a platform value during processing.

**Platform-supplementary events:** Carry `origin_authority = platform_supplementary`. They are stored as context and do not override SQL Server mirrored state for eligibility decisions.

---

### 20.3 AI Lifecycle Events

**Idempotency:** AI insight generation events are deduplicated by `(student_id, insight_type, date_period, prompt_version, version_number)` (Section 4.4).

**Attribution immutability:** Once an AI record reaches AI_GENERATED, the attribution fields (`model_used`, `prompt_version`, `generated_at`, `input_metrics_hash`) are immutable. Any event that would modify these fields on an AI_GENERATED-or-later record is rejected.

---

### 20.4 Report Lifecycle Events

**Idempotency:** Report generation and publication events are deduplicated by `(cohort_id, report_month, template_version, lineage_version)` (Section 4.3).

**Fingerprint recording:** Every report generation event carries the `source_snapshot_fingerprint` at generation time. This is immutable after REPORT_PUBLISHED. Historical regeneration records both the original and the regeneration-time fingerprint in the audit log.

---

### 20.5 Compliance Events

**Idempotency:** Compliance workflow events are deduplicated by `(workflow_id, event_type, sequence_number)`. Each compliance workflow transition produces exactly one audit entry.

**Pre-action entry uniqueness:** The pre-action audit entry for `(student_id, action_type, workflow_id)` is unique. A second attempt to write the same entry is rejected.

**Post-action entry idempotency:** If a post-action write fails and is retried, the retry checks for an existing post-action entry for the same `workflow_id` before writing.

---

### 20.6 Lifecycle Transition Log Idempotency

Every state transition in every domain produces a lifecycle log entry. Duplicate protection per domain:

| Domain | Log dedup key | Duplicate handling |
|---|---|---|
| Outreach | (tracking_id, from_state, to_state, correlation_id) | Duplicate rejected |
| Snapshot | (snapshot_id, from_state, to_state, correlation_id) | Duplicate rejected |
| Report | (report_id, from_state, to_state, correlation_id) | Duplicate rejected |
| AI Insight | (insight_id, from_state, to_state, correlation_id) | Duplicate rejected |
| Config Version | (version_id, from_state, to_state, correlation_id) | Duplicate rejected |
| Compliance | (workflow_id, from_state, to_state, audit_sequence_number) | Sequence is monotonically increasing per workflow |

**Correlation ID propagation:** A correlation_id generated at the entry point of any scheduled job or user-initiated request is propagated through all downstream log entries, database writes, and external API calls. The full lifecycle of a request is traceable from a single correlation_id.

---

### 20.7 Mirrored-Source Conflict Handling

When a SQL Server mirrored event conflicts with a platform-supplementary event for the same student and event type:

* The SQL Server mirrored event (`origin_authority = sql_server_authoritative`) governs eligibility decisions
* The platform-supplementary event is retained as context with `origin_authority = platform_supplementary`
* Both events are stored; neither is deleted
* The conflict is logged with both event IDs and their differing values

---

---

## 21. CROSS-DOMAIN CONCURRENCY INVARIANTS

---

### CONC-INVARIANT-1 — Append-Only Finalized Records

No FINALIZED snapshot row and no REPORT_PUBLISHED report row may be updated or deleted by any application service account. Any application-layer UPDATE or DELETE against these records is a production defect. The warehouse schema enforces this by granting only SELECT access to application service accounts. The Compliance Governance Pathway is the only lawful mutation path, operating through a separate compliance-pathway service account.

---

### CONC-INVARIANT-2 — Reproducibility Under Replay

A report generated from a given FINALIZED snapshot MUST produce identical output when replayed (same template version, same snapshot data). The invariant holds because:

* AI narrative content is sourced from physical text copies in the snapshot row, not from live LLM calls
* Trend analytics use finalized snapshot data, not live SQL Server queries
* The Reproducibility Fingerprint is immutable; any replay that produces different output with the same fingerprint is a reproducibility defect

---

### CONC-INVARIANT-3 — AI Snapshot Isolation Under Concurrent Operations

AI insight lifecycle events occurring concurrently with a report regeneration reading snapshot AI text do not interfere. The regeneration reads the physically copied text from the snapshot row; it does not query ai_insights. No locking relationship exists between ai_insights operations and snapshot AI text reads.

---

### CONC-INVARIANT-4 — Config Version Consistency at Snapshot Finalization

A snapshot finalization run captures exactly one config version reference, atomically at content lock time. If the active config version changes mid-batch, different snapshots in the same batch run may legitimately reference different config versions (each capturing whichever version was ACTIVE at their individual content lock time). This is expected behavior, not a concurrency defect.

---

### CONC-INVARIANT-5 — Compliance Workflow Serialization Per Student

A student may be subject to at most one active compliance workflow at any time. Any second compliance intake request for a student with a non-terminal workflow is rejected at the intake gate. This prevents conflicting compliance governance states for the same student's records.

---

### CONC-INVARIANT-6 — Historical Regeneration Read-Only Source Guarantee

During a historical report regeneration, the source FINALIZED snapshot is read-only. If the source snapshot enters COMPLIANCE_HOLD during a regeneration, the regeneration reads the snapshot data as it exists and completes; the compliance action proceeds in parallel without interrupting the in-flight regeneration. The regeneration audit record notes the compliance hold status.

---

### CONC-INVARIANT-7 — Audit Trail Atomicity

If any lifecycle transition occurs but its associated audit log entry cannot be written, the transition is rolled back. A state transition without an audit log entry is not a committed transition. This applies to all six domains. The audit entry write and the state transition write are atomic; neither commits without the other.

---

---

## 22. FAILURE & RECOVERY MODEL (CROSS-DOMAIN)

---

### 22.1 Partial Snapshot Finalization

| Failure scenario | Classification | Recovery path | Operator required |
|---|---|---|---|
| Snapshot generation interrupted mid-assembly | Retryable | Resume from last checkpoint; idempotency prevents duplicate FINALIZED rows | No (if checkpoint intact) |
| Fingerprint component unavailable | Expected | Record `UNKNOWN_V0`; finalization continues | No |
| Concurrent FINALIZED row detected at write time | Non-retryable conflict | Second attempt exits cleanly; existing FINALIZED preserved | No |
| Audit log write fails at VALIDATING → FINALIZED | Rollback | Transition rolled back; retry from VALIDATING | No |

---

### 22.2 Duplicate Report Publication

| Failure scenario | Classification | Recovery path | Operator required |
|---|---|---|---|
| Concurrent publication attempt | Non-retryable conflict | Second attempt exits; first publication preserved | No |
| Publication write succeeds but confirmation fails | Idempotent retry | Re-attempt finds existing REPORT_PUBLISHED; no-op | No |
| Report published but post-publication audit fails | Incident | Emergency audit write | Yes — review |

---

### 22.3 Stale AI Generations

| Failure scenario | Classification | Recovery path | Operator required |
|---|---|---|---|
| AI_GENERATION_FAILED; prior AI_REVIEWED exists | Non-blocking | Prior AI_REVIEWED served with `stale: true` | If stale threshold exceeded |
| AI_GENERATION_FAILED; no prior AI_REVIEWED | Blocking | Null insight returned | Yes |
| Force-refresh fails after max retries | Retryable | Operator may re-request; prior AI_REVIEWED remains in AI_REFRESH_REQUESTED | Yes |

---

### 22.4 Orphaned Regeneration Jobs

| Failure scenario | Classification | Recovery path | Operator required |
|---|---|---|---|
| Snapshot in REGENERATION_REQUESTED; job never starts | Detectable | Scheduler alerts on stale REGENERATION_REQUESTED beyond SLA | Yes |
| Report in REPORT_REGENERATION_REQUESTED; job never starts | Detectable | Same | Yes |
| Job starts but never completes (hung) | Detectable | Scheduler detects SLA breach; transitions to GENERATION_FAILED | No (automated) |

---

### 22.5 Fingerprint Mismatch Scenarios

| Scenario | Classification | Action | Audit required |
|---|---|---|---|
| Fingerprint mismatch at historical regeneration | Expected | Mark regenerated report POTENTIALLY_DIVERGENT; log both fingerprints | Yes |
| Fingerprint component ARCHIVED at regeneration time | Expected | Note in fingerprint; proceed with warning | Yes |
| Fingerprint component UNKNOWN_V0 | Expected | Proceed; note in audit log | Yes |
| Source snapshot fingerprint physically inconsistent (data corruption) | Incident | Block regeneration; alert; escalate | Yes — immediate |

---

### 22.6 Failed Compliance Execution

| Failure scenario | Classification | Recovery path | Operator required |
|---|---|---|---|
| Pre-action audit write fails | Hard block | IN_EXECUTION blocked; treat as incident | Yes — immediate |
| Partial deletion (some tables succeed, some fail) | Retryable with re-review | IN_EXECUTION → UNDER_REVIEW; updated scope; re-review before retry | Yes |
| Post-action audit write fails | Incident | Emergency audit record; human review | Yes — immediate |
| Compliance authority unavailable | Non-deadline block | Workflow remains in APPROVED_FOR_ACTION; no timeout | Required to proceed |

---

### 22.7 Concurrent Config Activation Conflicts

| Failure scenario | Classification | Recovery path | Operator required |
|---|---|---|---|
| Two simultaneous activation attempts | Non-retryable conflict | Second rejected; first wins; both actors notified | Yes (awareness) |
| Activation write fails (DB error) | Retryable | Version remains APPROVED; retry activation | Yes |
| Activation succeeds; snapshot batch mid-run | Expected | In-flight snapshots retain their captured version; new snapshots use new version | No |

---

### 22.8 Failure Classification Summary

| Class | Definition | Examples |
|---|---|---|
| Retryable | Transient failure; retry may succeed; no harm from re-attempting | Snapshot assembly, report generation, AI LLM calls |
| Terminal | Cannot be retried; outcome is final | FINALIZED, REPORT_PUBLISHED, COMPLIANCE_DELETED |
| Non-retryable conflict | Two valid operations claimed same resource; one wins; loser does not retry | Duplicate FINALIZED snapshot, concurrent publication |
| Operator-review-required | Automated handling insufficient; human judgment needed | Partial compliance execution, stale AI threshold breach |
| Incident | System invariant violated; immediate escalation | Missing pre-action audit, post-action write failure, data corruption |

---

---

## 23. EXECUTION MODE INTERACTIONS

---

### 23.1 Snapshot Generation in SHADOW Mode

SHADOW mode affects outbound communication dispatch only. Snapshot governance, finalization, and immutability rules apply equally in both modes.

| Aspect | Behavior |
|---|---|
| Snapshot generation | Permitted in SHADOW mode; full lifecycle applies |
| Outbound communication triggered by snapshot | Blocked; execution_mode = SHADOW recorded in outreach history |
| Snapshot content | Fully populated; fingerprint computed; AI text physically copied |
| Audit logging | Full audit logging regardless of execution_mode |
| Idempotency | Full idempotency rules apply; SHADOW-mode snapshots count against (student_id, snapshot_month) uniqueness |

---

### 23.2 Compliance Workflows in SHADOW Mode

Compliance workflows are governance operations, not subject to execution_mode gating. A compliance deletion authorized by a compliance authority executes regardless of whether the platform's outreach execution mode is SHADOW or LIVE. Compliance audit records carry no execution_mode field; they are always authoritative.

---

### 23.3 AI Refresh in Experimental Context

AI generation may be run against non-production prompt versions in a sandboxed context without creating AI_REVIEWED records in the operational store:

* The generation result is stored in a separate experimental audit table, not in ai_insights
* No AI_REVIEWED state is reached in the operational lifecycle
* Snapshot finalization is NOT permitted to use experimental AI output
* Experimental runs do not count against the in-flight deduplication check (Section 17.1)

---

### 23.4 Auditability by Execution Mode

| Operation | SHADOW mode audit | LIVE mode audit |
|---|---|---|
| Outreach trigger | execution_mode = SHADOW; simulated_status = NOT_SENT | execution_mode = LIVE; GHL response recorded |
| Snapshot generation | Full audit logging; indistinguishable from LIVE | Same |
| Report publication | Full audit logging | Same |
| Compliance action | Not mode-gated; full audit always | Same |
| Config version activation | Not mode-gated | Same |

---

---

## 24. ACCEPTANCE CRITERIA (NEW DOMAINS)

---

### Snapshot Domain

**Given** a monthly batch runs twice for the same student-month
**When** the second finalization attempt runs
**Then** the second attempt is rejected; the first FINALIZED snapshot is preserved; a duplicate rejection entry is written to the audit log

**Given** two workers concurrently attempt to finalize the same snapshot
**When** both writes are processed
**Then** exactly one FINALIZED record exists; the losing write exits cleanly; the conflict is logged with both correlation_ids

**Given** snapshot content changes during the VALIDATING phase
**When** the VALIDATING → FINALIZED transition commits
**Then** the fingerprint reflects the content state at the DRAFT → VALIDATING lock, not the modified state

---

### Report Domain

**Given** a report is published and a historical regeneration is requested
**When** the regeneration completes
**Then** a NEW report version record exists; the REPORT_PUBLISHED record is unmodified; both records are queryable with distinct lineage_version values

**Given** two operators simultaneously attempt to publish the same report
**When** both publication writes are processed
**Then** exactly one REPORT_PUBLISHED record exists; the duplicate attempt is logged as a no-op conflict; neither attempt produces an error surface to the operator beyond "already published"

---

### AI Insight Domain

**Given** an AI insight generation is in flight for a (student_id, insight_type, date_period) tuple
**When** a second generation request for the same tuple arrives
**Then** the second request is rejected; the in-flight generation completes normally; exactly one record exists in (AI_PENDING, AI_GENERATING, AI_REVIEW_PENDING) for the tuple

**Given** force-refresh is requested on an AI_REVIEWED insight and the new generation fails after max retries
**When** the insight endpoint is queried
**Then** the prior AI_REVIEWED generation (now in AI_REFRESH_REQUESTED state) is served with `stale: true`; the AI_GENERATION_FAILED record is not surfaced directly

---

### Config Version Domain

**Given** two administrators simultaneously attempt to activate two different APPROVED versions
**When** both activation writes are processed
**Then** exactly one version is ACTIVE; the other remains APPROVED; both actors are notified; the atomic invariant (never zero, never two ACTIVE) holds throughout

**Given** the active config version changes during a monthly batch run
**When** the batch completes
**Then** snapshots that locked content before the activation carry the prior version in their fingerprint; snapshots that locked after carry the new version; no snapshot carries both or neither

---

### Compliance Domain

**Given** a compliance deletion is APPROVED_FOR_ACTION and the pre-action audit write fails
**When** the IN_EXECUTION transition is attempted
**Then** the transition is blocked; the workflow remains in APPROVED_FOR_ACTION; an incident alert is raised; no records are deleted

**Given** a compliance deletion partially executes (3 of 5 tables succeed, 2 fail)
**When** the partial failure is detected
**Then** the workflow transitions IN_EXECUTION → UNDER_REVIEW; the partial execution is documented in compliance_audit with per-table completion status; the 3 completed tables are excluded from the re-review scope

---

---

## 25. DOWNSTREAM IMPLICATIONS

---

### 25.1 Data Model Implications (spec/08_data_model.md)

| Requirement | Implication |
|---|---|
| Snapshot idempotency key (student_id, snapshot_month) | Unique constraint on warehouse.student_snapshots (student_id, snapshot_month) scoped to FINALIZED records |
| One in-flight AI per (student_id, insight_type, date_period) | Partial unique index on ai_insights for in-flight states (AI_PENDING, AI_GENERATING, AI_REVIEW_PENDING) |
| Config version atomic swap | Transaction isolation required for APPROVED → ACTIVE write + ACTIVE → SUPERSEDED write in one atomic operation |
| Compliance one-active-per-student constraint | Application-enforced check at COMPLIANCE_REQUEST_RECEIVED intake |
| Audit entry atomic with transition | Transaction scope must include both the state column update and the log insert |
| Report publication dedup | Unique constraint on warehouse.monthly_reports (cohort_id, report_month, template_version, lineage_version) |

---

### 25.2 API Implications (spec/07_api_contracts.md)

| Requirement | Implication |
|---|---|
| Snapshot finalization idempotency | POST /snapshots/finalize returns existing FINALIZED record on duplicate key |
| Report publication idempotency | POST /reports/publish returns existing REPORT_PUBLISHED record on duplicate |
| AI force-refresh serialization | POST /ai-insights/refresh must not be called concurrently for the same tuple |
| Config version activation | POST /config-versions/{id}/activate returns whether this call activated or found already-active |
| Compliance intake idempotency | POST /compliance/request returns existing workflow_id if non-terminal workflow exists for student |

---

### 25.3 Warehouse Schema Implications (alembic/versions/0002_warehouse_schema.py)

| Requirement | Implication |
|---|---|
| FINALIZED snapshots append-only | warehouse schema: SELECT-only for application service accounts |
| Published reports append-only | Same access restriction |
| Compliance audit append-only | compliance_audit schema: restricted-write compliance-pathway service account only |
| Lifecycle log entries | Separate append-only log tables per domain |
| Report lineage_version tracking | lineage_version column on monthly_reports table; included in unique constraint |

---

### 25.4 Orchestration Implications

| Requirement | Implication |
|---|---|
| Snapshot batch idempotency | Batch runner must checkpoint progress per student; resumable from last successful checkpoint |
| Report generation SLA (60s) | Async job must emit progress events; scheduler detects and transitions hung jobs to GENERATION_FAILED |
| AI retry with backoff | Exponential backoff; max 2 retries (default); exceeded → AI_GENERATION_FAILED |
| Config version activation serialization | Activation must be a single-writer operation; distributed schedulers must coordinate |
| Compliance pre-action gate | Pre-action audit check must be atomic with the IN_EXECUTION transition; not a separate pre-check step |

---

---

## 26. UPDATED REFERENCES

---

Depends on:

* spec/03_state_transition_rules.md — Domains 1–6; Sections 14–45; Cross-Domain Invariants; Event Attribution Standard
* spec/01_requirements.md — Sections 3.15–3.19, 4.7, 4.8, 9.1–9.4, 11.1, 12.8, 13 (FAD-1 through FAD-6), 14 (readiness assessment)
* spec/07_api_contracts.md — API idempotency contract requirements (downstream implications)
* spec/08_data_model.md — Entity definitions and constraint requirements derived from this file
* runtime/system_loop.md (legacy reference — outreach domain)
* runtime/scheduler_design.md (legacy reference — outreach domain)
* failure/failure_playbook.md (legacy reference)
* meta/project_classification.md (legacy reference)

---

## END OF FILE
