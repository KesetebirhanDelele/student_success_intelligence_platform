# directives/agent_ownership_matrix.md

---

## LAYER 3 — DIRECTIVES (OPERATIONAL AUTHORITY ARCHITECTURE)

---

> **Version note:** This file was completely rewritten on 2026-05-26 to reflect the finalized governed historical intelligence platform architecture established in `directives/core_decision_engine.md`, `directives/outreach_eligibility_rules.md`, `directives/outreach_retry_policy.md`, `directives/channel_selection_rules.md`, `directives/escalation_rules.md`, `directives/llm_processing_contract.md`, and `directives/ghl_integration_contract.md`. The previous version described a simplistic agent responsibility matrix (generic role labels, single-owner assignment table, 12-row ownership matrix, no governance context, no replay semantics, no authority boundaries) that is architecturally incompatible with the governance-safe orchestration-intelligence platform defined in spec/01 through spec/09. Ownership is no longer generic responsibility mapping. It is governance-safe operational authority architecture.

---

## 1. PURPOSE

---

### 1.1 What This Directive Defines

The **Operational Authority Architecture** defines the bounded authority model for all actors — human and automated — that operate within the Student Success Intelligence Platform. It specifies:

* What authority each actor class holds, within which domains, and under what governance constraints
* What actions are permitted, prohibited, or approval-gated for each actor class
* How human override authority is exercised without corrupting immutable lineage or bypassing compliance holds
* How automation authority is bounded to prevent orchestration services from acting beyond their governance mandate
* How AI advisory authority is enforced as advisory-only — never as authorization, escalation, or governance decision
* How provider authority is constrained to execution telemetry delivery — never as governance source
* How replay authority is strictly isolated from LIVE operations
* How attribution and auditability requirements apply to every authority action
* How escalation ownership is transferred, acknowledged, and closed under governance constraints

This directive is the authoritative specification for **governance-safe operational authority**. It is consumed by:

* All service layer implementations as the reference for what authority classes may call what operations
* The escalation routing service when determining who may act on escalation advisory outputs
* Compliance workflows when evaluating whether an actor class is authorized for a given compliance action
* Audit and observability pipelines when constructing authority attribution records

---

### 1.2 What Ownership Is NOT

In the governance-safe operational authority model, ownership is explicitly **NOT**:

* **Generic responsibility mapping** — "who handles X" without authority boundaries is not ownership; it is organizational convenience
* **Static role assignment** — authority is bounded by governance domain, not by job title or system component label
* **Operational convenience assignment** — an actor class performing an action informally does not constitute authority; authority must be explicitly defined here
* **Mutable historical ownership** — authority records for past actions are immutable; no retroactive reassignment of authority is permitted
* **Provider authority** — external systems (GHL, AI providers) do not hold ownership over governance actions; they hold execution and advisory roles only
* **AI governance authority** — AI advisory output informs orchestration decisions; it does not constitute authority to make them

---

### 1.3 Authority Scope Definitions

Five explicit scopes apply to all authority classifications in this directive:

| Scope | Definition | Mutability |
|---|---|---|
| **Authority scope** | The set of governance actions an actor class may take without external approval | Defined here; immutable for historical records |
| **Approval scope** | Actions an actor class may initiate but that require approval from a higher authority before execution | Defined here; approval records append-only |
| **Override scope** | Actions an actor class may take to alter an automation-produced decision, with mandatory audit trail | Defined here; override records append-only |
| **Operational scope** | Actions an actor class takes in the normal course of their role, within bounded authority | Defined here; all produce attribution records |
| **Governance scope** | Actions that cross a governance boundary (config activation, compliance execution, FINALIZED mutation) | Strictly human-owned; no automation bypass |

---

## 2. AUTHORITY DOMAINS

---

### 2.1 Canonical Authority Domain Definitions

The platform's operational authority is organized into nine canonical domains. Each domain has a designated authority class — human-owned, automation-owned, external-bounded, or advisory-only.

| Domain | Authority class | Owner | Automation may act | Advisory-only | Immutable |
|---|---|---|---|---|---|
| **Governance Authority** | Human-owned | Governance Administrator | Never | No | Yes (historical records) |
| **Orchestration Authority** | Automation-owned | Core Decision Engine (advisory); Orchestration Services (execution) | Yes, within intent boundary | No | No (operational state) |
| **Execution Authority** | Automation-owned | State Management Service, Outreach Orchestration Service | Yes, under governance authorization | No | No |
| **Replay Authority** | Automation-owned, SHADOW-only | Replay Services | Yes, SHADOW only | No | Yes (replay records) |
| **Provider Authority** | External-bounded | GHL, AI Providers | Execution telemetry delivery only | Yes (AI); Execution telemetry (GHL) | No |
| **AI Advisory Authority** | Advisory-only | AI Advisory Systems | Advisory output only | Yes | No |
| **Escalation Authority** | Human-owned | Escalation Operators, Super Mentors | Escalation candidacy signaling (automation); routing and closure (human) | No | Yes (escalation records) |
| **Compliance Authority** | Human-owned | Compliance Operators | Never (automation may not initiate compliance actions) | No | Yes (compliance_audit records) |
| **Operational Override Authority** | Human-owned | Operational Administrators, Super Mentors | Never (overrides require human actor) | No | Yes (override records) |

---

### 2.2 Domain Interaction Rules

* **Authority does not transfer across domains.** An actor with Execution Authority does not hold Governance Authority. An actor with Operational Override Authority does not hold Compliance Authority.
* **Automation may signal but not authorize.** Orchestration services may produce escalation candidacy signals (via `EscalationOrchestrationAssessment`). The act of routing, acknowledging, and closing escalation belongs to the Escalation Authority domain — exclusively human-owned.
* **Advisory outputs do not constitute authorization.** AI advisory output and orchestration assessment outputs are consumed by the relevant authority domain. They do not grant the consuming service authority to act beyond its defined domain.
* **Historical domain records are immutable.** Once an authority action is recorded in the audit log, the record is append-only. No actor may modify, delete, or retroactively reassign authority in historical records.

---

## 3. AUTHORITY ACTOR DEFINITIONS

---

### 3.1 Governance Administrator

**Authority domain:** Governance Authority

**Allowed actions:**
* Activate a new config version (transitions previous ACTIVE to SUPERSEDED; new version becomes ACTIVE)
* Authorize config version supersession following the governance approval chain (spec/01 §12.8)
* Initiate compliance workflow authorization (approves COMPLIANCE_REQUEST_RECEIVED → APPROVED_FOR_ACTION transition)
* Authorize emergency authority delegation (UE-OWN5; not yet defined — governance decision required)

**Prohibited actions:**
* Retroactively alter any ACTIVE or SUPERSEDED config version record
* Execute compliance deletions directly (compliance execution belongs to Compliance Authority domain)
* Trigger outreach or escalation directly (Execution Authority domain)
* Access warehouse or compliance_audit schemas except via read-authorized API endpoints

**Replay restrictions:** Governance Administrator actions in replay context are SHADOW-only; no config version activation or compliance workflow authorization may be executed in replay mode.

**Escalation authority:** None direct. Governance escalation signals from the escalation routing service may require governance administrator decision; see §6.

**Audit obligations:** Every config version activation produces an `activation_actor_id` audit record in `config_version_registry`. Every compliance authorization produces a pre-action audit entry in `compliance_audit` before `IN_EXECUTION`.

**Attribution requirements:** `actor_identity = governance_administrator`, `attribution_timestamp`, `correlation_id` on all governance actions.

---

### 3.2 Operational Administrator

**Authority domain:** Operational Override Authority

**Allowed actions:**
* Execute operator quick actions: `FORCE_RETRY`, `CLOSE_CASE`, `MARK_CONTACTED`, `REOPEN_CASE`, `PAUSE_OUTREACH`
* Adjust student-level operational configuration (contact cadence notes, intervention flags)
* Acknowledge escalation cases routed to the operational tier
* Trigger full-table SQL Server sync on explicit demand
* Trigger AI insight force-refresh for a specific student
* Trigger report regeneration from a FINALIZED snapshot

**Prohibited actions:**
* Activate or deactivate config versions (Governance Authority domain)
* Initiate or approve compliance workflow actions (Compliance Authority domain)
* Alter `warehouse.student_snapshots` or `warehouse.snapshot_ai_narratives` directly
* Execute compliance deletions or anonymizations
* Override a compliance hold on a student without compliance operator authorization

**Replay restrictions:** Operational quick actions executed in replay context are SHADOW-only. Force-retry in SHADOW mode produces an advisory output, not a live dispatch.

**Escalation authority:** May acknowledge and route escalation cases to Escalation Operators. May close operational escalation cases with mandatory audit record.

**Audit obligations:** Every quick action produces an audit log entry: `actor_identity`, `action_type`, `student_id`, `attribution_timestamp`, `correlation_id`, `prior_state`, `new_state`.

**Attribution requirements:** `actor_identity = operational_administrator`, `origin_source = platform_operator_action`, `is_authoritative = false` (override actions are platform-supplementary relative to SQL Server-authoritative state).

---

### 3.3 Escalation Operator

**Authority domain:** Escalation Authority

**Allowed actions:**
* Acknowledge escalation cases routed to the escalation tier
* Route escalation to the appropriate operator (Mentor, Super Mentor, Governance Administrator)
* Record escalation interventions: meeting notes, intervention flags, outcome annotations
* Close escalation cases with a mandatory outcome record
* Trigger mentor assignment for a student in escalation state

**Prohibited actions:**
* Activate config versions or approve compliance workflows
* Override compliance holds (Compliance Authority domain)
* Execute force-retry or case-close outside the escalation workflow without Operational Administrator authority
* Alter warehouse records directly

**Replay restrictions:** Escalation acknowledgements in replay context are SHADOW-only and produce `REPLAY_ESCALATION_CANDIDATE` scope assessments (per `directives/escalation_rules.md` §6). No real escalation routing occurs in replay.

**Escalation authority:** Full escalation acknowledgement, routing, and closure authority within the operational tier. May not close governance-tier escalations without Governance Administrator involvement.

**Audit obligations:** Every escalation action produces an escalation lineage record: `actor_identity`, `action_type`, `escalation_type`, `escalation_id`, `attribution_timestamp`, `outcome`.

**Attribution requirements:** `actor_identity = escalation_operator`, `origin_source = platform_operator_action`, `correlation_id` propagated from originating escalation advisory.

---

### 3.4 Mentor

**Authority domain:** Operational Override Authority (restricted)

**Allowed actions:**
* Record student intervention notes and mentorship activity
* Flag students for escalation review
* Acknowledge assigned escalation cases at the student contact tier
* Request force-retry for a specific student (requires Operational Administrator approval)

**Prohibited actions:**
* Close escalation cases (Escalation Operator authority)
* Execute force-retry without approval
* Activate config versions, approve compliance workflows, or trigger compliance actions
* Alter any warehouse record
* Override a compliance hold

**Replay restrictions:** All mentor actions in replay context are SHADOW-only; no student-facing actions are produced.

**Escalation authority:** May flag escalation candidacy; may not route, close, or acknowledge escalation beyond the student contact tier.

**Audit obligations:** All mentor intervention records append to `student_timeline_events` with `origin_source = platform_mentor_action`, `actor_identity`, `attribution_timestamp`.

**Attribution requirements:** `actor_identity = mentor:{mentor_id}`, `is_authoritative = false`.

---

### 3.5 Super Mentor

**Authority domain:** Operational Override Authority (elevated); Escalation Authority (partial)

**Allowed actions:**
* All Mentor allowed actions
* Close escalation cases at the operational tier with mandatory outcome record
* Execute `CLOSE_CASE` and `FORCE_RETRY` without Operational Administrator approval (within audit obligations)
* Assign and reassign mentors to students
* Override intervention flags set by system automation

**Prohibited actions:**
* All Mentor prohibited actions apply
* May not close governance-tier escalations

**Replay restrictions:** Same as Mentor; all actions in replay are SHADOW-only.

**Escalation authority:** Full operational-tier escalation closure authority. May not close governance-tier or compliance-tier escalations.

**Audit obligations:** Same as Escalation Operator. Every case closure produces a mandatory outcome record.

**Attribution requirements:** `actor_identity = super_mentor:{mentor_id}`, `is_authoritative = false`.

---

### 3.6 AI Advisory Systems

**Authority domain:** AI Advisory Authority (advisory-only)

**Allowed actions:**
* Generate risk summaries, progress narratives, intervention recommendations, sentiment classifications, and monthly narratives
* Produce `AIAssessment` objects with governance-tier classifications (CONFIDENT, ADVISORY, STALE, IN_FLIGHT, UNAVAILABLE, FINALIZED_COPY)
* Provide advisory confidence scores that may influence priority ordering within orchestration decisions

**Prohibited actions:**
* Authorize any orchestration action, outreach dispatch, or state transition
* Override SQL Server-authoritative eligibility state
* Override deterministic rule evaluation outcomes
* Create escalation candidacy without rule-based basis (AP-AI14 / AP-OWN3)
* Generate live AI inference during replay or regeneration (AP-AI5 / AP-OWN2)
* Modify `warehouse.snapshot_ai_narratives` after finalization (FAD-1)
* Claim governance authority over any lifecycle domain

**Replay restrictions:** Live AI provider calls are suppressed in replay/regeneration. FINALIZED_COPY is the exclusive AI content source in those contexts.

**Escalation authority:** None. AI advisory output may elevate escalation severity if governance tier is CONFIDENT (per `directives/escalation_rules.md` Rule 14) but may not originate escalation candidacy.

**Audit obligations:** Every AI inference produces an audit record: `model_used`, `prompt_version`, `ai_version_number`, `correlation_id`, `confidence_score`, `ai_governance_tier`.

**Attribution requirements:** `actor_identity = ai_assessment_v{N}`, `origin_authority = platform_supplementary`, `is_authoritative = false`.

---

### 3.7 Core Decision Engine

**Authority domain:** Orchestration Authority (advisory)

**Allowed actions:**
* Synthesize multi-domain inputs into `OrchestrationIntent` objects: `INITIATE_OUTREACH`, `RETRY_OUTREACH`, `ESCALATE_TO_OPERATOR`, `DEFER_PENDING_AI`, `NO_ACTION`
* Produce eligibility assessments, retry assessments, escalation candidacy signals, and channel advisory inputs
* Route orchestration intents to the appropriate downstream service

**Prohibited actions:**
* Execute outreach directly
* Mutate student state directly
* Execute compliance actions
* Publish reports directly
* Finalize snapshots directly
* Override governance invariants (INVARIANT-1 through INVARIANT-7, spec/03 §40)

**Replay restrictions:** Orchestration intents produced in replay context carry `execution_mode = SHADOW`. The replay service may not use SHADOW intents to authorize LIVE dispatch.

**Escalation authority:** Produces `ESCALATE_TO_OPERATOR` intents for the Escalation Authority domain to act on. Does not itself perform escalation routing or closure.

**Audit obligations:** Every `OrchestrationIntent` produces an audit record: `intent_type`, `correlation_id`, `config_version_id`, `confidence_used`, `rule_path`.

**Attribution requirements:** `actor_identity = core_decision_engine`, `origin_source = platform_generated`.

---

### 3.8 Orchestration Services

**Authority domain:** Execution Authority

**Includes:** Outreach Orchestration Service, State Management Service, Snapshot Orchestration Service, Report Orchestration Service, AI Orchestration Service, Retry Orchestration Service, Escalation Routing Service.

**Allowed actions:**
* Execute state machine transitions authorized by the Core Decision Engine intent
* Dispatch outbound GHL triggers under governance authorization (per `directives/ghl_integration_contract.md`)
* Execute snapshot DRAFT assembly, content lock, and FINALIZED INSERT
* Trigger report generation from FINALIZED snapshot data
* Trigger AI insight generation for eligible students

**Prohibited actions:**
* Initiate actions outside the scope of an authorized `OrchestrationIntent`
* Bypass idempotency checks before state transitions or dispatches
* Execute LIVE operations in replay/regeneration context
* Write to `warehouse` or `compliance_audit` schemas from the standard application service account (finalization uses the finalization service account; compliance uses the compliance pathway service account)
* Override compliance holds

**Replay restrictions:** In replay context, all execution produces SHADOW assessments. No live dispatch, no live state transition, no external API call.

**Escalation authority:** Escalation Routing Service routes `EscalationOrchestrationAssessment` objects to the Escalation Authority domain. It does not close, acknowledge, or act on escalations — it routes them.

**Audit obligations:** Every state transition, dispatch, and execution produces a structured audit log entry with `correlation_id`, `intent_id`, `actor_identity`, `config_version_id`, `outcome`.

**Attribution requirements:** `actor_identity = [service_name]`, `origin_source = platform_generated`.

---

### 3.9 Provider Systems (GHL)

**Authority domain:** Provider Authority (execution telemetry only)

**Allowed actions:**
* Execute communication delivery workflows triggered by authorized platform dispatch
* Report delivery state via inbound webhooks
* Provide campaign activity metadata

**Prohibited actions:**
* All Governance Authority actions
* All Orchestration Authority actions
* Triggering student lifecycle state transitions
* Asserting `sql_server_authoritative` authority in webhook payloads
* Modifying platform config versions, snapshot state, or compliance records
* All Escalation Authority, Compliance Authority, and Operational Override Authority actions

**Replay restrictions:** Provider authority is non-existent in replay contexts. GHL does not participate in replay; the platform resolves historical provider telemetry from its own records.

**Escalation authority:** None. Provider retry exhaustion and circuit breaker states produce escalation candidacy signals that the Escalation Authority domain may act on. The provider does not hold escalation authority.

**Audit obligations:** All inbound GHL webhook events produce `processed_events` audit records; all outbound dispatch attempts produce delivery observability records (per `directives/ghl_integration_contract.md` §10).

**Attribution requirements:** `origin_source = ghl_webhook`, `origin_authority = platform_supplementary`, `is_authoritative = false`.

---

### 3.10 Replay Services

**Authority domain:** Replay Authority (SHADOW-only)

**Allowed actions:**
* Simulate orchestration assessment outcomes from historical records
* Produce `REPLAY_SIMULATION` and `SHADOW_SIMULATION` assessments for diagnostic purposes
* Source AI content from `warehouse.snapshot_ai_narratives` (FINALIZED_COPY)
* Source provider telemetry from `ghl_messages`, `outreach_history`, `processed_events`
* Produce `POTENTIALLY_DIVERGENT` annotations when current config fingerprint differs from historical

**Prohibited actions:**
* Execute any LIVE outbound dispatch (AP-GHL5, AP-AI5, AP-OWN2)
* Trigger student lifecycle state transitions
* Write to any platform table except diagnostic replay log entries
* Call live AI provider APIs (AP-AI5)
* Activate, supersede, or modify config versions
* Execute compliance actions

**Replay restrictions:** Replay Services exist exclusively to operate within replay context. Every output carries `execution_type = replay` or `execution_type = regeneration`. Live execution from a Replay Service is a specification violation.

**Escalation authority:** None. Replay-mode escalation assessments carry `REPLAY_ESCALATION_CANDIDATE` scope ceiling and are never acted on as LIVE escalations.

**Audit obligations:** Every replay execution produces a replay diagnostic record: `source_artifact_id`, `historical_config_version_id`, `fingerprint_comparison_outcome`, `replay_partial`.

**Attribution requirements:** `execution_type = replay | regeneration`, `governance_scope = REPLAY_ONLY`.

---

### 3.11 Compliance Operators

**Authority domain:** Compliance Authority

**Allowed actions:**
* Intake and review compliance requests (COMPLIANCE_REQUEST_RECEIVED)
* Approve compliance workflows for execution (APPROVED_FOR_ACTION) — requires Governance Administrator authorization for GDPR deletion
* Execute compliance deletion, anonymization, and data subject actions via the compliance pathway service account
* Write pre-action and post-action audit entries to `compliance_audit`
* Generate compliance audit exports

**Prohibited actions:**
* Activate config versions
* Trigger outreach or escalation for any student
* Alter warehouse records outside the compliance execution pathway
* Skip the pre-action audit entry gate before `IN_EXECUTION`
* Execute compliance actions for students not in an approved workflow

**Replay restrictions:** Compliance execution is excluded from replay. Execution mode (SHADOW/LIVE) does not gate compliance workflows (per spec/05 §10.6).

**Escalation authority:** None in the operational outreach sense. Compliance-driven escalation (`compliance_hold_active = true`) is surfaced to the Escalation Authority domain via the escalation advisory layer.

**Audit obligations:** All compliance actions are append-only to `compliance_audit`. Hard gate: `IN_EXECUTION` is blocked by the API if no pre-action audit entry exists.

**Attribution requirements:** `actor_identity = compliance_operator:{operator_id}`, all actions via compliance pathway service account.

---

## 4. AUTHORITY MATRIX

---

### 4.1 Governance Actions

| Action | Authority Domain | Authorized Actor(s) | Automation Permitted | Approval Required |
|---|---|---|---|---|
| Config version activation | Governance Authority | Governance Administrator | No | Governance approval chain (spec/01 §12.8) |
| Config version supersession | Governance Authority | Governance Administrator | No | Same |
| Compliance workflow initiation | Governance Authority | Governance Administrator (GDPR deletion) | No | Pre-action audit entry hard gate |
| Emergency override authorization | Governance Authority | Governance Administrator | No | UE-OWN5 (unresolved) |
| Governance escalation resolution | Governance Authority | Governance Administrator | No | Yes |

---

### 4.2 Orchestration Actions

| Action | Authority Domain | Authorized Actor(s) | Automation Permitted | Approval Required |
|---|---|---|---|---|
| Orchestration intent production | Orchestration Authority | Core Decision Engine | Yes (advisory only) | No |
| Outreach eligibility assessment | Orchestration Authority | Outreach Eligibility Service | Yes | No |
| Retry eligibility assessment | Orchestration Authority | Retry Policy Service | Yes | No |
| Channel advisory generation | Orchestration Authority | Channel Advisory Service | Yes | No |
| Escalation candidacy classification | Orchestration Authority | Escalation Routing Service | Yes (routing only) | No |
| AI governance tier assignment | AI Advisory Authority | AI Advisory Systems | Yes (advisory only) | No |

---

### 4.3 Execution Actions

| Action | Authority Domain | Authorized Actor(s) | Automation Permitted | Approval Required |
|---|---|---|---|---|
| Student state machine transition | Execution Authority | State Management Service | Yes, under authorized intent | No |
| Outbound GHL trigger dispatch | Execution Authority | Outreach Orchestration Service | Yes, under authorized intent | No |
| Snapshot DRAFT assembly | Execution Authority | Snapshot Orchestration Service | Yes | No |
| Snapshot FINALIZED INSERT | Execution Authority | Finalization Service (dedicated account) | Yes | No |
| Report generation from snapshot | Execution Authority | Report Orchestration Service | Yes | No |
| AI insight generation | Execution Authority | AI Orchestration Service | Yes | No |
| SQL Server sync | Execution Authority | Sync Service | Yes (on demand or scheduled) | No |

---

### 4.4 Override Actions

| Action | Authority Domain | Authorized Actor(s) | Automation Permitted | Audit Required |
|---|---|---|---|---|
| Force-retry (FORCE_RETRY) | Operational Override | Operational Administrator, Super Mentor | No | Yes — mandatory |
| Close case (CLOSE_CASE) | Operational Override | Operational Administrator, Super Mentor, Escalation Operator | No | Yes — mandatory |
| Mark contacted (MARK_CONTACTED) | Operational Override | Operational Administrator | No | Yes |
| Reopen case (REOPEN_CASE) | Operational Override | Operational Administrator | No | Yes |
| Pause outreach (PAUSE_OUTREACH) | Operational Override | Operational Administrator | No | Yes |
| AI insight force-refresh | Operational Override | Operational Administrator | No | Yes |
| Trigger report regeneration | Operational Override | Operational Administrator | Yes (service executes; human initiates) | Yes |
| Mentor assignment | Escalation Authority | Escalation Operator, Super Mentor | No | Yes |

---

### 4.5 Replay and Diagnostic Actions

| Action | Authority Domain | Authorized Actor(s) | LIVE Execution | Audit Required |
|---|---|---|---|---|
| Replay orchestration assessment | Replay Authority | Replay Services | No — SHADOW only | Yes |
| Report regeneration from snapshot | Execution Authority | Report Orchestration Service (human-initiated) | Yes (read-only from warehouse) | Yes |
| Historical config version query | Read-only | Any authorized service account | N/A | No |
| Replay config fingerprint comparison | Replay Authority | Replay Services | No | Yes |

---

### 4.6 Compliance Actions

| Action | Authority Domain | Authorized Actor(s) | Automation Permitted | Hard Gate |
|---|---|---|---|---|
| Compliance intake | Compliance Authority | Compliance Operator (via API) | No | No |
| Compliance approval | Compliance Authority | Governance Administrator | No | Pre-action audit entry required |
| Compliance execution (deletion/anonymization) | Compliance Authority | Compliance Operator via compliance pathway service account | No | Pre-action audit entry hard gate |
| Compliance audit export | Compliance Authority | Compliance Operator | No | No |
| Compliance correction record | Compliance Authority | Compliance Operator | No | Yes |

---

## 5. HUMAN vs AUTOMATION BOUNDARIES

---

### 5.1 What Automation May Execute

Automation (orchestration services, AI advisory, replay services) may execute the following without human approval:

* Orchestration intent production from the Core Decision Engine
* State machine transitions authorized by a valid `OrchestrationIntent`
* Outbound GHL dispatch authorized by a valid `INITIATE_OUTREACH` or `RETRY_OUTREACH` intent
* AI insight generation and governance tier classification
* Snapshot assembly, content lock, and finalization
* Report generation from FINALIZED snapshots
* SQL Server sync and upsert
* Inbound webhook ingestion, deduplication, and attribution
* Circuit breaker state management
* Escalation candidacy classification and routing (not closure)

---

### 5.2 What Requires Human Approval or Action

The following actions require a human actor from the specified authority domain:

| Action | Required human actor |
|---|---|
| Config version activation | Governance Administrator |
| Compliance workflow authorization | Governance Administrator |
| Compliance execution | Compliance Operator |
| Force-retry, close-case, reopen-case, pause-outreach | Operational Administrator or Super Mentor |
| Escalation acknowledgement and routing | Escalation Operator |
| Escalation closure with outcome record | Escalation Operator or Super Mentor |
| Governance escalation resolution | Governance Administrator |
| Emergency override authorization | Governance Administrator (UE-OWN5) |
| Mentor assignment | Escalation Operator or Super Mentor |

---

### 5.3 What May NEVER Be Overridden

The following governance boundaries are absolute. No actor class — human or automated — may override them:

| Boundary | Governing rule |
|---|---|
| FINALIZED snapshot content in `warehouse.student_snapshots` | FAD-1, spec/09 §1.2; only Compliance Governance Pathway may touch, under full pre-action audit |
| AI text in `warehouse.snapshot_ai_narratives` after finalization | FAD-1, AP-AI6, AP-OWN7 |
| Config version rollback (ACTIVE → prior ACTIVE) | spec/01 §12.1, spec/04 §18.5; rollback is explicitly prohibited |
| Attribution field immutability (`origin_source`, `origin_authority`, `is_authoritative`) | spec/09 §1.3, AP-GHL15, AP-OWN8 |
| Compliance hold bypass for outbound dispatch | spec/05 §10.6, AP-GHL5 (no dispatch under compliance hold) |
| SHADOW-to-LIVE execution escalation in replay context | AP-OWN2, AP-GHL5, AP-AI5 |
| Append-only constraints on `warehouse` and `compliance_audit` schemas | spec/05 §2.2, spec/09 §1.2; database-layer enforcement |
| `processed_events` audit entries for duplicate detections | spec/05 §5.5; no silent drops permitted |

---

### 5.4 What Humans May Override (With Audit)

Human actors with the appropriate authority domain may override automation-produced decisions, subject to mandatory audit records:

| Override | Permitted actors | Audit requirement |
|---|---|---|
| Close an outreach case | Operational Administrator, Super Mentor, Escalation Operator | Outcome record with `actor_identity`, `reason`, `attribution_timestamp` |
| Force-retry for a student | Operational Administrator, Super Mentor | Override record with prior state, new state, `actor_identity` |
| Mark student as contacted | Operational Administrator | Override record |
| Pause outreach for a student | Operational Administrator | Override record with duration or condition |
| Override AI advisory recommendation | Operational Administrator (via intervention flag) | Override record; AI advisory retained in audit log |
| Reassign mentor | Escalation Operator, Super Mentor | Assignment record |
| Reopen a closed case | Operational Administrator | Reopen record with justification |

Human overrides **do not erase** prior automation-produced decisions. Both the automation decision and the human override are retained in the append-only audit log. The override supersedes the automation decision operationally; neither record is deleted.

---

## 6. REPLAY AUTHORITY MODEL

---

### 6.1 Replay-Safe Operational Behavior

All orchestration evaluation, AI assessment, and provider governance evaluation is replay-safe. Re-running any evaluation for the same inputs produces the same advisory output. No re-run creates additional outbound dispatches, state transitions, or compliance actions.

Replay safety is enforced by:
* `processed_events` idempotency on all dispatches and inbound events
* Historical config version resolution in replay context (not live ACTIVE config)
* RULE 0 governance precondition gate across all six directives
* SHADOW enforcement on all automation in replay context

---

### 6.2 Replay Execution Restrictions

Replay Services hold the most restricted authority profile in the platform. The following restrictions are absolute:

* Replay may simulate orchestration assessment outcomes; it may not execute them
* Replay may produce `REPLAY_SIMULATION` events; it may not produce LIVE events
* Replay may read from `warehouse.snapshot_ai_narratives` (FINALIZED_COPY); it may not write to the warehouse schema
* Replay may not call live AI provider APIs
* Replay may not dispatch live GHL triggers
* Replay may not activate, supersede, or query config versions for modification
* Replay may not initiate, approve, or execute compliance actions
* Replay-mode escalation assessments carry `REPLAY_ESCALATION_CANDIDATE` scope ceiling; they are never acted on as LIVE escalations

---

### 6.3 SHADOW vs LIVE Ownership Semantics

| Mode | Automation behavior | Human operator behavior | Permitted outputs |
|---|---|---|---|
| LIVE | Full execution authority per defined domains | Full override authority per defined domains | State transitions, dispatches, escalation routing, compliance execution |
| SHADOW | Advisory outputs only; no LIVE execution | Actions may be simulated for diagnostic purposes | `SHADOW_SIMULATION` assessments, no state changes, no real communications |

SHADOW mode does not suppress inbound webhook ingestion. Inbound events in SHADOW are ingested and attributed normally; they are tagged `execution_mode = SHADOW` in the event log. No state transition is actioned from a SHADOW-tagged event.

---

### 6.4 Replay Observability Ownership

The Replay Service owns the diagnostic record for each replay execution:
* `source_artifact_id` — the snapshot or event log artifact replayed
* `historical_config_version_id` — the config version resolved for the replay context
* `fingerprint_comparison_outcome` — `MATCH`, `DIVERGENT`, or `UNKNOWN`
* `replay_partial` — whether `UNKNOWN_V0` was substituted for any threshold

These records are append-only to the replay diagnostic log. No human actor may alter them.

---

### 6.5 Regeneration Restrictions

Report regeneration from a FINALIZED snapshot is an Execution Authority action (human-initiated, service-executed). Regeneration:
* Reads `warehouse.student_snapshots` and `warehouse.snapshot_ai_narratives` exclusively (FAD-2)
* Does not call any external system (SQL Server, AI providers, GHL)
* Produces identical output for identical inputs (CONC-INVARIANT-2)
* Does not modify any warehouse row

Regeneration is not replay. Replay simulates historical orchestration decisions. Regeneration re-renders a historical report from immutable snapshot data.

---

## 7. ESCALATION OWNERSHIP GOVERNANCE

---

### 7.1 Escalation Acknowledgement Authority

Escalation cases may be acknowledged by:
* **Escalation Operators** — all operational-tier escalation cases
* **Super Mentors** — operational-tier escalation cases assigned to their mentee students
* **Governance Administrators** — governance-tier escalation cases only

Automation (Escalation Routing Service) routes escalation advisory outputs to the appropriate human operator tier. Routing is not acknowledgement. No automation actor may mark an escalation as acknowledged.

---

### 7.2 Escalation Closure Authority

| Escalation tier | Closure authority |
|---|---|
| Operational outreach escalation | Escalation Operator, Super Mentor, Operational Administrator |
| Provider failure escalation | Operational Administrator |
| Compliance-driven escalation | Compliance Operator (for compliance hold release) |
| Governance-tier escalation | Governance Administrator only |
| AI-assisted escalation (elevated severity) | Same closure authority as underlying escalation tier |

Every escalation closure produces a mandatory outcome record: `actor_identity`, `escalation_id`, `escalation_type`, `closure_outcome`, `attribution_timestamp`, `correlation_id`.

---

### 7.3 Escalation Override Authority

Human actors within the Escalation Authority domain may override an automation-produced escalation candidacy signal by:
* Closing an escalation case as `NOT_ACTIONABLE` with mandatory justification record
* Downgrading escalation severity with mandatory justification record

Escalation override records are append-only. The original automation-produced escalation candidacy signal is retained in the audit log.

**AI-assisted escalation override:** When AI advisory elevated an escalation severity (per `directives/escalation_rules.md` Rule 14), a human actor closing or downgrading that escalation must include the AI governance tier context in the override record. This enables future audits to trace AI advisory influence on human escalation decisions.

---

### 7.4 Escalation Audit Requirements

Every escalation action produces an escalation lineage record appended to `compliance_audit` or `student_timeline_events` (per spec/03 §39):

| Field | Required |
|---|---|
| `escalation_id` | UUID v4 |
| `actor_identity` | Yes |
| `action_type` | `ACKNOWLEDGED`, `ROUTED`, `CLOSED`, `OVERRIDDEN`, `DOWNGRADED` |
| `escalation_type` | From `EscalationOrchestrationAssessment.escalation_type` |
| `attribution_timestamp` | Yes |
| `correlation_id` | Yes (propagated from originating assessment) |
| `outcome` | Required on closure |
| `ai_governance_tier_at_time` | Required if AI advisory influenced the escalation severity |

---

### 7.5 Escalation Replay Restrictions

Escalation advisory outputs in replay context carry `REPLAY_ESCALATION_CANDIDATE` scope ceiling (per `directives/escalation_rules.md` §6). These are diagnostic outputs only:
* No human actor may act on a `REPLAY_ESCALATION_CANDIDATE` as if it were a LIVE escalation
* No routing, acknowledgement, or closure record is created from a replay-mode escalation
* Replay escalation diagnostics are recorded in the replay diagnostic log only

---

## 8. AI AUTHORITY LIMITS

---

### 8.1 Advisory-Only Boundaries

AI advisory systems hold exclusively advisory authority. The `AIAssessment` output is consumed by orchestration services and operator interfaces; it does not constitute authorization to act.

| AI output field | Advisory use | Prohibited use |
|---|---|---|
| `advisory_content.recommended_intervention` | May inform operator decision; may adjust orchestration priority | May not authorize dispatch without Core Decision Engine intent |
| `advisory_content.prioritization_signal` | May adjust ordering within eligible student queue | May not override rule-based eligibility |
| `advisory_content.sentiment_trend` | May inform escalation severity assessment | May not originate escalation candidacy |
| `confidence_metadata.confidence_score` | May elevate escalation severity if CONFIDENT tier | May not override SQL Server-authoritative state |
| `advisory_content.sentiment` | May inform operator dashboard | May not govern cohort classification |

---

### 8.2 Prohibited AI Actions

AI advisory systems may not:
* Authorize any orchestration action, outreach dispatch, or state transition (AP-AI1 / AP-OWN3)
* Override SQL Server-authoritative eligibility state (AP-AI4)
* Override deterministic rule evaluation outcomes or governance invariants
* Create escalation candidacy without rule-based basis (AP-AI14 / AP-OWN3)
* Generate live AI inference during replay or regeneration (AP-AI5 / AP-OWN2)
* Modify `warehouse.snapshot_ai_narratives` after finalization (FAD-1 / AP-AI6)
* Claim config authority over any lifecycle domain
* Act as workflow authority, governance decision-maker, or orchestration executor (AP-AI1)

---

### 8.3 Confidence Governance

The AI confidence score (`advisory_content.advisory_confidence`) governs the AI governance tier assignment:
* CONFIDENT tier (≥ 0.70): advisory scope = FULL; may elevate escalation severity
* ADVISORY tier (0.40–0.69): advisory scope = LIMITED; may not independently drive LIVE escalation
* STALE tier (beyond TTL): advisory scope = LIMITED; LIVE escalation blocked (AP-AI11)
* UNAVAILABLE tier (null insight): advisory scope = UNAVAILABLE; rule-based evaluation only

AI confidence thresholds are operational defaults (pending UE-AI2 resolution from `directives/llm_processing_contract.md`). They are not yet config-governed.

---

### 8.4 Stale-AI Restrictions

When AI insight is STALE or UNAVAILABLE:
* Orchestration services must proceed with rule-based evaluation only
* Stale AI advisory content may not independently drive LIVE escalation (AP-AI11)
* Snapshot finalization proceeds with `ai_content_stale = true` flag; finalization is not blocked
* Operator dashboards must surface the stale AI signal to human actors

---

### 8.5 FINALIZED_COPY Immutability

Once AI text is physically copied into `warehouse.snapshot_ai_narratives` at FINALIZED state, it is immutable (FAD-1). No authority actor — human or automated — may alter it except through the Compliance Governance Pathway under full pre-action audit entry requirements. This includes:
* No force-refresh that overwrites FINALIZED_COPY content
* No AI advisory update that retroactively changes FINALIZED text
* No operator override that modifies FINALIZED AI narratives

---

## 9. PROVIDER AUTHORITY LIMITS

---

### 9.1 Provider Execution Scope

GHL (and all future communication providers) hold execution telemetry delivery authority only. Provider authority does not extend to any governance domain.

| Provider action | Permitted | Authority domain |
|---|---|---|
| Execute communication workflows triggered by platform dispatch | Yes | Provider Authority (execution-only) |
| Report delivery state via inbound webhooks | Yes | Provider Authority (telemetry) |
| Provide campaign activity metadata | Yes | Provider Authority (telemetry) |
| Trigger student lifecycle state transitions | No | Execution Authority (automation-owned) |
| Assert SQL Server authority in webhook payloads | No | Specification violation |
| Modify config versions | No | Governance Authority (human-owned) |
| Trigger escalation | No | Escalation Authority (human-owned) |
| Modify warehouse records | No | Immutable boundary |

---

### 9.2 Synchronization Ownership

Provider synchronization is governed by the platform:
* The platform pulls SQL Server state via a read-only sync service
* GHL pushes webhook events to the platform's ingestion service; the platform owns ingestion logic
* The platform never allows GHL to write to any platform-owned table directly
* Synchronization discrepancies between GHL delivery state and platform-authoritative state are resolved in favor of platform-authoritative state (spec/05 §2.5)

---

### 9.3 Webhook Attribution Ownership

Attribution fields on all GHL-originated records are set by the platform ingestion service, never by the GHL payload itself (AP-GHL15, AP-OWN8):
* `origin_source = ghl_webhook` — set by ingestion service
* `origin_authority = platform_supplementary` — set by ingestion service
* `is_authoritative = false` — set by ingestion service
* `attribution_timestamp` — sourced from GHL payload event time; set by ingestion service

A GHL payload that carries `origin_source` or `origin_authority` fields is validated and those field values are ignored; the platform sets them independently.

---

### 9.4 Provider Audit Obligations

All GHL provider interactions produce audit records per `directives/ghl_integration_contract.md` §10:
* Inbound: `processed_events` deduplication entry + `ghl_messages` record
* Outbound: delivery observability record with `dispatch_initiated_at`, `provider_call_duration_ms`, `delivery_state_after_dispatch`
* Circuit breaker state transitions: structured log entry

---

## 10. OVERRIDE GOVERNANCE

---

### 10.1 Allowed Override Paths

Human overrides of automation-produced decisions are permitted when:
1. The overriding actor holds the appropriate authority domain for the action (§4.4)
2. The override is recorded in the append-only audit log before taking effect
3. The prior automation-produced decision is retained in the audit log
4. The override does not bypass a compliance hold
5. The override is not applied to an immutable governance boundary (§5.3)

---

### 10.2 Prohibited Override Paths

The following override paths are explicitly prohibited regardless of actor authority:

| Prohibited override | Reason |
|---|---|
| Retroactively alter a FINALIZED snapshot | FAD-1; immutable boundary |
| Roll back a config version activation | spec/01 §12.1; rollback explicitly prohibited |
| Bypass a compliance hold to dispatch outreach | spec/05 §10.6; compliance authority required |
| Erase prior attribution fields from historical records | spec/09 §1.3; lineage integrity protection |
| Override a compliance audit entry | `compliance_audit` is append-only; corrections create new records referencing prior ones |
| Close an escalation without an outcome record | Mandatory audit obligation; no silent closure |
| Execute a LIVE action in replay context | AP-OWN2; absolute prohibition |
| Override AI content in a FINALIZED snapshot | FAD-1; AP-AI6; only compliance pathway permitted |

---

### 10.3 Override Audit Requirements

Every override must produce an audit record containing:

| Field | Required |
|---|---|
| `override_id` | UUID v4 |
| `actor_identity` | Yes — the human actor performing the override |
| `action_type` | Override type (FORCE_RETRY, CLOSE_CASE, etc.) |
| `student_id` | Opaque student identifier |
| `prior_state` | The automation-produced state being overridden |
| `new_state` | The state after override |
| `attribution_timestamp` | When the override was executed |
| `correlation_id` | Propagated from the originating orchestration context |
| `override_reason` | Required for case closure and force-retry |
| `ai_governance_tier_at_time` | Required if AI advisory influenced the overridden decision |

Override records are append-only to `student_timeline_events` with `origin_source = platform_operator_action`.

---

### 10.4 Override Replay Restrictions

Overrides executed in SHADOW mode produce override simulation records. They do not produce real state transitions. A SHADOW-mode override may not be replayed as a LIVE override without a separate LIVE execution under full audit.

---

### 10.5 Immutable-State Override Restrictions

Actors within any authority domain may not apply operational overrides to records in:
* `warehouse.student_snapshots` (FINALIZED rows)
* `warehouse.snapshot_ai_narratives`
* `warehouse.monthly_reports` (REPORT_PUBLISHED rows)
* `compliance_audit` (all rows; corrections are new append-only rows)
* `processed_events` (all rows)
* `config_version_registry` (SUPERSEDED or ARCHIVED versions)

---

## 11. OBSERVABILITY & ATTRIBUTION

---

### 11.1 Authority Traceability Requirements

Every authority action — automation or human — must emit a structured log record (JSON to stdout):

```json
{
  "timestamp": "ISO-8601",
  "level": "info | warn | error",
  "service": "authority_domain_service_name",
  "event": "short_event_name",
  "actor_identity": "string",
  "actor_domain": "governance | orchestration | execution | replay | provider | ai_advisory | escalation | compliance | operational_override",
  "action_type": "string",
  "student_id": "opaque_id | null",
  "correlation_id": "uuid",
  "causation_id": "uuid | null",
  "execution_mode": "SHADOW | LIVE",
  "execution_type": "original | replay | regeneration",
  "outcome": "success | failure | override | shadow_only",
  "config_version_id": "string | null",
  "override_of": "prior_action_id | null"
}
```

PII (student name, email, phone, transcript content, payment details) must not appear in authority traceability logs (AP-OWN10). Log opaque `student_id` and `correlation_id` only.

---

### 11.2 Operational Attribution

All operational actions — state transitions, dispatches, override actions, escalation actions — carry the full attribution chain:
* `actor_identity` identifies who performed the action
* `correlation_id` links to the triggering orchestration context
* `causation_id` links to the immediate cause (prior intent, webhook event, or human trigger)
* `config_version_id` identifies the config thresholds active at the time of the action
* `attribution_timestamp` records when the action occurred (not when it was logged)

---

### 11.3 Override Lineage

Override records must carry the `override_of` field referencing the prior automation decision's `correlation_id`. This enables forensic reconstruction: "The automation decided X; the operator overrode it to Y because Z." Both records are permanently queryable.

---

### 11.4 Replay Diagnostics

Replay executions must emit the full replay diagnostic set (per §6.4):
* `source_artifact_id`
* `historical_config_version_id`
* `fingerprint_comparison_outcome`
* `replay_partial`

---

### 11.5 Escalation Traceability

Every escalation in the platform must be traceable from the originating risk signal through to closure:
* Originating risk signal → `EscalationOrchestrationAssessment.correlation_id`
* Routing event → Escalation Routing Service audit record
* Acknowledgement → Escalation Operator audit record
* Closure → Escalation closure record with outcome

If an escalation cannot be traced end-to-end via `correlation_id`, it is an observability defect.

---

### 11.6 Governance Audit Continuity

Governance authority actions — config version activation, compliance authorization, compliance execution — are permanently auditable:
* Config version audit: `activation_actor_id`, `activation_timestamp`, `approval_chain` in `config_version_registry`
* Compliance audit: all entries in `compliance_audit` schema; permanently queryable regardless of operational record deletion (spec/05 §10.5)
* Governance escalation resolution: record in escalation lineage with `actor_identity = governance_administrator`

---

## 12. ARCHITECTURE PRESERVATION RULES

---

The following rules are MUST NOT prohibitions. Violation of any rule is a specification defect.

| Rule | Prohibition |
|---|---|
| **AP-OWN1** | MUST NOT allow any actor to silently escalate their own authority beyond their defined domain; authority domain boundaries are defined here and are not self-grantable |
| **AP-OWN2** | MUST NOT allow Replay Services to execute LIVE operations; all replay outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`; live dispatch, live state transition, and live external API calls from replay context are specification violations |
| **AP-OWN3** | MUST NOT allow AI advisory systems to authorize orchestration decisions, create escalation candidacy without rule-based basis, or override governance invariants; AI advisory output is consumed — not obeyed (AP-AI1, AP-AI14) |
| **AP-OWN4** | MUST NOT allow provider systems (GHL) to become governance authority; provider authority is bounded to execution telemetry delivery; no GHL action may trigger a platform state transition, governance action, or escalation |
| **AP-OWN5** | MUST NOT allow operational overrides to bypass active compliance holds; compliance hold enforcement on outbound dispatch is absolute; override actors without Compliance Authority cannot lift a compliance hold |
| **AP-OWN6** | MUST NOT allow student lifecycle state machine transitions to be written by any actor other than the designated Orchestration Services under a valid `OrchestrationIntent`; state writes without an authorized intent are specification violations |
| **AP-OWN7** | MUST NOT allow FINALIZED snapshot rows in `warehouse.student_snapshots` or `warehouse.snapshot_ai_narratives` to be mutated by any actor outside the Compliance Governance Pathway executing under full pre-action audit entry requirements (FAD-1) |
| **AP-OWN8** | MUST NOT allow override actions to erase, overwrite, or suppress prior attribution fields (`origin_source`, `origin_authority`, `is_authoritative`, `attribution_timestamp`, `correlation_id`) from historical records; overrides append new records referencing prior ones — they do not replace them |
| **AP-OWN9** | MUST NOT allow escalation cases to be closed without a mandatory outcome record containing `actor_identity`, `escalation_id`, `closure_outcome`, and `attribution_timestamp`; silent escalation closure is a specification violation |
| **AP-OWN10** | MUST NOT log raw PII (student name, email, phone, transcript content, payment details) in authority traceability logs; opaque `student_id` and `correlation_id` only |
| **AP-OWN11** | MUST NOT allow AI advisory confidence scores alone to override rule-based eligibility decisions, escalation candidacy, or cohort classification; confidence governs advisory scope and severity escalation only (AP-AI14) |
| **AP-OWN12** | MUST NOT allow Mentor-class actors to execute compliance pathway actions; compliance execution requires Compliance Operator actor class with compliance pathway service account |
| **AP-OWN13** | MUST NOT allow provider webhook events to trigger direct student lifecycle state transitions; webhooks are inputs to the platform's state management service processed under governance authorization |
| **AP-OWN14** | MUST NOT allow human override actions to bypass replay isolation; overrides executed in replay context are SHADOW-only and must not produce LIVE state transitions or communications |
| **AP-OWN15** | MUST NOT allow any actor to write to `warehouse` or `compliance_audit` schemas outside the designated service account paths (finalization service account for warehouse; compliance pathway service account for compliance_audit); any application-layer code path that constructs a write to these schemas via the standard service account is a specification violation |

---

## 13. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Operational Administrator and Governance Administrator roles defined; Mentor/Super Mentor/Escalation Operator roles deferred
* Basic audit logging: `actor_identity`, `action_type`, `correlation_id`, `attribution_timestamp`
* Quick actions: `FORCE_RETRY`, `CLOSE_CASE` implemented; no approval gate
* SHADOW mode enforcement on automation
* No override audit gate (override logging only)
* Compliance Authority deferred; no compliance workflow execution at MVP scope

---

### STANDARD

* Full actor class definitions enforced
* Override audit gate: every quick action blocked until audit record written
* Escalation routing service routes to human operator tier (Escalation Operator role required)
* AI advisory governance tier enforced: CONFIDENT/ADVISORY/STALE/UNAVAILABLE distinction active
* Compliance workflow intake and approval implemented; execution deferred to PRODUCTION
* Replay diagnostics fully emitted for all replay-mode interactions
* SHADOW/LIVE enforcement on all automation

---

### PRODUCTION

* Full authority domain enforcement across all actor classes
* Compliance workflow execution active (pre-action audit entry hard gate enforced)
* Governance escalation tier active (Governance Administrator escalation resolution implemented)
* Emergency override authority model defined (UE-OWN5 resolved)
* AI advisory confidence governance tier boundaries formally config-governed (pending UE-AI2 resolution)
* Full override lineage in all audit records
* Governance audit continuity verified: config version activation, compliance execution, escalation closure all permanently queryable

---

## 14. ACCEPTANCE CRITERIA

---

### AC-OWN1 — Bounded Authority Enforcement

**Given** any actor class attempts an action outside its defined authority domain
**When** the action is submitted
**Then** the action is blocked; a structured error log is emitted with `actor_domain`, `action_type`, and `AUTHORITY_DOMAIN_VIOLATION` reason code; no state change or dispatch occurs

---

### AC-OWN2 — Replay-Safe Authority Behavior

**Given** `execution_type = replay`
**When** any automation service evaluates an orchestration, AI, or provider assessment
**Then** `governance_scope = REPLAY_ONLY`; no LIVE dispatch is generated; no LIVE state transition occurs; all outputs carry `execution_type = replay`

---

### AC-OWN3 — Immutable Lineage Preservation

**Given** a human override action is executed
**When** the override audit record is written
**Then** the prior automation-produced decision record is unchanged; the override record carries `override_of` referencing the prior decision's `correlation_id`; both records are permanently queryable

---

### AC-OWN4 — Attribution Continuity

**Given** any authority action — human or automated — is executed
**When** the action completes
**Then** an audit record exists with `actor_identity`, `action_type`, `attribution_timestamp`, `correlation_id`, and `execution_mode`; no authority action is unattributed

---

### AC-OWN5 — Override Auditability

**Given** an Operational Administrator executes a `FORCE_RETRY` quick action
**When** the retry executes
**Then** an override audit record exists in `student_timeline_events` with `origin_source = platform_operator_action`, `actor_identity`, `prior_state`, `new_state`, `override_reason`, `attribution_timestamp`; the override record is append-only and unmodifiable

---

### AC-OWN6 — Provider Authority Isolation

**Given** a GHL webhook event is received
**When** the event is ingested and processed
**Then** no student lifecycle state transition occurs from the webhook event alone; the state management service processes the validated, attributed webhook record under governance authorization; `is_authoritative = false` is present on the stored record

---

### AC-OWN7 — AI Authority Isolation

**Given** an `AIAssessment` output carries `recommended_intervention = ESCALATE`
**When** the orchestration service evaluates the assessment
**Then** no escalation is created from AI advisory output alone; a rule-based escalation candidacy basis must exist (per `directives/escalation_rules.md` Rule 14); the AI advisory is logged as a severity-adjustment input, not as an escalation trigger

---

### AC-OWN8 — Config Version Reproducibility Under Governance

**Given** a config version activation is executed
**When** the audit record is queried
**Then** `activation_actor_id` identifies the Governance Administrator who activated; `activation_timestamp` is present; the superseded prior version remains permanently queryable in `config_version_registry`; no automation service account appears as the activating actor

---

### AC-OWN9 — Compliance Hold Dispatch Blocking

**Given** `compliance_hold_active = true` for a student
**When** any authority actor (human or automated) attempts to trigger outreach for that student
**Then** the dispatch is blocked; `COMPLIANCE_HOLD_ACTIVE_DISPATCH_BLOCKED` reason code is emitted; no outbound GHL trigger is generated; the compliance hold remains active until a Compliance Operator lifts it through the compliance workflow

---

### AC-OWN10 — FINALIZED Snapshot Immutability Under Authority Model

**Given** a FINALIZED snapshot exists in `warehouse.student_snapshots`
**When** any actor outside the compliance governance pathway attempts to alter a field
**Then** the attempt fails at the database layer with `insufficient_privilege`; no application-layer override path exists for this action; the snapshot record remains unchanged

---

### AC-OWN11 — Escalation Attribution Continuity

**Given** an escalation case is closed by an Escalation Operator
**When** the closure record is written
**Then** the closure record contains `actor_identity`, `escalation_id`, `escalation_type`, `closure_outcome`, `attribution_timestamp`, and `correlation_id` propagated from the originating escalation advisory; no escalation case is closed without a complete audit record

---

### AC-OWN12 — SHADOW Mode Enforcement on Automation

**Given** `execution_mode = SHADOW`
**When** any orchestration service, AI advisory service, or provider orchestration service evaluates an action
**Then** no LIVE state transition occurs; no LIVE outbound dispatch is generated; no LIVE AI inference is made; all automation outputs carry `outcome = shadow_only`; inbound webhook events are ingested and tagged `execution_mode = SHADOW` without actioning state transitions

---

## 15. UNRESOLVED CONCERNS

---

### UE-OWN1 — Emergency Override Authority (GOVERNANCE DECISION)

**Problem:** No emergency override authority model exists for governance-blocking scenarios — for example, when a compliance hold is incorrectly applied to a student, or when a config version activation error blocks all snapshot generation. No escalation path bypasses governance boundaries without a full authorization chain.

**Impact:** Blocks incident response for governance-level blocking scenarios. An incorrect compliance hold with no fast-path lift procedure could delay outreach for affected students indefinitely.

**Classification:** Governance decision. Requires defining an emergency override actor class, the scope of their authority, the mandatory pre-action and post-action audit requirements, and the conditions that qualify as governance emergencies.

---

### UE-OWN2 — Multi-Admin Conflict Resolution (GOVERNANCE DECISION)

**Problem:** No conflict resolution protocol exists when two Governance Administrators concurrently attempt to activate different config versions, or when concurrent compliance workflow authorizations conflict.

**Impact:** Blocks safe multi-administrator governance. The platform enforces exactly-one-ACTIVE config version at the database layer, but the governance protocol for resolving conflicting authorization claims has not been defined.

**Classification:** Governance decision. The database enforces the constraint; this concern is about the organizational protocol when the constraint prevents an activation from succeeding.

---

### UE-OWN3 — Mentor Escalation Ownership (OPERATIONAL DECISION)

**Problem:** The boundary between Mentor-class acknowledgement authority and Escalation Operator routing authority is undefined for cases where the student's mentor is also an Escalation Operator. The authority model classifies these as separate actor classes, but the same individual may hold both roles.

**Impact:** Blocks clear audit attribution in dual-role scenarios. The audit record must attribute the action to the correct authority domain; dual-role actors create ambiguity.

**Classification:** Operational decision. Requires defining whether dual-role actors must explicitly select their authority domain before executing escalation actions, or whether the system infers the appropriate domain from context.

---

### UE-OWN4 — Human vs System Accountability for AI-Assisted Decisions (GOVERNANCE DECISION)

**Problem:** When AI advisory output elevated an escalation severity and the subsequent human action (based on that escalated severity) produced a harmful outcome, the accountability chain between the AI system and the human actor is undefined.

**Impact:** Blocks formal accountability allocation for AI-assisted escalation decisions in PRODUCTION. Without a defined accountability model, the platform cannot formally attribute harmful outcomes to either the AI advisory system or the human actor who acted on it.

**Classification:** Governance decision. Requires defining the accountability boundary between AI advisory authority and human decision authority for AI-assisted escalations.

---

### UE-OWN5 — Governance Delegation Limits (GOVERNANCE DECISION)

**Problem:** No authority delegation model exists. A Governance Administrator cannot formally delegate config approval authority to an Operational Administrator, even temporarily. All Governance Authority actions require a Governance Administrator directly.

**Impact:** Blocks operational continuity when no Governance Administrator is available. An urgent config change may be blocked if the Governance Administrator is unavailable and no delegation path exists.

**Classification:** Governance decision. Requires defining whether and under what conditions governance authority can be temporarily delegated, to whom, and what audit requirements apply to delegated actions.

---

## 16. DOWNSTREAM IMPLICATIONS

---

### 16.1 Service Layer

| Service | Authority governance dependency |
|---|---|
| `app/services/outreach.py` | Checks for compliance hold before dispatch; requires valid `OrchestrationIntent` from Core Decision Engine; override quick actions produce audit records |
| `app/services/state_management.py` | All state transitions require authorized `OrchestrationIntent`; human override transitions require override audit record |
| `app/services/escalation.py` | Routes `EscalationOrchestrationAssessment` to human operator tier; does not acknowledge, close, or act on escalations autonomously |
| `app/services/snapshot.py` | Finalization executes under finalization service account only; no override path to warehouse from standard application service account |
| `app/services/config_registry.py` | Config activation only via Governance Administrator-authenticated API call; no automation activates config versions |
| `app/services/compliance.py` | All compliance execution via compliance pathway service account; pre-action audit entry hard gate enforced before `IN_EXECUTION` |
| `app/services/ai_insights.py` | AI output is advisory; consuming services enforce governance boundaries; AI output does not authorize dispatch or state transition |
| `app/services/ghl_sync.py` | Provider webhook events are inputs processed under governance authorization; no direct state mutation from webhook events |

---

### 16.2 API Layer

| Endpoint | Authority requirement |
|---|---|
| `POST /outreach/quick-action` | Operational Administrator or Super Mentor authentication; audit record written before execution |
| `POST /escalation/acknowledge` | Escalation Operator or Super Mentor authentication |
| `POST /escalation/close` | Escalation Operator, Super Mentor, or Operational Administrator; mandatory outcome record |
| `POST /config/activate` | Governance Administrator authentication; governance approval chain verified |
| `POST /compliance/request` | Compliance Operator authentication |
| `POST /sync/mssql` | Operational Administrator or scheduled service; no external actor |
| `POST /ai-insights/force-refresh` | Operational Administrator authentication |
| `GET /reports/{id}/regenerate` | Operational Administrator authentication; reads from warehouse only |

---

### 16.3 Audit Log Consumers

| Consumer | Authority governance dependency |
|---|---|
| Compliance audit export | Reads `compliance_audit` schema only; no cross-schema FK dependencies; survivable after operational deletion |
| Escalation lineage report | Reads `student_timeline_events` for escalation action records; `correlation_id` chain for traceability |
| Override history report | Reads `student_timeline_events` for `origin_source = platform_operator_action` events |
| Config version history | Reads `config_version_registry` for all versions; SUPERSEDED versions permanently queryable |
| Authority attribution query | Reads `compliance_audit` and `student_timeline_events` by `actor_identity`; must support forensic reconstruction |

---

## 17. REFERENCES

---

Canonical inputs:

* `spec/01_requirements.md` — System purpose; Config V2 Governance Catalog (§12); governance classification model (§12.2); governance approval chain (§12.8)
* `spec/03_state_transition_rules.md` — All 6 lifecycle domain state machines; INVARIANT-1 through INVARIANT-7; Event Attribution Standard (§39); operator quick actions (§6.3)
* `spec/04_idempotency_concurrency.md` — Idempotency per domain; CONC-INVARIANT-1 through CONC-INVARIANT-7; concurrency authority (exactly-one-ACTIVE invariant §18.4)
* `spec/05_external_integrations.md` — System authority classification (§3.1); authoritative vs derivative (§3.2); compliance governance isolation (§10.6); governance isolation boundaries
* `spec/06_observability_operations.md` — Structured logging standards; authority action log requirements; correlation ID requirements
* `spec/07_api_contracts.md` — API endpoint authentication requirements; operator quick action contracts
* `spec/08_data_model.md` — `student_timeline_events`, `compliance_audit`, `config_version_registry` schema; authority record storage
* `spec/09_security_privacy.md` — Governance-aware security (§1.1); historical integrity protection (§1.2); lineage integrity protection (§1.3); audit survivability (§1.4)
* `directives/core_decision_engine.md` — Orchestration Authority model; intent production authority; what the engine is NOT
* `directives/outreach_eligibility_rules.md` — Eligibility assessment authority; SQL Server-authoritative boundary
* `directives/outreach_retry_policy.md` — Retry eligibility authority; escalation candidacy signaling
* `directives/channel_selection_rules.md` — Channel advisory authority; provider health constraint
* `directives/escalation_rules.md` — Escalation candidacy classification; AP-X1–AP-X15; escalation authority boundaries; RULE 0 governance precondition gate
* `directives/llm_processing_contract.md` — AI advisory authority model; AP-AI1–AP-AI15; FINALIZED_COPY immutability; AI governance tier boundaries
* `directives/ghl_integration_contract.md` — Provider authority model; AP-GHL1–AP-GHL15; outbound authorization chain; provider audit obligations
* FAD-1 — AI physical copy immutability
* FAD-2 — Historical report reproducibility
* FAD-3 — Prospective-only config activation

---

## END OF FILE
