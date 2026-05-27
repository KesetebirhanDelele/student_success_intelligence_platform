# meta/project_classification.md

---

## LAYER 1 — META (PLATFORM CLASSIFICATION)

---

> **Version note:** This file was completely rewritten on 2026-05-27 to reflect the finalized governance-safe orchestration architecture established in `spec/01_requirements.md` through `spec/09_security_privacy.md` and all rewritten governance contracts. The previous version described an MVP-era scope-tier execution model: MVP/STANDARD/PRODUCTION capability gating, hardcoded `MAX_ATTEMPTS` values per scope (MVP=1, STANDARD=2, PRODUCTION=3), hardcoded `RETRY_INTERVAL` (24 hours), hardcoded `CONCURRENCY_LIMIT` (MVP=10, STANDARD=25, PRODUCTION=50), feature flags `ENABLE_RETRY`/`ENABLE_LLM`/`ENABLE_CHANNEL_FALLBACK`/`ENABLE_ESCALATION`/`ENABLE_OBSERVABILITY`, and a migration path `MVP → STANDARD → PRODUCTION` implying governance is incrementally acquired. That architecture is incompatible with the governance-safe orchestration model. Platform classification is no longer feature gating by capability tier. It is governance-safe environment and execution classification.

---

## 1. PURPOSE

---

This file defines:

* **Environment governance classification** — what distinguishes LOCAL, STAGING, and PRODUCTION deployment environments operationally
* **Execution-mode governance classification** — the canonical six runtime modes and their governance semantics
* **Deployment-stage governance classification** — the governance-first sequencing phases governing when LIVE activation is authorized
* **Replay/shadow operational classification** — the containment invariants that apply across all classification tiers

This file is the **canonical classification reference** for:

> What the platform is authorized to do in each environment and execution mode

Governance architecture is invariant across all environments. Environments differ operationally — they do not differ architecturally.

---

## 2. FUNDAMENTAL CLASSIFICATION PRINCIPLES

---

### 2.1 Governance Is Invariant

All governance invariants (INV-1 through INV-7) and foundational architecture decisions (FAD-1 through FAD-6) apply equally in all environments and all execution modes. There is no environment where governance is relaxed, partial, or optional.

---

### 2.2 Orchestration Emits Intents, Not Actions

Across all environments and modes, orchestration loops emit governed orchestration intents. No runtime loop, classification tier, or environment-level configuration authorizes a loop to directly dispatch to providers.

---

### 2.3 Config V2 Governs Runtime Behavior

Retry thresholds, timing windows, concurrency limits, and channel progression are governed by Config Version Registry values. No environment configuration, no classification tier, and no feature flag may substitute hardcoded constants for Config V2-governed parameters.

---

### 2.4 Replay/SHADOW Isolation Is Universal

SHADOW mode is a mandatory operational tier. REPLAY mode is a controlled historical simulation mode. Both are fully isolated from LIVE effects in all environments. There is no environment where SHADOW containment or replay isolation is deactivated.

---

### 2.5 Attribution Continuity Is Mandatory

Every record in every environment carries `correlation_id`, `execution_mode`, `execution_type`, and `config_version_id`. Null attribution fields surface `ATTRIBUTION_INCOMPLETE` regardless of environment. Attribution is not relaxed in LOCAL or STAGING environments.

---

## 3. EXECUTION MODE CLASSIFICATION

---

Six execution modes govern all orchestration behavior. Mode is determined by environment configuration and applies to every orchestration loop in every domain.

---

### 3.1 LIVE

| Aspect | Governance semantics |
|---|---|
| Authorized operations | Full orchestration evaluation; governed outbound dispatch delegation; AI inference; escalation routing; webhook ingestion |
| Provider governance | GHL dispatch authorized when `ProviderOrchestrationAssessment.governance_scope = AUTHORIZED` |
| Outbound suppression | `outbound_suppressed = false` — governed provider delegation permitted |
| Live effects produced | ≥ 0 (each effect attributed, observable, lineage-complete) |
| AI restrictions | STALE AI may not independently drive LIVE escalation (AP-AI11); FINALIZED_COPY is immutable |
| Replay restrictions | No replay-mode call may produce LIVE effects (INV-4, AP-RT2) |
| Observability | Full telemetry required; all records tagged `execution_mode = LIVE` |
| Activation gate | Requires Governance Administrator authorization + `activation_record_present = true` + explicit acknowledgement; automated services may not trigger this transition (AP-RT7) |

---

### 3.2 SHADOW

| Aspect | Governance semantics |
|---|---|
| Authorized operations | Full orchestration evaluation; AI inference (advisory only); inbound webhook ingestion (tagged `execution_mode = SHADOW`); replay diagnostics |
| Provider governance | All outbound dispatch suppressed; `governance_scope = SHADOW_ONLY` |
| Outbound suppression | `outbound_suppressed = true` — no HTTP outbound calls; no provider API calls |
| Live effects produced | 0 (containment invariant; non-zero → CRITICAL governance alert) |
| AI restrictions | AI advisory evaluated; outputs tagged `outcome = shadow_only`; FINALIZED_COPY semantics apply normally |
| Replay restrictions | Replay orchestration remains SHADOW-only within SHADOW mode |
| Observability | Full telemetry required; all outcomes tagged `execution_mode = SHADOW` |
| Default mode | Platform starts in SHADOW mode by default; SHADOW is a mandatory operational tier, not a debugging convenience (`runtime/system_loop.md §3.5`) |

---

### 3.3 REPLAY

| Aspect | Governance semantics |
|---|---|
| Authorized operations | Historical orchestration simulation; SHADOW-only outputs; historical record reads; replay diagnostic emission |
| Provider governance | All provider interactions return historical records from `processed_events`/`ghl_messages` only; no live GHL API calls |
| Outbound suppression | `outbound_suppressed = true`; `governance_scope = REPLAY_ONLY` |
| Live effects produced | 0 (invariant; non-zero → CRITICAL governance alert — AP-RT2) |
| AI restrictions | Live AI inference suppressed; FINALIZED_COPY sourced exclusively from `warehouse.snapshot_ai_narratives` |
| Lineage attribution | `execution_type = replay`; `causation_id` points to original `correlation_id`; `historical_config_version_id` used (never current ACTIVE) |
| Observability | Full telemetry required; all records tagged `execution_type = replay`, `governance_scope = REPLAY_ONLY` |

---

### 3.4 REGENERATION

| Aspect | Governance semantics |
|---|---|
| Authorized operations | Historical report regeneration from `warehouse.student_snapshots` (FINALIZED state only); regenerated output tagged `sourced_from_warehouse = true` |
| Source restriction | Reads `warehouse` schema exclusively; no live operational data consumed |
| Output classification | `execution_type = regeneration`; never presented as newly-generated output |
| Live effects produced | 0 |
| Observability | Full telemetry required; fingerprint comparison logged before execution |

---

### 3.5 DEGRADED

| Aspect | Governance semantics |
|---|---|
| Authorized operations | Partial orchestration under deterministic degradation conditions; no silent fallback execution (AP-FP4) |
| Degradation governance | Config V2-governed degradation thresholds apply; degradation condition is observable and attributable |
| Provider governance | Degradation does not authorize direct provider dispatch; delegation model remains intact |
| Recovery governance | Recovery cadence governed by Config V2; no hardcoded retry-immediately behavior (AP-FP3); retry thresholds resolve from `outreach_max_retry_attempts` |
| Observability | DEGRADED alert emitted with `degradation_reason`, `affected_domains`, `recovery_estimate`; never silently swallowed |

---

### 3.6 MAINTENANCE

| Aspect | Governance semantics |
|---|---|
| Authorized operations | Read-only platform access; no orchestration evaluation loops; governance-safe maintenance window operations |
| Provider governance | All outbound suppressed |
| Live effects produced | 0 |
| Observability | Maintenance window entry/exit logged with `correlation_id` and operator attribution |

---

## 4. ENVIRONMENT CLASSIFICATION

---

Environments differ operationally — not architecturally. Governance invariants apply equally in all environments.

---

### 4.1 LOCAL

| Aspect | Classification |
|---|---|
| Default execution mode | SHADOW |
| Permitted execution modes | SHADOW, REPLAY, REGENERATION, DEGRADED |
| LIVE activation | Not permitted without explicit Governance Administrator override |
| Data sources | Local PostgreSQL dev instance; SQL Server mocked or pointed at non-production source |
| Provider interactions | `outbound_suppressed = true` in all modes |
| Governance invariants | All invariants enforced identically to PRODUCTION |
| Attribution continuity | Enforced; `ATTRIBUTION_INCOMPLETE` surfaces on null fields |
| Purpose | Development, unit verification, governance contract validation |

---

### 4.2 STAGING

| Aspect | Classification |
|---|---|
| Default execution mode | SHADOW |
| Permitted execution modes | SHADOW, REPLAY, REGENERATION, DEGRADED |
| LIVE activation | Requires Governance Administrator authorization + deployment-stage certification checkpoint per `execution/build_phases.md` |
| Data sources | Staging PostgreSQL; SQL Server staging mirror or sanitized extract |
| Provider interactions | `outbound_suppressed = true` unless LIVE activation is explicitly authorized |
| Governance invariants | All invariants enforced identically to PRODUCTION |
| Attribution continuity | Enforced |
| Purpose | Integration verification, governance contract certification, deployment-stage validation |

---

### 4.3 PRODUCTION

| Aspect | Classification |
|---|---|
| Default execution mode | SHADOW until Phase 12 certification complete |
| Permitted execution modes | All six modes |
| LIVE activation | Requires Phase 12 certification + Governance Administrator authorization + `activation_record_present = true` + explicit acknowledgement; automated services prohibited from triggering (AP-RT7) |
| Data sources | Live PostgreSQL three-schema instance; SQL Server read-only authoritative source |
| Provider interactions | Governed per execution mode |
| Governance invariants | All invariants enforced; certification suite must pass before LIVE activation |
| Attribution continuity | Enforced; audit record required for every governance-boundary-crossing action |
| Purpose | LIVE orchestration under full governance; immutable lineage production |

---

## 5. GOVERNANCE INVARIANTS

---

All invariants apply in all environments and all execution modes.

### 5.1 Invariants (INV-1 through INV-7)

Defined authoritatively in `spec/03_state_transition_rules.md`. Enforced across all execution layers. Certified by `tests/test_shadow_safety.py` and `tests/test_dashboard.py`.

| Invariant | Rule |
|---|---|
| INV-1 | FINALIZED snapshot is immutable — no update, overwrite, or deletion |
| INV-2 | Exactly one Config Version is ACTIVE at all times |
| INV-3 (FAD-3) | Config Version activation is prospective-only — no backdated activation |
| INV-4 (AP-RT2) | No LIVE effects from replay — `live_effects_produced = 0` on all replay outputs |
| INV-5 | Attribution continuity — `correlation_id`, `execution_mode`, `execution_type` mandatory on every record |
| INV-6 (FAD-1) | FINALIZED_COPY AI narrative immutability — `allows_update = false` after FINALIZED state |
| INV-7 | No hardcoded thresholds — all orchestration parameters governed by Config Version Registry |

---

### 5.2 Foundational Architecture Decisions (FAD-1 through FAD-6)

Defined authoritatively in `spec/01_requirements.md`. Non-negotiable across all environments.

| FAD | Decision |
|---|---|
| FAD-1 | Frozen AI copy — AI narrative is deep-copied at snapshot FINALIZED time and remains immutable |
| FAD-2 | Snapshot-centric historical — all longitudinal analysis uses warehouse snapshots, not live operational data |
| FAD-3 | Prospective-only config activation — no retroactive config version changes |
| FAD-4 | Append-only audit log — `student_timeline_events` and `state_transition_log` are append-only; no deletions |
| FAD-5 | SQL Server read-only boundary — no write grants provisioned; write attempt produces `ArchitecturalViolation` |
| FAD-6 | Three-schema privilege separation — `public`, `warehouse`, `compliance_audit` with distinct service accounts |

---

## 6. CONFIG V2 GOVERNANCE

---

### 6.1 Runtime Parameters Are Config V2-Governed

No environment configuration, classification tier, or feature flag may substitute hardcoded constants for the following Config Version Registry parameters:

| Parameter class | Config V2 Group | Governed parameter |
|---|---|---|
| Retry attempt ceiling | Group A | `outreach_max_retry_attempts` |
| Retry timing window | Group A | `outreach_retry_interval_hours` |
| Concurrency limit | Group A | `orchestration_concurrency_limit` |
| Channel progression | Group A | `outreach_channel_sequence` |
| Eligibility thresholds | Group B | `eligibility_*` parameters |
| Escalation thresholds | Group C | `escalation_*` parameters |

---

### 6.2 Config Version Lifecycle Governance

* Exactly one Config Version is ACTIVE at all times (INV-2)
* Config Version activation is prospective-only (INV-3, FAD-3) — no retroactive changes
* All orchestration cycles consume the ACTIVE config at evaluation time and record `config_version_id` in every output
* Replay cycles use `historical_config_version_id` — never the current ACTIVE version
* Config Version rollback is forbidden — superseded versions are immutable historical records

---

## 7. OPERATIONAL FEATURE GOVERNANCE

---

### 7.1 Feature Governance Principles

Platform features do not have enable/disable flags that vary by classification tier. Feature availability is governed by:

* Execution mode (SHADOW suppresses outbound; REPLAY suppresses live inference)
* Config Version Registry parameters (thresholds, windows, concurrency)
* Deployment-stage certification checkpoints (per `execution/build_phases.md`)
* Governance Administrator authorization (for LIVE activation)

No feature may be enabled in a way that violates governance invariants. No feature may be disabled in a way that silently bypasses attribution continuity.

---

### 7.2 Replay-Safe Feature Governance

All feature invocations must be replay-safe by construction. A feature that behaves differently in replay context than in LIVE context without explicit governance authorization is a specification defect. Replay-safe behavior is not optional and is not a deployment-stage add-on.

---

### 7.3 Feature Rollout Attribution

Feature rollout changes (new Config Version activation, updated orchestration parameters) are governance events. They produce:

* `config_version_id` transition recorded in Config Version Registry
* `SUPERSEDED` state for the previous ACTIVE version
* `activation_record_present = true` for the new ACTIVE version
* Attribution lineage enabling reconstruction of which orchestration cycles ran under which config version

---

## 8. DEPLOYMENT-STAGE GOVERNANCE

---

### 8.1 Governance-First Sequencing

Governance infrastructure must exist before any operation that creates governance-sensitive records. Deployment stage does not authorize relaxation of governance foundations. The 12-phase governance-first sequencing model in `execution/build_phases.md` governs the order of LIVE activation authorization.

---

### 8.2 Deployment Maturity Classification

| Deployment stage | Governance state | LIVE activation status |
|---|---|---|
| Phases 1–5 complete | Pre-governance execution services operational in SHADOW mode | LIVE not authorized |
| Phases 6–9 complete | Governance foundations operational; snapshot and reporting lifecycle initialized | LIVE not authorized until Phase 12 certification |
| Phases 10–11 complete | Compliance workflow and observability validation complete | Governance Administrator may initiate Phase 12 review |
| Phase 12 complete | Full governance certification | LIVE activation authorized pending Governance Administrator sign-off |

---

### 8.3 SHADOW→LIVE Transition Governance

SHADOW→LIVE is a governance boundary crossing, not an operational toggle. Requirements:

* Phase 12 certification complete (`execution/build_phases.md §12`)
* Governance Administrator authorization recorded
* `activation_record_present = true` in Config Version Registry
* Explicit acknowledgement checkbox completed by Governance Administrator
* Automated services prohibited from triggering this transition (AP-RT7, `runtime/system_loop.md §3.5`)

Governance does not downgrade after LIVE activation. LIVE→SHADOW transitions are permitted for operational safety. SHADOW→LIVE reactivation requires the same authorization sequence.

---

## 9. IMMUTABLE LINEAGE GUARANTEES

---

These guarantees apply in all environments, all execution modes, and all deployment stages.

| Guarantee | Enforcement |
|---|---|
| FINALIZED snapshot immutability | `allows_update = false`; write attempt → `IMMUTABLE_RECORD_VIOLATION` |
| Append-only audit log | `student_timeline_events`, `state_transition_log` — INSERT only; no UPDATE/DELETE permissions granted (FAD-4) |
| REPORT_PUBLISHED immutability | Report record locked at publication; regeneration creates new version lineage |
| FINALIZED_COPY AI narrative immutability | `warehouse.snapshot_ai_narratives` — `allows_update = false` after FINALIZED state (FAD-1, INV-6) |
| Attribution record completeness | `correlation_id`, `execution_mode`, `execution_type`, `config_version_id` non-nullable on every governance-quality record (INV-5) |
| SQL Server read-only boundary | No write grants on SQL Server service account; write attempt → `ArchitecturalViolation` (FAD-5) |

---

## 10. ACCEPTANCE CRITERIA

---

### Case 1 — Governance Invariant Universality

**Given** any environment (LOCAL, STAGING, PRODUCTION)  
**When** any orchestration operation executes  
**Then** INV-1 through INV-7 and FAD-1 through FAD-6 apply without relaxation

---

### Case 2 — SHADOW Containment

**Given** execution mode = SHADOW  
**When** any orchestration intent is evaluated  
**Then** `outbound_suppressed = true`, `governance_scope = SHADOW_ONLY`, `live_effects_produced = 0`

---

### Case 3 — Replay Isolation

**Given** execution mode = REPLAY  
**When** any orchestration cycle executes  
**Then** `governance_scope = REPLAY_ONLY`, `execution_type = replay`, `live_effects_produced = 0`, `historical_config_version_id` used (never current ACTIVE)

---

### Case 4 — Config V2 Parameter Resolution

**Given** any orchestration cycle in any environment  
**When** retry threshold, concurrency limit, or timing window is evaluated  
**Then** value resolves from ACTIVE Config Version Registry — no hardcoded constant substitution permitted (INV-7)

---

### Case 5 — SHADOW→LIVE Transition Gate

**Given** platform is in SHADOW mode in PRODUCTION  
**When** LIVE activation is requested  
**Then** requires Governance Administrator authorization + `activation_record_present = true` + explicit acknowledgement; automated service trigger → governance defect (AP-RT7)

---

### Case 6 — Attribution Continuity in All Environments

**Given** any environment  
**When** any governance-quality record is written  
**Then** `correlation_id`, `execution_mode`, `execution_type`, `config_version_id` are non-null; null fields surface `ATTRIBUTION_INCOMPLETE` (INV-5)

---

### Case 7 — FINALIZED Immutability in All Environments

**Given** any environment  
**When** update or deletion is attempted on a FINALIZED snapshot or FINALIZED_COPY AI narrative  
**Then** operation is rejected; `IMMUTABLE_RECORD_VIOLATION` produced; no silent acceptance (INV-1, INV-6)

---

### Case 8 — Replay Live-Effects Prohibition

**Given** execution mode = REPLAY  
**When** any orchestration cycle completes  
**Then** `live_effects_produced = 0`; non-zero → CRITICAL governance alert regardless of environment (INV-4, AP-RT2)

---

### Case 9 — Deterministic Degradation Observability

**Given** execution mode = DEGRADED  
**When** orchestration operates under degraded conditions  
**Then** DEGRADED alert emitted with `degradation_reason`, `affected_domains`, observable `recovery_estimate`; no silent fallback execution (AP-FP4)

---

### Case 10 — Deployment-Stage LIVE Gate

**Given** deployment stage = pre-Phase 12  
**When** LIVE activation is requested  
**Then** request rejected; Phase 12 certification required before LIVE authorization is available to Governance Administrator

---

## 11. REFERENCES

---

This file is governed by and inherits from:

| Document | Governance inheritance |
|---|---|
| `spec/01_requirements.md` | Platform purpose, FAD-1–FAD-6, operational domains |
| `spec/03_state_transition_rules.md` | INV-1–INV-7, lifecycle domain governance boundaries |
| `spec/04_idempotency_concurrency.md` | Idempotency, concurrency, replay safety |
| `spec/05_external_integrations.md` | Provider authority boundaries, SQL Server read-only boundary |
| `spec/06_observability_operations.md` | Two-category telemetry, governance observability |
| `runtime/system_loop.md` | Six runtime modes (canonical), AP-RT7, degradation governance |
| `runtime/scheduler_design.md` | Scheduler governance, recovery cycle attribution |
| `failure/failure_playbook.md` | AP-FP1–AP-FP8, deterministic degradation, resilience governance |
| `ux/user_experience.md` | UX governance contract, interaction model |
| `ux/operator_workflows.md` | Operator workflow governance |
| `ux/admin_dashboard.md` | Governance-safe visibility architecture |
| `execution/build_phases.md` | 12-phase governance-first sequencing, LIVE activation gates |
| `execution/implementation_plan.md` | Service implementation order, SHADOW→LIVE rollout model |
| `tests/test_shadow_safety.py` | SHADOW containment and replay isolation certification (74 tests) |
| `tests/test_dashboard.py` | Observability governance certification (87 tests) |

---

## END OF FILE
