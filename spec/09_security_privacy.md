# spec/09_security_privacy.md

---

## LAYER 2 — SPECIFICATIONS (SECURITY & PRIVACY)

---

## 1. SECURITY PHILOSOPHY

---

### 1.1 Governance-Aware Security

Security in SSIP is inseparable from governance. The platform operates on student records that are legally protected (FERPA), historically immutable (append-only warehouse architecture), and compliance-auditable (governance-isolated `compliance_audit` schema). Security controls must enforce not just access restrictions but governance boundaries: who may perform what class of operation on what class of data, under what authorization chain.

Security rules in SSIP fall into two categories:

| Category | Examples | Enforcement layer |
|---|---|---|
| **Operational security** | API authentication, role-based endpoint access, input validation, credential management | Application layer + API gateway |
| **Governance security** | Immutable snapshot protection, compliance pathway enforcement, append-only audit, attribution integrity | Database permission layer (hard) + application layer (defense-in-depth) |

Governance security is the harder layer. Operational security can be bypassed by application bugs. Governance security cannot be bypassed even if application code contains a defect — the database permission layer enforces it unconditionally.

---

### 1.2 Historical Integrity Protection

FINALIZED snapshots in `warehouse.student_snapshots` and REPORT_PUBLISHED records in `warehouse.monthly_reports` are the platform's historical intelligence assets. Their integrity guarantees historical reproducibility (FAD-1, FAD-2, FAD-6).

Historical integrity protection means:

* No application service account may UPDATE or DELETE finalized snapshot rows or published report rows under any condition
* Database-level SELECT-only grants on the `warehouse` schema for standard service accounts are the hard enforcement mechanism
* A code defect that attempts an UPDATE against the `warehouse` schema fails at the database layer with `insufficient_privilege` — not silently
* The only lawful mutation path for finalized historical records is the Compliance Governance Pathway, executed by a dedicated service account under full pre-action audit entry requirements

Historical integrity is not a soft convention. It is a database-enforced invariant.

---

### 1.3 Lineage Integrity Protection

Every event, ingested record, state transition, and snapshot carries attribution metadata that forms the lineage chain: `origin_source`, `origin_authority`, `is_authoritative`, `attribution_timestamp`, `actor_identity`, `correlation_id`. These fields are the chain of custody for student data.

Lineage integrity means:

* Attribution fields are set by the platform at ingestion or creation time — never accepted from external API callers
* A client cannot assert SQL Server authority by sending `origin_source = mirrored_sql_server`; that value is set by the SQL Server sync service
* `attribution_timestamp` records when the event occurred in the source system; it cannot be backfilled to a different time post-ingestion
* ETL transforms that strip, overwrite, or fail to propagate attribution fields are specification violations (see `spec/05_external_integrations.md` §2.3)
* Conflicts between SQL Server-authoritative records and platform-supplementary records must retain both records; the SQL Server-authoritative record is never overwritten

Lineage integrity enables forensic reconstruction. If lineage is broken, the forensic chain is broken.

---

### 1.4 Audit Survivability

The compliance audit record is the platform's most durable artifact. Audit entries in the `compliance_audit` schema must survive even the full deletion of the student's operational and warehouse records they document.

Audit survivability means:

* `compliance_audit` schema has **no foreign key dependencies** on the `public` or `warehouse` schemas — cascade deletes cannot silently delete audit entries
* The compliance pathway service account is the only account with INSERT privileges on `compliance_audit`; the standard application service account has SELECT-only access
* No audit entry is ever modified or deleted by any code path — `compliance_audit` is INSERT-only from all service accounts
* Compliance audit entries must remain queryable and exportable after the associated student's records are deleted

Any system architecture that permits audit record deletion — whether through FK cascade, direct DELETE, or indirect cascade — is a compliance defect.

---

### 1.5 Reproducibility Preservation

Historical report reproducibility (CONC-INVARIANT-2) is a security guarantee as well as a data guarantee. Reproducibility assures auditors, operators, and compliance authorities that a report produced today reflects exactly what was true at the time it was originally generated.

Reproducibility preservation as a security concern means:

* The Snapshot Reproducibility Fingerprint (FAD-6) must not be modifiable after finalization — its five components are locked at `VALIDATING → FINALIZED`
* AI text physically copied into finalized snapshots (FAD-1) must not be mutable by any subsequent AI operation, force-refresh, or model change
* Report regeneration must produce identical output from the same source snapshot and template version — if it does not, the POTENTIALLY_DIVERGENT flag is logged and the operator is notified
* No code path may retroactively reprocess historical snapshots under a new configuration version (FAD-3 — prospective-only semantics)

Reproducibility violations are audit findings, not merely bugs.

---

### 1.6 Privileged Workflow Isolation

Certain platform operations are governed workflows, not ordinary API calls. These include:

* Snapshot finalization (VALIDATING → FINALIZED)
* Report publication (REPORT_APPROVED → REPORT_PUBLISHED)
* Configuration version activation (APPROVED → ACTIVE)
* Compliance execution (APPROVED_FOR_ACTION → IN_EXECUTION)

Each of these operations crosses an irreversible governance boundary. Each requires:

* A dedicated service account (or role-checked authorization)
* A pre-execution gate (idempotency check, pre-action audit entry, or authorization verification)
* An immutable audit record produced atomically with the transition (CONC-INVARIANT-7)

Privileged workflow isolation means these operations cannot be triggered by standard API calls, cron jobs, or webhook handlers that do not carry the required authorization context. No governance boundary may be crossed without the full precondition chain being satisfied.

---

### 1.7 Operational vs. Governance Security Actions

| Action class | Examples | Authorization model | Reversibility |
|---|---|---|---|
| **Operational** | Query student roster, trigger outreach, view AI insights, log notes | Role-based; per-request validation | Reversible or idempotent |
| **Governance** | Finalize snapshot, publish report, activate config version, execute compliance deletion | Elevated role or privileged service account; pre-authorization audit; hard gate | Irreversible; cannot be retried without new authorization |

Governance actions require additional security scrutiny at both design time and runtime. A governance action executed without its precondition chain is a compliance incident (from `spec/04_idempotency_concurrency.md` §22.8).

---

### 1.8 Mutable vs. Immutable Security Boundaries

| Boundary | Data in scope | Mutability | Enforcement mechanism |
|---|---|---|---|
| DRAFT snapshot | `public` schema draft queue | Fully mutable | Application layer |
| FINALIZED snapshot | `warehouse.student_snapshots` | Immutable | DB permission (SELECT-only for app SA) |
| REPORT_PUBLISHED report | `warehouse.monthly_reports` | Immutable | DB permission (SELECT-only for app SA) |
| ACTIVE config version | `public.config_version_registry` | Immutable once ACTIVE | Application layer + atomic activation |
| compliance_audit | `compliance_audit` schema | Append-only | DB permission (INSERT-only for compliance SA) |
| AI insight (AI_REVIEWED) | `public.ai_insights` | Attribution locked; content locked at AI_REVIEWED | Application layer |

The boundary between mutable and immutable is crossed when a governance state is reached. Security controls before the boundary permit modifications under role-based access; security controls after the boundary prohibit modifications absolutely.

---

## 2. ROLE-BASED ACCESS CONTROL (RBAC)

---

### 2.1 Platform User Roles

SSIP defines nine distinct user roles. Roles map to job functions, not technical identities.

| Role | Description |
|---|---|
| `admin` | System administrator; manages user accounts, role assignments, system configuration; does not inherently have elevated student data access |
| `operator` | Operations staff; full student roster; all quick actions; alert queue; outreach management; historical reports |
| `super_mentor` | Oversight role for multiple mentors; transitive visibility over all students assigned to supervised mentors |
| `mentor` | Primary mentor; assigned students only; coursework, lifecycle, placement readiness, AI insights, communication history |
| `instructor` | Curriculum support; assigned students only; coursework and lifecycle data; no payment or outreach access |
| `compliance_officer` | Initiates, reviews, and executes compliance workflows; reads compliance audit records; elevated for governance operations only |
| `auditor` | Read-only access to compliance audit logs, report audit logs, and snapshot lifecycle logs; no student data modification rights |
| `config_manager` | Proposes and activates configuration version changes; requires separate authorization from operations roles |
| `report_publisher` | Approves and publishes monthly reports (PRODUCTION scope; may overlap with operator role in MVP/STANDARD) |

---

### 2.2 Role Permission Matrix — Student Data and Operations

This matrix extends spec/01_requirements.md §3.20 to include governance and compliance roles.

| Feature | admin | operator | super_mentor | mentor | instructor | compliance_officer | auditor | config_manager |
|---|---|---|---|---|---|---|---|---|
| Full student roster | ✗ | ✓ | ✗ (supervised only) | ✗ (assigned only) | ✗ (assigned only) | ✗ | ✗ | ✗ |
| Payment details | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Outreach queue | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| AI insights | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| Communication history | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| Lifecycle timeline | ✗ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |
| Coursework engagement | ✗ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |
| Placement readiness | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| Quick actions | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| System alerts | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Historical reports | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Report approval / publication | ✗ | ✓ (PRODUCTION: report_publisher only) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Config version management | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |
| Compliance workflow initiation | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ |
| Compliance audit read | ✗ | ✓ (read) | ✗ | ✗ | ✗ | ✓ | ✓ | ✗ |
| Report audit log read | ✗ | ✓ | ✗ | ✗ | ✗ | ✓ | ✓ | ✗ |
| Snapshot lifecycle log read | ✗ | ✓ | ✗ | ✗ | ✗ | ✓ | ✓ | ✗ |
| User / role management | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

---

### 2.3 Schema-Level Permissions by Role

API-level permissions enforce business logic. Schema-level permissions enforce data architecture. These are not the same layer.

| Role | public schema | warehouse schema | compliance_audit schema |
|---|---|---|---|
| `admin` | Restricted to system config tables; no student data | SELECT on reports for system health | No access |
| `operator` | READ on relevant operational tables | SELECT on student_snapshots, monthly_reports, report_audit_log | SELECT (read-only audit view) |
| `super_mentor` | READ on assigned-student tables (supervisor-scoped) | No access | No access |
| `mentor` | READ on assigned-student tables only | No access | No access |
| `instructor` | READ on assigned-student coursework/lifecycle tables | No access | No access |
| `compliance_officer` | READ (student identity and history for scope definition) | SELECT | SELECT + INSERT (via compliance pathway SA) |
| `auditor` | No write; no student operational data | SELECT on report_audit_log | SELECT only |
| `config_manager` | READ + INSERT on config_version_registry only | No access | No access |
| `report_publisher` | READ + governance-gated PUBLISH action | SELECT | No access |

All write paths to `warehouse` and `compliance_audit` schemas are mediated through dedicated service accounts — not through user-session credentials.

---

### 2.4 Governance Operation Permissions

These operations cross irreversible governance boundaries. Standard role-based access is insufficient; elevated authorization is required.

| Governance Operation | Required role | Additional precondition |
|---|---|---|
| Snapshot finalization (VALIDATING → FINALIZED) | Automated (finalization service account) | All fingerprint components present; no duplicate FINALIZED row |
| Report approval (REPORT_REVIEW_PENDING → REPORT_APPROVED) | `operator` or `report_publisher` | Report in correct state; operator identity logged |
| Report publication (REPORT_APPROVED → REPORT_PUBLISHED) | `operator` or `report_publisher` | REPORT_APPROVED state confirmed; publication idempotency key checked |
| Config version activation (APPROVED → ACTIVE) | `config_manager` | Version in APPROVED state; no concurrent activation in flight |
| Compliance initiation (COMPLIANCE_REQUEST_RECEIVED) | `compliance_officer` | No existing non-terminal workflow for same student |
| Compliance authorization (→ APPROVED_FOR_ACTION) | `compliance_officer` | Scope manifest defined; authorization identity recorded |
| Compliance execution (→ IN_EXECUTION) | Compliance pathway service account | Pre-action audit entry exists in compliance_audit (hard gate) |

No governance operation may be triggered by an unauthenticated request, a scheduler without elevated context, or an API call from a role without the required permission.

---

### 2.5 Report Visibility Rules

| Report type | Visible to |
|---|---|
| Current-month draft report (REPORT_GENERATING, REPORT_GENERATED, REPORT_REVIEW_PENDING) | `operator`, `report_publisher` |
| Published report (REPORT_PUBLISHED) | `operator`, `report_publisher` |
| Historical regenerated report (all lineage versions) | `operator` |
| POTENTIALLY_DIVERGENT flagged report | `operator` (with divergence warning) |
| Report audit log | `operator`, `auditor`, `compliance_officer` |
| Report fingerprint detail | `operator`, `auditor` |

Mentors and instructors do not have access to published reports. AI narrative text embedded in reports is accessible to operators only.

---

### 2.6 Historical Artifact Visibility

| Artifact | Visible to | Notes |
|---|---|---|
| `warehouse.student_snapshots` | `operator` (via report API) | Not directly queryable by mentors or instructors |
| `warehouse.snapshot_ai_narratives` | `operator` (via snapshot/report APIs) | Physical copy of AI text; same access as the snapshot |
| `warehouse.monthly_reports` | `operator`, `report_publisher` | Mentor-facing summaries are a future capability; not currently in scope |
| `warehouse.report_audit_log` | `operator`, `auditor`, `compliance_officer` | |
| `compliance_audit.deletion_log` | `compliance_officer`, `auditor` | Standard operators have read-only view; not direct table access |
| Snapshot Reproducibility Fingerprint | `operator`, `auditor` | Queryable via fingerprint inspection endpoint |

---

### 2.7 Super Mentor Transitive Visibility

Super mentors have transitive access to all students assigned to their supervised mentors. This transitive access must be enforced at query time, not at data ingest time.

* A super mentor's student roster is derived dynamically from the current supervision graph: all `(mentor_id → student_id)` assignments where the mentor is supervised by the super mentor
* The supervision graph is an external input (see spec/01 §11.2 open assumption D-2); until it is resolved, super mentor roster queries return an empty set or error rather than a full-roster fallback
* Super mentor access MUST NOT silently escalate to full operator-level access when the supervision graph is undefined
* Every super mentor roster query must log the supervision graph reference used, for auditability

---

## 3. SCHEMA ISOLATION & DATA GOVERNANCE

---

### 3.1 Three-Schema Security Boundary

The three PostgreSQL schemas form three independent security domains with distinct mutability and access profiles. This is not a logical convention — it is an enforced database architecture (see `spec/09_warehouse_physical_architecture.md` §1.3 and §1.4).

```
public schema:         READ+WRITE for standard application service account
warehouse schema:      SELECT-only for standard service account; INSERT-only for finalization SA
compliance_audit:      SELECT-only for standard service account; INSERT-only for compliance SA
```

The security significance of this three-schema isolation:

* A bug in application code that attempts an UPDATE on `warehouse.student_snapshots` fails with a PostgreSQL `insufficient_privilege` error — it cannot succeed even in error
* A bug in application code that attempts an INSERT to `compliance_audit.deletion_log` fails for the same reason — only the compliance pathway SA can write there
* A cascade DELETE on a public schema record cannot delete its corresponding warehouse or compliance_audit records — no FK dependencies exist between schemas (FAD-4)

---

### 3.2 public Schema Security Profile

| Property | Value |
|---|---|
| Access | Standard application service account: READ + WRITE |
| Mutability | Full CRUD for operational tables; append-only convention for audit log tables |
| Governance boundary | None at the schema level; governance boundaries are enforced by application state machines |
| Sensitive tables | `student_trigger_data` (student PII), `ai_insights` (AI content), `outreach_history` (communication records) |
| Append-only by convention | `outreach_history`, `state_transition_log`, `student_campaign_activity`, `student_quick_action_log`, `processed_events` |

API access to sensitive public schema tables must enforce role-based scoping at the application layer. The database does not perform row-level filtering by assignment or role.

---

### 3.3 warehouse Schema Security Profile

| Property | Value |
|---|---|
| Access | Standard service account: SELECT-only; finalization service account: INSERT-only |
| Mutability | INSERT-only from finalization SA; no UPDATE or DELETE from any application account |
| Governance enforcement | Database-level SELECT grant for standard SA; INSERT grant for finalization SA |
| Who may delete | Compliance pathway service account only; requires COMPLIANCE_HOLD → COMPLIANCE_DELETED workflow |
| What cannot happen | In-place modification of FINALIZED snapshots or REPORT_PUBLISHED records — ever |

The `warehouse` schema is the platform's append-only historical archive. No application service may modify records once inserted. This is the primary technical enforcement of the INVARIANT-1 (append-only finalized reporting) from `spec/03_state_transition_rules.md`.

---

### 3.4 compliance_audit Schema Security Profile

| Property | Value |
|---|---|
| Access | Standard service account: SELECT-only; compliance pathway SA: INSERT-only |
| Mutability | INSERT-only, forever — no UPDATE or DELETE from any account |
| FK dependencies | None — no FK references to public or warehouse schema tables |
| What cannot happen | Any application code path deleting or modifying an audit entry |
| Survivability | Compliance audit entries outlive the student data they document |

The `compliance_audit` schema is governance-isolated infrastructure. It is not an ordinary application database schema. Its purpose is legal chain-of-custody, not operational functionality.

---

### 3.5 Cross-Schema FK Independence as a Security Guarantee

The absence of foreign key constraints between schemas is a deliberate security design, not an oversight.

* If `compliance_audit.deletion_log` had a FK on `public.student_trigger_data(UserID)`, a CASCADE DELETE of a student's public record would delete the audit entries documenting that deletion — destroying the chain of custody
* FK independence means operational deletions never cascade to the compliance audit layer
* FK independence means warehouse records do not depend on public operational records for referential integrity; a student's operational record can be deleted without breaking their snapshot history
* Application-layer references (snapshot looks up student data) are acceptable; database-layer FK constraints across schemas are not

---

### 3.6 Survivability Expectations

| Schema | Survives what |
|---|---|
| `compliance_audit` | Full deletion of a student's `public` and `warehouse` records; database-level FK cascade; application schema evolution |
| `warehouse` | Deletion of a student's `public` operational records; does NOT survive compliance pathway deletion (that is the authorized path) |
| Lifecycle log tables in `public` | Normal operational deletes; not subject to cascade from outreach or student records |

A compliance audit record that documents the deletion of student records must remain intact indefinitely. There is no retention limit for compliance audit entries.

---

## 4. SERVICE ACCOUNT GOVERNANCE

---

### 4.1 Standard Application Service Account

The standard application service account is the runtime identity used by the FastAPI application for all routine operations.

**Access:**

| Schema | Grants |
|---|---|
| `public` | SELECT, INSERT, UPDATE, DELETE on all operational tables |
| `warehouse` | SELECT only on all warehouse tables |
| `compliance_audit` | SELECT only on all compliance_audit tables |

**Responsibilities:** All student data reads, outreach state machine writes, AI insight generation and storage, configuration version reads, GHL sync writes, campaign activity logging, idempotency key storage.

**Prohibited operations:** INSERT, UPDATE, DELETE on `warehouse`; INSERT on `compliance_audit`; direct execution of governance boundary transitions that require elevated service accounts.

---

### 4.2 Finalization Service Account

The finalization service account is the runtime identity used exclusively by the snapshot finalization service at the `VALIDATING → FINALIZED` governance boundary.

**Access:**

| Schema | Grants |
|---|---|
| `public` | SELECT only (reads student_trigger_data, ai_insights, config_version_registry) |
| `warehouse` | INSERT only on student_snapshots, snapshot_ai_narratives, monthly_reports, report_audit_log |
| `compliance_audit` | No access |

**Responsibilities:** Writing FINALIZED snapshot rows and AI narrative copies to the warehouse schema. Writing report generation records and audit log entries.

**Prohibited operations:** UPDATE or DELETE anywhere; INSERT into `compliance_audit`; full CRUD on `public` schema operational tables.

**Operational accountability:** Every INSERT by the finalization service account must carry a `correlation_id` linking it to the finalization job that triggered it. The finalization service account should never be used for any purpose other than finalization.

---

### 4.3 Compliance Pathway Service Account

The compliance pathway service account is the runtime identity used exclusively by the Compliance Governance workflow at the `APPROVED_FOR_ACTION → IN_EXECUTION` governance boundary.

**Access:**

| Schema | Grants |
|---|---|
| `public` | SELECT; DELETE on student-identifiable tables (scoped to compliance action targets only) |
| `warehouse` | SELECT; DELETE on student_snapshots, snapshot_ai_narratives (scoped to compliance action targets only) |
| `compliance_audit` | INSERT only (no UPDATE or DELETE — audit entries are permanent) |

**Responsibilities:** Executing authorized compliance deletions and anonymizations; writing pre-action and post-action audit entries to `compliance_audit`; transitioning snapshots to COMPLIANCE_DELETED state.

**Prohibited operations:** INSERT into warehouse except via standard pathways; UPDATE or DELETE on `compliance_audit`; usage outside the Compliance Governance workflow.

**Operational accountability:** The compliance pathway service account is the most privileged account in the platform. Every use must be:
* Authorized by a pre-action audit entry in `compliance_audit`
* Scoped to the specific `workflow_id` and `scope_manifest` approved
* Logged with the compliance officer identity who authorized the action

The compliance pathway service account MUST NOT be used for any non-compliance purpose. Credential access to this account must be restricted to the compliance workflow service component only.

---

### 4.4 Config Activation Accountability

Configuration version activation (`APPROVED → ACTIVE`) is a governance operation that is atomic and globally serialized (see `spec/04_idempotency_concurrency.md` §18.1). Accountability requirements:

* The activating identity (`activated_by`) is recorded in the `config_version_registry` version record
* The activation is performed through the standard application service account (no separate SA required), but the `config_manager` role is required
* The prior active version's `superseded_at` timestamp is set atomically with the new version's `activated_at`
* Every activation produces a structured log entry: activating identity, version IDs (prior and new), `effective_from` timestamp, `correlation_id`

No activation may proceed without a documented `change_rationale` and an `authorized_by` identity recorded in the version record.

---

### 4.5 AI Orchestration Boundary

The AI orchestration layer (AI insight generation, snapshot narrative assembly) runs under the standard application service account. No separate service account is required. However, the following security constraints apply specifically to AI orchestration:

* AI prompts are assembled by the platform and must contain no PII (see §7.4)
* AI provider API keys are environment-injected and must not appear in any log output, prompt payload, or snapshot content
* AI responses are validated against the declared output schema before storage; invalid responses are retried or failed, never stored as-is
* Prompt version is captured at AI_PENDING creation and is immutable from that point (see `spec/04_idempotency_concurrency.md` §17.3)
* AI orchestration events produce structured log entries that include: `prompt_version`, `model_version`, `latency_ms`, `outcome` — never AI content text in the log

---

### 4.6 Ingestion Service Boundary

Ingestion services (SQL Server sync, GHL webhook processing) run under the standard application service account. Security constraints:

* SQL Server connection uses a **read-only** SQL Server login; the SQL Server RBAC enforces this at the database layer, not merely by application convention
* The SQL Server login for SSIP must have `SELECT` only on `AI_ChatBot_TriggerData`; no INSERT, UPDATE, DELETE, or DDL grants
* GHL webhook handlers must validate webhook signatures before processing any payload (signature verification mechanism per UI-3 in `spec/05_external_integrations.md` §15)
* Attribution fields (`origin_source`, `origin_authority`, `is_authoritative`) on ingested records are set by the ingestion service — never accepted from the webhook payload
* A GHL webhook that fails signature verification is rejected with 401; no payload data is processed

---

### 4.7 Privilege Separation and Operational Accountability

The three-service-account model enforces privilege separation:

* Standard account: cannot write to historical archive (warehouse) or audit schema (compliance_audit)
* Finalization account: can write to warehouse but cannot write to compliance_audit and cannot DELETE from anywhere
* Compliance account: can DELETE from public and warehouse within scoped compliance actions; can write audit entries

This separation means:
* A bug in the standard application service cannot corrupt historical archives
* A bug in the finalization service cannot corrupt compliance audit records
* The compliance account's DELETE privilege is the only path for historical record deletion — and it requires a hard-gated audit entry precondition

Every service account must have its own credential set. Shared credentials between accounts are prohibited.

---

## 5. API SECURITY MODEL

---

### 5.1 Authentication Boundary

Every API request must authenticate before any resource is accessed or any operation is executed. Unauthenticated access to student data is prohibited (spec/01 §4.6 and §6).

Authentication requirements by scope:

| Scope | Authentication mechanism |
|---|---|
| MVP | Simple token or session-based authentication |
| STANDARD | Authenticated sessions with role claims; role validated per request |
| PRODUCTION | Secure token-based authentication with expiry; MFA for governance-operation roles |

Authentication must occur at the application entry point, before any database access or business logic execution. The authentication result (authenticated identity + role claims) is the authorization context for the entire request lifecycle.

---

### 5.2 Authorization Boundary

Authorization is enforced at every endpoint, per request. Authorization rules:

* Every protected endpoint validates the authenticated user's role against the required role for that endpoint
* Role validation is not cached — it is checked on every request
* Student data endpoints enforce assignment scoping for mentor and instructor roles: the student's assigned mentor must match the authenticated identity
* Governance operation endpoints enforce the required governance role (see §2.4)
* Authorization failure returns 403 Forbidden with a structured error body; the error body does not include details about what the correct role would be

Authorization checking must be implemented as a consistent middleware or decorator pattern; per-endpoint ad-hoc checks are not permitted.

---

### 5.3 Immutable Resource Protection

API endpoints that represent immutable resources must enforce immutability at the API layer in addition to the database layer.

| Resource | Immutability rule |
|---|---|
| FINALIZED snapshot | No PUT, PATCH, or DELETE endpoint may target a FINALIZED snapshot; only GET and governance-pathway endpoints |
| REPORT_PUBLISHED report | No in-place modification endpoint; regeneration creates a new version via dedicated endpoint |
| ACTIVE config version | No edit endpoint for ACTIVE version; activation creates a new superseding version |
| compliance_audit entries | No DELETE or PATCH endpoint for audit entries under any condition |

An API that returns a 2xx response to a PUT against a FINALIZED snapshot is a specification defect, not an implementation choice.

---

### 5.4 Lineage Inspection API Security

Lineage inspection endpoints (fingerprint queries, snapshot audit log queries, report lineage queries) are read-only operations. Their security profile:

* Operator role required for all lineage inspection; mentors and instructors have no access
* Lineage endpoints do not expose PII beyond what the requester is already authorized to see
* Snapshot fingerprint endpoint returns the five fingerprint components without exposing the raw AI content text
* Attribution endpoints return `origin_source`, `origin_authority`, `actor_identity` — sufficient for forensic audit without exposing operationally sensitive student data

---

### 5.5 Regeneration API Security

Report regeneration creates a new report version from archived snapshot data. Security requirements:

* Operator role required (historical reports are not accessible to mentors)
* Regeneration is read-only from the snapshot perspective; the source FINALIZED snapshot is not modified
* Regeneration audit log entry includes: requesting actor identity, request timestamp, source snapshot fingerprint, correlation ID
* If the source snapshot is in COMPLIANCE_HOLD state, regeneration proceeds but the regeneration audit log notes the hold status
* Unauthorized regeneration attempts (wrong role, invalid state) return 403 Forbidden

Regeneration operations do not make new AI provider calls (FAD-1). An endpoint that triggers a new LLM call as part of "historical regeneration" is a specification defect.

---

### 5.6 Compliance API Security

Compliance workflow endpoints are the most sensitive in the API surface. Security requirements:

* `compliance_officer` role required for all compliance workflow initiation, review, and authorization
* Compliance execution (`APPROVED_FOR_ACTION → IN_EXECUTION`) is performed by the compliance pathway service account; it is not triggered by a user-facing API call but by an internal governance workflow step
* The compliance intake endpoint validates that no non-terminal workflow exists for the student before accepting the request (duplicate rejection)
* Pre-action audit entry creation must be atomic with the state transition to IN_EXECUTION (CONC-INVARIANT-7)
* All compliance workflow transitions are logged with: actor identity, workflow ID, timestamp, correlation ID

The compliance API must not surface student data beyond what is required for scope definition. A compliance officer initiating a workflow does not gain operator-level access to the student's operational data.

---

### 5.7 AI Insight API Security

AI insight endpoints carry AI-generated advisory content. Security requirements:

* Role-based access: operators, super mentors, primary mentors may read current AI insights; instructors may not
* `force_refresh` parameter requires the same role as normal read access; it does not require elevated authorization
* AI insight history (archived versions) is accessible to operators; not to mentors or instructors
* The AI insight API must not return PII fields in the response; AI content text may contain context derived from anonymized metrics, but never raw PII
* Attribution metadata (`model_used`, `prompt_version`, `generated_at`) is always returned with AI insight responses for auditability

---

### 5.8 Report Publication API Security

Report approval and publication require elevated authorization in PRODUCTION scope. Security requirements:

* PRODUCTION scope: `report_publisher` role required for REPORT_APPROVED → REPORT_PUBLISHED transition
* MVP/STANDARD scope: auto-approval; `operator` role required for any publication trigger
* Report publication is idempotent; duplicate publication attempts return the existing REPORT_PUBLISHED record, not an error
* The publication event is logged with the publishing actor's identity and a correlation ID
* Publication of a report that contains data from a student under COMPLIANCE_HOLD is blocked until the hold is resolved or the report is regenerated excluding the affected student

---

### 5.9 Forbidden Operations

The following operations are explicitly forbidden at the API layer, regardless of role or authentication status:

* Any endpoint that would UPDATE or DELETE a FINALIZED snapshot row
* Any endpoint that would UPDATE or DELETE a REPORT_PUBLISHED report row (regeneration creates a new version via the regeneration endpoint, not modification)
* Any endpoint that would directly write to `compliance_audit` schema (the compliance pathway SA handles this internally)
* Any endpoint that accepts client-supplied values for `origin_source`, `origin_authority`, or `is_authoritative` fields
* Any endpoint that accepts client-supplied `attribution_timestamp` values for SQL Server-authoritative events
* Any regeneration endpoint that makes a new LLM call for historical AI content (must use physical copy from snapshot row)
* Any endpoint that skips the pre-action audit gate for compliance execution

---

### 5.10 Replay Attack Prevention

Defense against replay attacks at the API layer:

* Authentication tokens (STANDARD and PRODUCTION) carry expiry; expired tokens are rejected
* Idempotency keys checked before all side-effecting operations (see `spec/04_idempotency_concurrency.md` §4)
* A request replayed with a stale token is rejected with 401 Unauthorized
* Webhook signature verification prevents replayed webhook payloads (GHL webhook authentication, when implemented per UI-3)
* Duplicate detection in `processed_events` table prevents replay of ingestion operations with the same event ID

---

### 5.11 Attribution Tampering Prevention

Attribution fields are set by the platform, not accepted from external callers.

* The sync service sets `origin_source = mirrored_sql_server` on all SQL Server-derived records; this field is never accepted from a client payload
* GHL webhook handlers set `origin_source = ghl_webhook` and `origin_authority = platform_supplementary`; these are not configurable by the GHL caller
* The `is_authoritative` flag is set to `true` only for SQL Server-authoritative events and `false` for all others; no API caller can assert this flag
* `correlation_id` is generated at the platform entry point; any `correlation_id` in an inbound request payload is discarded and replaced with a platform-generated UUID

---

## 6. SECRET & CREDENTIAL GOVERNANCE

---

### 6.1 SQL Server Credentials

* SQL Server connection credentials are injected via environment variable (`MSSQL_DSN`)
* The SQL Server login used by the platform must be configured as **READ-ONLY** at the SQL Server RBAC layer — `SELECT` only on `AI_ChatBot_TriggerData`, no `INSERT`, `UPDATE`, `DELETE`, or DDL
* Read-only enforcement at the SQL Server level is a defense-in-depth requirement; the application must never write to SQL Server regardless (spec/01 §6), but the database-level grant prevents it even if application code contains a write attempt
* SQL Server credentials must not appear in any log output; connection string references in logs use `<redacted>` for password components
* Credential rotation requires a container environment variable update and restart; no code changes required

---

### 6.2 PostgreSQL Service Account Credentials

Three separate PostgreSQL credentials must exist:

| Account | Use | Credential storage |
|---|---|---|
| Standard application SA | All operational CRUD | `DATABASE_URL` environment variable |
| Finalization SA | Warehouse INSERT | `FINALIZATION_DATABASE_URL` environment variable |
| Compliance pathway SA | Compliance DELETE and compliance_audit INSERT | `COMPLIANCE_DATABASE_URL` environment variable |

Sharing a single database credential for all three accounts is a security defect. The three accounts enforce privilege separation; sharing credentials eliminates that separation.

Credential access:
* Only the finalization service component has access to `FINALIZATION_DATABASE_URL`
* Only the compliance workflow service component has access to `COMPLIANCE_DATABASE_URL`
* Standard application code must not reference the finalization or compliance credentials

---

### 6.3 AI Provider Credentials

* AI provider API keys (Anthropic, OpenAI) are injected via environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`)
* API keys must not appear in any structured log output — log lines referencing AI calls redact the key entirely
* API keys must not appear in AI prompts, snapshot content, or any database-stored field
* API key rotation: STANDARD scope requires a service restart; PRODUCTION scope requires hot-reload capability (see `spec/05_external_integrations.md` UI-5)
* The AI provider credential is the only platform credential that is sent to an external system; its exposure window is therefore larger than database credentials and rotation policy must account for this

---

### 6.4 Communication Provider Credentials

* GHL API key and webhook signing secret are injected via environment variables
* The GHL webhook signing secret is used for signature verification of inbound webhook payloads; it must not be logged
* If the GHL webhook signing secret is rotated, the platform must be updated with the new secret before webhooks can be processed
* Communication provider credentials must not be embedded in platform-generated outreach payloads

---

### 6.5 Environment Separation

| Environment | Credential rule |
|---|---|
| Local development | Developer-specific credentials for local PostgreSQL instances; no production SQL Server access; AI provider keys for individual developer accounts (not shared production keys) |
| CI/CD | Isolated test credentials; no production SQL Server or AI provider keys; test PostgreSQL instances |
| Staging | Production-equivalent credential structure with staging-specific values; separate SQL Server read-only login pointing to staging/test data |
| Production | Production credentials; injected via container environment; not accessible to developers without explicit escalation |

Developer access to production credentials requires explicit authorization and must be auditable. Production credential access for debugging purposes is a temporary elevated privilege, not an ongoing entitlement.

---

### 6.6 Credential Rotation

| Credential | Rotation frequency | Rotation mechanism |
|---|---|---|
| SQL Server login | Per enterprise IT policy; platform requires restart on rotation | Environment variable update + container restart |
| PostgreSQL service account passwords | Per security policy (recommended: 90-day maximum for sensitive accounts) | Environment variable update + container restart |
| AI provider API keys | On provider-suggested rotation schedule or on any suspicion of compromise | Environment variable update; PRODUCTION: hot-reload target |
| GHL API key | Per GHL policy or on compromise | Environment variable update + container restart |
| GHL webhook secret | On GHL rotation or on compromise | Coordinate with GHL; update before webhook signature verification breaks |

Credential rotation must not require code changes. All credentials are environment-injected.

---

### 6.7 Developer Access Boundaries

* Developers do not have production credentials by default
* Production database access for debugging requires an explicit, time-limited authorization with audit log entry
* No developer may use the compliance pathway service account credentials for any development or debugging purpose
* Local development uses local PostgreSQL instances; no connection to production SQL Server
* AI provider keys used in development should be separate accounts from production where the provider supports it

---

### 6.8 Secrets in Code and Snapshots — Prohibition

The following are strictly prohibited:

* Any credential, API key, password, or connection string hardcoded in source code
* Any credential embedded in a snapshot row, AI insight content, or compliance audit entry
* Any credential committed to the git repository, including in `.env` files
* Any credential logged in structured or unstructured log output
* Any credential included in a prompt payload sent to an AI provider

If a secret is accidentally committed to the repository, it must be treated as compromised: rotate immediately, then clean the history.

---

## 7. TRANSCRIPT & AI CONTENT SECURITY

---

### 7.1 Transcript Access Controls

Conversation transcripts (stored in `outreach_history.llm_analysis` or related fields) are sensitive communication records. Access requirements:

* Operators have access to transcripts for students in their roster
* Mentors have access to transcripts for their assigned students
* Instructors do not have access to transcripts
* Transcripts must not be returned in bulk list endpoints; access is always per-student
* Transcript content is not logged in structured logs (only metadata: sentiment outcome, model used, latency)

Transcripts that are exported as part of a compliance action scope follow the FERPA governance pathway (see §9.3).

---

### 7.2 AI Narrative and Insight Access Controls

AI-generated insights and narratives (`ai_insights.content_text`) carry advisory content derived from student operational data. Access:

| AI content type | Access |
|---|---|
| `risk_summary` | Operators, super mentors, primary mentors |
| `progress_summary` | Operators, super mentors, primary mentors |
| `intervention_recommendation` | Operators, super mentors, primary mentors |
| `communication_sentiment` | Operators, super mentors, primary mentors |
| `trend_interpretation` | Operators, super mentors, primary mentors |
| `monthly_narrative` | Operators only |
| AI insight version history (archived versions) | Operators only |

Instructors have no access to AI insight content. Compliance officers have read access for scope definition purposes only; they do not routinely access AI insights.

AI insights are advisory. They are not shared with students. AI insight content is not disclosed outside the platform boundary.

---

### 7.3 Frozen Snapshot Narrative Immutability

AI text physically copied into `warehouse.student_snapshots` and `warehouse.snapshot_ai_narratives` at FINALIZED state is frozen content (FAD-1).

Security guarantees:

* No API endpoint may update or overwrite frozen snapshot narrative text after FINALIZED
* Force-refresh of an `ai_insights` record has zero effect on the frozen text in the snapshot row (INVARIANT-3)
* A compliance deletion of an `ai_insights` record does not affect the frozen text in the snapshot — there is no FK dependency
* Historical report regeneration reads the frozen text from the snapshot row; it does not reconstruct AI content from the current `ai_insights` state
* The only lawful mechanism for removing frozen snapshot narrative text is the Compliance Governance Pathway (COMPLIANCE_HOLD → COMPLIANCE_DELETED)

Any implementation that re-derives or re-fetches AI content from the AI provider during historical report regeneration is a specification defect, not a performance optimization.

---

### 7.4 PII Prohibition in AI Prompts

AI prompts must never contain:

* Student names (FirstName, LastName)
* Email addresses
* Phone numbers
* Student identifiers (UserID, ClassSignupsID) in a form that could be reverse-mapped to a real individual outside the platform
* Any other direct identifiers per FERPA definitions

Permitted in AI prompts:
* Anonymized academic metrics: `HWsBehind`, `AvgEffRating`, `LastActivityDays`
* Program context: curriculum path name, weeks in program, section progress percentage
* Risk classification labels: `AT_RISK`, `CRITICAL`, `HIGH_PAYMENT_RISK`
* Aggregated statistics: cohort averages, program benchmarks

Prompt construction is a platform responsibility. No external caller may provide prompt content. Prompt templates are versioned; each version is reviewed before activation to confirm PII prohibition compliance.

---

### 7.5 Privacy Boundaries for AI Content

* AI insight content is operator/mentor advisory only; it is never shared with the student directly
* AI narrative content in published reports is not publicly accessible; report access is operator-gated
* AI providers receive only prompt payloads (anonymized metrics); they do not receive raw student records or database dumps
* AI provider responses are stored in `ai_insights`; the response metadata is logged; the content text is not logged

---

### 7.6 Retention Expectations

AI insight records (`ai_insights`) have the following retention characteristics:

* AI_REVIEWED (current): retained until superseded by a newer version
* AI_ARCHIVED (prior versions): retained indefinitely by application code; subject to FERPA retention policy (U-9 unresolved)
* AI content embedded in finalized snapshots: retained with the snapshot per the warehouse retention policy (U-9 unresolved)
* Post-FERPA-deletion: AI insight records for a deleted student are removed via the Compliance Governance Pathway; the snapshot AI text copy is removed with the snapshot row

Until U-9 (snapshot retention policy) is resolved by Legal/Compliance, no AI content is automatically deleted.

---

### 7.7 Export Controls

AI content and transcripts are not freely exportable. Export requirements:

* Compliance audit exports: governance-controlled; auditor or compliance officer role required; format TBD (see UI-7 in `spec/05_external_integrations.md`)
* Report exports (PDF-renderable payload): operator role required; the export request is logged with actor identity and timestamp
* Bulk AI insight exports: not supported in current scope; any bulk export of student data requires compliance officer authorization

---

## 8. AUDIT & ATTRIBUTION INTEGRITY

---

### 8.1 Attribution Field Integrity

The following attribution fields are set by the platform at ingestion or event creation time. They are immutable after creation:

| Field | Who sets it | When it is set | Modifiable after? |
|---|---|---|---|
| `origin_source` | Platform (sync service, webhook handler, scheduler) | At record creation | No |
| `origin_authority` | Platform | At record creation | No |
| `is_authoritative` | Platform (SQL Server sync sets to `true`; all others `false`) | At record creation | No |
| `attribution_timestamp` | Platform (occurrence time from source system) | At record creation | No |
| `actor_identity` | Platform (authenticated user identity or service account name) | At event creation | No |
| `correlation_id` | Platform (generated at request entry point, propagated) | At request entry | No |
| `model_used`, `prompt_version` | Platform (AI orchestration service) | At AI_GENERATED state | No |
| `source_snapshot_fingerprint` | Platform (report generation service) | At report job creation | No |

No external caller may supply, overwrite, or modify any of these fields.

---

### 8.2 Origin Source Immutability

`origin_source = mirrored_sql_server` with `origin_authority = sql_server_authoritative` is the highest-trust attribution value in the platform. It must be protected:

* Only the SQL Server sync service may create records with `origin_source = mirrored_sql_server`
* Any API endpoint that accepts `origin_source` as a client-supplied parameter must validate that the caller cannot supply `mirrored_sql_server` or `sql_server_authoritative` values
* A platform-supplementary event that arrives for the same `(user_id, event_type, attribution_timestamp)` as an existing SQL Server-authoritative record must not overwrite it (both are retained; conflict is logged per CONC-INVARIANT-7)
* ETL processes that transform sync data must not strip or overwrite `origin_source` during processing (spec/05 §2.3)

---

### 8.3 Audit Log Survivability

Every lifecycle domain produces append-only log entries (INVARIANT-4 from `spec/03_state_transition_rules.md`):

| Domain | Log table | Survivability guarantee |
|---|---|---|
| Outreach | `state_transition_log` | Append-only convention; retained indefinitely |
| Snapshot | `snapshot_lifecycle_log` | Append-only; retained with warehouse |
| Report | `warehouse.report_audit_log` | Append-only; INSERT-only for finalization SA |
| AI Insight | `ai_insight_lifecycle_log` | Append-only convention |
| Config Version | Embedded in `config_version_registry` transitions | Version records are never deleted |
| Compliance | `compliance_audit.deletion_log` | Append-only, permanent, governance-isolated |

A state transition without an audit log entry is not a committed transition (CONC-INVARIANT-7). The audit log entry and the state transition are atomic; neither commits without the other.

---

### 8.4 Tamper Resistance Expectations

| Audit artifact | Tamper resistance mechanism |
|---|---|
| compliance_audit entries | Database-level INSERT-only via compliance pathway SA; no UPDATE/DELETE from any account |
| warehouse.report_audit_log | Database-level INSERT-only via finalization SA; no UPDATE/DELETE from any application account |
| state_transition_log | Application-layer append-only convention; no delete code path |
| snapshot_lifecycle_log | Application-layer append-only convention; no delete code path |

The database-level enforcement on `compliance_audit` and `warehouse` schemas means even a compromised application service account cannot tamper with audit records. Tamper resistance is strongest where the stakes are highest (compliance audit > warehouse > public schema logs).

---

### 8.5 Append-Only Audit Guarantees

No audit record in any domain is deleted or modified by application code. Rules:

* An audit entry that requires correction creates a NEW entry referencing the original as a correction record; the original is not modified
* Compliance audit entries are never deleted — there is no code path that DELETEs from `compliance_audit` schema under any condition
* If a duplicate audit entry is inadvertently created (race condition), both entries are retained; the duplicate is logged as a warning, not resolved by deletion
* Log rotation or archival of application logs does not apply to database-level audit tables; those are permanent

---

### 8.6 Privileged Audit Visibility

Audit records contain sensitive information about governance operations. Visibility must be restricted:

| Audit record type | Read access |
|---|---|
| compliance_audit.deletion_log | `compliance_officer`, `auditor`; operators have a read-only view without raw `scope_manifest_snapshot` |
| warehouse.report_audit_log | `operator`, `auditor`, `compliance_officer` |
| snapshot_lifecycle_log | `operator`, `auditor` |
| AI insight lifecycle log | `operator` |
| state_transition_log | `operator` |
| config_version_registry history | `operator`, `config_manager`, `auditor` |

Audit records must not be accessible to mentors or instructors. The audit records contain operational details (actor identities, scope manifests, compliance rationales) that are not relevant to teaching or mentoring workflows.

---

### 8.7 Compliance Survivability Rules

Compliance audit survivability is a legal obligation, not a design preference:

* `compliance_audit` schema has no FK dependencies on `public` or `warehouse` schemas (FAD-4)
* Compliance audit records created before a student's records are deleted must remain intact after the deletion
* The compliance audit schema must be independently exportable for external auditor review
* Compliance audit entries must be importable to an external compliance system if the platform migrates architectures (the FK-independence design enables this without data loss)
* There is no expiry or TTL on compliance audit records; they are permanent

---

## 9. PRIVACY & FERPA GOVERNANCE

---

### 9.1 Student Data Classification

All student data in the platform derives from SQL Server educational records and is governed by FERPA (Family Educational Rights and Privacy Act) for applicable institutions.

| Data class | FERPA applicability | Platform protection |
|---|---|---|
| Student identity (name, email, phone) | Educational record | Access restricted; PII excluded from AI prompts; not logged |
| Academic metrics (HWsBehind, AvgEffRating, etc.) | Educational record | Role-gated; anonymized before AI processing |
| Enrollment and program data | Educational record | Role-gated; SQL Server authoritative |
| AI-generated assessments (risk summaries, narratives) | Platform-derived; treated as educational record | Role-gated; operator/mentor advisory only |
| Communication records (transcripts, GHL messages) | Potentially educational record | Role-gated; transcript PII excluded from AI prompts |
| Payment data | Financial record; potentially FERPA | Operator-only; not accessible to mentors or instructors |
| Compliance audit records | Governance record | Compliance officer and auditor only |

FERPA governs access to educational records. The platform's role-based access control is the FERPA access control mechanism. Every role with access to student data has a legitimate educational interest defined in §2.

---

### 9.2 Minimum Necessary Access

Each role receives the minimum data access required for its function:

* Mentors see only their assigned students and only the data relevant to mentoring (coursework, lifecycle, placement, AI insights)
* Instructors see only coursework and lifecycle data — no payment, no AI insights, no communication records
* Compliance officers access student data only for scope definition of compliance actions; they do not gain routine operational visibility
* AI providers receive only anonymized metrics (§7.4) — the minimum required for insight generation
* GHL receives only the contact information and outreach metadata required for communication execution — not AI outputs, not payment data, not academic metrics

Data access boundaries are enforced at the API layer. Returning data beyond what a role needs, even if it is "just informational," is a minimum necessary access violation.

---

### 9.3 FERPA Deletion Pathway

FERPA and similar regulations may require deletion of a student's educational records upon request. The platform's Compliance Governance Pathway (spec/01 §4.7, spec/03 Domain 6) is the authorized deletion mechanism.

The FERPA deletion pathway requires:

1. Compliance request received and logged
2. Review by compliance authority
3. Scope manifest defining all affected tables and records
4. Pre-action audit entry in `compliance_audit` schema
5. Execution via compliance pathway service account
6. Post-action audit entry documenting all deletions

FERPA deletions follow the same Compliance Governance Pathway as any other compliance deletion. FERPA provides the legal basis (`audit_rationale` in the pre-action audit entry); the pathway governs the execution.

A FERPA deletion that bypasses the compliance pathway is a compliance defect, not a feature.

---

### 9.4 Historical Deletion Annotations

When a FERPA or compliance deletion removes a student's snapshot data after that data contributed to a published aggregate report:

* The published aggregate report statistics are **not** retroactively recalculated (this is by design per spec/01 §7 edge case and spec/03 §37.4)
* The published report record is annotated with a `compliance_action_flag` indicating that a student's records were removed after original publication
* The report remains in REPORT_PUBLISHED state; it does not become invalid
* Future consumers of the report must note that annotated reports may contain aggregated statistics derived from data that is no longer present in the system

This annotation model preserves the historical record while acknowledging its post-hoc modification. Whether this satisfies FERPA obligations for aggregated data is an unresolved legal question (see US-3).

---

### 9.5 AI Processing Privacy Constraints

AI processing involves transmitting data to third-party AI providers. Privacy constraints:

* Only anonymized metrics are transmitted to AI providers (see §7.4)
* The platform's FERPA obligations extend to data shared with AI providers — data processing agreements with providers must cover student record handling
* AI providers must not use transmitted student metrics to train their models; confirm this in the provider's data processing agreement (see US-4)
* AI-generated content is returned to the platform and stored in `ai_insights`; it does not remain at the AI provider
* No AI provider receives historical snapshot data or compliance audit records

---

### 9.6 Communication Log Privacy

Communication records (GHL messages, outreach history, campaign activity) are sensitive records:

* Communication logs are role-gated: operators, super mentors, and primary mentors may access them; instructors may not
* Inbound student communications (GHL inbound messages) are the most sensitive: they reflect the student's direct voice; access is gated to operators and assigned mentors
* Communication log export is not supported without compliance officer authorization
* Communication records of a deleted student are removed as part of the FERPA deletion scope manifest

---

### 9.7 Export Governance

| Export type | Authorization | Logging requirement |
|---|---|---|
| Monthly report export (PDF/JSON) | Operator role | Actor identity, timestamp, correlation_id |
| Historical report export | Operator role | Same; audit log records the source snapshot fingerprint |
| Compliance audit export | Compliance officer or auditor role | Full export request logged in compliance_audit |
| Student data export (individual) | Operator role + compliance officer authorization | Full audit trail; not self-service |
| Bulk student data export | Not supported without compliance pathway authorization | Same |

Exports that contain PII are treated as data disclosures. Every data disclosure must be loggable.

---

### 9.8 Cross-System Propagation Expectations

The platform shares data with external systems. Data sharing boundaries:

| System | What is sent | What is prohibited from being sent |
|---|---|---|
| GHL | Student contact information (name, email, phone for outreach), checkpoint metadata, outreach trigger context | AI assessments, payment data, academic risk scores, compliance records |
| AI providers | Anonymized academic metrics, program context | Student PII, SQL Server raw records, snapshot data, compliance data |
| SQL Server | Nothing — SQL Server is read-only; the platform never writes to it | All platform-generated data |

Platform-generated data (AI insights, snapshots, compliance records) must never be propagated back to SQL Server or to GHL beyond the scoped outreach execution context.

---

### 9.9 Historical Reproducibility vs. FERPA Tension

FERPA requires deletion of educational records upon request. Historical reproducibility requires that archived reports remain identical to their original form. These two requirements are in tension.

The platform's resolution:

* Individual student snapshots are deleted via the Compliance Governance Pathway
* Aggregate reports that incorporated the deleted student's data are annotated with `compliance_action_flag` but not regenerated
* The aggregate statistics in the published report remain from the original generation (before deletion)
* Future trend analysis for that student returns gaps for deleted months

Whether this resolution satisfies FERPA requirements for aggregate reports that contain a deleted student's contributions is an unresolved legal question (US-3). Legal/Compliance must confirm the resolution before the first production snapshot is taken.

---

## 10. OBSERVABILITY & LOGGING SECURITY

---

### 10.1 PII Redaction Rules

The following fields must never appear in structured log output:

| Field | Redaction rule |
|---|---|
| `Email` | `***@***` |
| `PhoneNumber` | `***` |
| `FirstName`, `LastName` | `[REDACTED]` in production; may appear in development/staging with explicit opt-in |
| `UserID` as a naked identifier | Log as a hashed or opaque reference in logs that may be externally accessible |
| `ClassSignupsID` | `[REDACTED]` |
| Any field containing direct PII | `[REDACTED]` |

Structured logging events must contain `student_id` as a hash or internal opaque identifier for correlation, not raw PII fields. Operators investigating a specific student can correlate the hash to the actual student via the platform UI, not by reading logs.

---

### 10.2 Credential Redaction

The following must never appear in any log output:

* Database connection strings and passwords
* AI provider API keys
* SQL Server credentials
* GHL API key and webhook signing secret
* Internal service account tokens

Log lines that reference credential-carrying variables must substitute `<redacted>` for the credential value. Example: `"Connecting to AI provider with key <redacted>"`. This is required in both structured and unstructured logs.

---

### 10.3 AI Output Logging Constraints

AI generation events produce structured log entries with metadata only — never AI content text:

**Log: AI generation event**
```json
{
  "event": "ai_insight_generated",
  "student_id": "<opaque_ref>",
  "insight_type": "risk_summary",
  "prompt_version": "v3.2",
  "model_used": "claude-sonnet-4-6",
  "latency_ms": 2340,
  "outcome": "success",
  "correlation_id": "uuid"
}
```

The `content_text` field (the actual AI narrative) must **never** appear in a log entry. AI narrative content is PII-adjacent; it contains assessments derived from educational records. Log consumers must not be able to reconstruct student assessments from log streams.

---

### 10.4 Audit-Event Logging

All governance boundary transitions produce structured audit-event log entries in addition to database audit records:

```json
{
  "event": "governance_transition",
  "domain": "snapshot",
  "entity_id": "snapshot_id",
  "from_state": "VALIDATING",
  "to_state": "FINALIZED",
  "actor_identity": "finalization_service_account",
  "attribution_timestamp": "ISO-8601",
  "correlation_id": "uuid",
  "fingerprint_components": {
    "schema_version": "0002",
    "config_registry_version": "V3",
    "ai_prompt_version": {"risk_summary": "v3.1"},
    "ai_model_version": {"risk_summary": "claude-sonnet-4-6"},
    "report_template_version": "t2.0"
  }
}
```

Governance boundary transitions include: FINALIZED, REPORT_PUBLISHED, ACTIVE config version, IN_EXECUTION (compliance), COMPLIANCE_DELETED.

---

### 10.5 Privileged Operation Logging

In addition to database audit records, structured log entries are required for:

| Operation | Required log fields |
|---|---|
| SQL Server sync | `rows_synced`, `schema_drifts_detected`, `duration_ms`, `correlation_id` |
| Config version activation | `prior_version_id`, `new_version_id`, `activated_by`, `effective_from`, `correlation_id` |
| Compliance execution | `workflow_id`, `action_type`, `affected_tables`, `row_counts_per_table`, `correlation_id` |
| Historical report regeneration | `source_snapshot_id`, `source_fingerprint`, `original_fingerprint`, `divergence_flag`, `requesting_actor`, `correlation_id` |
| Report publication | `report_id`, `cohort_id`, `report_month`, `lineage_version`, `publishing_actor`, `correlation_id` |

These structured log entries are the operational equivalent of the database audit records. Both must exist; neither replaces the other.

---

### 10.6 Log Storage and Retention

* Structured logs are written to stdout and captured by the container runtime
* Structured logs must not be written to ad-hoc files; log rotation and retention are the container orchestration layer's responsibility
* Governance audit log entries in the database (compliance_audit, report_audit_log) are permanent; they are not subject to log rotation
* Application logs (stdout) are subject to retention policies defined at the infrastructure layer; the compliance audit schema is the authoritative audit record, not the log stream

---

### 10.7 Anti-Pattern Prohibition

The following logging anti-patterns are specification violations in this codebase:

* `console.log(studentRecord)` — unstructured; may contain PII
* Catching exceptions with `except Exception as e: log(str(e))` where `str(e)` may contain PII from the exception context
* Logging the full request body for endpoints that accept student data
* Logging AI output text as part of "debug" output
* Logging SQL queries that contain interpolated student PII values

Logs must never become shadow databases of student records. The structured logging discipline is a privacy protection, not merely a log hygiene preference.

---

## 11. SECURITY FAILURE & RECOVERY

---

### 11.1 Credential Compromise

**Scenario:** An environment variable containing a service account credential or API key is exposed.

**Containment:**
1. Rotate the compromised credential immediately — it is now treated as fully compromised from the time of exposure
2. Revoke the old credential at the source (SQL Server RBAC, PostgreSQL role password, AI provider dashboard, GHL dashboard)
3. Deploy the new credential via environment variable update and container restart
4. Audit all writes and reads made under the compromised credential during the exposure window; check for unauthorized data access or modifications

**Recovery expectation:** Credential rotation must be possible without code changes, schema migrations, or extended downtime. All credentials are environment-injected by design.

**Forensic survivability:** The audit log contains `actor_identity` on all governance boundary transitions. If the compromised credential was used for a governance operation, the audit log records the operation. The compliance audit is append-only; it cannot be retroactively erased.

---

### 11.2 Privilege Escalation Attempt

**Scenario:** An authenticated user in a lower-privilege role attempts to access an endpoint or operation requiring a higher-privilege role.

**Response:**
1. Return 403 Forbidden with a structured error body (no information about the correct role in the error body)
2. Log the failed attempt with: authenticated identity, attempted endpoint, required role, actual role, `correlation_id`
3. Do not expose any response body that reveals the existence of the resource being accessed (403 is appropriate; not 404 with details)

**Escalation alert:** Repeated privilege escalation attempts from the same identity within a short window should trigger an operator alert.

---

### 11.3 Audit Corruption Attempt

**Scenario:** Code or an actor attempts to UPDATE or DELETE a record in `compliance_audit` or `warehouse.report_audit_log`.

**Behavior:** The database rejects the attempt with `insufficient_privilege` — the compliance pathway SA and finalization SA only have INSERT access to these tables. The application surfaces the error as an unexpected system error.

**Alert:** Any `insufficient_privilege` error on a compliance_audit or warehouse table from a service account that should not have that access is a security incident. Alert immediately; investigate.

The database enforcement means this attempt cannot succeed even if it originates from a code defect. Document the attempt in the platform's security incident log.

---

### 11.4 Replay Attack Detection

**Scenario:** A prior authenticated request is replayed to trigger a side-effecting operation a second time.

**Defense:** Idempotency keys checked before all side-effecting operations (spec/04). Expired authentication tokens rejected with 401. `processed_events` table deduplicates event-based ingestion.

**Detection:** A replay that reaches idempotency key checking is logged as a duplicate attempt with the original and replay `correlation_id`. Repeated replay attempts from the same token or payload are an audit indicator of attack, not a routine event.

---

### 11.5 Unauthorized Regeneration Attempt

**Scenario:** A non-operator role attempts to access the historical report regeneration endpoint.

**Response:** 403 Forbidden; attempt logged with actor identity and `correlation_id`.

**Additional check:** Regeneration endpoints validate that the source snapshot exists in FINALIZED or REGENERATED state before proceeding. An attempt to regenerate from a non-existent or non-FINALIZED snapshot returns 404 or 409 (Conflict), not 200 with empty data.

---

### 11.6 Unauthorized Config Activation

**Scenario:** An operator (not `config_manager`) attempts to activate a configuration version.

**Response:** 403 Forbidden; attempt logged.

**Additional check:** The atomic activation invariant (exactly one ACTIVE version) means even a successful unauthorized activation would be detected — it would produce a duplicate ACTIVE version window, which is a system defect alert.

**Containment:** If an unauthorized activation somehow succeeded (which the role check should prevent), the recovery path is to create a new version record that supersedes the unauthorized one and restore the previous values — since rollback to a prior version is forbidden (per FAD-3), the fix requires a new version authoring.

---

### 11.7 Failed Compliance Operations

**Scenario:** A compliance execution (`APPROVED_FOR_ACTION → IN_EXECUTION`) fails mid-execution (partial deletion, post-action audit write failure).

**Classification:** This is an incident, not a retryable error (per spec/04 §22.8 and spec/03 §41.5).

**Response:**
1. Workflow transitions to UNDER_REVIEW
2. Partial execution is documented in `compliance_audit`: which tables were completed, which were not, row counts for each
3. Human compliance authority review required before retry
4. Retry scope manifest excludes already-completed tables to prevent double-deletion
5. Post-action audit write failure: emergency recovery write required immediately; treat as an incident

No compliance execution failure is silently ignored. Every failure produces a compliance audit entry documenting the failure state.

---

### 11.8 Containment and Recovery Expectations

| Incident class | Containment | Recovery |
|---|---|---|
| Credential compromise | Rotate immediately; audit access window | New credentials deployed via env update |
| Governance boundary violation attempt (e.g., direct DELETE on warehouse) | DB enforcement rejects it; alert generated | Investigate source; fix application defect |
| Unauthorized governance state transition | Application rejects; attempt logged | Audit log preserved; investigate |
| Partial compliance execution | Workflow to UNDER_REVIEW; audit logged | Human review + scoped retry |
| Post-action audit write failure | Immediate emergency audit write | Human review of completeness |
| Duplicate FINALIZED snapshot | DB enforcement rejects second finalization; idempotency log preserved | No recovery needed; system resolved correctly |
| Compliance audit record deletion attempt | DB enforcement rejects (INSERT-only SA); alert generated | Document the attempt; investigate |

---

### 11.9 Forensic Survivability

The platform must support forensic investigation of security incidents. Forensic survivability requirements:

* `correlation_id` is propagated through all database writes, log entries, and external API calls — a single ID traces the full lifecycle of any request
* Governance boundary transitions are atomically logged (state transition + audit entry in same transaction)
* Compliance audit entries survive even if operational data is deleted
* Report audit log entries in `warehouse.report_audit_log` survive as long as the warehouse schema is intact
* Service account identity (`actor_identity`) is recorded on every governance operation

If a forensic investigation requires reconstructing "who did what, when, in what order," the correlation IDs and append-only audit logs provide the complete chain. A system that cannot answer these questions from its audit records is non-compliant with INVARIANT-4.

---

## 12. FUTURE SECURITY EXTENSIBILITY

---

These are conceptual architecture extensions. No implementation is implied by this section.

---

### 12.1 SSO Integration

Single sign-on via SAML 2.0 or OIDC would allow institutional identity providers to authenticate users directly. Role claims would be delivered as SAML attributes or OIDC claims from the IdP, eliminating platform-local user management for large deployments. The platform's role model (§2.1) maps cleanly to IdP group membership.

---

### 12.2 MFA

Multi-factor authentication for governance-operation roles (`compliance_officer`, `config_manager`, `report_publisher`) reduces the risk of credential compromise enabling unauthorized governance actions. TOTP-based MFA or hardware security key support would require identity provider integration or a dedicated MFA layer.

---

### 12.3 Enterprise RBAC

Dynamic role assignment (rather than static role configuration) via an external authorization server (e.g., Open Policy Agent) would enable fine-grained permission changes without code deployments. The permission matrix in §2.2 represents the stable permission model; its evaluation could be delegated to an external policy engine.

---

### 12.4 Field-Level Encryption

Encrypting PII fields (`Email`, `PhoneNumber`, `FirstName`, `LastName`) at rest, with decryption only at the application layer, provides an additional layer of protection against database dump exposure. Field-level encryption requires key management infrastructure and adds latency to PII-field queries.

---

### 12.5 Row-Level Security

PostgreSQL row-level security (RLS) could enforce mentor-student assignment scoping at the database layer, eliminating the risk of application-layer scoping bugs. RLS would require each database session to carry the authenticated user's identity as a session variable. This is architecturally compatible with the current three-schema model.

---

### 12.6 Customer-Managed Keys

Institutions operating under strict data residency or encryption requirements may need to manage their own encryption keys. Customer-managed key (CMK) support would require integration with an external KMS (AWS KMS, Azure Key Vault, HashiCorp Vault) and transparent encryption of the PostgreSQL data volumes.

---

### 12.7 External Audit Integrations

The `compliance_audit` schema is designed to be independently exportable (no FK dependencies, no external references). Future integration with a dedicated audit system (Splunk, Elastic SIEM, dedicated compliance audit SaaS) would pull from this schema without requiring access to operational data. The schema's FK independence enables this migration without data loss.

---

## 13. ACCEPTANCE CRITERIA

---

### AC-1 — Immutable Historical Protection

**Given** a FINALIZED snapshot row exists in `warehouse.student_snapshots`
**When** the standard application service account attempts an UPDATE on any field in that row
**Then** the database rejects the operation with `insufficient_privilege`; the snapshot row is unchanged; the application surfaces this as an unexpected system error, not a silent no-op

---

### AC-2 — Audit Survivability

**Given** a student's records in `public` and `warehouse` schemas are deleted via the Compliance Governance Pathway
**When** `compliance_audit.deletion_log` is queried for that student
**Then** pre-action and post-action audit entries are present, unmodified, and fully populated; no FK cascade deleted them; the entries are queryable independently of the deleted student's records

---

### AC-3 — Governance Isolation

**Given** a compliance workflow is in `APPROVED_FOR_ACTION` state
**When** a standard application service account attempts to transition the workflow to `IN_EXECUTION` without a pre-action audit entry in `compliance_audit`
**Then** the transition is blocked; the workflow remains in `APPROVED_FOR_ACTION`; the attempt is logged with actor identity; an incident alert is raised

---

### AC-4 — Least Privilege Enforcement

**Given** an authenticated user with the `mentor` role queries the historical reports endpoint
**When** the request is processed
**Then** the request is rejected with 403 Forbidden; no historical report data is returned; the attempt is logged with the mentor's identity and `correlation_id`

---

### AC-5 — Attribution Integrity

**Given** a GHL webhook delivers a message event with a client-supplied `origin_source = mirrored_sql_server` field in the payload
**When** the webhook handler processes the event
**Then** the client-supplied `origin_source` value is discarded; the platform sets `origin_source = ghl_webhook` and `origin_authority = platform_supplementary`; the event is stored with platform-assigned attribution

---

### AC-6 — Reproducibility Protection

**Given** a FINALIZED snapshot has AI narrative text physically copied into `warehouse.snapshot_ai_narratives`
**When** an AI force-refresh operation is performed for the same student and insight type
**Then** the snapshot row in `warehouse.snapshot_ai_narratives` is unchanged; the force-refresh creates a new `ai_insights` record only; no code path modifies the warehouse copy

---

### AC-7 — Compliance Workflow Isolation

**Given** an authenticated user with `operator` role attempts to initiate a compliance deletion workflow
**When** the request is processed
**Then** the request is rejected with 403 Forbidden; the compliance deletion API requires `compliance_officer` role; the operator's attempt is logged; no compliance workflow record is created

---

## 14. DOWNSTREAM IMPLICATIONS AND UNRESOLVED SECURITY CONCERNS

---

### 14.1 API Implications (spec/07_api_contracts.md)

| Requirement | Implication |
|---|---|
| Role-based endpoint access | Every protected endpoint requires role validation middleware; role matrix from §2.2 must be enforced at each endpoint |
| Governance operation gating | Governance endpoints return 403 (not 404) on role mismatch; they do not leak resource existence |
| Attribution field protection | Request schemas for ingestion endpoints must exclude client-controllable attribution fields |
| Immutable resource endpoints | No PUT/PATCH/DELETE endpoints for FINALIZED snapshots or REPORT_PUBLISHED records |
| Compliance API gating | Compliance workflow endpoints require `compliance_officer` role; scope manifest must be validated before APPROVED_FOR_ACTION |

---

### 14.2 Service Implications

| Requirement | Implication |
|---|---|
| Three service accounts | Connection string environment variables for each account; service components use only their designated connection |
| Finalization service boundary | Finalization service must not be callable from standard API routes; it is an internal governance service |
| Compliance pathway service boundary | Compliance pathway service must not be callable without a valid `workflow_id` and `pre_action_audit_entry_id` |
| PII-free AI prompts | Prompt assembly service must filter PII fields before sending to AI provider; no raw SQL Server record fields in prompts |

---

### 14.3 Scheduler Implications

| Requirement | Implication |
|---|---|
| Scheduler attribution | All scheduler-triggered events carry `actor_identity = scheduler` and a fresh `correlation_id` |
| Snapshot batch accountability | The finalization service account, not the standard service account, is used for warehouse INSERTs |
| Compliance workflow gating | Schedulers must not trigger compliance execution; compliance workflows require human authorization at `APPROVED_FOR_ACTION` |

---

### 14.4 Observability Implications

| Requirement | Implication |
|---|---|
| PII redaction | Structured log formatting must apply PII redaction rules (§10.1) before emitting log events |
| Governance event logging | All governance boundary transitions emit structured log events in addition to database audit records |
| Credential redaction | API clients (AI provider, GHL, SQL Server) must log outbound call metadata without including credential values |

---

### 14.5 Deployment Architecture Implications

| Requirement | Implication |
|---|---|
| Three-SA model | Production deployment must configure three separate PostgreSQL roles with distinct grants before first startup |
| SQL Server read-only login | SQL Server RBAC must grant SELECT-only on AI_ChatBot_TriggerData to the SSIP login; no other grants |
| Credential injection | All six credential types (SQL Server, 3 PostgreSQL SAs, AI provider, GHL) must be injectable via environment variables without code changes |

---

### 14.6 Unresolved Security Concerns

These concerns are documented and tracked. Each requires external input before the dependent security model is finalized.

| # | Concern | Severity | Required from | Urgency |
|---|---|---|---|---|
| US-1 | Authentication mechanism not specified — JWT vs. session cookies vs. API keys; affects token expiry, MFA readiness, SSO integration surface | **HIGH** | Engineering / Product | HIGH — must resolve before multi-user PRODUCTION deployment |
| US-2 | SQL Server read-only enforcement at SQL Server RBAC level — must confirm the SQL Server login is configured with SELECT-only grants, not assumed by application convention | **HIGH** | IT / Engineering | HIGH — should be verified before first production SQL Server connection |
| US-3 | FERPA obligations for aggregate reports containing a deleted student's data — whether annotating the report satisfies FERPA or whether aggregate recalculation is legally required | **HIGH** | Legal / Compliance | HIGH — must resolve before first production snapshot |
| US-4 | AI provider data processing agreements — whether Anthropic/OpenAI DPAs cover student data handling under FERPA; confirm providers do not use transmitted metrics for model training | **MEDIUM** | Legal / Engineering | HIGH — must resolve before AI insights are generated for real students |
| US-5 | Compliance audit export credential model — how compliance auditors access `compliance_audit` data (read-only credentials vs. signed export mechanism); format TBD (see spec/05 UI-7) | **MEDIUM** | Compliance / Engineering | MEDIUM — resolve before compliance pathway goes to production |
| US-6 | GHL webhook signature verification — mechanism not yet defined; STANDARD tier requires verification before production use (see spec/05 UI-3) | **MEDIUM** | Engineering (GHL API review) | MEDIUM — resolve before GHL webhook processing is live |
| US-7 | Row-level security for super mentor supervision graph — super mentor assignment scoping depends on resolution of open assumption D-2 (spec/01 §11.2); RLS cannot be implemented until supervision graph source is defined | **LOW** | Engineering / Operations | LOW for STANDARD; HIGH before PRODUCTION multi-role deployment |

---

## 15. SCOPE-SPECIFIC BEHAVIOR

---

### MVP Scope

| Concern | Behavior |
|---|---|
| Authentication | Simple token or session-based; single admin role |
| Authorization | Minimal role enforcement; operator role only |
| Schema permissions | Three-SA model defined but may use shared credentials in local dev; MUST be separate in any shared deployment |
| PII in prompts | Enforced regardless of scope |
| Audit logging | State transition log and outreach history required; compliance audit not yet operational |
| Credential governance | Environment variable injection required; no hardcoded secrets |

---

### STANDARD Scope

| Concern | Behavior |
|---|---|
| Authentication | Authenticated sessions with role claims; mentor and instructor role separation |
| Authorization | Role matrix from §2.2 enforced at all student data endpoints |
| Schema permissions | Three-SA model fully deployed; separate credentials per service account |
| Audit logging | Full lifecycle log tables operational; warehouse.report_audit_log operational |
| GHL webhook | Signature verification recommended; STANDARD tier target |
| Attribution integrity | Full attribution field enforcement; no client-controllable attribution fields |

---

### PRODUCTION Scope

| Concern | Behavior |
|---|---|
| Authentication | Secure token-based auth with expiry; MFA for governance roles (compliance_officer, config_manager) |
| Authorization | Full role matrix enforced; super mentor transitive visibility; report_publisher role separation |
| Compliance pathway | Fully operational with separate service account; FERPA deletion supported |
| AI provider DPA | Confirmed before first real student AI processing |
| GHL webhook auth | Signature verification required before production webhook processing |
| Audit | Complete audit trail for all six lifecycle domains; compliance_audit export capability |
| Observability | Full PII redaction in production logs; governance event logging |

---

## 16. REFERENCES

---

Canonical inputs:

* `spec/01_requirements.md` — §3.20 (RBAC), §4.6 (security NFRs), §4.7 (reporting warehouse immutability, compliance audit area), §6 (constraints), §9.2 (AI non-responsibilities), §11.2 (open assumptions D-2, U-9), §13 (FAD-1 through FAD-6)
* `spec/03_state_transition_rules.md` — §17 (snapshot finalization preconditions), §37 (compliance authorization boundary), §38 (compliance invariants), §39 (event attribution standard), §40 (cross-domain invariants, INVARIANT-1 through INVARIANT-7)
* `spec/04_idempotency_concurrency.md` — §2.5 (irreversible operations), §19.6 (audit survivability), CONC-INVARIANT-1 through CONC-INVARIANT-7
* `spec/05_external_integrations.md` — §2 (integration philosophy), §3 (authoritative boundary model), §10 (compliance and governance integration), §15 (UI-1 through UI-7)
* `spec/07_api_contracts.md` — API endpoint definitions; role-based visibility matrix
* `spec/08_data_model.md` — §13 (schema ownership architecture, access control matrix), §19 (compliance governance model), §22 (cross-domain data invariants)
* `spec/09_warehouse_physical_architecture.md` — §1.3 (append-only enforcement), §1.4 (immutable history enforcement), §2.9 (compliance audit physical domain)
* `alembic/versions/0002_warehouse_schema.py` — warehouse schema physical grants; compliance_audit schema creation
* `alembic/versions/0003_config_version_registry.py` — config_version_registry access model

---

## END OF FILE
