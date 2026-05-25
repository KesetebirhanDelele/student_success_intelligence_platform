# spec/03_state_transition_rules.md

---

## LAYER 2 — SPECIFICATIONS (STATE TRANSITION RULES)

---

## 1. PURPOSE

This file defines the complete state-transition model for all lifecycle domains in the Student Operational Intelligence Platform (SSIP). It covers:

* All **valid and invalid state transitions** across all lifecycle domains
* Enforcement rules at system and application level
* Guardrails to prevent state corruption
* Cross-domain invariants and governance boundaries

The goal is to ensure:

* Deterministic lifecycle progression in every domain
* No invalid or out-of-order transitions
* System integrity across retries, failures, and manual actions
* Governance boundaries (FINALIZED snapshots, REPORT_PUBLISHED reports) are inviolable
* Compliance-governed mutations are the only lawful path to modify immutable records

### Lifecycle Domains Covered

| Domain | Description | Governance Boundary |
|---|---|---|
| **Outreach** (Domain 1) | Student outreach lifecycle from eligibility to closure | CLOSED is terminal |
| **Snapshot** (Domain 2) | Monthly student snapshot from generation through finalization and compliance deletion | FINALIZED is irreversible |
| **Monthly Report** (Domain 3) | Enterprise cohort report from generation through publication | REPORT_PUBLISHED is immutable |
| **AI Insight** (Domain 4) | AI-generated student insight from generation through archival | Attribution metadata is immutable after generation |
| **Config Version** (Domain 5) | Configuration Version Registry lifecycle | Exactly one version ACTIVE at all times; rollback is forbidden |
| **Compliance Governance** (Domain 6) | Compliance deletion and anonymization workflow | Pre-action audit entry is a hard gate before execution |

---

## 2. SOURCE OF TRUTH

---

This file is the **authoritative source** for:

> What state transitions are allowed

---

### Relationship to Other Files

| File                        | Role                 |
| --------------------------- | -------------------- |
| state/system_state_model.md | Defines outreach states (legacy reference) |
| state/outreach_lifecycle.md | Explains outreach lifecycle (legacy reference) |
| spec/01_requirements.md     | FADs and functional requirements governing all domains |
| spec/08_data_model.md       | Entity definitions referenced by this file |
| spec/04_idempotency_concurrency.md | Concurrency and idempotency rules that intersect with state transitions |
| ✅ THIS FILE                 | Enforces transitions across all domains |

---

---

## 3. STATE ENUM (REFERENCE)

---

```plaintext
ELIGIBLE
QUEUED
CONTACTED
NO_RESPONSE
RETRY
RESPONDED
ANALYZED
INTERVENTION_REQUIRED
RESOLVED
CLOSED
```

> **Note:** `MEETING_SCHEDULED` was removed from the implemented state machine. `RETRY` was added as a distinct state between `NO_RESPONSE` and re-contact, replacing the previous `NO_RESPONSE → QUEUED` loop. `RESOLVED` is now reachable directly from `RESPONDED`, `ANALYZED`, and `INTERVENTION_REQUIRED`.

---

---

## 4. VALID TRANSITIONS

---

### Core Transition Map

```plaintext
ELIGIBLE → QUEUED
ELIGIBLE → CLOSED

QUEUED → CONTACTED
QUEUED → CLOSED

CONTACTED → NO_RESPONSE
CONTACTED → RESPONDED
CONTACTED → CLOSED
CONTACTED → INTERVENTION_REQUIRED  ← operator ESCALATE

NO_RESPONSE → RETRY
NO_RESPONSE → CLOSED
NO_RESPONSE → INTERVENTION_REQUIRED  ← operator ESCALATE

RETRY → CONTACTED
RETRY → CLOSED
RETRY → INTERVENTION_REQUIRED  ← operator ESCALATE

RESPONDED → ANALYZED
RESPONDED → RESOLVED
RESPONDED → CLOSED
RESPONDED → INTERVENTION_REQUIRED  ← operator ESCALATE

ANALYZED → INTERVENTION_REQUIRED
ANALYZED → RESOLVED
ANALYZED → CLOSED

INTERVENTION_REQUIRED → RESOLVED
INTERVENTION_REQUIRED → CLOSED

RESOLVED → CLOSED

CLOSED → (none — terminal)
```

> Transitions marked `← operator ESCALATE` are triggered only by the manual `ESCALATE` action via `POST /actions/manual`. They are not reachable by the automated scheduler.

---

---

## 5. INVALID TRANSITIONS (EXPLICIT)

---

The following transitions are **strictly forbidden**:

---

### 5.1 Terminal State Violations

```plaintext
CLOSED → ANY_STATE ❌
```

---

### 5.2 Backward Transitions

```plaintext
CONTACTED → QUEUED ❌
RESPONDED → CONTACTED ❌
ANALYZED → RESPONDED ❌
RETRY → NO_RESPONSE ❌
```

---

### 5.3 Skip-Level Transitions

```plaintext
ELIGIBLE → CONTACTED ❌
QUEUED → RESPONDED ❌
CONTACTED → ANALYZED ❌  (must pass RESPONDED)
NO_RESPONSE → CONTACTED ❌  (must pass RETRY)
```

---

### 5.4 Retry Violations

```plaintext
RESPONDED → NO_RESPONSE ❌
ANALYZED → NO_RESPONSE ❌
ANALYZED → RETRY ❌
```

---

### 5.5 Scheduler Cannot ESCALATE

```plaintext
(scheduler) → INTERVENTION_REQUIRED from CONTACTED ❌
(scheduler) → INTERVENTION_REQUIRED from NO_RESPONSE ❌
(scheduler) → INTERVENTION_REQUIRED from RETRY ❌
(scheduler) → INTERVENTION_REQUIRED from RESPONDED ❌
```

> The automated scheduler may only reach `INTERVENTION_REQUIRED` from `ANALYZED`. All other `INTERVENTION_REQUIRED` transitions require a human operator via the `ESCALATE` manual action.

---

---

## 6. CONDITIONAL TRANSITIONS

---

### 6.1 Retry Loop

---

Allowed ONLY IF:

* current_attempt < MAX_ATTEMPTS
* retry_policy allows

```plaintext
NO_RESPONSE → RETRY
```

> The RETRY state is a holding state. The scheduler then moves the student from RETRY → CONTACTED on the next execution cycle. RETRY is distinct from QUEUED — it carries context that a prior contact was attempted.

---

---

### 6.2 Forced Closure

---

Allowed ONLY via manual action (`CLOSE_CASE`):

```plaintext
ANY_NON_CLOSED_STATE → CLOSED
```

### Constraints

* Must include notes (optional but recommended)
* Must write OutreachHistory record with action = `CASE_CLOSED`
* Must write StateTransitionLog record

---

### 6.3 Manual ESCALATE

---

Allowed via manual action (`ESCALATE`):

```plaintext
CONTACTED → INTERVENTION_REQUIRED
NO_RESPONSE → INTERVENTION_REQUIRED
RETRY → INTERVENTION_REQUIRED
RESPONDED → INTERVENTION_REQUIRED
```

### Constraints

* Not allowed from CLOSED, ELIGIBLE, QUEUED, ANALYZED, INTERVENTION_REQUIRED, RESOLVED
* Must write OutreachHistory and StateTransitionLog
* MAX_ATTEMPTS guard does NOT apply to ESCALATE (only to FORCE_RETRY)

---

---

### 6.3 Direct Resolution (No Meeting)

---

Allowed when:

* Issue resolved without intervention

```plaintext
ANALYZED → RESOLVED
```

---

---

## 7. STATE TRANSITION VALIDATION RULES

---

### RULE 1 — MUST BE IN VALID MAP

```plaintext
IF transition NOT in VALID_TRANSITIONS → REJECT
```

---

---

### RULE 2 — TERMINAL STATE LOCK

```plaintext
IF current_state = CLOSED → BLOCK ALL TRANSITIONS
```

---

---

### RULE 3 — ATTEMPT CONSISTENCY

* contact_attempt must increment ONLY on:

```plaintext
QUEUED → CONTACTED
```

---

---

### RULE 4 — SINGLE TRANSITION PER EVENT

* One event = one state change
* No chained transitions in single operation

---

---

### RULE 5 — TIMESTAMP REQUIRED

Every transition MUST include:

```plaintext
timestamp  
previous_state  
new_state  
```

---

---

## 8. DATABASE ENFORCEMENT

---

### Recommended Constraints

---

#### Option A — Application Layer Enforcement (Required)

* Validate before update

---

---

#### Option B — DB Constraint (Optional Advanced)

```sql
CHECK (state IN (...))
```

---

---

#### Option C — Transition Log Table (Recommended)

```plaintext
StateTransitionLog
  - user_id
  - previous_state
  - new_state
  - timestamp
  - reason
```

---

---

## 9. FAILURE HANDLING

---

### Invalid Transition Attempt

---

**Behavior:**

1. Reject update
2. Log error
3. Preserve original state

---

---

### Missing State

---

**Behavior:**

* Default to safe fallback
* Log anomaly

---

---

## 10. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Minimal states
* Limited enforcement

---

---

### STANDARD

* Core transitions enforced
* Basic validation

---

---

### PRODUCTION

* Full transition map enforced
* Strict validation
* Logging required
* No exceptions allowed

---

---

## 11. INVARIANTS

---

* CLOSED is terminal — no transitions out, ever
* No backward transitions allowed
* No skip-level transitions (unless explicitly listed in section 4)
* Automated retry enters RETRY state, not QUEUED
* RETRY can only be entered from NO_RESPONSE
* INTERVENTION_REQUIRED from active outreach states (CONTACTED, NO_RESPONSE, RETRY, RESPONDED) requires a human operator ESCALATE action
* ESCALATE is blocked on CLOSED, ELIGIBLE, QUEUED, ANALYZED, INTERVENTION_REQUIRED, RESOLVED
* FORCE_RETRY is blocked when current_attempt ≥ MAX_ATTEMPTS
* State must always be a valid enum value from section 3
* Every transition must produce a StateTransitionLog record

---

---

## 12. ACCEPTANCE CRITERIA

---

### Case 1 — Valid Transition

**Given** QUEUED → CONTACTED
**When** processed
**Then** transition allowed

---

---

### Case 2 — Invalid Transition

**Given** CLOSED → CONTACTED
**When** attempted
**Then** rejected

---

---

### Case 3 — Retry Transition

**Given** NO_RESPONSE
**And** retry allowed
**When** processed
**Then** QUEUED

---

---

### Case 4 — Skip-Level Transition

**Given** CONTACTED → ANALYZED
**When** attempted
**Then** rejected

---

---

## 13. REFERENCES

---

Depends on:

* state/system_state_model.md
* state/outreach_lifecycle.md
* runtime/system_loop.md
* directives/core_decision_engine.md
* meta/project_classification.md

---

---

---

## DOMAIN 1 — OUTREACH LIFECYCLE

> **Note:** Sections 3–13 above fully define the Outreach lifecycle domain. That content is preserved as-is. Sections 14 onward introduce the remaining five lifecycle domains.

---

---

## DOMAIN 2 — SNAPSHOT LIFECYCLE

---

This domain governs the lifecycle of monthly student snapshots from initial draft generation through finalization, historical regeneration, and compliance-governed deletion. Snapshots are the primary input to the Reporting Intelligence layer and the foundation for all historical reproducibility guarantees.

Reference: spec/01_requirements.md Sections 3.18, 4.7, 4.8, 6, 7, FAD-1, FAD-4, FAD-6.

---

## 14. SNAPSHOT STATE ENUM

---

```plaintext
DRAFT
VALIDATING
FINALIZED
REGENERATION_REQUESTED
REGENERATED
COMPLIANCE_HOLD
COMPLIANCE_DELETED
GENERATION_FAILED
DISCARDED
```

**State descriptions:**

| State | Description |
|---|---|
| `DRAFT` | Snapshot being assembled; mutable; may be replaced or discarded before finalization |
| `VALIDATING` | Validation pass in progress: data completeness checked, Reproducibility Fingerprint computed; content locked for validation |
| `FINALIZED` | **Irreversible governance boundary.** AI text physically copied; fingerprint immutably locked; immutability guarantee fully applies |
| `REGENERATION_REQUESTED` | Authorized operator has requested a historical report regeneration using this snapshot as the source |
| `REGENERATED` | At least one historical regeneration has been successfully executed from this snapshot's data; snapshot itself is unchanged |
| `COMPLIANCE_HOLD` | Snapshot is under active compliance review; no ordinary operations permitted until hold is resolved |
| `COMPLIANCE_DELETED` | Terminal. Student records removed (or anonymized) via the Compliance Governance Pathway; audit entry exists |
| `GENERATION_FAILED` | Snapshot generation or validation could not complete; operator intervention required for a new attempt |
| `DISCARDED` | Terminal. DRAFT snapshot discarded before finalization; includes compliance-driven discard of drafts |

> `REGENERATED` does not mean the snapshot was changed. It records that this snapshot has been used as the source for at least one historical regeneration.

---

## 15. SNAPSHOT VALID TRANSITIONS

---

```plaintext
DRAFT → VALIDATING
DRAFT → GENERATION_FAILED
DRAFT → DISCARDED              ← operator discard; or compliance deletion request received while still DRAFT

VALIDATING → FINALIZED         ← all preconditions met; fingerprint locked (see Section 17)
VALIDATING → DRAFT             ← validation failure; operator reviews and retries
VALIDATING → GENERATION_FAILED ← unrecoverable validation error

FINALIZED → REGENERATION_REQUESTED   ← operator requests historical report regeneration
FINALIZED → COMPLIANCE_HOLD          ← compliance deletion or anonymization request received

REGENERATION_REQUESTED → REGENERATED        ← regeneration succeeded; audit log written
REGENERATION_REQUESTED → GENERATION_FAILED  ← regeneration process failed

REGENERATED → REGENERATION_REQUESTED  ← another regeneration requested from this snapshot
REGENERATED → COMPLIANCE_HOLD         ← compliance request received

COMPLIANCE_HOLD → COMPLIANCE_DELETED  ← Compliance Governance Pathway completed (action executed)
COMPLIANCE_HOLD → FINALIZED           ← compliance hold lifted without action; snapshot reverts to FINALIZED
COMPLIANCE_HOLD → REGENERATED         ← compliance hold lifted; snapshot was in REGENERATED before hold

GENERATION_FAILED → DRAFT             ← operator initiates a new DRAFT attempt

COMPLIANCE_DELETED → (none — terminal)
DISCARDED → (none — terminal)
```

---

## 16. SNAPSHOT FORBIDDEN TRANSITIONS

---

### 16.1 Terminal State Violations

```plaintext
COMPLIANCE_DELETED → ANY  ❌
DISCARDED → ANY           ❌
```

---

### 16.2 Immutability Boundary Violations

```plaintext
FINALIZED → DRAFT          ❌  — FINALIZED is an irreversible governance boundary; no reversion
FINALIZED → DISCARDED      ❌  — cannot discard a finalized snapshot directly; must use COMPLIANCE_HOLD → COMPLIANCE_DELETED
FINALIZED → VALIDATING     ❌  — cannot re-validate a finalized snapshot
FINALIZED → GENERATION_FAILED  ❌  — nonsensical; FINALIZED means generation succeeded
REGENERATED → DRAFT        ❌  — cannot revert a snapshot that has been used for regeneration
REGENERATED → DISCARDED    ❌  — must use COMPLIANCE_HOLD → COMPLIANCE_DELETED
```

---

### 16.3 Authorization Bypass Violations

```plaintext
DRAFT → COMPLIANCE_HOLD    ❌  — compliance hold requires a FINALIZED or REGENERATED snapshot; DRAFTs are discarded directly
FINALIZED → COMPLIANCE_DELETED without COMPLIANCE_HOLD  ❌  — compliance hold is mandatory before deletion
```

---

### 16.4 Skip-Level Violations

```plaintext
DRAFT → FINALIZED          ❌  — must pass through VALIDATING
DRAFT → COMPLIANCE_HOLD    ❌  — (see 16.3)
VALIDATING → COMPLIANCE_HOLD ❌  — must reach FINALIZED first
```

---

## 17. SNAPSHOT CONDITIONAL TRANSITIONS AND FREEZING POINTS

---

### 17.1 Finalization Preconditions

The transition `VALIDATING → FINALIZED` is allowed **ONLY IF** all of the following are true:

* All required snapshot content fields are populated or explicitly null (no fields in an indeterminate state)
* All five Snapshot Reproducibility Fingerprint components are present (unknown components recorded as `UNKNOWN_V0`, which is permitted and does not block finalization)
* No concurrent FINALIZED snapshot exists for the same `(student_id, snapshot_month)` pair

---

### 17.2 Content and Metadata Freezing Points

| What freezes | When it freezes | Notes |
|---|---|---|
| Snapshot content fields (academic, financial, placement summaries, etc.) | At `DRAFT → VALIDATING` | Content is locked for the validation pass; not modifiable while VALIDATING |
| AI-generated text (risk summary, progress summary, monthly narrative) | At `VALIDATING → FINALIZED` | Physical text copies committed to snapshot row; irreversible (FAD-1) |
| Snapshot Reproducibility Fingerprint (all 5 components) | At `VALIDATING → FINALIZED` | Fingerprint is immutable after FINALIZED; no component may be changed (FAD-6) |
| Configuration Version Registry reference | At `VALIDATING → FINALIZED` | Active config version at finalization time is captured in fingerprint; future config changes do not affect this snapshot (FAD-3) |

---

### 17.3 Compliance Override Path for Finalized Snapshots

A FINALIZED or REGENERATED snapshot may only be deleted or anonymized via the following sequence:

1. Transition: `FINALIZED` (or `REGENERATED`) → `COMPLIANCE_HOLD`
2. Compliance authority reviews and authorizes the action
3. Scope definition completed; pre-action audit entry created in `compliance_audit` schema
4. Transition: `COMPLIANCE_HOLD` → `COMPLIANCE_DELETED`

Any deletion or anonymization of a FINALIZED snapshot that bypasses this sequence is a compliance defect.

---

### 17.4 Compliance-Driven Discard of DRAFT Snapshots

A DRAFT snapshot subject to a compliance deletion request is handled separately:

* Transition: `DRAFT → DISCARDED`
* A discard audit entry is created in the `compliance_audit` schema (student ID, discard timestamp, rationale)
* The full Compliance Governance Pathway is **not** required (no finalized records to govern)
* The student is treated as if no snapshot was taken for that month

---

### 17.5 Retry Semantics

| Failure scenario | Retry path |
|---|---|
| `GENERATION_FAILED` from draft assembly | `GENERATION_FAILED → DRAFT`; new draft; idempotency key prevents duplicate FINALIZED rows on retry |
| `VALIDATING → DRAFT` (validation failure) | Operator reviews content; retry allowed from `DRAFT`; same idempotency key applies |
| `REGENERATION_REQUESTED → GENERATION_FAILED` | Regeneration failure does NOT affect the snapshot state itself; operator retries the regeneration request; snapshot remains in `REGENERATION_REQUESTED` until resolved |

---

## 18. SNAPSHOT INVARIANTS

---

* `FINALIZED` is irreversible — the only permitted outbound transitions are `REGENERATION_REQUESTED` and `COMPLIANCE_HOLD`
* Exactly one snapshot per `(student_id, snapshot_month)` may be in `FINALIZED` state; a second finalization attempt for the same pair is rejected
* Physical AI text copies are locked at `FINALIZED`; no subsequent AI insight operation (force-refresh, regeneration, archival, compliance deletion of `ai_insights` records) modifies them
* The Reproducibility Fingerprint is immutable after `FINALIZED`; no component may be changed post-finalization
* DRAFT snapshots are mutable and may be freely discarded; the immutability guarantee applies **only** to `FINALIZED` snapshots
* `DISCARDED` and `COMPLIANCE_DELETED` are terminal — no transitions out; records retained for audit
* Every snapshot lifecycle transition MUST produce a `snapshot_lifecycle_log` entry with: snapshot_id, student_id, snapshot_month, from_state, to_state, actor_identity, attribution_timestamp, correlation_id

---

---

## DOMAIN 3 — MONTHLY REPORT LIFECYCLE

---

This domain governs the lifecycle of enterprise monthly cohort reports from generation through publication, archival, and historical regeneration. Reports are generated exclusively from finalized snapshot data. A published report is immutable; new versions replace rather than overwrite.

Reference: spec/01_requirements.md Sections 3.18, 3.19, 4.7, 4.8, FAD-2, FAD-6.

---

## 19. REPORT STATE ENUM

---

```plaintext
REPORT_PENDING
REPORT_GENERATING
REPORT_GENERATED
REPORT_REVIEW_PENDING
REPORT_APPROVED
REPORT_PUBLISHED
REPORT_ARCHIVED
REPORT_REGENERATION_REQUESTED
REPORT_GENERATION_FAILED
```

**State descriptions:**

| State | Description |
|---|---|
| `REPORT_PENDING` | Generation has been scheduled but not yet started |
| `REPORT_GENERATING` | Async generation in progress; may persist up to the 60-second SLA |
| `REPORT_GENERATED` | Content assembled from snapshot data; pre-publication review pending |
| `REPORT_REVIEW_PENDING` | Report awaiting operator approval before publication (PRODUCTION scope only) |
| `REPORT_APPROVED` | Operator approved for publication; pending final publication step |
| `REPORT_PUBLISHED` | **Publication boundary.** Report is finalized and published; immutable after this point |
| `REPORT_ARCHIVED` | Terminal. Published report superseded or moved to cold storage |
| `REPORT_REGENERATION_REQUESTED` | Authorized operator requested a historical regeneration producing a new version |
| `REPORT_GENERATION_FAILED` | Generation or regeneration failed; operator intervention required |

---

## 20. REPORT VALID TRANSITIONS

---

```plaintext
REPORT_PENDING → REPORT_GENERATING
REPORT_PENDING → REPORT_GENERATION_FAILED

REPORT_GENERATING → REPORT_GENERATED
REPORT_GENERATING → REPORT_GENERATION_FAILED

REPORT_GENERATED → REPORT_REVIEW_PENDING  ← operator review required (PRODUCTION scope)
REPORT_GENERATED → REPORT_APPROVED        ← auto-approve when review not configured (MVP/STANDARD)

REPORT_REVIEW_PENDING → REPORT_APPROVED
REPORT_REVIEW_PENDING → REPORT_GENERATION_FAILED  ← operator rejects; new generation required

REPORT_APPROVED → REPORT_PUBLISHED

REPORT_PUBLISHED → REPORT_ARCHIVED
REPORT_PUBLISHED → REPORT_REGENERATION_REQUESTED  ← operator requests historical re-run as new version

REPORT_REGENERATION_REQUESTED → REPORT_GENERATED  ← regeneration succeeded; enters review pipeline
REPORT_REGENERATION_REQUESTED → REPORT_GENERATION_FAILED

REPORT_GENERATION_FAILED → REPORT_PENDING  ← operator retries

REPORT_ARCHIVED → (none — terminal)
```

---

## 21. REPORT FORBIDDEN TRANSITIONS

---

### 21.1 Terminal State Violations

```plaintext
REPORT_ARCHIVED → ANY  ❌
```

---

### 21.2 Publication Boundary Violations

```plaintext
REPORT_PUBLISHED → REPORT_GENERATING    ❌  — cannot regenerate in-place; must use REPORT_REGENERATION_REQUESTED
REPORT_PUBLISHED → REPORT_GENERATED     ❌
REPORT_PUBLISHED → REPORT_REVIEW_PENDING ❌  — cannot un-publish
REPORT_PUBLISHED → REPORT_APPROVED      ❌  — cannot un-publish
REPORT_APPROVED → REPORT_REVIEW_PENDING ❌  — cannot un-approve
REPORT_APPROVED → REPORT_GENERATED      ❌
```

---

### 21.3 Skip-Level and Backward Violations

```plaintext
REPORT_PENDING → REPORT_GENERATED       ❌  — must pass through REPORT_GENERATING
REPORT_PENDING → REPORT_PUBLISHED       ❌
REPORT_GENERATING → REPORT_PUBLISHED    ❌  — must pass through review and approval
REPORT_GENERATED → REPORT_PUBLISHED     ❌  — must be approved before publication
REPORT_REVIEW_PENDING → REPORT_PUBLISHED ❌  — must pass through REPORT_APPROVED
```

---

## 22. REPORT CONDITIONAL TRANSITIONS AND CONSTRAINTS

---

### 22.1 Publication Boundary

The transition `REPORT_APPROVED → REPORT_PUBLISHED` is the publication boundary:

* Before this transition: report content is not yet committed; regeneration and operator review may still alter it
* After this transition: report is immutable; a new version MUST be created for any change; the published record is never modified

---

### 22.2 Asynchronous Generation Expectations

* The transition `REPORT_PENDING → REPORT_GENERATING` initiates an asynchronous job
* The caller receives a job reference (job ID or status endpoint); the state remains `REPORT_GENERATING` until completion or failure
* If the async job exceeds the 60-second generation SLA (Section 4.1), it transitions to `REPORT_GENERATION_FAILED`
* Long-running generation jobs emit progress events for observability; they do not silently hang

---

### 22.3 Historical Regeneration Behavior

When `REPORT_PUBLISHED → REPORT_REGENERATION_REQUESTED`:

* A **NEW** report version record is created; the published report is not modified
* The regeneration uses finalized snapshot data **only**; no live operational table queries
* AI narrative content is reproduced from the **physical text copies** in the snapshot; no new LLM call is made
* The source snapshot's Reproducibility Fingerprint is compared against the original report's recorded fingerprint
* If fingerprints differ, the regeneration audit log records both fingerprints and marks the new version as `POTENTIALLY_DIVERGENT`
* Regeneration audit log includes: requesting actor, timestamp, target month, source snapshot fingerprint, template version used, fingerprint comparison outcome

---

### 22.4 Operator Review Responsibilities (PRODUCTION Scope)

While in `REPORT_REVIEW_PENDING`:

* Operator must review report content for accuracy before approving publication
* Rejection (→ `REPORT_GENERATION_FAILED`) is appropriate when source data integrity is in question; a new generation is required
* A report remaining in `REPORT_REVIEW_PENDING` beyond the configured review SLA triggers an operator alert

---

## 23. REPORT INVARIANTS

---

* `REPORT_PUBLISHED` is immutable — no published report row is modified after reaching this state
* Historical regeneration produces a NEW version record — the source published report is never overwritten; both versions are queryable
* All report generations from the same `(snapshot, template_version)` pair produce deterministically identical output
* Every report generation event records the source snapshot's Reproducibility Fingerprint
* Operator review is mandatory before publication in PRODUCTION scope; MVP and STANDARD auto-approve
* `REPORT_ARCHIVED` is terminal — no transitions out; the record is retained for historical audit
* Every report lifecycle transition MUST produce a `report_lifecycle_log` entry with: report_id, report_month, from_state, to_state, actor_identity, attribution_timestamp, source_snapshot_id, source_fingerprint (if applicable)

---

---

## DOMAIN 4 — AI INSIGHT LIFECYCLE

---

This domain governs the lifecycle of AI-generated student insights. AI insights are advisory; they are never authoritative for eligibility determinations, state transitions, or financial decisions.

Reference: spec/01_requirements.md Sections 3.17, 9.1–9.4, FAD-1, FAD-6.

---

## 24. AI INSIGHT STATE ENUM

---

```plaintext
AI_PENDING
AI_GENERATING
AI_GENERATED
AI_REVIEW_PENDING
AI_REVIEWED
AI_ARCHIVED
AI_REFRESH_REQUESTED
AI_GENERATION_FAILED
```

**State descriptions:**

| State | Description |
|---|---|
| `AI_PENDING` | Insight generation request queued; not yet in flight |
| `AI_GENERATING` | LLM call in flight; output being generated and validated |
| `AI_GENERATED` | Output produced and schema-validated; ready for review or serving |
| `AI_REVIEW_PENDING` | Awaiting operator review before serving (PRODUCTION scope, when review is configured) |
| `AI_REVIEWED` | Current active insight for this `(student_id, insight_type, date_period)`; served to callers within TTL |
| `AI_ARCHIVED` | Terminal for this version. Prior insight version retained in history; not served as current |
| `AI_REFRESH_REQUESTED` | Operator triggered force-refresh on an AI_REVIEWED insight; new generation in progress |
| `AI_GENERATION_FAILED` | Generation failed after max retries; last valid AI_REVIEWED insight (if any) served with `stale: true` |

---

## 25. AI INSIGHT VALID TRANSITIONS

---

```plaintext
AI_PENDING → AI_GENERATING
AI_PENDING → AI_GENERATION_FAILED

AI_GENERATING → AI_GENERATED
AI_GENERATING → AI_GENERATION_FAILED

AI_GENERATED → AI_REVIEW_PENDING  ← operator review required (PRODUCTION scope, configured)
AI_GENERATED → AI_REVIEWED        ← direct when review not required (MVP/STANDARD scope)
AI_GENERATED → AI_ARCHIVED        ← superseded by a newer generation before review completes

AI_REVIEW_PENDING → AI_REVIEWED
AI_REVIEW_PENDING → AI_ARCHIVED   ← superseded by a newer generation during review window

AI_REVIEWED → AI_ARCHIVED          ← superseded by a newer AI_REVIEWED version for the same (student_id, insight_type, date_period)
AI_REVIEWED → AI_REFRESH_REQUESTED ← operator triggers explicit force-refresh

AI_REFRESH_REQUESTED → AI_ARCHIVED ← when the new force-refresh generation reaches AI_REVIEWED; this record is then archived

AI_GENERATION_FAILED → AI_PENDING  ← retry; allowed if below max_retries; otherwise remains AI_GENERATION_FAILED

AI_ARCHIVED → (none — terminal for this version; record retained in history)
```

---

## 26. AI INSIGHT FORBIDDEN TRANSITIONS

---

```plaintext
AI_ARCHIVED → AI_GENERATED    ❌  — archived insights cannot be un-archived
AI_ARCHIVED → AI_REVIEWED     ❌
AI_ARCHIVED → AI_PENDING      ❌
AI_GENERATION_FAILED → AI_GENERATED ❌  — must go through AI_PENDING → AI_GENERATING
AI_REVIEWED → AI_GENERATING   ❌  — force-refresh creates a NEW record; it does not mutate the existing AI_REVIEWED record directly
AI_REVIEWED → AI_GENERATED    ❌  — same reason
```

---

## 27. AI INSIGHT CONDITIONAL TRANSITIONS AND SEMANTICS

---

### 27.1 Force-Refresh Semantics

When an operator requests `force_refresh=true` on an `AI_REVIEWED` insight:

1. The existing `AI_REVIEWED` insight transitions to `AI_REFRESH_REQUESTED`
2. A **NEW** insight record is created in `AI_PENDING` state (new `version_number`, new `generated_at`)
3. The new record is generated independently: `AI_PENDING → AI_GENERATING → AI_GENERATED → AI_REVIEWED`
4. When the new record reaches `AI_REVIEWED`, the `AI_REFRESH_REQUESTED` record transitions to `AI_ARCHIVED`
5. The existing `AI_REVIEWED` record is **never modified**; it is versioned and retained

Force-refresh creates a new record with an incremented `version_number`. The idempotency tuple `(student_id, insight_type, date_period, prompt_version, version_number)` is unique per record.

---

### 27.2 Versioning Behavior

* Each generation creates a new record with a monotonically increasing `version_number` per `(student_id, insight_type)` tuple
* Prior versions transition to `AI_ARCHIVED` when superseded; they are never deleted by application code
* The most recently `AI_REVIEWED` record is the "current" insight served to callers; older versions are queryable for history and audit

---

### 27.3 Relationship to Finalized Snapshots

When a monthly snapshot finalization occurs (`VALIDATING → FINALIZED` in Domain 2):

* The AI-generated text in `AI_REVIEWED` state for the relevant insight types is **physically copied** into the snapshot row as point-in-time text
* This physical copy is independent of the `ai_insights` record
* Subsequent operations on `ai_insights` records — force-refresh, archival, compliance deletion — have **NO effect** on the snapshot's AI content
* The `ai_prompt_version` and `ai_model_version` fields in the Snapshot Reproducibility Fingerprint are populated from the `AI_REVIEWED` records at snapshot finalization time

---

### 27.4 Review Expectations (PRODUCTION Scope)

While in `AI_REVIEW_PENDING`:

* Operator reviews AI output for quality and appropriateness before it is served
* Rejection transitions the record to `AI_ARCHIVED`; a new generation must be requested via `AI_PENDING`
* Review gate applies to PRODUCTION scope only; MVP and STANDARD auto-transition `AI_GENERATED → AI_REVIEWED`

---

### 27.5 Attribution Guarantees

Every AI insight record carries immutable attribution metadata set at `AI_GENERATED` state and never modified:

| Attribute | Description |
|---|---|
| `model_used` | LLM model identifier (e.g., `claude-sonnet-4-6`) |
| `prompt_version` | Version of the prompt template used to generate this insight |
| `generated_at` | Timestamp of the generation |
| `input_metrics_hash` | Hash of the input student metrics (for reproducibility verification) |

---

## 28. AI INSIGHT INVARIANTS

---

* AI insights are advisory — `AI_REVIEWED` state grants no authority over student state, eligibility decisions, or financial records
* Finalized snapshot AI content is isolated from the `ai_insights` lifecycle — changes to `ai_insights` records never affect snapshot content
* Attribution metadata (`model_used`, `prompt_version`, `generated_at`) is immutable after `AI_GENERATED` state
* Exactly one insight record per `(student_id, insight_type, date_period)` may be in `AI_PENDING`, `AI_GENERATING`, or `AI_REVIEW_PENDING` at a time; concurrent in-flight generation for the same tuple is rejected
* `AI_ARCHIVED` is terminal for that version — record retained for history; never deleted by application code
* Every AI insight transition MUST produce an `ai_insight_lifecycle_log` entry with: insight_id, student_id, insight_type, from_state, to_state, actor_identity, attribution_timestamp, version_number

---

---

## DOMAIN 5 — CONFIGURATION VERSION GOVERNANCE

---

This domain governs the lifecycle of version records in the Configuration Version Registry. Exactly one version record is `ACTIVE` at any time. All other versions are historical. Configuration changes are prospective only; no version change retroactively affects historical snapshots, reports, or cohort classification records.

Reference: spec/01_requirements.md Section 12.8, FAD-3.

---

## 29. CONFIG VERSION STATE ENUM

---

```plaintext
PROPOSED
UNDER_REVIEW
APPROVED
ACTIVE
SUPERSEDED
ARCHIVED
```

**State descriptions:**

| State | Description |
|---|---|
| `PROPOSED` | Change documented and submitted; not yet under formal review |
| `UNDER_REVIEW` | Change under review by designated authority |
| `APPROVED` | Change approved for activation; not yet effective |
| `ACTIVE` | **Exactly one record may be ACTIVE at any time.** All new classification runs, snapshots, and AI generations use this version |
| `SUPERSEDED` | Prior version replaced by a newer ACTIVE version; fully queryable for historical fingerprint lookups and audit |
| `ARCHIVED` | Version has exceeded the active retention window; fully queryable but flagged as historical-only |

---

## 30. CONFIG VERSION VALID TRANSITIONS

---

```plaintext
PROPOSED → UNDER_REVIEW
PROPOSED → (withdrawn — proposal record discarded; no terminal state created)

UNDER_REVIEW → APPROVED
UNDER_REVIEW → PROPOSED       ← reviewer requests changes; back to proposal stage
UNDER_REVIEW → (withdrawn — same as PROPOSED)

APPROVED → ACTIVE             ← activation; effective_from timestamp set;
                              ← prior ACTIVE version simultaneously transitions to SUPERSEDED (atomic swap)

ACTIVE → SUPERSEDED           ← when a newer version is activated (only permitted outbound transition)

SUPERSEDED → ARCHIVED         ← after a defined retention threshold; record remains fully queryable
```

---

## 31. CONFIG VERSION FORBIDDEN TRANSITIONS

---

### 31.1 Rollback Violations (Explicit Prohibition)

```plaintext
SUPERSEDED → ACTIVE  ❌  — rollback to a prior version is explicitly forbidden
ARCHIVED → ACTIVE    ❌  — archived versions cannot be reactivated
ARCHIVED → SUPERSEDED ❌  — terminal in this direction
```

---

### 31.2 De-Activation Violations

```plaintext
ACTIVE → PROPOSED      ❌  — cannot de-activate without introducing a new replacement version
ACTIVE → UNDER_REVIEW  ❌  — same
ACTIVE → ARCHIVED      ❌  — must become SUPERSEDED first, then ARCHIVED through normal retention progression
ACTIVE → APPROVED      ❌  — nonsensical; APPROVED precedes ACTIVE
```

---

## 32. CONFIG VERSION CONDITIONAL TRANSITIONS AND CONSTRAINTS

---

### 32.1 Activation Boundary

The transition `APPROVED → ACTIVE` is the activation boundary:

* Before this transition: the proposed configuration change has NO effect on any classification run, snapshot generation, or AI insight generation
* After this transition: all subsequent runs use the new version; the prior ACTIVE becomes SUPERSEDED
* The `effective_from` timestamp is set atomically; there is no window where zero or two versions are simultaneously ACTIVE

**Atomic activation requirement:** The `ACTIVE → SUPERSEDED` (for the prior version) and `APPROVED → ACTIVE` (for the new version) MUST occur atomically. No classification run or snapshot generation may observe a state with zero or two ACTIVE versions.

---

### 32.2 Prospective-Only Behavior

Configuration version activation is strictly prospective (FAD-3):

* Historical snapshots retain their original `configuration_registry_version` fingerprint component
* Finalized reports retain their original version attribution
* Prior cohort classification records are not retroactively reprocessed
* The platform MUST NOT trigger reprocessing of any historical data when a new version is activated
* Any migration or backfill that reprocesses historical records under a new version requires explicit business owner sign-off and a compliance audit entry

---

### 32.3 Historical Preservation Guarantees

* `SUPERSEDED` and `ARCHIVED` version records are never deleted by application code
* Any snapshot fingerprint that references a version ID must be able to retrieve that version record, even if `ARCHIVED`
* If a version is unavailable at fingerprint lookup time, the fingerprint notes it as `ARCHIVED`; regeneration proceeds with a logged warning (per Section 7 edge case in spec/01_requirements.md)

---

### 32.4 Rollback Semantics

Rollback to a prior version is **explicitly forbidden**. If a configuration change is determined to be incorrect:

1. A new `PROPOSED` version record is created that reverts the values to the desired state
2. The new version goes through the full `PROPOSED → UNDER_REVIEW → APPROVED → ACTIVE` lifecycle
3. Historical snapshots generated under the incorrect version retain their attribution to that version; they are not retroactively corrected

---

## 33. CONFIG VERSION INVARIANTS

---

* Exactly one version record is `ACTIVE` at all times — no more, no less; the initial V1 seed record is the first ACTIVE
* `ACTIVE → SUPERSEDED` and `APPROVED → ACTIVE` occur atomically — no window with zero or two ACTIVE versions
* Version records are append-only; no version record is modified after being activated
* All configurable rule values in Sections 12.1–12.7 of spec/01_requirements.md are included in the `rule_set_snapshot` field of each version record (complete snapshot, not a diff)
* Every new version record references its prior version via `prior_version_id`; the chain is complete and linked back to V1
* `SUPERSEDED` and `ARCHIVED` records are permanently retained; they are never deleted by application code

---

---

## DOMAIN 6 — COMPLIANCE GOVERNANCE

---

This domain governs the lifecycle of compliance actions (deletion and anonymization) applied to finalized student records. Compliance actions are governance workflows, not ordinary operational mutations. They are gated by authorization, scope definition, and mandatory pre-action audit requirements.

Reference: spec/01_requirements.md Sections 4.7, 6, 7, FAD-4.

---

## 34. COMPLIANCE STATE ENUM

---

```plaintext
COMPLIANCE_REQUEST_RECEIVED
UNDER_REVIEW
APPROVED_FOR_ACTION
IN_EXECUTION
DELETED
ANONYMIZED
REJECTED
WITHDRAWN
```

**State descriptions:**

| State | Description |
|---|---|
| `COMPLIANCE_REQUEST_RECEIVED` | Compliance deletion or anonymization request received and logged; no action taken |
| `UNDER_REVIEW` | Request under review by designated compliance authority |
| `APPROVED_FOR_ACTION` | Action authorized; scope defined; pre-action audit entry MUST exist before IN_EXECUTION |
| `IN_EXECUTION` | Deletion or anonymization actively executing across all scoped tables |
| `DELETED` | Terminal. Scoped records removed; post-action audit entry complete |
| `ANONYMIZED` | Terminal. Scoped records anonymized; post-action audit entry complete |
| `REJECTED` | Terminal. Compliance action request denied by compliance authority |
| `WITHDRAWN` | Terminal. Request withdrawn by requester before or during review |

---

## 35. COMPLIANCE VALID TRANSITIONS

---

```plaintext
COMPLIANCE_REQUEST_RECEIVED → UNDER_REVIEW
COMPLIANCE_REQUEST_RECEIVED → REJECTED   ← immediate rejection (e.g., no legal standing)
COMPLIANCE_REQUEST_RECEIVED → WITHDRAWN  ← requester withdraws before review begins

UNDER_REVIEW → APPROVED_FOR_ACTION
UNDER_REVIEW → REJECTED
UNDER_REVIEW → COMPLIANCE_REQUEST_RECEIVED  ← reviewer requests additional information; back to intake
UNDER_REVIEW → WITHDRAWN                    ← requester withdraws during review

APPROVED_FOR_ACTION → IN_EXECUTION  ← GATED: pre-action audit entry MUST exist before this transition
                                    ← action_type, scope_manifest, authorized_by, affected_student_id all confirmed

IN_EXECUTION → DELETED     ← action_type = DELETE; all scoped records removed; post-action audit written
IN_EXECUTION → ANONYMIZED  ← action_type = ANONYMIZE; all scoped records anonymized; post-action audit written
IN_EXECUTION → UNDER_REVIEW  ← execution failure; partial execution logged; requires re-review before retry

DELETED → (none — terminal)
ANONYMIZED → (none — terminal)
REJECTED → (none — terminal)
WITHDRAWN → (none — terminal)
```

---

## 36. COMPLIANCE FORBIDDEN TRANSITIONS

---

### 36.1 Terminal State Violations

```plaintext
DELETED → ANY     ❌
ANONYMIZED → ANY  ❌
REJECTED → ANY    ❌
WITHDRAWN → ANY   ❌
```

---

### 36.2 Authorization Bypass Violations

```plaintext
UNDER_REVIEW → IN_EXECUTION              ❌  — must pass through APPROVED_FOR_ACTION
COMPLIANCE_REQUEST_RECEIVED → IN_EXECUTION ❌  — authorization is required; no shortcut
COMPLIANCE_REQUEST_RECEIVED → DELETED     ❌
APPROVED_FOR_ACTION → DELETED without IN_EXECUTION  ❌  — IN_EXECUTION tracking is required for partial failure recovery
REJECTED → APPROVED_FOR_ACTION           ❌  — must restart from COMPLIANCE_REQUEST_RECEIVED
```

---

## 37. COMPLIANCE CONDITIONAL TRANSITIONS AND CONSTRAINTS

---

### 37.1 Authorization Boundary (Hard Gate)

The transition `APPROVED_FOR_ACTION → IN_EXECUTION` is gated by ALL of the following preconditions. Every precondition MUST be confirmed before execution begins:

| Precondition | Description |
|---|---|
| Pre-action audit entry exists | A record in the `compliance_audit` schema with all required fields populated (see Section 4.7 of spec/01_requirements.md) |
| `authorized_by` recorded | Identity of the approving compliance authority is recorded in the audit entry |
| `scope_manifest` complete | Explicit enumeration of all affected tables and estimated record counts |
| `action_type` declared | Explicitly `DELETE` or `ANONYMIZE` — not ambiguous |
| `affected_student_id` confirmed | The student ID is validated against the scope manifest |

If any precondition is unmet, the transition is **blocked**. The workflow remains in `APPROVED_FOR_ACTION` until preconditions are satisfied.

---

### 37.2 Audit Requirements

Every compliance workflow state transition produces an audit entry in the `compliance_audit` schema:

| Transition | Audit entry type |
|---|---|
| `COMPLIANCE_REQUEST_RECEIVED → UNDER_REVIEW` | Request intake log |
| `UNDER_REVIEW → APPROVED_FOR_ACTION` | Authorization log (authorized_by, authorization_timestamp) |
| `APPROVED_FOR_ACTION → IN_EXECUTION` | Pre-action audit entry (required before execution) |
| `IN_EXECUTION → DELETED` or `IN_EXECUTION → ANONYMIZED` | Completion audit entry (affected_record_count per table) |
| `IN_EXECUTION → UNDER_REVIEW` | Partial execution failure log (which tables succeeded, which failed) |

Compliance audit records are append-only. No audit record is modified or deleted after creation. Audit records survive the operational deletions they document.

---

### 37.3 Relationship to Snapshot and Report Immutability

For FINALIZED snapshots subject to a compliance action:
* Domain 2 (Snapshot Lifecycle) runs in parallel: snapshot transitions `FINALIZED → COMPLIANCE_HOLD`
* Domain 6 (Compliance Governance) governs the authorization and execution workflow
* The snapshot may only reach `COMPLIANCE_DELETED` (Domain 2) **after** the compliance governance workflow reaches `DELETED` or `ANONYMIZED` (Domain 6)
* These are two views of the same governance event: Domain 2 tracks the snapshot's state; Domain 6 tracks the authorization workflow's state

---

### 37.4 Interaction with Historical Reporting

When a compliance action targets a student whose snapshot contributed to published aggregate reports:

* The published aggregate report statistics are **not** retroactively recalculated (per Section 7 edge case in spec/01_requirements.md)
* The published report record is annotated with a compliance-action flag indicating that a student's records were removed after original publication
* The report itself remains in `REPORT_PUBLISHED` state; it does not transition to `REPORT_GENERATION_FAILED`

---

## 38. COMPLIANCE INVARIANTS

---

* A compliance action MUST have a pre-action audit entry before `IN_EXECUTION` begins — this is a hard gate; no exception
* No application service account may write to the `compliance_audit` schema; only the compliance pathway service account has write access
* Compliance audit records are append-only — no audit record is ever modified or deleted after creation
* The `scope_manifest` is mandatory for any compliance action involving finalized snapshots or published reports
* Compliance actions do not retroactively modify aggregate statistics in published reports; reports are annotated instead
* All four terminal states (`DELETED`, `ANONYMIZED`, `REJECTED`, `WITHDRAWN`) have no outbound transitions
* A new `COMPLIANCE_REQUEST_RECEIVED` for the same student may only be initiated after a prior compliance workflow has reached a terminal state

---

---

## 39. EVENT ATTRIBUTION STANDARD

---

All event-driven domains in the platform share a common attribution standard. Every state transition event, regardless of domain, conceptually carries the following fields.

---

### 39.1 Attribution Fields

| Field | Type | Description | Required |
|---|---|---|---|
| `origin_source` | enum | Where the event originated | Always |
| `origin_authority` | enum | What grants the event authority for operational decisions | Always |
| `execution_mode` | enum | `SHADOW` or `LIVE` | Communication and outreach events |
| `attribution_timestamp` | datetime (timezone-aware) | When the event was created or attributed | Always |
| `actor_identity` | string | Who or what initiated the event | Always |
| `correlation_id` | uuid | Cross-domain trace identifier propagated through all downstream operations | Always |

---

### 39.2 Origin Source Values

| Value | Applicable Domains | Description |
|---|---|---|
| `scheduler` | All domains | Event triggered by the APScheduler automated scheduler |
| `operator` | Outreach, Snapshot, Report, AI, Compliance | Event triggered by an authenticated operator action |
| `mirrored_sql_server` | Access events | Event read from SQL Server on a sync cycle |
| `platform_manual` | Access events | Event created by operator action within the platform |
| `platform_system` | Access events | Event created by platform automated logic |
| `compliance_pathway` | Compliance | Event created within the Compliance Governance workflow |
| `ghl` | Communication events | Event originating from GHL (GoHighLevel) API |
| `ai_subsystem` | AI events | Event created by the AI/LLM subsystem |

---

### 39.3 Origin Authority Values

| Value | Description |
|---|---|
| `sql_server_authoritative` | Event reflects SQL Server state; authoritative for eligibility and access status decisions |
| `platform_supplementary` | Event is platform-originated; supplementary context only; does not override SQL Server state |
| `operator_authorized` | Event is authorized by an authenticated operator; carries operator identity and timestamp |
| `compliance_authorized` | Event is authorized by the Compliance Governance Pathway; carries compliance authorization record reference |
| `system_automated` | Event is automated platform logic; advisory; not authoritative for eligibility decisions |

---

### 39.4 Domain-Specific Attribution Requirements

| Domain | Required attribution fields | Notes |
|---|---|---|
| Outreach lifecycle transitions | `origin_source`, `execution_mode`, `attribution_timestamp`, `actor_identity` | `execution_mode = SHADOW` blocks real outbound communication |
| Access events | `origin_source`, `origin_authority`, `attribution_timestamp` | `mirrored_sql_server` events carry `origin_authority = sql_server_authoritative`; platform events carry `platform_supplementary` |
| Snapshot lifecycle transitions | `origin_source`, `attribution_timestamp`, `actor_identity`, `correlation_id` | All transitions logged |
| AI insight events | `origin_source`, `attribution_timestamp`, `model_used`, `prompt_version` | Model and prompt version are part of attribution; immutable after `AI_GENERATED` |
| Report lifecycle events | `origin_source`, `attribution_timestamp`, `actor_identity`, `source_snapshot_fingerprint` | Fingerprint recorded for all report generation and regeneration events |
| Compliance governance events | `origin_source = compliance_pathway`, `origin_authority = compliance_authorized`, `authorized_by`, `attribution_timestamp` | Pre-action and post-action audit entries both required |
| Config version transitions | `operator`, `attribution_timestamp`, `actor_identity` | Activation identity recorded; prior version ID linked |

---

---

## 40. CROSS-DOMAIN INVARIANTS

---

These invariants are platform-wide. They apply across all domains and supersede any domain-specific rule that might otherwise conflict.

---

### INVARIANT-1 — Append-Only Finalized Reporting

No `FINALIZED` snapshot row and no `REPORT_PUBLISHED` report row may be updated or deleted by any application code path. The `warehouse` schema exposes only `SELECT` access to application service accounts. Any application-layer `UPDATE` or `DELETE` against a finalized snapshot or published report is a **production defect**.

The Compliance Governance Pathway is the **only** lawful mutation path for records in these states. It requires the full precondition chain: authorization, scope definition, and pre-action audit entry.

---

### INVARIANT-2 — Reproducibility Guarantee

A report generated from month M's `FINALIZED` snapshot data MUST produce identical output regardless of when it is generated or who generates it, given the same report template version. This requires:

* AI narrative content sourced from physical text copies in the snapshot (not from live `ai_insights` records)
* Trend analytics sourced exclusively from finalized snapshot data (not from live SQL Server mirror data)
* The Snapshot Reproducibility Fingerprint captured immutably at finalization and logged at every regeneration

---

### INVARIANT-3 — AI Snapshot Isolation

AI-generated text captured in a `FINALIZED` snapshot is immutable and isolated from the `ai_insights` record lifecycle. The following operations MUST NOT affect finalized snapshot AI content:

* Force-refresh of an `ai_insights` record
* Regeneration of an `ai_insights` record
* Archival of an `ai_insights` record
* Compliance deletion or anonymization of an `ai_insights` record
* LLM provider change

---

### INVARIANT-4 — Historical Auditability

Every state transition in every domain MUST produce an audit log entry containing: domain, entity ID, `from_state`, `to_state`, `actor_identity`, `attribution_timestamp`, `correlation_id`. No state transition is silent. A system that cannot reconstruct the complete transition history for any entity from its audit log is non-compliant with this invariant.

---

### INVARIANT-5 — Source Attribution Consistency

Every event in every domain carries `origin_source` and `attribution_timestamp`. No event is recorded without a declared origin. Events with `origin_source = mirrored_sql_server` and `origin_authority = sql_server_authoritative` govern operational eligibility decisions. Events with any other origin are supplementary unless explicitly governed (e.g., `compliance_pathway` events govern compliance execution).

---

### INVARIANT-6 — SQL Server Authority Boundaries

SQL Server-mirrored state is the authoritative source for a student's current access status, enrollment status, and academic metrics for all eligibility decisions, outreach gating, and operational alerts. Platform-originated events in these domains are supplementary. The platform MUST NOT allow platform-originated events to override SQL Server-mirrored state for operational eligibility decisions unless platform-owned access control is explicitly introduced as a separately approved architectural decision (FAD-5).

---

### INVARIANT-7 — Compliance Override Restriction

No code path other than the Compliance Governance Pathway may modify a `FINALIZED` snapshot or `REPORT_PUBLISHED` report. The Compliance Governance Pathway requires: authorization from a designated compliance authority, explicit scope definition, pre-action audit entry in the `compliance_audit` schema before execution, and post-action audit entry after execution. Any bypass of this pathway is a **compliance defect**, not a feature.

---

---

## 41. FAILURE & RECOVERY MODELING

---

### 41.1 Snapshot Domain Failures

| Failure scenario | Retryable | Recovery path | Operator intervention |
|---|---|---|---|
| Partial snapshot generation (some fields assembled, not all) | Yes | `GENERATION_FAILED → DRAFT`; operator reviews data; retry from new DRAFT | Required if failure is data-quality vs. transient |
| Fingerprint component unknown at finalization | Expected | Record as `UNKNOWN_V0`; finalization proceeds without blocking | None required; audit record sufficient |
| Fingerprint mismatch at historical regeneration | Not a failure | Regeneration completes; mismatch logged; report marked `POTENTIALLY_DIVERGENT` | Operator notified; not blocking |
| Stale config version reference (ARCHIVED) | Not a failure | Fingerprint notes version as `ARCHIVED`; warning logged; regeneration proceeds | Audit concern only |
| Concurrent finalization for same `(student_id, snapshot_month)` | Not retryable | Second finalization rejected by idempotency check; exits cleanly | None required |
| Snapshot job interrupted mid-run | Yes | Job resumes from last successful student checkpoint; idempotency prevents duplicate FINALIZED rows | None required if checkpoint mechanism is intact |
| All generation retries exhausted | No | `GENERATION_FAILED` state persists; operator initiates new DRAFT manually | Required |

Non-retryable facts:
* `FINALIZED` state cannot fail; it is the success terminal in the generation direction
* Compliance deletion of a DRAFT goes to `DISCARDED`, not `GENERATION_FAILED`

---

### 41.2 Report Domain Failures

| Failure scenario | Retryable | Recovery path | Operator intervention |
|---|---|---|---|
| No finalized snapshot for requested month | No | `NOT_AVAILABLE` returned; no retry; no live data fallback | None required unless snapshot generation itself failed |
| Report generation failure (general) | Yes | `REPORT_GENERATION_FAILED → REPORT_PENDING` | Required if repeated failures indicate systemic issue |
| Historical regeneration failure | Yes | Same; audit log records failed attempt including partial fingerprint comparison | Required if repeated |
| Async generation timeout (> 60s SLA) | Yes | `REPORT_GENERATION_FAILED → REPORT_PENDING` | Required if systemic timeout |
| Template version unavailable at regeneration | No | `NOT_AVAILABLE` for that template version; operator may select an available version | Operator selects template version |

---

### 41.3 AI Insight Domain Failures

| Failure scenario | Retryable | Recovery path | Operator intervention |
|---|---|---|---|
| LLM call timeout | Yes | Retry up to `max_retries` (default: 2) with exponential backoff | If all retries fail → `AI_GENERATION_FAILED` |
| LLM invalid structured output | Yes | Retry up to 2 times | If all retries fail → `AI_GENERATION_FAILED` |
| LLM provider outage (HTTP 5xx, 429) | Yes | Retry with backoff; queue for retry when provider recovers; alert raised | Prior cached `AI_REVIEWED` insight served with `stale: true` |
| All retries exhausted | No | `AI_GENERATION_FAILED`; last valid `AI_REVIEWED` insight served with `stale: true`; failure logged | Operator notified if stale threshold exceeded |
| Concurrent generation for same tuple | Not a failure | Second generation request rejected; existing in-flight generation completes | None required |

---

### 41.4 Configuration Version Domain Failures

| Failure scenario | Retryable | Recovery path | Operator intervention |
|---|---|---|---|
| Activation write failure (DB error during `APPROVED → ACTIVE`) | Yes | Version remains `APPROVED`; retry activation | Required |
| Config registry unavailable at snapshot finalization | Not a failure | `configuration_registry_version` fingerprint component recorded as `UNKNOWN_V0` | Audit warning logged |
| Version record unavailable at fingerprint lookup (corrupted, manually deleted) | Not a failure | Fingerprint notes version as `ARCHIVED`; regeneration proceeds with warning | Audit concern |

Non-retryable:
* Rollback to a prior version; explicitly forbidden; requires new version record to revert

---

### 41.5 Compliance Domain Failures

| Failure scenario | Retryable | Recovery path | Operator intervention |
|---|---|---|---|
| Pre-action audit write failure | No | `APPROVED_FOR_ACTION → IN_EXECUTION` is blocked; cannot proceed without audit entry | Required immediately; treat as incident |
| Partial deletion failure (some tables succeed, some fail) | Yes | `IN_EXECUTION → UNDER_REVIEW`; partial execution documented; re-review before retry | Required; scope must be re-evaluated |
| Post-action audit write failure after successful deletion | Yes | Emergency audit record creation; deletion action already completed | Required immediately; compliance defect |
| Compliance authority unavailable for authorization | Not retryable on a deadline | Workflow remains in `UNDER_REVIEW`; no deadline | Required to proceed |

Non-retryable:
* A compliance action that proceeds to `IN_EXECUTION` without a pre-action audit entry is a compliance incident, not a normal failure

---

---

## 42. SCOPE-SPECIFIC BEHAVIOR (ALL DOMAINS)

---

### MVP Scope

| Domain | Behavior |
|---|---|
| Outreach lifecycle | Minimal states; limited enforcement (see Section 10) |
| Snapshot lifecycle | Not operational |
| Report lifecycle | Not operational |
| AI insight lifecycle | Not operational |
| Config version governance | Not operational; V1 baseline recorded at STANDARD launch |
| Compliance governance | Not operational; no finalized records exist |

---

### STANDARD Scope

| Domain | Behavior |
|---|---|
| Outreach lifecycle | Core transitions enforced; basic validation |
| Snapshot lifecycle | `DRAFT → VALIDATING → FINALIZED`; basic fingerprint (`UNKNOWN_V0` for unimplemented components); no compliance pathway; no `COMPLIANCE_HOLD` |
| Report lifecycle | Report generation from snapshots; `REPORT_PUBLISHED`; auto-approve (no operator review gate) |
| AI insight lifecycle | Risk summary + intervention recommendation; `AI_GENERATED → AI_REVIEWED` (no manual review gate); TTL caching; force-refresh |
| Config version governance | V1 active; append-only registry; version captured in fingerprint |
| Compliance governance | Not yet operational; scope manifest defined |

---

### PRODUCTION Scope

| Domain | Behavior |
|---|---|
| Outreach lifecycle | Full transition map enforced; strict validation; complete audit logging |
| Snapshot lifecycle | Full lifecycle including `COMPLIANCE_HOLD` and `COMPLIANCE_DELETED`; all 5 fingerprint components populated; compliance pathway operational |
| Report lifecycle | Full lifecycle including `REPORT_REVIEW_PENDING`; historical regeneration with fingerprint comparison; `POTENTIALLY_DIVERGENT` flagging |
| AI insight lifecycle | Full insight suite; operator review gate for monthly narrative (when configured); complete version history; attribution guarantees |
| Config version governance | Full lifecycle including `SUPERSEDED` and `ARCHIVED`; atomic activation; rollback explicitly forbidden and enforced |
| Compliance governance | Full lifecycle; pre-action audit required (hard gate); scope manifest required; all audit entry fields required |

---

---

## 43. ACCEPTANCE CRITERIA (NEW DOMAINS)

---

### Snapshot Domain

**Given** a monthly snapshot job runs for a student with all content fields assembled
**When** all validation preconditions are met (fingerprint computed; no concurrent FINALIZED snapshot)
**Then** the snapshot transitions `VALIDATING → FINALIZED`; the Reproducibility Fingerprint is locked; AI text is physically copied into the snapshot row

**Given** a FINALIZED snapshot receives a compliance deletion request
**When** the Compliance Governance Pathway is invoked
**Then** the snapshot transitions `FINALIZED → COMPLIANCE_HOLD` before any records are deleted; the transition `COMPLIANCE_HOLD → COMPLIANCE_DELETED` is blocked until a pre-action audit entry exists

**Given** a DRAFT snapshot receives a compliance deletion request
**When** processed
**Then** the DRAFT transitions to `DISCARDED`; a discard audit entry is created in `compliance_audit`; the full Compliance Governance Pathway is NOT invoked

**Given** a second snapshot finalization attempt for the same `(student_id, snapshot_month)` pair
**When** the second attempt runs
**Then** it is rejected by the idempotency check; the existing FINALIZED snapshot is preserved; no duplicate is created

---

### Report Domain

**Given** a historical report is regenerated after an AI model or prompt version change
**When** regeneration runs
**Then** AI narrative content is reproduced from the physical text copy in the snapshot; no LLM call is made; the new version is marked `POTENTIALLY_DIVERGENT` if its source snapshot fingerprint differs from the original

**Given** a report is in `REPORT_PUBLISHED` state and a regeneration is requested
**When** the regeneration is processed
**Then** a NEW report version record is created; the `REPORT_PUBLISHED` record is not modified; both versions are queryable

---

### AI Insight Domain

**Given** force-refresh is requested for an `AI_REVIEWED` insight
**When** processed
**Then** a NEW insight record is created in `AI_PENDING`; the existing `AI_REVIEWED` record transitions to `AI_REFRESH_REQUESTED`; the existing record is NOT modified

**Given** AI insight generation fails after max retries
**When** the insight endpoint is queried
**Then** the last `AI_REVIEWED` insight (if any) is returned with a `stale: true` flag; the `AI_GENERATION_FAILED` record is not served directly

---

### Config Version Domain

**Given** a new configuration version is activated
**When** the activation is processed
**Then** exactly one version transitions from `APPROVED → ACTIVE`; the prior `ACTIVE` version simultaneously transitions to `SUPERSEDED`; this happens atomically with no window where zero or two versions are ACTIVE

**Given** a `SUPERSEDED` version is referenced in a historical snapshot fingerprint
**When** the fingerprint is looked up for audit purposes
**Then** the SUPERSEDED version record is fully queryable and returns the complete rule set active at snapshot generation time

---

### Compliance Domain

**Given** a compliance action is `APPROVED_FOR_ACTION`
**When** a transition to `IN_EXECUTION` is attempted without a pre-action audit entry in the `compliance_audit` schema
**Then** the transition is blocked; the workflow remains in `APPROVED_FOR_ACTION`; an alert is raised

**Given** a compliance action completes (`IN_EXECUTION → DELETED`) on a student whose snapshot contributed to published aggregate cohort reports
**When** the action completes
**Then** the published report record is annotated with a compliance-action flag; the aggregate statistics are NOT retroactively recalculated; the report remains `REPORT_PUBLISHED`

---

---

## 44. UPDATED INVARIANTS (ALL DOMAINS COMBINED)

---

### Outreach Domain (original — preserved)

* `CLOSED` is terminal — no transitions out, ever
* No backward transitions allowed
* No skip-level transitions (unless explicitly listed in Section 4)
* Automated retry enters `RETRY` state, not `QUEUED`
* `RETRY` can only be entered from `NO_RESPONSE`
* `INTERVENTION_REQUIRED` from active outreach states (`CONTACTED`, `NO_RESPONSE`, `RETRY`, `RESPONDED`) requires a human operator ESCALATE action
* `ESCALATE` is blocked on `CLOSED`, `ELIGIBLE`, `QUEUED`, `ANALYZED`, `INTERVENTION_REQUIRED`, `RESOLVED`
* `FORCE_RETRY` is blocked when `current_attempt ≥ MAX_ATTEMPTS`
* State must always be a valid enum value from Section 3
* Every transition must produce a `StateTransitionLog` record

---

### Snapshot Domain

* `FINALIZED` is irreversible — only `REGENERATION_REQUESTED` and `COMPLIANCE_HOLD` are outbound
* Exactly one snapshot per `(student_id, snapshot_month)` may be `FINALIZED`
* Physical AI text copies are locked at `FINALIZED`; no subsequent AI operation modifies them
* Reproducibility Fingerprint is immutable after `FINALIZED`
* `DRAFT` snapshots are mutable; immutability applies only to `FINALIZED`
* `DISCARDED` and `COMPLIANCE_DELETED` are terminal
* Every transition produces a `snapshot_lifecycle_log` entry

---

### Report Domain

* `REPORT_PUBLISHED` is immutable — no published report row is modified after this state
* Historical regeneration produces a NEW version; published reports are never overwritten
* All generations from the same `(snapshot, template_version)` are deterministically identical
* Every generation records the source snapshot's Reproducibility Fingerprint
* `REPORT_ARCHIVED` is terminal

---

### AI Insight Domain

* AI insights are advisory — `AI_REVIEWED` state grants no authority over student state or financial records
* Snapshot AI content is isolated from `ai_insights` lifecycle changes
* Attribution metadata is immutable after `AI_GENERATED`
* One in-flight generation per `(student_id, insight_type, date_period)` at a time
* `AI_ARCHIVED` is terminal for that version; record retained

---

### Config Version Domain

* Exactly one version is `ACTIVE` at all times
* `ACTIVE → SUPERSEDED` and `APPROVED → ACTIVE` are atomic
* Version records are append-only after activation
* Rollback to a prior version is explicitly forbidden
* `SUPERSEDED` and `ARCHIVED` records are permanently retained

---

### Compliance Domain

* Pre-action audit entry in `compliance_audit` is a hard gate before `IN_EXECUTION`
* No application service account writes to `compliance_audit` schema
* Compliance audit records are append-only
* `DELETED`, `ANONYMIZED`, `REJECTED`, `WITHDRAWN` are terminal
* Compliance actions do not retroactively modify published report aggregate statistics

---

---

## 45. UPDATED REFERENCES

---

Depends on:

* spec/01_requirements.md — Sections 3.15, 3.17, 3.18, 3.19, 4.7, 4.8, 6, 7, 9.1–9.4, 11.1, 12.8, 13 (FAD-1 through FAD-6), 14 (readiness assessment)
* spec/08_data_model.md — Entity definitions referenced by lifecycle states
* spec/04_idempotency_concurrency.md — Concurrency rules intersecting with snapshot and config-version activation
* state/system_state_model.md (legacy reference — outreach domain)
* state/outreach_lifecycle.md (legacy reference — outreach domain)
* runtime/system_loop.md (legacy reference)
* directives/core_decision_engine.md (legacy reference)

---

## END OF FILE
