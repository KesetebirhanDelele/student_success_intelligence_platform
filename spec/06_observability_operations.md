# spec/06_observability_operations.md

---

## LAYER 2 — SPECIFICATIONS (OBSERVABILITY & OPERATIONAL GOVERNANCE)

---

## 1. OBSERVABILITY PHILOSOPHY

---

### 1.1 Governance-Aware Observability

Observability in SSIP is not a generic logging exercise. The platform operates across six lifecycle domains, three database schemas with distinct permission models, and three service accounts with privilege separation. Observability must be aware of these governance dimensions:

* Telemetry must distinguish between operational events (mutable runtime behavior) and governance events (irreversible state transitions that cross boundaries defined by INVARIANT-1 through INVARIANT-7 in `spec/03_state_transition_rules.md`)
* A log entry that records `VALIDATING → FINALIZED` is a governance event. It must carry attribution fields, fingerprint metadata, and correlation ID with the same fidelity as the database audit record it accompanies
* The observability layer is not a replacement for database audit records — it is a supplementary real-time signal that enables operational response, while the database record enables legal and compliance reconstruction
* Governance-aware observability means: when a governance boundary is crossed, the log entry is produced atomically with the state transition and contains enough context to reconstruct the authorization chain without querying the database

This distinction is not academic. A governance boundary crossed without a corresponding governance-quality log entry is an observability defect that weakens forensic capability, even if the database audit record exists.

---

### 1.2 Two-Category Telemetry Model

Platform telemetry divides into two non-overlapping categories with different durability, access, and completeness requirements:

| Category | Purpose | Enforcement layer | Durability | Access |
|---|---|---|---|---|
| **Operational telemetry** | Real-time monitoring, alerting, SLA tracking, debugging | Application log stream (stdout) | Container runtime; rotated per policy | Operations; may be observed by dev/ops teams |
| **Governance telemetry** | Audit, lineage reconstruction, compliance evidence, reproducibility validation | Database-level audit tables (append-only) + structured log stream | Permanent (database records); log stream is supplementary | Privileged roles only: compliance_officer, auditor, operator (scoped) |

Operational telemetry answers: "What is the system doing right now?"
Governance telemetry answers: "What did the system do, who authorized it, and can we prove it?"

Both categories are required. Neither replaces the other. In an investigation, governance telemetry is authoritative; operational telemetry is contextual.

---

### 1.3 Lineage-Aware Telemetry

Every telemetry event that crosses a data lineage boundary must carry the lineage context. Lineage context means:

* The `origin_source` of the data being processed (per `spec/03_state_transition_rules.md` §39.2)
* The `origin_authority` indicating whether the origin is `sql_server_authoritative` or `platform_supplementary`
* The `correlation_id` binding the event to the request or job that produced it
* The `causation_id` (where applicable) binding the event to the upstream event that caused it — enabling multi-hop lineage reconstruction
* The `attribution_timestamp` of the originating event (not the processing timestamp)

A lineage-aware log entry for a snapshot finalization includes all five fingerprint components. A lineage-aware log entry for a report generation includes the source snapshot ID and fingerprint. A lineage-aware log entry for an AI generation includes the `prompt_version` and `model_used`. These fields are not metadata embellishments — they are the forensic chain.

---

### 1.4 Orchestration Visibility

The platform executes multi-phase orchestration workflows that span database writes, external service calls, and state machine transitions. Each phase must be independently visible:

* Every orchestration phase produces a log entry on phase entry, phase completion, and phase failure
* Phase-level log entries carry the same `correlation_id` as the parent job entry — enabling per-job phase timeline reconstruction
* The orchestration root log entry (job start) records: job type, student scope, trigger type, execution mode, correlation ID
* Intermediate phase entries record: phase name, input summary (non-PII), outcome, duration_ms
* Final log entry (job completion) records: total duration, per-phase outcome summary, any stale results served, any governance boundaries crossed

A multi-phase orchestration workflow whose execution cannot be reconstructed from log entries is an observability defect.

---

### 1.5 Replay Observability

Historical report regeneration and replay ingestion are governance-sensitive executions. They must be distinguishable from original executions in the log stream:

* Replay executions carry `execution_type: replay` or `execution_type: regeneration` to distinguish them from `execution_type: original`
* The source artifact (snapshot ID, original job correlation ID) is recorded in the replay entry
* Fingerprint comparison is logged at the start of each replay: the stored fingerprint versus the current system fingerprint
* Any divergence between stored and current fingerprint produces a `POTENTIALLY_DIVERGENT` log warning — even if regeneration proceeds

Replay observability must support the question: "Did this regeneration produce the same output as the original?"

---

### 1.6 Reproducibility-Aware Diagnostics

The Snapshot Reproducibility Fingerprint (FAD-6) is the platform's reproducibility contract. Diagnostics must reference the fingerprint:

* When a snapshot is finalized, the five fingerprint components are logged: `schema_version`, `config_registry_version`, `ai_prompt_version`, `ai_model_version`, `report_template_version`
* When a historical report regeneration runs, the stored fingerprint and the current system state are compared; the comparison result is logged
* If any fingerprint component is `UNKNOWN_V0` (captured when a component version was unavailable at finalization time), this is a known audit gap — it is logged as a warning, not an error
* Fingerprint mismatch alerts are surfaced as `SEVERITY: MEDIUM` governance alerts (see §10)

---

### 1.7 Audit-Correlated Operations

Every governance operation must produce both a database audit record (permanent, append-only) and a structured log entry (operational). The two are correlated by `correlation_id`.

The database audit record is authoritative for legal and compliance purposes.
The structured log entry is authoritative for operational monitoring and real-time alerting.

Neither is a substitute for the other. If a governance operation produced only a log entry (no database audit record), the governance audit is incomplete. If a governance operation produced only a database record (no log entry), the operational monitoring is blind.

---

### 1.8 Observability vs. Audit Logging

These are distinct concepts with different purposes, audiences, and retention profiles:

| Dimension | Observability (operational logs) | Audit logging (governance records) |
|---|---|---|
| **Primary purpose** | Real-time monitoring, alerting, debugging | Legal evidence, compliance reconstruction, forensics |
| **Storage** | Container log stream (stdout); rotated per policy | Database tables (`compliance_audit`, `warehouse.report_audit_log`, `state_transition_log`); permanent |
| **Retention** | Container runtime policy; typically 30–90 days | Indefinite for compliance_audit; permanent for governance records |
| **Audience** | Operations team, developers (with redaction) | Compliance officer, auditor, legal team |
| **Content** | Operational metrics, durations, outcomes, non-PII context | Full authorization chain, actor identity, scope manifest, affected record counts |
| **Modification** | Log streams may be rotated; individual entries are ephemeral | Append-only; entries are never modified or deleted |
| **Cross-reference** | Points to entity IDs and correlation_ids | Points to specific records and authorization artifacts |

**Critical rule:** Audit-quality logging (governance telemetry) is only satisfied by the database-level append-only records. Structured log entries are a necessary complement; they are never a sufficient substitute.

---

## 2. STRUCTURED LOGGING ARCHITECTURE

---

### 2.1 Universal Log Schema

All log entries from all platform components use the following base schema. Fields marked `required` must be present on every log entry; fields marked `conditional` must be present when applicable:

```json
{
  "timestamp": "ISO-8601 (required)",
  "level": "info | warn | error | debug (required)",
  "service": "api | snapshot_service | report_service | ai_service | sync_service | compliance_service | scheduler (required)",
  "event": "short_snake_case_event_name (required)",
  "correlation_id": "uuid-v4 (required)",
  "causation_id": "uuid-v4 (conditional — present when this event was caused by another event)",
  "execution_mode": "SHADOW | LIVE (required for all outreach and AI operations)",
  "actor_identity": "service_account_name | authenticated_user_identity (required for state-transition events)",
  "origin_source": "scheduler | operator | mirrored_sql_server | ghl | ai_subsystem | compliance_pathway (conditional — required for data-producing events)",
  "origin_authority": "sql_server_authoritative | platform_supplementary | operator_authorized | compliance_authorized | system_automated (conditional — required when origin_source present)",
  "lifecycle_state": "current state of the entity being operated on (conditional — required for state-transition events)",
  "duration_ms": "integer (conditional — required for timed operations)",
  "outcome": "success | failure | partial | skipped (required for all operations that have a completion)",
  "error_class": "TimeoutError | ValidationError | GovernanceViolation | DuplicateKeyError | ProviderError | ... (required when outcome=failure)",
  "context": {
    "entity_type": "snapshot | report | ai_insight | config_version | compliance_workflow | outreach | sync (conditional)",
    "entity_id": "opaque internal ID (conditional — never raw PII)",
    "student_id": "opaque_hash_ref (conditional — never raw UserID; hash for correlation only)"
  }
}
```

Fields that must never appear in any log entry:
* Raw student PII (email, phone, FirstName, LastName, UserID as a naked identifier)
* AI content text (`content_text` from `ai_insights`)
* Credential values (database passwords, API keys, connection strings)
* Raw compliance scope manifests (these belong in `compliance_audit` only)

---

### 2.2 Required Correlation Fields

These fields form the traceability backbone and must be present on every log entry:

| Field | Propagation rule | Generation rule |
|---|---|---|
| `correlation_id` | Propagated from inbound `X-Correlation-ID` header; generated server-side if absent | UUID v4; generated at entry point (API request, scheduler trigger, webhook receipt) |
| `causation_id` | Set to the `correlation_id` of the upstream event that caused this one | Present when an event was triggered by another traceable event (e.g., AI generation triggered by snapshot job) |
| `attribution_timestamp` | Sourced from the original event timestamp (not the processing timestamp) | When the event occurred in the source system |
| `execution_mode` | Propagated from the platform `EXECUTION_MODE` configuration | Never inferred; always explicit |

A log entry with a `correlation_id` but no `causation_id` is a root event (user request, scheduler trigger, webhook receipt). A log entry with both is a derived event. The causation chain is reconstructed by following `causation_id → correlation_id` links.

---

### 2.3 API Request Logging

Every API request produces two log entries: one at request receipt and one at response dispatch.

**Request entry:**
```json
{
  "event": "api_request_received",
  "method": "POST | GET | ...",
  "path": "/snapshots/finalize",
  "role": "operator | compliance_officer | ...",
  "actor_identity": "<authenticated_identity>",
  "correlation_id": "<from header or generated>",
  "execution_mode": "SHADOW | LIVE"
}
```

**Response entry:**
```json
{
  "event": "api_response_dispatched",
  "status_code": 200,
  "duration_ms": 45,
  "outcome": "success | failure",
  "error_class": "<if failure>",
  "correlation_id": "<same as request>"
}
```

Governance-boundary API calls (finalization, publication, compliance initiation) additionally emit a `governance_transition` log entry (see §2.5, §2.7, §2.9).

---

### 2.4 Orchestration Job Logging

Scheduled and async orchestration jobs produce a log entry at each of: job start, each phase transition, and job completion.

**Job start:**
```json
{
  "event": "orchestration_job_started",
  "job_type": "monthly_snapshot_generation | monthly_report_generation | ai_enrichment_batch | sql_server_sync | cohort_classification",
  "trigger_type": "scheduled | operator_requested | system_retry",
  "scope": "all_active_students | cohort_id=... | student_id=<opaque>",
  "correlation_id": "<job correlation_id>",
  "execution_mode": "SHADOW | LIVE"
}
```

**Phase entry/exit:**
```json
{
  "event": "orchestration_phase_entered | orchestration_phase_completed | orchestration_phase_failed",
  "job_type": "monthly_snapshot_generation",
  "phase": "draft_assembly | content_lock | ai_enrichment | fingerprint_freeze | finalization",
  "correlation_id": "<same as job>",
  "causation_id": "<job start correlation_id>",
  "duration_ms": "<phase duration if completed or failed>",
  "outcome": "success | failure | partial"
}
```

**Job completion:**
```json
{
  "event": "orchestration_job_completed",
  "job_type": "monthly_snapshot_generation",
  "total_students_scoped": 200,
  "students_succeeded": 198,
  "students_failed": 2,
  "students_skipped": 0,
  "total_duration_ms": 47000,
  "governance_boundaries_crossed": ["VALIDATING→FINALIZED"],
  "correlation_id": "<same as job start>"
}
```

---

### 2.5 Snapshot Generation Logging

In addition to orchestration job logs, snapshot generation produces domain-specific entries at each lifecycle transition:

```json
{
  "event": "snapshot_state_transition",
  "from_state": "VALIDATING",
  "to_state": "FINALIZED",
  "snapshot_id": "<opaque>",
  "student_id": "<opaque_hash_ref>",
  "snapshot_month": "2026-04",
  "actor_identity": "finalization_service_account",
  "origin_source": "scheduler",
  "attribution_timestamp": "ISO-8601",
  "correlation_id": "<job correlation_id>",
  "fingerprint_components": {
    "schema_version": "0002",
    "config_registry_version": "V3",
    "ai_prompt_version": {"risk_summary": "v3.1", "progress_summary": "v2.0"},
    "ai_model_version": {"risk_summary": "claude-sonnet-4-6"},
    "report_template_version": "t2.0"
  }
}
```

The `fingerprint_components` block must appear on the `VALIDATING → FINALIZED` log entry. It does not appear on any other snapshot transition entry.

For `GENERATION_FAILED` transitions, the `error_class` field must be set to the specific failure class (e.g., `DataQualityError`, `FingerprintAssemblyFailure`, `ConcurrentFinalizationRejected`).

---

### 2.6 AI Enrichment Logging

AI generation events produce structured log entries that carry metadata only — never AI content text (spec/09 §10.3).

```json
{
  "event": "ai_insight_generation_completed",
  "insight_type": "risk_summary",
  "student_id": "<opaque_hash_ref>",
  "prompt_version": "v3.2",
  "model_used": "claude-sonnet-4-6",
  "version_number": 5,
  "is_force_refresh": false,
  "latency_ms": 2340,
  "retry_count": 0,
  "outcome": "success",
  "correlation_id": "<uuid>",
  "causation_id": "<snapshot_job_correlation_id if triggered by snapshot batch>"
}
```

For failure events:
```json
{
  "event": "ai_insight_generation_failed",
  "insight_type": "risk_summary",
  "student_id": "<opaque_hash_ref>",
  "prompt_version": "v3.2",
  "model_used": "claude-sonnet-4-6",
  "retry_count": 2,
  "error_class": "ProviderTimeoutError | RateLimitError | InvalidOutputError",
  "stale_insight_served": true,
  "stale_insight_version": 4,
  "correlation_id": "<uuid>"
}
```

The `content_text` field must never appear in any AI log entry. The combination of `insight_type`, `prompt_version`, `model_used`, and `student_id` (opaque) is sufficient for operational correlation and reproducibility auditing.

---

### 2.7 Report Publication Logging

```json
{
  "event": "report_state_transition",
  "from_state": "REPORT_APPROVED",
  "to_state": "REPORT_PUBLISHED",
  "report_id": "<opaque>",
  "cohort_id": "<cohort_identifier>",
  "report_month": "2026-04",
  "lineage_version": 1,
  "publishing_actor": "<authenticated_identity>",
  "source_snapshot_fingerprint": {
    "schema_version": "0002",
    "config_registry_version": "V3"
  },
  "attribution_timestamp": "ISO-8601",
  "correlation_id": "<uuid>"
}
```

For regeneration events:
```json
{
  "event": "report_regeneration_started",
  "original_report_id": "<opaque>",
  "report_month": "2026-04",
  "requesting_actor": "<authenticated_identity>",
  "stored_fingerprint": {"schema_version": "0002", "config_registry_version": "V3"},
  "current_fingerprint": {"schema_version": "0002", "config_registry_version": "V4"},
  "fingerprint_match": false,
  "divergence_flag": "POTENTIALLY_DIVERGENT",
  "correlation_id": "<uuid>"
}
```

The `divergence_flag` must be logged at regeneration start (before execution), not after. If fingerprints match, `divergence_flag: null`.

---

### 2.8 Config Activation Logging

```json
{
  "event": "config_version_activated",
  "prior_version_id": "<version_id>",
  "new_version_id": "<version_id>",
  "activated_by": "<actor_identity>",
  "effective_from": "ISO-8601",
  "change_rationale": "<one-line summary — never omitted>",
  "origin_source": "operator",
  "origin_authority": "operator_authorized",
  "correlation_id": "<uuid>"
}
```

Config activation is a globally serialized operation. If two concurrent activation attempts occur, the losing attempt produces:
```json
{
  "event": "config_activation_rejected_concurrent",
  "attempted_version_id": "<version_id>",
  "winning_version_id": "<version_id>",
  "error_class": "ConcurrentActivationConflict",
  "correlation_id": "<uuid>"
}
```

---

### 2.9 Compliance Execution Logging

Compliance execution log entries must be present in the structured log stream in addition to the database audit entries in `compliance_audit`. These are not the same records and are not substitutes for each other.

```json
{
  "event": "compliance_execution_started",
  "workflow_id": "<workflow_identifier>",
  "action_type": "DELETE | ANONYMIZE",
  "affected_student_id_ref": "<opaque — never raw UserID>",
  "pre_action_audit_entry_id": "<compliance_audit entry ID confirming gate was satisfied>",
  "authorized_by": "<compliance_authority_identity>",
  "origin_source": "compliance_pathway",
  "origin_authority": "compliance_authorized",
  "correlation_id": "<uuid>"
}
```

```json
{
  "event": "compliance_execution_completed",
  "workflow_id": "<workflow_identifier>",
  "action_type": "DELETE",
  "affected_tables": ["public.student_trigger_data", "warehouse.student_snapshots", "warehouse.snapshot_ai_narratives"],
  "row_counts_per_table": {"public.student_trigger_data": 1, "warehouse.student_snapshots": 3, "warehouse.snapshot_ai_narratives": 3},
  "post_action_audit_entry_id": "<compliance_audit entry ID>",
  "outcome": "success",
  "correlation_id": "<uuid>"
}
```

Partial execution (failure mid-workflow) produces:
```json
{
  "event": "compliance_execution_partial_failure",
  "workflow_id": "<workflow_identifier>",
  "tables_succeeded": ["public.student_trigger_data"],
  "tables_failed": ["warehouse.student_snapshots"],
  "error_class": "DatabaseWriteError",
  "recovery_path": "workflow_returned_to_UNDER_REVIEW",
  "correlation_id": "<uuid>"
}
```

---

### 2.10 Ingestion Workflow Logging

SQL Server sync and GHL webhook ingestion events:

**SQL Server sync job:**
```json
{
  "event": "sql_server_sync_completed",
  "rows_scanned": 76,
  "rows_succeeded": 76,
  "rows_failed": 0,
  "schema_drifts_detected": 0,
  "schema_drift_details": [],
  "duration_ms": 3400,
  "origin_source": "mirrored_sql_server",
  "origin_authority": "sql_server_authoritative",
  "correlation_id": "<uuid>"
}
```

Schema drift events produce a separate log entry per drifted column:
```json
{
  "event": "schema_drift_detected",
  "drift_type": "missing_column | new_column | type_mismatch",
  "column_name": "<column>",
  "expected": "<expected_type_or_presence>",
  "actual": "<actual_type_or_absent>",
  "impact": "column_skipped | sync_partial",
  "correlation_id": "<sync job correlation_id>"
}
```

**GHL webhook ingestion:**
```json
{
  "event": "ghl_webhook_processed",
  "webhook_type": "message_received | contact_updated",
  "dedup_key": "<ghl_message_id or event_key>",
  "duplicate_detected": false,
  "origin_source": "ghl",
  "origin_authority": "platform_supplementary",
  "correlation_id": "<uuid>"
}
```

---

### 2.11 Execution Mode in Logs

All outreach operations, AI provider calls, and compliance executions must carry `execution_mode` in their log entries.

| `execution_mode` | Meaning |
|---|---|
| `SHADOW` | Operation was evaluated but no external communication occurred; outreach triggers are no-ops |
| `LIVE` | Operation executed with real external effects |

`execution_mode: SHADOW` in a log entry is not a failure. It is a deliberate operational state. Alert systems must not treat SHADOW entries as failures. SHADOW mode suppresses outbound communication; it does not suppress logging.

---

## 3. TRACE PROPAGATION & CORRELATION

---

### 3.1 Correlation ID Architecture

The `correlation_id` is the primary traceability key. Architecture:

* Generated as a UUID v4 at the system entry point: API request receipt, scheduler job fire, webhook receipt
* Propagated as `X-Correlation-ID` HTTP header to all downstream service calls
* Propagated as a payload field in all async job messages and orchestration event payloads
* Written into every database record produced during the lifecycle of the originating event
* Never regenerated mid-execution; the same correlation_id that entered the system exits in the response and in all database records

A request lifecycle that begins with `correlation_id: abc-123` must be identifiable end-to-end by querying for `abc-123` across: API logs, orchestration logs, database records (student_snapshots, ai_insights, report_audit_log, compliance_audit), and any downstream webhook or provider call logs.

---

### 3.2 Causation Chain Propagation

The `causation_id` enables multi-hop lineage reconstruction:

* When a snapshot finalization job triggers AI enrichment, the AI enrichment job's log entries carry `causation_id` set to the snapshot job's `correlation_id`
* When a report generation job reads a snapshot, the report generation entries carry `causation_id` set to the snapshot finalization `correlation_id`
* When a compliance workflow execution is triggered by an operator approval, the execution's entries carry `causation_id` set to the approval API request's `correlation_id`

This two-level chain (correlation_id → causation_id) is sufficient for current orchestration depth. Deeper chains are reconstructed by following the link: event A's `causation_id` = event B's `correlation_id`, event B's `causation_id` = event C's `correlation_id`.

---

### 3.3 Async Orchestration Propagation

Async orchestration jobs (snapshot batch, report generation) communicate via shared job state in the database. Correlation ID propagation across async boundaries:

* The job initiation record (in the database or job queue) carries the `correlation_id` from the triggering request
* Workers that pick up deferred jobs restore the `correlation_id` from the job record and use it for all log entries and database writes during that job
* A worker that generates a new `correlation_id` instead of restoring from the job record breaks the traceability chain — this is an observability defect

---

### 3.4 Ingestion Pipeline Propagation

SQL Server sync jobs and GHL webhook handlers:

* SQL Server sync generates a new `correlation_id` per sync run; all database writes during that sync carry the same `correlation_id`
* GHL webhook handlers generate a new `correlation_id` per webhook event; the webhook payload's GHL event ID is recorded as `context.external_event_id` for cross-system correlation
* Processed event deduplication checks (against `processed_events` table) include the `correlation_id` of the original receipt in the dedup record, enabling reconstruction of when and why a duplicate was rejected

---

### 3.5 AI Orchestration Propagation

AI generation events exist within a parent context (snapshot batch, on-demand API request, daily batch job):

* The `causation_id` on an AI generation event points to the parent orchestration job's `correlation_id`
* The `prompt_version` and `model_used` are recorded in the log at `AI_PENDING → AI_GENERATING` and are immutable from that point in both log stream and database record
* A force-refresh triggered by an operator API call propagates the API request's `correlation_id` as the AI generation's `causation_id`
* A force-refresh for a student whose snapshot is FINALIZED must log a note confirming that the force-refresh does not affect the frozen snapshot AI text (INVARIANT-3 enforcement visibility)

---

### 3.6 Compliance Workflow Propagation

Compliance workflows span multiple user actions and may span days:

* Each workflow has a stable `workflow_id` generated at `COMPLIANCE_REQUEST_RECEIVED` and propagated to every subsequent event in the workflow
* Individual state transitions within the workflow carry: `workflow_id` (stable), `correlation_id` (per-request), `causation_id` (pointing to prior transition)
* The pre-action audit entry in `compliance_audit` references the `workflow_id` and the `correlation_id` of the authorization request
* The execution job that reads the pre-action audit entry and begins deletion propagates the authorization `correlation_id` as its `causation_id`

This chain means: given a `compliance_audit` entry, the full operational trace can be reconstructed by following `workflow_id` through all log and database entries.

---

### 3.7 Propagation Guarantees

| Guarantee | Requirement |
|---|---|
| Single-hop traceability | Any single log entry's `correlation_id` can retrieve all other entries from the same job or request |
| Causation reconstruction | Following `causation_id → correlation_id` links reconstructs the full triggering chain for any derived event |
| Cross-schema correlation | Database records in `public`, `warehouse`, and `compliance_audit` schemas all carry the `correlation_id` from the originating job |
| Provider call correlation | Outbound calls to GHL, AI providers, and SQL Server carry the `correlation_id` in request metadata for cross-system debugging |

---

### 3.8 Replay Semantics

Replay executions (historical regeneration, idempotency retry, failed job resume) must be distinguishable from original executions:

* A replay or retry generates a new `correlation_id` for the replay execution itself
* The new `correlation_id`'s `causation_id` points to the `correlation_id` of the original execution that is being replayed or retried
* Log entries carry `execution_type: replay | retry | original` to disambiguate
* The source artifact identity (original snapshot ID, original job ID) is always included in the replay entry's context

---

### 3.9 Retry Trace Continuity

Retries within a single execution (e.g., AI provider retry, snapshot generation retry after `GENERATION_FAILED`) must maintain trace continuity:

* A retry within the same execution uses the same `correlation_id` as the original attempt
* The retry log entry records `retry_count: N` and `prior_error_class: <what failed>`
* If a retry succeeds, the success log entry references the previous failure's `correlation_id` so that the failure-and-recovery arc is traceable
* Retries that spawn new jobs (e.g., `GENERATION_FAILED → DRAFT` generating a new draft job) use the new job's own `correlation_id` with `causation_id` pointing to the failed job

---

### 3.10 Regeneration Trace Isolation

Historical regeneration is governance-sensitive and must be fully isolated in the trace:

* A regeneration request creates a new lineage version in `warehouse.monthly_reports` and a new `correlation_id`
* The original report's `correlation_id` and the source snapshot's `correlation_id` are recorded as `context.original_report_correlation_id` and `context.source_snapshot_correlation_id` in the regeneration log entry
* The regeneration trace never writes to or modifies the original report or snapshot records — any log entry that shows an UPDATE to a FINALIZED or REPORT_PUBLISHED record during a regeneration is a specification defect signal

---

## 4. ORCHESTRATION VISIBILITY

---

### 4.1 Snapshot Generation Phase Visibility

The snapshot generation workflow has six phases. Each must produce a log entry on entry, completion, and failure:

| Phase | Entry trigger | Key log fields |
|---|---|---|
| 1. DRAFT assembly | Scheduler fires or operator initiates | `job_type`, `snapshot_month`, `student_scope`, `correlation_id` |
| 2. Content lock | Transition `DRAFT → VALIDATING` | `snapshot_id`, `locked_fields`, `correlation_id` |
| 3. AI enrichment | After content lock; before fingerprint freeze | `insight_types_requested`, `prompt_versions`, `causation_id` |
| 4. Fingerprint freeze | All AI enrichment complete; fingerprint computed | `fingerprint_components` (all 5), `correlation_id` |
| 5. Finalization gate | Idempotency check; duplicate FINALIZED detection | `idempotency_key`, `duplicate_detected`, `correlation_id` |
| 6. FINALIZED write | After gate passes | Full governance_transition entry (§2.5) |

If phase 5 detects a duplicate FINALIZED row, the job exits cleanly and logs:
```json
{
  "event": "snapshot_finalization_duplicate_rejected",
  "reason": "FINALIZED_row_already_exists",
  "existing_snapshot_id": "<opaque>",
  "error_class": "DuplicateKeyError",
  "correlation_id": "<new job>",
  "causation_id": "<original finalization correlation_id if recoverable>"
}
```

---

### 4.2 Report Publication Phase Visibility

| Phase | Entry trigger | Key log fields |
|---|---|---|
| 1. REPORT_PENDING → REPORT_GENERATING | Scheduler or operator trigger | `report_month`, `cohort_id`, `source_snapshot_count`, `correlation_id` |
| 2. Snapshot data read | Report generator reads finalized snapshots | `snapshots_read_count`, `missing_snapshots`, `correlation_id` |
| 3. AI narrative assembly | Reads frozen narrative text from snapshot rows | `ai_narratives_assembled`, `stale_count`, `correlation_id` |
| 4. REPORT_GENERATED | Content assembled | `template_version_used`, `correlation_id` |
| 5. Operator review | REPORT_REVIEW_PENDING | `review_requested_by`, `correlation_id` |
| 6. REPORT_APPROVED | Operator approves | `approved_by`, `correlation_id` |
| 7. REPORT_PUBLISHED | Publication boundary | Full governance_transition entry (§2.7) |

---

### 4.3 AI Enrichment Phase Visibility

| Phase | Entry trigger | Key log fields |
|---|---|---|
| 1. AI_PENDING creation | Generation request received | `insight_type`, `student_id (opaque)`, `prompt_version`, `correlation_id` |
| 2. In-flight dedup check | Before AI_GENERATING | `existing_in_flight`, `duplicate_rejected` if applicable |
| 3. Prompt assembly | Platform assembles prompt | `prompt_version`, `pii_fields_excluded: true` (assertion) |
| 4. Provider call | AI provider request sent | `model_used`, `latency_ms`, `retry_count` |
| 5. Output validation | Structured output validated | `schema_valid`, `validation_error` if applicable |
| 6. AI_REVIEWED write | Successful storage | `version_number`, `causation_id`, `correlation_id` |

---

### 4.4 Ingestion Workflow Visibility

SQL Server sync phases:
1. **Connection established** — log connection type, driver, whether SSL negotiated; no credential values
2. **Rows fetched** — log row count, columns mapped, any unmapped columns (schema drift)
3. **Coercion pass** — log type coercion outcomes; any coercion failures per field
4. **Upsert execution** — log rows inserted, rows updated, rows skipped (idempotency), rows failed
5. **Sync completed** — aggregate outcome entry (§2.10)

GHL webhook phases:
1. **Webhook received** — log event type, size; signature verification outcome
2. **Dedup check** — log `processed_events` lookup outcome
3. **Attribution assignment** — log `origin_source`, `origin_authority` set by platform
4. **Record write** — log outcome, idempotency key
5. **Webhook acknowledged** — log response sent to GHL

---

### 4.5 Config Activation Phase Visibility

| Phase | Entry trigger | Key log fields |
|---|---|---|
| 1. DRAFT creation | `config_manager` proposes new version | `version_id`, `change_rationale`, `correlation_id` |
| 2. APPROVED transition | Authorization step | `approved_by`, `correlation_id` |
| 3. Singleton check | One-ACTIVE invariant verified before write | `current_active_version_id`, `singleton_confirmed` |
| 4. Atomic swap | Prior ACTIVE → SUPERSEDED; new APPROVED → ACTIVE | `prior_version_id`, `new_version_id`, `effective_from` |
| 5. Activation logged | Full governance_transition entry (§2.8) | All fields |

A failed singleton check (concurrent activation detected) is logged with `error_class: ConcurrentActivationConflict` and the competing version ID, then the operation is rejected without executing the swap.

---

### 4.6 Compliance Execution Phase Visibility

| Phase | Entry trigger | Key log fields |
|---|---|---|
| 1. Intake | `COMPLIANCE_REQUEST_RECEIVED` | `workflow_id`, `action_type`, `student_id_ref (opaque)`, `correlation_id` |
| 2. Review | `UNDER_REVIEW` | `reviewer_identity`, `correlation_id` |
| 3. Authorization | `APPROVED_FOR_ACTION` | `authorized_by`, `scope_manifest_ref`, `correlation_id` |
| 4. Pre-action gate | Precondition check before `IN_EXECUTION` | `pre_action_audit_entry_id`, `all_preconditions_met: true/false` |
| 5. Execution start | `IN_EXECUTION` | Full compliance_execution_started entry (§2.9) |
| 6. Execution completion | `DELETED` or `ANONYMIZED` | Full compliance_execution_completed entry (§2.9) |

If the pre-action gate fails (preconditions not met), the workflow is blocked and the failure is logged:
```json
{
  "event": "compliance_execution_gate_blocked",
  "workflow_id": "<workflow_id>",
  "unmet_preconditions": ["pre_action_audit_entry_missing"],
  "error_class": "GovernanceGateViolation",
  "correlation_id": "<uuid>"
}
```

This is a `SEVERITY: CRITICAL` alert event (see §10).

---

### 4.7 State-Transition Visibility

Every state transition in every domain must produce a structured log entry with the following minimum fields (INVARIANT-4):

```json
{
  "event": "state_transition",
  "domain": "snapshot | report | ai_insight | config_version | compliance | outreach",
  "entity_id": "<opaque>",
  "from_state": "<prior_state>",
  "to_state": "<new_state>",
  "actor_identity": "<who performed the transition>",
  "origin_source": "<what triggered the transition>",
  "attribution_timestamp": "ISO-8601",
  "correlation_id": "<uuid>"
}
```

A state transition recorded in the database without a corresponding structured log entry is an observability defect (INVARIANT-4 requires auditability via log, not only database records, for operational response purposes).

---

### 4.8 Failure Visibility

Every orchestration failure must log:
* The exact phase that failed (`phase` field)
* The `error_class` (specific, not generic `Error`)
* Whether the failure is retryable (`retryable: true | false`)
* The recovery path if retryable (`recovery_path: "return_to_DRAFT" | "operator_retry_required" | ...`)
* The current state the entity is left in after failure

Silent failures (try/catch without structured log) are production defects (per CLAUDE.md Failure-First Design).

---

### 4.9 Retry Visibility

Retry log entries must distinguish:
* Automatic retry (within the same job execution) — same `correlation_id`, incremented `retry_count`
* Operator-initiated retry (new job execution after terminal failure) — new `correlation_id`, `causation_id` points to failed job
* Scheduled retry (deferred job on backoff) — new `correlation_id`, backoff duration logged as `retry_delay_ms`

For AI provider retries:
```json
{
  "event": "ai_provider_retry",
  "retry_count": 1,
  "prior_error_class": "ProviderTimeoutError",
  "retry_delay_ms": 2000,
  "correlation_id": "<same as original attempt>"
}
```

---

### 4.10 Replay Visibility

Replay executions (historical regeneration, replay ingestion of a corrected batch) must always declare their execution type and source:

```json
{
  "event": "historical_regeneration_initiated",
  "execution_type": "regeneration",
  "source_snapshot_id": "<opaque>",
  "report_month": "2026-04",
  "requesting_actor": "<identity>",
  "stored_fingerprint_hash": "<fingerprint summary>",
  "current_fingerprint_hash": "<fingerprint summary>",
  "fingerprint_match": true | false,
  "new_lineage_version": 2,
  "correlation_id": "<uuid>"
}
```

---

## 5. REPLAY & REGENERATION OBSERVABILITY

---

### 5.1 Historical Regeneration Visibility

Historical report regeneration is a governance-sensitive execution. Its full observability requirements:

1. **Initiation log** — requesting actor, source month, source snapshot IDs, stored vs. current fingerprint comparison (§4.10)
2. **Snapshot read log** — which snapshots were read; no snapshots from months other than the target month; no live SQL Server queries
3. **AI narrative assembly log** — frozen narrative text read from snapshot rows; no AI provider calls
4. **Template version log** — which template version was used; whether it matches the original
5. **Divergence determination log** — `POTENTIALLY_DIVERGENT` or `IDENTICAL` determination with both fingerprint versions
6. **Completion log** — new report record ID, lineage version, divergence flag, `correlation_id`

The audit log entry in `warehouse.report_audit_log` must exist before the regeneration completes. If the audit write fails, the regeneration is rolled back.

---

### 5.2 Replay Ingestion Observability

When SQL Server sync data is reprocessed (e.g., after a sync error correction):

* The replay is distinguished from the original by `execution_type: replay` and a reference to the original sync job's `correlation_id`
* Deduplication is enforced via the `processed_events` table; replay rows that match existing dedup keys are logged as `duplicate_detected: true` and skipped without error
* Attribution fields on replayed records carry the original `attribution_timestamp` from the source event, not the replay processing timestamp

---

### 5.3 Retry Execution Traceability

A retry after `GENERATION_FAILED` is not a replay — it is a fresh attempt. Traceability:

* New `correlation_id` for the retry job
* `causation_id` points to the failed job's `correlation_id`
* Log entry includes `retry_attempt_number: N` for N-th attempt
* The entity state at the time of retry is recorded (e.g., snapshot is in `GENERATION_FAILED`; transition to `DRAFT` is the retry start)

---

### 5.4 Fingerprint Divergence Diagnostics

When a fingerprint mismatch is detected at regeneration time:

1. Both fingerprints are logged (stored vs. current) in full
2. The differing components are identified: e.g., `config_registry_version: V3 (stored) vs. V4 (current)`
3. The `POTENTIALLY_DIVERGENT` flag is set on the regenerated report record
4. A `SEVERITY: MEDIUM` alert is raised (§10.9)
5. The operator is notified via the governance operations dashboard (§11.7)

Fingerprint divergence does not block regeneration. It is an audit finding, not an execution blocker.

---

### 5.5 Stale AI Detection

A stale AI insight is an `AI_REVIEWED` insight that was not refreshed within its configured TTL (default: 24 hours). Stale AI detection:

* A `stale_insight_served` log entry is produced when the endpoint serves an insight beyond its TTL
* The staleness age (`stale_for_hours`) is logged alongside the insight version and `correlation_id`
* Stale AI at snapshot finalization time (when the AI enrichment phase fails and the prior version is used) is explicitly logged:
```json
{
  "event": "snapshot_ai_content_frozen_from_stale",
  "insight_type": "risk_summary",
  "stale_version": 4,
  "stale_for_hours": 26,
  "student_id": "<opaque>",
  "correlation_id": "<finalization job correlation_id>"
}
```

---

### 5.6 Replay vs. Original Execution Differentiation

| Attribute | Original execution | Replay / Regeneration |
|---|---|---|
| `execution_type` | `original` | `replay` or `regeneration` |
| `correlation_id` | Generated at entry | New UUID; different from original |
| `causation_id` | Absent (root event) | Points to original execution correlation_id |
| `fingerprint_match` | N/A | Logged at regeneration start |
| `divergence_flag` | N/A | `POTENTIALLY_DIVERGENT` or null |
| Governance boundary crossed? | Yes (FINALIZED, REPORT_PUBLISHED) | No (regeneration creates new version; original is not modified) |

---

### 5.7 Reproducibility Validation

Reproducibility validation is a diagnostic operation that confirms whether the current system state would produce an identical report for a given historical month. It is an operational tool, not a governance action.

Reproducibility validation log entry:
```json
{
  "event": "reproducibility_validation_run",
  "target_month": "2026-04",
  "stored_fingerprint": {"config_registry_version": "V3", "ai_model_version": "..."},
  "current_fingerprint": {"config_registry_version": "V4", "ai_model_version": "..."},
  "components_matched": 4,
  "components_diverged": 1,
  "diverged_components": ["config_registry_version"],
  "reproducibility_status": "POTENTIALLY_DIVERGENT",
  "correlation_id": "<uuid>"
}
```

---

## 6. SCHEDULER & ASYNC JOB OBSERVABILITY

---

### 6.1 Scheduler Heartbeat Architecture

The APScheduler instance must emit a heartbeat log entry on each scheduler tick to confirm liveness:

```json
{
  "event": "scheduler_heartbeat",
  "scheduler_id": "<instance_id>",
  "jobs_registered": 5,
  "jobs_pending": 0,
  "timestamp": "ISO-8601"
}
```

Heartbeat interval: aligned to the shortest scheduled job interval (typically 1–5 minutes in STANDARD/PRODUCTION). A gap of > 2× the heartbeat interval is treated as a scheduler outage event (SEVERITY: CRITICAL, §10.5).

---

### 6.2 Deferred Job Visibility

Deferred jobs (retry-after-failure, scheduled future runs) must be visible in the log stream:

```json
{
  "event": "job_deferred",
  "job_type": "ai_enrichment_batch",
  "defer_reason": "provider_rate_limit",
  "defer_until": "ISO-8601",
  "retry_attempt": 1,
  "correlation_id": "<uuid>"
}
```

Every job in a PENDING or DEFERRED state must be discoverable via log query or database state — never silently lost.

---

### 6.3 Queue Depth and Execution Latency

For each job type, the following metrics are emitted on job completion:

| Metric | Logged as |
|---|---|
| Job queue depth at time of execution | `queue_depth_at_start` |
| Time from scheduling to execution start | `scheduling_to_start_ms` |
| Job execution latency | `execution_duration_ms` |
| SLA compliance | `within_sla: true | false` (SLA per job type, see §10) |

SLA values by job type:
* Monthly snapshot batch: ≤ 10 minutes for 2,000 students (spec/01 §4.1)
* Historical report generation: ≤ 60 seconds (spec/01 §4.1)
* AI insight generation per student: ≤ 10 seconds (spec/01 §4.1)
* SQL Server sync: alert if not run in > 24 hours

---

### 6.4 Retry Visibility

Retry behavior must be traceable from the log stream without querying the database:

* The log stream must show: initial failure, retry attempt, retry outcome
* A job that exhausts all retries and enters a terminal failure state produces a `SEVERITY: HIGH` alert (§10.2 / §10.3)
* The cumulative retry count is logged in the final failure entry

---

### 6.5 Stuck Workflow Detection

A workflow is considered stuck when it remains in a non-terminal, non-progressing state beyond a defined threshold:

| Domain | Stuck threshold | State(s) watched |
|---|---|---|
| Snapshot | > 2 hours in `VALIDATING` or `GENERATION_FAILED` | `VALIDATING`, `GENERATION_FAILED` |
| Report | > 2 hours in `REPORT_GENERATING` | `REPORT_GENERATING` |
| AI Insight | > 30 minutes in `AI_PENDING` or `AI_GENERATING` | `AI_PENDING`, `AI_GENERATING` |
| Compliance | > 24 hours in `APPROVED_FOR_ACTION` without moving to `IN_EXECUTION` | `APPROVED_FOR_ACTION` |
| Config Version | > 24 hours in `APPROVED` without activation | `APPROVED` |

Stuck workflow detection produces a `SEVERITY: MEDIUM` or `SEVERITY: HIGH` alert depending on domain sensitivity. Compliance stuck workflows are always `SEVERITY: HIGH`.

---

### 6.6 Orphaned Workflow Detection

An orphaned workflow is one that has no corresponding active job consuming it — e.g., a snapshot in `VALIDATING` state with no active finalization job. Detection:

* The scheduler checks for orphaned entity states on each tick (or at a configured interval)
* Orphaned states older than the stuck threshold produce orphan detection log entries and alerts
* Orphan detection entries carry enough context (entity_id, state, age) to enable operator investigation without database access

---

### 6.7 Duplicate Execution Detection

Duplicate execution (same job fired twice by scheduler double-fire) is detected and logged:

```json
{
  "event": "duplicate_job_execution_detected",
  "job_type": "monthly_snapshot_generation",
  "snapshot_month": "2026-04",
  "existing_job_correlation_id": "<already_running_job>",
  "rejected_job_correlation_id": "<duplicate_attempt>",
  "error_class": "DuplicateJobExecution"
}
```

The duplicate job exits cleanly. The idempotency mechanism (spec/04 §15.1) ensures no duplicate FINALIZED rows. The log entry confirms the rejection.

---

### 6.8 SLA Visibility

SLA compliance is logged as a structured metric on every job completion:

```json
{
  "event": "job_sla_status",
  "job_type": "historical_report_generation",
  "execution_duration_ms": 58000,
  "sla_threshold_ms": 60000,
  "within_sla": true,
  "correlation_id": "<uuid>"
}
```

Jobs that breach SLA automatically emit a `SEVERITY: HIGH` alert entry (§10).

---

## 7. AI ORCHESTRATION TELEMETRY

---

### 7.1 AI Request Execution Telemetry

Every AI provider call produces a request telemetry entry:

```json
{
  "event": "ai_provider_request",
  "provider": "anthropic | openai",
  "model_requested": "claude-sonnet-4-6",
  "insight_type": "risk_summary",
  "prompt_version": "v3.2",
  "student_id": "<opaque_hash_ref>",
  "request_timestamp": "ISO-8601",
  "correlation_id": "<uuid>"
}
```

The prompt content is never logged. The prompt_version is always logged. The combination of `prompt_version` + `model_requested` + `student_id (opaque)` is sufficient to reconstruct reproducibility context without exposing PII or AI content.

---

### 7.2 Model Selection Attribution

Model selection is an attribution event:

* When the AI model is configured via environment variable, the selected model is logged at service start and on each request
* If the model configuration changes between two AI insight versions for the same student, the change is visible in version history via `model_used` field — it is not obscured
* Historical insight versions retain the model that generated them; a model change does not retroactively alter prior version attribution

---

### 7.3 Prompt-Version Attribution

Prompt version attribution:

* Prompt version is captured at `AI_PENDING → AI_GENERATING` and logged in the generation entry
* If a prompt template is updated between two generation events for the same student, both versions are logged; the versions are distinguishable by `prompt_version` in the log stream
* Prompt version changes require a version bump in the prompt registry; deploying a changed prompt without bumping the version is a reproducibility defect — it would make two generations with identical `prompt_version` fields but different actual prompts

---

### 7.4 Latency and Retry Telemetry

```json
{
  "event": "ai_provider_response",
  "provider": "anthropic | openai",
  "model_used": "claude-sonnet-4-6",
  "insight_type": "risk_summary",
  "latency_ms": 2340,
  "retry_count": 0,
  "output_valid": true,
  "validation_errors": [],
  "outcome": "success",
  "correlation_id": "<uuid>"
}
```

P50, P95, P99 latency must be computable from the log stream by querying `latency_ms` across `ai_provider_response` entries grouped by `provider` + `model_used` + `insight_type`.

---

### 7.5 Provider Failure Telemetry

```json
{
  "event": "ai_provider_failure",
  "provider": "anthropic",
  "model_used": "claude-sonnet-4-6",
  "error_class": "RateLimitError | TimeoutError | ProviderUnavailable | InvalidOutputSchema",
  "http_status_code": 429,
  "retry_count": 2,
  "max_retries": 2,
  "stale_insight_version_served": 4,
  "correlation_id": "<uuid>"
}
```

Provider failures are never silently swallowed. The error class, HTTP status (if applicable), and whether a stale insight was served are all logged. Accumulation of provider failures triggers a `SEVERITY: HIGH` alert when failure rate exceeds threshold (§10.3).

---

### 7.6 Stale Insight Detection

Stale insight detection telemetry must:

* Log when a stale insight is served instead of a fresh one, including the staleness duration
* Log when a snapshot finalization proceeds with stale AI text (not an error — a known operational condition)
* Distinguish between planned staleness (24-hour TTL; normal operation) and unplanned staleness (provider failure causing multi-day staleness)

Unplanned staleness exceeding 48 hours produces a `SEVERITY: HIGH` alert.

---

### 7.7 Frozen Snapshot AI Isolation

A fundamental observability requirement: confirming that frozen snapshot AI text is isolated from the operational `ai_insights` lifecycle.

The following events must produce a confirmation log entry that the isolation was honored:

* Force-refresh of an `ai_insights` record for a student with a FINALIZED snapshot: log entry confirms the snapshot's frozen text was not modified
* AI model version change: log entry confirms finalized snapshots retain the model attribution from when they were frozen
* Compliance deletion of `ai_insights` records: log entry confirms the snapshot row's frozen text is not affected (no FK dependency)

These are assertion-style log entries. Their purpose is not to describe behavior but to confirm that isolation was enforced:
```json
{
  "event": "snapshot_ai_isolation_confirmed",
  "action": "force_refresh",
  "snapshot_id": "<opaque>",
  "snapshot_state": "FINALIZED",
  "frozen_text_modified": false,
  "correlation_id": "<uuid>"
}
```

---

### 7.8 Provider Attribution

Provider attribution is a lineage requirement:

* Every stored `ai_insights` record carries the provider used (`model_used` field)
* The log stream entry for every AI generation carries the same value
* Switching providers requires no configuration change to historical records — prior records carry their original provider attribution
* The operational dashboard (§11.4) surfaces a breakdown of active AI insight versions by provider, enabling detection of inadvertent provider drift

---

### 7.9 Reproducibility-Safe Diagnostics

AI diagnostics must not violate snapshot isolation or introduce PII into log streams:

* Diagnostic queries for AI performance (latency distribution, failure rate by insight_type) operate on metadata only — never on `content_text`
* A diagnostic that reconstructs student assessments from log data is a privacy violation, even if the purpose is debugging
* Prompt construction diagnostics (confirming PII exclusion) are handled by prompt version review before activation — not by logging prompt content at runtime

---

## 8. CONFIG & GOVERNANCE OBSERVABILITY

---

### 8.1 Config Activation Visibility

Config version activation is the highest-impact routine governance operation. Full observability requires:

* Pre-activation state: current ACTIVE version, proposed version, change summary
* Activation authorization: `approved_by` identity, `authorized_by` identity (may differ for propose vs. approve workflows)
* Atomic swap outcome: both the SUPERSEDED transition and ACTIVE transition logged as a single governance event
* Post-activation confirmation: new singleton check confirms exactly one ACTIVE version after swap

---

### 8.2 Config Supersession Visibility

When a config version becomes SUPERSEDED:

* A `state_transition` log entry for the prior version records its transition from `ACTIVE → SUPERSEDED`
* The superseding version ID is logged alongside the superseded version ID
* The `effective_from` timestamp of the new version determines when new orchestration jobs use the new config; this boundary is visible in the log stream

---

### 8.3 Prospective-Only Enforcement Observability

FAD-3 prohibits retroactive application of config changes to finalized snapshots. Enforcement observability:

* Any attempt by application code to apply a new config version to a finalized or in-finalization snapshot produces a `GovernanceViolation` log entry and is rejected
* The governance dashboard (§11.7) surfaces a timeline of config activations alongside snapshot finalization events, enabling visual confirmation that each snapshot was processed under the correct config version
* The fingerprint component `config_registry_version` in each finalized snapshot is the primary audit artifact confirming which config governed that snapshot

---

### 8.4 Governance Approval Visibility

Governance approvals (compliance UNDER_REVIEW → APPROVED_FOR_ACTION, report REPORT_REVIEW_PENDING → REPORT_APPROVED) produce log entries with:

* Approving actor identity
* Entity being approved (workflow_id or report_id — opaque)
* Approval timestamp
* Any conditions or scope restrictions attached to the approval
* Correlation_id linking to the original request

---

### 8.5 Report Publication Approval Visibility

In PRODUCTION scope, report publication requires explicit `report_publisher` approval:

* The approval-to-publication sequence produces two log entries: one for the approval step and one for the publication step
* Both entries carry the same entity identifiers and the publication log entry's `causation_id` points to the approval log entry's `correlation_id`
* Auto-approval (MVP/STANDARD) is logged as:
```json
{
  "event": "report_auto_approved",
  "scope": "MVP | STANDARD",
  "report_id": "<opaque>",
  "auto_approval_reason": "review_gate_not_configured",
  "correlation_id": "<uuid>"
}
```

---

### 8.6 Governance Transition Observability

All irreversible governance transitions must produce an entry matching the schema in §10.4 of spec/09 (the `governance_transition` JSON template). These entries are in addition to the `state_transition` entries (§4.7). The distinction:

* `state_transition` entries are emitted for every state change in every domain
* `governance_transition` entries are emitted only for irreversible governance boundary crossings: `VALIDATING → FINALIZED`, `REPORT_APPROVED → REPORT_PUBLISHED`, `APPROVED → ACTIVE` (config), `APPROVED_FOR_ACTION → IN_EXECUTION` (compliance), `IN_EXECUTION → DELETED`, `IN_EXECUTION → ANONYMIZED`

`governance_transition` entries carry fingerprint context and authorization context not present in generic state_transition entries.

---

### 8.7 Audit Correlation

Every governance transition log entry must correlate with a database audit record via `correlation_id`. This correlation enables:

1. Given a compliance audit entry: find the operational log sequence that preceded and followed it
2. Given a report publication log entry: find the snapshot fingerprint that underpins the published report
3. Given a config activation log entry: find all snapshot finalization events that used that config version

The log stream does not replace the database audit records. Both exist. Both are correlated. An investigation uses both.

---

## 9. COMPLIANCE & AUDIT OBSERVABILITY

---

### 9.1 Deletion Workflow Visibility

Every compliance deletion workflow state transition produces structured log entries (§2.9 and §4.6). Full visibility:

* All transitions visible: COMPLIANCE_REQUEST_RECEIVED through DELETED/ANONYMIZED
* Partial execution (IN_EXECUTION → UNDER_REVIEW on failure) produces a partial failure log entry with which tables succeeded and which failed
* The scope manifest reference is logged by ID, not by content — the content resides in `compliance_audit.scope_manifests` only

---

### 9.2 Export Workflow Observability

Compliance audit exports (for external auditor review, per spec/05 §10.3) must be logged:

```json
{
  "event": "compliance_audit_export_initiated",
  "export_requested_by": "<actor_identity>",
  "export_scope": "workflow_id=... | student_id_ref=<opaque> | date_range=...",
  "actor_role": "compliance_officer | auditor",
  "correlation_id": "<uuid>"
}
```

Export completion log includes the export format, record count, and export artifact reference (not the content). Exports that contain PII fields are treated as data disclosures; the export log entry is the disclosure audit record.

---

### 9.3 Audit Generation Visibility

Compliance audit entry creation (in `compliance_audit` schema) must be reflected in the log stream:

```json
{
  "event": "compliance_audit_entry_created",
  "entry_type": "pre_action | post_action | scope_manifest | intake_log",
  "workflow_id": "<workflow_id>",
  "entry_id": "<compliance_audit entry ID>",
  "origin_source": "compliance_pathway",
  "correlation_id": "<uuid>"
}
```

This confirms the database write succeeded. If the compliance pathway service account fails to write the pre-action audit entry, the execution gate (§4.6) blocks `IN_EXECUTION` — and the gate block log entry references the missing entry ID.

---

### 9.4 Compliance Execution Observability

Full observability for compliance execution requires:

* Pre-execution: confirmation that pre-action audit entry exists (§4.6)
* Per-table execution: log entry per table being acted on (not combined; per-table for partial failure recovery)
* Post-execution: confirmation that post-action audit entry was written to `compliance_audit`
* Snapshot state transition: the FINALIZED → COMPLIANCE_HOLD and COMPLIANCE_HOLD → COMPLIANCE_DELETED transitions are logged via standard state_transition entries

---

### 9.5 Governance Override Visibility

A governance override attempt — any code path that tries to modify a FINALIZED snapshot or REPORT_PUBLISHED report outside the Compliance Governance Pathway — must log:

```json
{
  "event": "governance_override_attempt_rejected",
  "attempted_operation": "UPDATE | DELETE",
  "entity_type": "snapshot | monthly_report",
  "entity_id": "<opaque>",
  "entity_state": "FINALIZED | REPORT_PUBLISHED",
  "rejection_reason": "immutability_constraint | insufficient_privilege",
  "error_class": "GovernanceViolation",
  "correlation_id": "<uuid>"
}
```

`SEVERITY: CRITICAL` alert generated for every governance override attempt (§10.8).

---

### 9.6 Survivability Guarantees

The `compliance_audit` schema has no FK dependencies on `public` or `warehouse` schemas (FAD-4). Its observability survivability requirements:

* Compliance audit records must remain queryable after operational or warehouse records they reference are deleted
* The structured log stream entries for compliance audit entry creation (§9.3) are operational; they may be rotated. The database records are permanent.
* If the log stream for a compliance event is rotated away, the database record remains the authoritative audit artifact — this is expected and designed

---

### 9.7 Immutable Audit Visibility

Compliance audit records are INSERT-only in the database. The log stream must reflect this:

* No `DELETE` or `UPDATE` log entry should ever reference a `compliance_audit` table entry
* A log entry showing a `DELETE` or `UPDATE` against `compliance_audit` is a specification defect signal — the database-level INSERT-only grant prevents it from succeeding, but the attempt itself must be flagged as `SEVERITY: CRITICAL`

---

### 9.8 Privileged-Access Monitoring

Access to compliance audit records is privileged. Observability requirements for privileged access:

* Every query against `compliance_audit.deletion_log` or `compliance_audit.scope_manifests` by an authenticated user is logged with actor identity and query scope
* Export requests (§9.2) are always logged with full context
* Production database access for debugging purposes (developer accessing production credentials — spec/09 §6.7) requires an explicit time-limited authorization that produces a structured log entry

---

## 10. ALERTING & SLA GOVERNANCE

---

### 10.1 Alert Classification Model

| Severity | Definition | Response requirement |
|---|---|---|
| `CRITICAL` | Governance violation, compliance gate blocked, data loss risk, SQL Server write attempt, authentication bypass | Immediate operator intervention; escalation if unresolved in 15 minutes |
| `HIGH` | Snapshot finalization failure, report publication failure, AI provider sustained outage (> 30 min), missed scheduler run, SLA breach | Operator investigation within 1 hour |
| `MEDIUM` | Fingerprint divergence, stale AI enrichment (24–48 hours), ingestion drift (> 1 sync cycle gap), stuck workflow not yet critical | Operator review within 4 hours |
| `LOW` | Schema drift detected, individual AI generation retry, single webhook delivery failure | Logged; surfaced in dashboard; no immediate response required |
| `INFO` | Successful governance transitions, scheduled job completions, config activations | No action required; informational only |

---

### 10.2 Failed Snapshot Finalization

| Condition | Severity | Alert trigger | Escalation |
|---|---|---|---|
| `GENERATION_FAILED` after first attempt | LOW | Log entry only | None |
| `GENERATION_FAILED` after all retries exhausted | HIGH | Alert + operator notification | Operator initiates new DRAFT |
| Snapshot stuck in `VALIDATING` > 2 hours | HIGH | Stuck workflow detection (§6.5) | Operator investigation |
| Duplicate finalization attempt detected | INFO | Logged; no alert | None; idempotency handled |

---

### 10.3 Report Publication Failures

| Condition | Severity | Alert trigger |
|---|---|---|
| `REPORT_GENERATION_FAILED` after all retries | HIGH | Alert + operator notification |
| Report stuck in `REPORT_GENERATING` > 60s (SLA breach) | HIGH | SLA visibility (§6.3) |
| Report publication blocked (COMPLIANCE_HOLD student in report) | MEDIUM | Operator notification to resolve hold first |
| `POTENTIALLY_DIVERGENT` flag on regenerated report | MEDIUM | Governance operations dashboard (§11.7) |

---

### 10.4 Stale AI Enrichment

| Condition | Severity | Alert trigger |
|---|---|---|
| AI insight TTL exceeded (< 48 hours) | LOW | Surfaced in dashboard |
| AI insight stale > 48 hours due to provider failure | HIGH | Alert |
| AI insights absent for all students for > 24 hours | CRITICAL | Alert; immediate investigation |
| Snapshot finalized with stale AI text | MEDIUM | Log entry; operator informed |

---

### 10.5 Scheduler Outages

| Condition | Severity | Alert trigger |
|---|---|---|
| No heartbeat for > 2× heartbeat interval | CRITICAL | Alert; immediate investigation |
| Scheduled job missed (did not fire at expected time) | HIGH | Alert |
| Job queue backed up (depth > configurable threshold) | HIGH | Alert |

---

### 10.6 Ingestion Drift

| Condition | Severity | Alert trigger |
|---|---|---|
| No SQL Server sync in > 24 hours | CRITICAL | Alert; operator notification |
| Sync completed with partial failure (some rows failed) | MEDIUM | Alert with failure details |
| Schema drift detected (column missing or renamed) | MEDIUM | Alert with affected column |
| GHL webhook delivery failure (signature invalid) | HIGH | Alert; potential integration issue |

---

### 10.7 Compliance Failures

| Condition | Severity | Alert trigger |
|---|---|---|
| Compliance execution gate blocked (preconditions unmet) | CRITICAL | Immediate alert |
| Compliance execution partial failure | CRITICAL | Alert; workflow returned to UNDER_REVIEW |
| Pre-action audit entry write failure | CRITICAL | Execution blocked; alert generated |
| Compliance workflow stuck > 24 hours in `APPROVED_FOR_ACTION` | HIGH | Alert |

---

### 10.8 Unauthorized Operations

| Condition | Severity | Alert trigger |
|---|---|---|
| UPDATE or DELETE attempt against warehouse schema | CRITICAL | Alert; forensic investigation required |
| DELETE attempt against compliance_audit schema | CRITICAL | Alert; forensic investigation |
| API call to a governance endpoint without required role | HIGH | Alert with actor identity |
| Attribution field tampering attempt (client supplies `origin_source`) | HIGH | Alert |
| SQL Server write attempt by platform | CRITICAL | Alert; immediate escalation |

---

### 10.9 Fingerprint Mismatches

| Condition | Severity | Alert trigger |
|---|---|---|
| Fingerprint mismatch at historical regeneration | MEDIUM | Alert; `POTENTIALLY_DIVERGENT` flag set on report |
| Fingerprint component `UNKNOWN_V0` at finalization | LOW | Warning log; no alert |
| Config version referenced in fingerprint is ARCHIVED or missing | LOW | Warning at regeneration time |

---

### 10.10 Escalation Model

Escalation path when alerts are not resolved within their response window:

| Severity | Resolution window | Escalation path |
|---|---|---|
| CRITICAL | 15 minutes | Operations escalation → engineering escalation → senior stakeholder |
| HIGH | 1 hour | Operations investigation → engineering if structural |
| MEDIUM | 4 hours | Operations review; engineering if recurring |
| LOW | Next business day | Dashboard review |

Escalation artifacts: a structured `escalation_event` log entry is created at each escalation step, referencing the original alert's `correlation_id`.

---

### 10.11 Operational Ownership

| Alert domain | Operational owner | Note |
|---|---|---|
| Snapshot finalization failures | Operations team | Daily monitoring |
| Report publication failures | Operations team | Monthly cadence; pre-publication checklist |
| AI enrichment failures | Engineering | Involves external provider |
| Scheduler outages | Engineering + Operations | Infrastructure-level |
| SQL Server sync drift | Engineering | Infrastructure + SQL Server access |
| Compliance execution failures | Compliance officer + Engineering | Compliance-sensitive |
| Governance override attempts | Engineering + Security | Potential security incident |
| Unauthorized operations | Security team primary | Incident response triggered |

---

## 11. OPERATIONAL DASHBOARDS & METRICS

---

### 11.1 Orchestration Health Dashboard

Primary metrics for operational monitoring of all six lifecycle domains:

| Metric | Domain | Frequency | Alert threshold |
|---|---|---|---|
| Snapshot finalization success rate (rolling 7 days) | Snapshot | Daily | < 95%: HIGH |
| Average snapshot job duration | Snapshot | Per run | > 10 min for 2K students: HIGH |
| Report generation success rate (rolling 30 days) | Report | Monthly | < 100%: HIGH |
| AI enrichment success rate (rolling 24 hours) | AI Insight | Hourly | < 90%: HIGH |
| SQL Server sync success rate (rolling 7 days) | Ingestion | Daily | < 98%: MEDIUM |
| Config activation count (rolling 30 days) | Config | Monthly | Informational |
| Compliance workflow completion rate | Compliance | Per workflow | Informational |

---

### 11.2 Replay Activity Dashboard

| Metric | Tracked as |
|---|---|
| Historical regeneration count (rolling 30 days) | Count of `report_regeneration_initiated` events |
| Regeneration with fingerprint divergence | Count where `fingerprint_match: false` |
| `POTENTIALLY_DIVERGENT` reports active | Count of reports with divergence flag set |
| Replay ingestion count | Count of `execution_type: replay` sync events |
| Reproducibility validation runs | Count with pass/fail distribution |

---

### 11.3 Compliance Activity Dashboard

| Metric | Tracked as |
|---|---|
| Active compliance workflows | Count in non-terminal states |
| Workflows in `APPROVED_FOR_ACTION` (awaiting execution) | Count + age |
| Compliance executions completed (rolling 90 days) | Count by action_type |
| Compliance audit entries created (rolling 90 days) | Count by entry_type |
| Gate block events | Count of `compliance_execution_gate_blocked` |

Access to this dashboard is restricted to `compliance_officer` and `auditor` roles.

---

### 11.4 AI Provider Health Dashboard

| Metric | Tracked as |
|---|---|
| AI generation success rate (rolling 24 hours) | By insight_type, by provider |
| P50 / P95 / P99 latency by insight_type | From `ai_provider_response.latency_ms` |
| Retry rate by insight_type | From `retry_count > 0` events |
| Stale insight count (by staleness age band) | < 24h, 24–48h, > 48h |
| Provider error rate by error_class | RateLimitError, TimeoutError, InvalidOutputSchema |
| Active provider (current model_used) | From recent AI generation events |

---

### 11.5 Ingestion Health Dashboard

| Metric | Tracked as |
|---|---|
| Last SQL Server sync timestamp | Most recent `sql_server_sync_completed` event |
| Rows synced (rolling 7 days) | Trend from `rows_succeeded` |
| Schema drifts detected (rolling 30 days) | Count of `schema_drift_detected` events |
| GHL webhook success rate (rolling 24 hours) | From webhook processing events |
| GHL webhook duplicate rejection rate | `duplicate_detected: true` events |
| Sync gap alert | Time since last successful sync |

---

### 11.6 Regeneration History Dashboard

| Column | Source |
|---|---|
| Report month | `target_month` in regeneration event |
| Requested by | `requesting_actor` |
| Request timestamp | `attribution_timestamp` |
| Source snapshot fingerprint | `stored_fingerprint_hash` |
| Divergence status | `divergence_flag` |
| New lineage version | `new_lineage_version` |
| Correlation ID | `correlation_id` |

All historical regeneration requests are visible to `operator` and `auditor` roles. The divergence flag is highlighted for `POTENTIALLY_DIVERGENT` entries.

---

### 11.7 Governance Operations Dashboard

This dashboard surfaces all irreversible governance transitions across all domains:

| Domain | Shown as | Audience |
|---|---|---|
| Snapshot FINALIZED | Finalization timeline | Operator, Auditor |
| Report REPORT_PUBLISHED | Publication record | Operator, Auditor |
| Config version ACTIVE | Activation timeline | Operator, Config manager, Auditor |
| Compliance IN_EXECUTION | Execution log | Compliance officer, Auditor |
| Compliance DELETED / ANONYMIZED | Completion log | Compliance officer, Auditor |

Config activation overlay: the dashboard shows config activation events on the same timeline as snapshot finalization events — enabling visual confirmation that snapshots were finalized under the intended config version.

---

### 11.8 Lineage Divergence Dashboard

| Metric | Tracked as |
|---|---|
| POTENTIALLY_DIVERGENT reports | Count + list with details |
| Fingerprint mismatch events (rolling 30 days) | Count by diverged component |
| `UNKNOWN_V0` fingerprint components | Count by component type |
| Stale config version references | Count at regeneration time |

---

### 11.9 Operational vs. Governance Metric Distinction

| Category | Example metrics | Dashboard | Retention |
|---|---|---|---|
| **Operational metrics** | AI latency, sync duration, queue depth, error rate | Orchestration health, AI health, ingestion health | Log rotation (30–90 days) |
| **Governance metrics** | Config activation count, compliance workflow outcomes, governance override attempts | Governance operations, compliance activity | Permanent (sourced from DB audit records) |

Governance metrics are sourced from permanent database records, not from the log stream. They are available indefinitely, even after the log stream is rotated.

---

### 11.10 Mutable vs. Immutable Metrics

| Metric type | Mutability | Notes |
|---|---|---|
| Operational latency (P95 AI latency) | Mutable — rolling window recalculates | Each new measurement is independent |
| Snapshot finalization count for month M | Immutable — month M is closed | Cannot change after month end |
| Report publication count for month M | Immutable | |
| Compliance workflow outcomes | Immutable once terminal | DELETED is permanent |
| Config activation timeline | Immutable | Each activation is a permanent record |

Dashboards that display immutable historical governance metrics must reflect the database records, not a rolling window. Rolling window metrics apply only to operational health indicators.

---

## 12. REDACTION & PRIVACY-AWARE TELEMETRY

---

### 12.1 Student PII Redaction

Per spec/09 §10.1, the following fields must never appear in any structured log output:

| Field | Redaction in production | Redaction in development |
|---|---|---|
| `Email` | `***@***` | May appear with explicit environment opt-in |
| `PhoneNumber` | `***` | May appear with explicit environment opt-in |
| `FirstName`, `LastName` | `[REDACTED]` | May appear with explicit environment opt-in |
| `UserID` (raw) | Hashed opaque reference only | Same |
| `ClassSignupsID` | `[REDACTED]` | Same |

The production log stream must never contain raw student PII. Operators investigating a specific student correlate the opaque hash to the actual student via the platform UI.

---

### 12.2 AI Narrative Redaction

AI content text (`content_text` from `ai_insights`, frozen narrative text from `warehouse.snapshot_ai_narratives`) must never appear in any log entry. AI observability is metadata-only:

* What is logged: `insight_type`, `prompt_version`, `model_used`, `latency_ms`, `outcome`
* What is never logged: the actual text of any AI-generated assessment, narrative, or recommendation
* A log consumer must not be able to reconstruct a student's AI risk assessment from log data alone

---

### 12.3 Transcript Redaction

Conversation transcripts stored in `outreach_history` are not logged. Log entries for transcript-related operations contain only:

* `transcript_id` (opaque reference)
* `transcript_status`: available, missing, empty
* `sentiment_outcome`: positive, negative, neutral, unavailable
* `analysis_model_used`, `analysis_latency_ms`

The transcript text is never included in any log entry.

---

### 12.4 Compliance Workflow Redaction

Compliance workflow log entries contain:

* `workflow_id` (stable opaque identifier)
* `action_type`: DELETE or ANONYMIZE
* `affected_student_id_ref`: opaque hash, never raw UserID
* `affected_tables`: table names (not row content)
* `row_counts_per_table`: counts only

Compliance scope manifests (which enumerate all affected records with their full identifiers) reside exclusively in `compliance_audit.scope_manifests`. They are never written to the log stream.

---

### 12.5 Report Artifact Redaction

Report content JSON (`report_content_json` from `warehouse.monthly_reports`) is not logged. Log entries for report operations contain:

* `report_id` (opaque)
* `cohort_id`
* `report_month`
* `lineage_version`
* `student_count` in the report (aggregate — not individual student IDs)

Aggregate statistics from published reports (engagement rate, homework risk rate) may appear in operational dashboard metrics without requiring redaction, as they are aggregate figures.

---

### 12.6 Field-Level Redaction Table

| Log context | Fields to include | Fields prohibited |
|---|---|---|
| API request log | method, path, role, actor_identity, correlation_id | Request body, query params containing PII |
| Snapshot generation log | snapshot_id (opaque), snapshot_month, fingerprint_components | student name, UserID, any snapshot content field |
| AI generation log | insight_type, prompt_version, model_used, latency_ms | content_text, student name, email |
| SQL Server sync log | row counts, schema drift details | Row content, student data values |
| Compliance log | workflow_id, action_type, affected_tables, row_counts | Scope manifest content, student identity fields |
| GHL webhook log | webhook_type, dedup_key, outcome | GHL message content, student contact details |

---

### 12.7 Retention Boundaries

| Log type | Retention | Authority |
|---|---|---|
| Operational log stream (stdout) | Container runtime policy (typically 30–90 days) | Container orchestration layer |
| Governance telemetry (database) | Permanent for compliance_audit; retained with warehouse | Platform architecture |
| AI generation metadata logs | Same as operational log stream | Container runtime |
| Compliance audit database entries | Permanent; no TTL | spec/09 §3.6 |
| Export logs (§9.2) | Retained as operational logs; export artifacts subject to data governance policy | Data governance / compliance policy |

Governance audit records in the database are permanent and are explicitly exempt from log rotation policies. The log stream is supplementary.

---

### 12.8 Privileged Observability Access

Access to observability data is role-scoped:

| Observability artifact | Read access |
|---|---|
| Operational log stream (stdout) | Engineering team (with PII redaction in production) |
| Governance operations dashboard | `operator`, `auditor`, `compliance_officer` |
| Compliance activity dashboard | `compliance_officer`, `auditor` |
| AI provider health dashboard | `operator`, engineering |
| Compliance audit database entries | `compliance_officer`, `auditor` only |
| Structured log entries containing opaque student IDs | Engineering with audit obligation |

Direct log access in production that exposes student-correlated entries requires the same authorization and logging obligation as any other privileged data access (spec/09 §6.7).

---

### 12.9 Telemetry Minimization

Observability systems must not become shadow data warehouses. Anti-pattern prohibitions:

* Do not log full request/response bodies for API calls involving student data
* Do not log AI prompt content at any verbosity level in production
* Do not log SQL query results during sync operations (log counts and schema events only)
* Do not construct log entries by serializing ORM model instances — field-level selection is required
* Do not forward structured logs to third-party analytics platforms that lack data processing agreements for student data (see spec/09 §9.5 on AI provider DPAs — same principle applies to log aggregators)
* The log stream must not contain enough information for a log consumer to reconstruct a student's academic profile, financial situation, or compliance status

---

## 13. FAILURE & RECOVERY OBSERVABILITY

---

### 13.1 Partial Workflow Recovery Visibility

Partial workflow failure (some phases succeeded, some failed) must be fully visible:

* The completion log entry for a partial failure documents: phases succeeded, phases failed, entity state after failure, recovery path
* The entity state after failure is the authoritative current state — the log entry confirms this rather than implying an unknown state
* Recovery paths are declarative in the log entry: "return_to_DRAFT", "operator_retry_required", "workflow_returned_to_UNDER_REVIEW"

A partial failure that leaves an entity in an ambiguous state (state not recorded in log or database) is an observability defect and a potential data integrity concern.

---

### 13.2 Replay After Failure

When a failed operation is retried (operator-initiated or scheduled retry):

* The retry's `causation_id` points to the failed attempt's `correlation_id`
* The entity state at retry start is confirmed in the retry initiation log entry
* If the retry succeeds after a prior failure, the success log entry references both the current `correlation_id` and the prior failure's `correlation_id`

This enables reconstruction of: "This succeeded on the 3rd attempt after failing twice for reasons X and Y."

---

### 13.3 Orphaned Operation Detection

Orphaned operations are detectable from the log stream and database state:

* Orphan detection log entries (§6.6) carry the entity_id, state, age, and last-known job that was supposed to process the entity
* An orphan is confirmed when the entity is in a mutable, non-progressing state and no active job has the entity in its scope
* Orphan detection is a scheduler responsibility; the detection log entry triggers a MEDIUM or HIGH alert depending on domain sensitivity

---

### 13.4 Stale Retry Detection

A stale retry is a retry that was scheduled but fired after the window when it was still relevant (e.g., an AI retry that fires after the snapshot was already finalized):

```json
{
  "event": "stale_retry_detected",
  "job_type": "ai_enrichment_retry",
  "reason": "snapshot_already_finalized",
  "entity_state": "FINALIZED",
  "retry_discarded": true,
  "error_class": "StaleOperationError",
  "correlation_id": "<uuid>"
}
```

Stale retries are logged and discarded. They do not cause failures. Repeated stale retries indicate a scheduler or job queue ordering issue and produce a MEDIUM alert.

---

### 13.5 Duplicate Orchestration Detection

Duplicate orchestration (same job triggered twice within the same execution window) is detected via idempotency checks and logged (§6.7). The log stream differentiates:

* **True duplicate** (idempotency key collision): logged as `duplicate_job_execution_detected`; second job exits cleanly
* **Concurrent race** (two workers picked up the same job simultaneously): logged with both workers' correlation IDs; one wins (first valid write wins per spec/04 §2.3); the loser logs a clean exit

---

### 13.6 Governance Rollback Attempt Visibility

Governance rollback — attempting to reverse an irreversible state (e.g., reverting a FINALIZED snapshot to DRAFT, rolling back a config activation) — is explicitly prohibited and must be visible in the log stream:

```json
{
  "event": "governance_rollback_attempt_rejected",
  "attempted_from_state": "FINALIZED",
  "attempted_to_state": "DRAFT",
  "rejection_reason": "irreversible_state_transition",
  "error_class": "GovernanceViolation",
  "correlation_id": "<uuid>"
}
```

Config version rollback attempts (attempting to reactivate a SUPERSEDED version by moving it back to ACTIVE) produce the same pattern with `error_class: ConfigRollbackForbidden`. Both are `SEVERITY: HIGH` alerts.

---

### 13.7 Forensic Survivability

The observability architecture must support forensic reconstruction of any event in platform history:

* Governance audit records in the database are permanent and form the forensic foundation
* The structured log stream is supplementary context; log rotation does not impair forensic capability for events that produced database audit records
* A forensic investigation for a FINALIZED snapshot can reconstruct: who triggered it, which job ran it, which fingerprint was locked, whether AI enrichment succeeded or stale content was used — from the combination of `warehouse.student_snapshots`, `snapshot_lifecycle_log`, and the log stream (if retained)
* A forensic investigation for a compliance deletion can reconstruct: the full authorization chain, scope manifest, affected records, execution outcome — from `compliance_audit.deletion_log` and `compliance_audit.scope_manifests` alone, without requiring the log stream

---

### 13.8 Root-Cause Visibility

Root-cause analysis requirements:

* `error_class` on every failure log entry must be specific (not generic `Error`). `TimeoutError`, `ValidationError`, `GovernanceViolation`, `DuplicateKeyError`, `ProviderUnavailable` — all are specific. `Error` is not acceptable in production log entries.
* The full error context (HTTP status, failed validation fields, lock owner ID for race conditions) is included in `context` without including PII
* A failure that can only be diagnosed by querying the database (because the log entry lacks context) is an observability defect
* Correlation ID linkage enables "given this alert, find the full execution context" — this must be achievable without constructing multi-system joins

---

## 14. FUTURE OPERATIONAL EXTENSIBILITY

---

### 14.1 Distributed Tracing (Architecture-Level)

The current correlation/causation ID architecture is a foundation for distributed tracing. Future evolution path:

* The `correlation_id` and `causation_id` fields in all log entries are compatible with distributed tracing span semantics (W3C Trace Context `traceparent` header uses a trace ID + parent span ID model that maps to `correlation_id` + `causation_id`)
* Adopting a distributed tracing protocol (e.g., W3C Trace Context) requires adding header propagation to outbound HTTP calls and reading the standard header on inbound calls — the log field semantics remain unchanged
* This evolution requires no log schema changes; only header propagation and trace exporter integration

---

### 14.2 Centralized Telemetry (Architecture-Level)

Future centralized log aggregation (ELK, Loki, Splunk, CloudWatch):

* The JSON-structured stdout log format is directly ingestible by all major log aggregators without transformation
* Log forwarders (Fluentd, Vector, Fluent Bit) can be added to the container sidecar layer without application code changes
* The `service` field enables per-service index or stream routing in centralized platforms
* PII redaction must be verified to apply before log shipping, not at the aggregator — aggregators must not receive raw PII fields

---

### 14.3 SIEM Integration

Security Information and Event Management integration:

* `governance_transition` and `governance_override_attempt_rejected` log entries are the primary candidates for SIEM forwarding — these represent the security-relevant governance events
* The existing log schema carries all fields a SIEM requires: timestamp, actor_identity, event type, entity ID, outcome
* SIEM integration for compliance monitoring requires no schema changes; only log forwarding configuration

---

### 14.4 Enterprise Monitoring

For enterprise monitoring platform integration (Datadog, New Relic, Prometheus):

* The current log-based metrics (latency, success rate, queue depth) can be emitted as structured metrics alongside log entries, or derived from log queries
* The `duration_ms` and `outcome` fields in job completion entries are the primary time-series signals for operational health
* `within_sla` boolean entries are direct data points for SLA compliance tracking dashboards
* These metrics require no schema changes; only a metrics emission layer alongside the log stream

---

### 14.5 AI Observability Platforms

Dedicated AI observability platforms (for prompt performance, model drift, output quality):

* The `prompt_version`, `model_used`, `latency_ms`, `retry_count`, and `output_valid` fields in AI log entries provide the base data for AI observability dashboards
* Integration with AI observability platforms must not require transmission of `content_text` or any student-derived content — only metadata
* Prompt version lineage (which prompt version produced which snapshot fingerprint's AI component) is already captured in the snapshot fingerprint — AI observability platforms can consume this for longitudinal prompt performance analysis

---

### 14.6 Governance Analytics

Future governance analytics capabilities:

* Config version activation timeline analytics — how often config changes, what the activation frequency pattern is, whether activation correlates with report regeneration volume
* Compliance workflow volume analytics — FERPA request frequency, action_type distribution, workflow completion time distributions
* Fingerprint divergence analytics — which fingerprint components diverge most often, which config version changes cause the most regeneration events

All of these are derivable from existing governance audit database records. No schema changes are required. The capability requires query and reporting tooling.

---

### 14.7 Anomaly Detection

Future anomaly detection integration points:

* Unusually high compliance request volume for a specific student or time period — detectable from `compliance_audit.deletion_log` entry rate
* Unusual AI generation failure rate — detectable from AI telemetry failure rate trend
* Unusual governance transition frequency (e.g., many config activations in a short period) — detectable from config activation log entries
* Authentication anomalies (many failed role authorization attempts from a single identity) — detectable from `api_response_dispatched` entries where `status_code: 403` with the same `actor_identity`

These detection patterns require log aggregation and statistical analysis layers — not log schema changes.

---

## 15. ACCEPTANCE CRITERIA

---

### AC-1 — Cross-Domain Traceability

**Given** a snapshot finalization job triggers an AI enrichment sub-job which triggers a snapshot write
**When** the log stream is queried for the snapshot finalization job's `correlation_id`
**Then** all log entries from: job start, AI enrichment initiation, AI provider call, snapshot write, and governance_transition are returned; the AI enrichment entry's `causation_id` matches the finalization job's `correlation_id`

---

### AC-2 — Governance-Aware Observability

**Given** a `VALIDATING → FINALIZED` transition is executed
**When** the log stream is queried for the event
**Then** the log entry carries: `event: governance_transition`, `fingerprint_components` (all 5 components), `actor_identity`, `attribution_timestamp`, `correlation_id`; and a corresponding record exists in `snapshot_lifecycle_log` with the same `correlation_id`

---

### AC-3 — Replay Visibility

**Given** a historical report regeneration is requested for month M
**When** the regeneration completes
**Then** the log stream contains: a `report_regeneration_started` entry with both stored and current fingerprints; a `fingerprint_match` value; a `divergence_flag`; and a `historical_regeneration_initiated` entry with `execution_type: regeneration`; no log entry shows an UPDATE to the original FINALIZED snapshot

---

### AC-4 — Attribution Continuity

**Given** a GHL webhook is received and processed
**When** the resulting timeline event is stored
**Then** the log entry carries `origin_source: ghl` and `origin_authority: platform_supplementary`; the stored record carries the same attribution fields; no log entry shows these fields being accepted from the webhook payload itself

---

### AC-5 — Audit Survivability

**Given** a student's public schema records are deleted via the Compliance Governance Pathway
**When** the `compliance_audit.deletion_log` is queried after deletion
**Then** all compliance audit entries for that student's workflow remain queryable; the `compliance_audit_entry_created` log entries from the pre-action and post-action phases are present in the log stream (if within retention window); the database audit records are permanent regardless of log stream retention

---

### AC-6 — Redaction Compliance

**Given** a SQL Server sync job processes a student with `Email = student@example.com`
**When** the structured log stream is searched for `student@example.com`
**Then** zero matches are found; the sync log contains only row counts, schema outcomes, and opaque student identifiers

---

### AC-7 — SLA Visibility

**Given** a historical report generation job takes 65 seconds (exceeding the 60-second SLA)
**When** the job completion log entry is emitted
**Then** the entry contains `within_sla: false`, `execution_duration_ms: 65000`, `sla_threshold_ms: 60000`; and a `SEVERITY: HIGH` alert entry is emitted with the same `correlation_id`

---

### AC-8 — Orchestration Diagnosability

**Given** a snapshot generation job fails at the `AI enrichment` phase
**When** the log stream is queried for the job's `correlation_id`
**Then** the phase entry log shows `orchestration_phase_failed` with `phase: ai_enrichment`, `error_class: ProviderUnavailable`, `retryable: true`, `recovery_path: retry_ai_enrichment`; and the job completion entry shows `students_failed: N` with the phase failure summary

---

## 16. DOWNSTREAM IMPLICATIONS & UNRESOLVED OPERATIONAL CONCERNS

---

### Downstream Implications — Service Layer

| Service | Observability requirement |
|---|---|
| Snapshot finalization service | Must emit: orchestration phase entries (§4.1), governance_transition entry (§2.5), snapshot_ai_isolation_confirmed entry (§7.7) |
| Report generation service | Must emit: phase entries (§4.2), governance_transition on publication (§2.7), fingerprint comparison on regeneration (§5.4) |
| AI enrichment service | Must emit: AI request/response entries (§7.1–§7.5), stale insight entries (§7.6), isolation confirmation (§7.7) |
| SQL Server sync service | Must emit: sync completion entry (§2.10), schema drift entries (§2.10), attribution assignment confirmation |
| GHL webhook handler | Must emit: webhook processing entries (§2.10), dedup entries, attribution assignment |
| Compliance workflow service | Must emit: all compliance workflow phase entries (§4.6), pre-action gate entry, execution entries (§2.9), audit generation entries (§9.3) |
| Config activation service | Must emit: config activation entries (§2.8), singleton check entry, atomic swap confirmation |
| Scheduler | Must emit: heartbeat (§6.1), job start/completion entries (§2.4), deferred job entries (§6.2), stuck/orphan detection entries (§6.5–§6.6) |

---

### Downstream Implications — APIs

| API group | Observability requirement |
|---|---|
| All API endpoints | Request receipt + response dispatch log entries (§2.3) |
| Governance endpoints | Additional governance_transition entries on crossing boundaries |
| Compliance endpoints | Compliance execution entries; pre-action gate confirmation entries |
| Report endpoints | Publication and regeneration entries with fingerprint context |
| AI insight endpoints | AI generation entries; stale serving entries |
| Lineage endpoints | Attribution confirmation entries confirming read-only access |

The `X-Correlation-ID` response header must be set on every API response to the value of the request's `correlation_id`, enabling client-side correlation of requests to log entries.

---

### Downstream Implications — Scheduler Jobs

All scheduled jobs must:
* Generate a unique `correlation_id` at trigger time
* Log job start with trigger type (`scheduled` vs. `operator_requested`)
* Emit heartbeat from the scheduler instance (§6.1)
* Log SLA compliance on completion (§6.3)
* Detect and log stuck/orphaned entities on each tick (§6.5–§6.6)
* Detect and log duplicate execution on each tick (§6.7)

---

### Downstream Implications — Deployment Architecture

| Concern | Requirement |
|---|---|
| Log capture | All structured logs to stdout; container runtime captures and retains per policy |
| Log rotation | Container orchestration responsibility; does not apply to database governance records |
| PII validation at deployment | Production deployments must confirm PII redaction is active before receiving live student data |
| Log stream security | Log aggregators and forwarders must have data processing agreements if they process student-correlated log entries |
| Correlation ID header | API gateway or reverse proxy must pass `X-Correlation-ID` header without stripping it |

---

### Downstream Implications — Support Operations

| Support scenario | Observability artifact |
|---|---|
| "Why did this student's AI insight not update?" | AI generation log entries for that `student_id (opaque)`, `stale_insight_served` entries, `ai_provider_failure` entries |
| "Did the snapshot job run this month?" | `orchestration_job_started` and `orchestration_job_completed` entries for `job_type: monthly_snapshot_generation` |
| "Was this report the same as the original?" | `report_regeneration_started` with `fingerprint_match` and `divergence_flag` values |
| "What config version governed this snapshot?" | Snapshot `fingerprint_components.config_registry_version` from the `governance_transition` log entry |
| "Was the compliance action authorized?" | `compliance_audit.deletion_log` pre-action entry; `compliance_execution_started` log entry with `pre_action_audit_entry_id` |

---

### Unresolved Operational Concerns

**UO-1 (HIGH):** Log aggregation platform and retention policy — the platform writes structured logs to stdout but no log aggregation destination is specified. Without a central log destination with appropriate retention, log-based investigation windows are container-runtime-dependent. Before production deployment, a log aggregation platform must be selected and its data processing agreements verified for student-correlated log entries.

**UO-2 (HIGH):** Scheduler observability in distributed deployment — APScheduler heartbeat (§6.1) and job deduplication (§6.7) work reliably in single-instance deployments. If the platform scales horizontally, APScheduler's default in-memory job store cannot coordinate across instances. Distributed job locking and scheduler coordination must be addressed before horizontal scale-out.

**UO-3 (MEDIUM):** Student opaque ID hashing scheme — spec/09 §10.1 specifies that student IDs in logs use "a hash or internal opaque identifier." The specific hash function, salt, and mapping scheme are not yet defined. Without a defined scheme, log-based investigation requires an ad-hoc lookup mechanism. The hashing scheme must be defined and stable before production logging is operationalized.

**UO-4 (MEDIUM):** Alert delivery mechanism — the alert classification model (§10) defines severity and escalation paths but not the delivery mechanism (email, PagerDuty, Slack, etc.). The platform does not currently have a notification service for operational alerts (separate from the Cory briefing concept in CLAUDE.md). A notification delivery mechanism must be designed before operational alerting is functional.

**UO-5 (MEDIUM):** Structured log forwarding to SIEM or audit retention system — governance_transition and governance_override_attempt_rejected events are candidates for SIEM forwarding (§14.3). Whether the production environment requires SIEM integration and which events must be forwarded is a decision for Security/Compliance and must be resolved before the platform processes real student data.

**UO-6 (MEDIUM):** Causation ID propagation across async job boundaries — the causation chain model (§3.2) requires that deferred jobs restore `causation_id` from the job record. If the current job queue implementation does not persist `causation_id` in the job payload, the causation chain is broken at async boundaries. This must be verified when the async job persistence layer is designed.

**UO-7 (LOW):** Governance dashboard access control — the governance operations dashboard (§11.7) and compliance activity dashboard (§11.3) carry privileged governance information. Their access controls (operator, auditor, compliance_officer roles) must be enforced at the dashboard API layer in the same manner as the data APIs. A dashboard that bypasses role checks by serving pre-rendered content is a role access defect.

---

## 17. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Observability: operational log stream (stdout) with correlation IDs; basic governance_transition entries for the three implemented state transitions
* Alerts: CRITICAL alerts for governance override attempts, compliance gate blocks, SQL Server write attempts; other alert levels are informational only
* Dashboards: none; log queries serve debugging needs
* Compliance activity: N/A (no compliance workflow implementation in MVP)
* Replay visibility: N/A (no historical regeneration in MVP)

---

### STANDARD

* Observability: full structured logging per this spec; all phase-level entries; all domain-specific entries; correlation/causation propagation across all synchronous operations
* Alerts: all severity levels active; scheduler heartbeat implemented; SLA tracking active; fingerprint divergence alerting
* Dashboards: orchestration health, AI provider health, ingestion health (text-based or simple JSON summaries via API endpoints)
* Async observability: causation chain across async boundaries; deferred job visibility; stuck workflow detection
* Compliance activity: compliance workflow log entries; pre-action gate logging; execution logging

---

### PRODUCTION

* Observability: full spec as written; distributed causation chain; log aggregation to external platform with verified DPA; all alerts operational with delivery mechanism
* Dashboards: all dashboards per §11 implemented; governance operations dashboard with config/snapshot timeline overlay; compliance activity dashboard with restricted access
* SIEM: governance event forwarding implemented; unauthorized operation alerts sent to security team
* AI observability: metadata-only provider telemetry; prompt version lineage visible
* Distributed: scheduler coordination for horizontal scale-out; per-instance heartbeat with instance ID; duplicate execution detection across instances

---

## 18. REFERENCES

---

* `spec/01_requirements.md` — §4.5 (Observability NFRs), §4.1 (Performance SLAs), §4.3 (Reliability), §4.6 (Security), §4.7 (Reporting Warehouse Immutability), §4.8 (Historical Reproducibility), §9 (AI Augmentation)
* `spec/03_state_transition_rules.md` — §39 (Event Attribution Standard), §40 (Cross-Domain Invariants INVARIANT-1 through INVARIANT-7), §41 (Failure & Recovery Modeling)
* `spec/04_idempotency_concurrency.md` — §2.4 (Platform Concurrency Philosophy), §2.5 (Irreversible Operations), §4 (Idempotency Keys)
* `spec/05_external_integrations.md` — §4 (SQL Server Integration), §5 (GHL Integration), §11 (Failure and Retry Semantics)
* `spec/07_api_contracts.md` — §2.4 (Standard Response Envelope with correlation_id)
* `spec/08_data_model.md` — §13 (Schema Ownership Architecture), §22 (Cross-Domain Data Invariants)
* `spec/09_security_privacy.md` — §10 (Observability & Logging Security), §8 (Audit & Attribution Integrity), §4 (Service Account Governance)
* `spec/09_warehouse_physical_architecture.md` — §1.3 (Append-Only Enforcement Strategy), §7 (Compliance Audit Storage)
* `spec/10_pre_migration_storage_validation.md` — §6.3 (Compliance Storage Review)
* `alembic/versions/0002_warehouse_schema.py` — Physical table definitions for `warehouse` and `compliance_audit` schemas
* `alembic/versions/0003_config_version_registry.py` — Physical config version registry table and singleton index
