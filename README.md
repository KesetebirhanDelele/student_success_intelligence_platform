# Student Success Intelligence Platform (SSIP)

A **governance-safe orchestration and operational intelligence platform** for monitoring, analyzing, and acting on the full operational lifecycle of enrolled students.

Outreach automation is a **subsystem** of this platform — not its primary architectural identity. The platform's central responsibility is **orchestration-intent governance**: evaluating student risk signals, emitting governed orchestration intents, and maintaining immutable lineage across all lifecycle transitions.

**Execution mode: SHADOW** — all outbound provider calls are suppressed until `EXECUTION_MODE=LIVE` is explicitly set via Governance Administrator authorization. SHADOW mode is a mandatory operational tier, not a debugging convenience (governed by `runtime/system_loop.md §3.5`).

---

## Governance Model

The SSIP governance model establishes non-negotiable baseline guarantees across all execution modes and scope tiers.

### Core Principles

| Principle | Governance contract |
|---|---|
| Orchestration emits intents, not actions | Runtime coordinates governance-safe intent delegation; no loop directly dispatches to providers |
| Providers are `platform_supplementary` | GHL, Synthflow, SMS, and email are delivery vehicles; they are not authority boundaries |
| Replay and SHADOW are isolated from LIVE | Replay outputs carry `execution_type = replay` and `governance_scope = REPLAY_ONLY`; no LIVE effects permitted |
| Immutable lineage is foundational | FINALIZED snapshots, REPORT_PUBLISHED reports, and archived AI narratives are permanently read-only |
| Config V2 governs orchestration behavior | Retry thresholds, timing windows, and concurrency limits are Config Version Registry values; no hardcoded constants permitted |
| Attribution continuity is mandatory | Every record carries `correlation_id`, `execution_mode`, `execution_type`, and `config_version_id`; null fields surface `ATTRIBUTION_INCOMPLETE` |
| SQL Server is read-only authoritative | No platform service may write to SQL Server; SQL Server data wins on field conflicts with `origin_authority = sql_server_authoritative` |

### Governance Invariants (INV-1 through INV-7)

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

### Foundational Architecture Decisions (FAD-1 through FAD-6)

Defined authoritatively in `spec/01_requirements.md`.

| FAD | Decision |
|---|---|
| FAD-1 | Frozen AI copy — AI narrative is deep-copied at snapshot FINALIZED time and remains immutable |
| FAD-2 | Snapshot-centric historical — all longitudinal analysis uses warehouse snapshots, not live operational data |
| FAD-3 | Prospective-only config activation — no retroactive config version changes |
| FAD-4 | Append-only audit log — `student_timeline_events` and `state_transition_log` are append-only; no deletions |
| FAD-5 | SQL Server read-only boundary — no write grants provisioned; write attempt produces `ArchitecturalViolation` |
| FAD-6 | Three-schema privilege separation — `public`, `warehouse`, `compliance_audit` with distinct service accounts |

---

## Architecture

### Governance Layers

| Layer | Location | Role |
|---|---|---|
| **Specifications** | `/spec/` | Canonical governance contracts, state machine rules, API contracts, data model |
| **Directives** | `/directives/` | Advisory intent and evaluation criteria — no business logic, no hardcoded thresholds |
| **Runtime** | `/runtime/`, `/failure/` | Governance-safe orchestration coordination, resilience governance, replay-safe sequencing |
| **Execution** | `/app/` | Deterministic service implementations; SHADOW mode until Phase 12 certification |
| **UX** | `/frontend/`, `/ux/` | Governance-safe visibility surfaces — governed state display + governed API invocations only |
| **Verification** | `/tests/` | Governance-safe certification suite — certifies invariants and containment, not feature outputs |

### What Each Layer Does NOT Do

| Layer | Explicitly prohibited |
|---|---|
| Directives | Contains no business logic, no execution code, no hardcoded thresholds |
| Runtime | Directly dispatches to providers; owns provider API credentials; mutates orchestration state directly |
| UX | Executes business logic; calculates thresholds; triggers live effects through replay pathways |
| Verification | Substitutes for database constraints; validates UI rendering details |

### Orchestration Architecture

```
SQL Server (read-only, origin_authority: sql_server_authoritative)
    │
    ▼  read-only ingestion with attribution fields
SQL Server Ingestion Service ─── UPSERT public.student_trigger_data
    │                         └── origin_source: mirrored_sql_server
    │                         └── idempotency key: processed_events
    ▼
Eligibility + Priority Evaluation ─── Config V2 governed thresholds
    │
    ▼
Orchestration Intent Emission ─── governance_scope, execution_mode, correlation_id
    │
    ├── SHADOW: outbound_suppressed=true — no HTTP — governance_scope=SHADOW_ONLY
    └── LIVE:   governed provider delegation — governance_scope=LIVE
    │
    ▼
Provider Orchestration Services ─── origin_authority: platform_supplementary
    │
    ▼
Append-Only Persistence ─── warehouse.student_snapshots (FINALIZED = immutable)
                         └── student_timeline_events (append-only, FAD-4)
                         └── state_transition_log (append-only, FAD-4)
```

**Replay path:** Replay orchestration produces `governance_scope = REPLAY_ONLY`, `execution_type = replay`, `live_effects_produced = 0`, and uses `historical_config_version_id` — never the current ACTIVE config. Replay outputs never enter LIVE provider paths (INV-4, AP-RT2).

---

## Execution Mode Governance

| Behavior | SHADOW | LIVE | REPLAY |
|---|---|---|---|
| SQL Server sync | Reads normally | Reads normally | Reads warehouse snapshots |
| Outbound provider calls | `outbound_suppressed = true`; no HTTP | Dispatches via governed provider services | `outbound_suppressed = true`; `governance_scope = REPLAY_ONLY` |
| Orchestration intents | `governance_scope = SHADOW_ONLY` | `governance_scope = LIVE` | `governance_scope = REPLAY_ONLY` |
| Live effects produced | 0 (containment invariant) | ≥ 0 | 0 (invariant; non-zero → CRITICAL governance alert) |
| Dashboard mode badge | `SHADOW MODE` | `LIVE MODE` | `REPLAY MODE` |

**SHADOW → LIVE transition:** Requires Governance Administrator authorization, `activation_record_present = true` in Config Version Registry, and explicit acknowledgement checkbox. Automated services may not trigger this transition (AP-RT7, `runtime/system_loop.md`).

---

## Technology Stack

| Layer | Technology |
|---|---|
| API | Python 3.11 · FastAPI |
| Database | PostgreSQL 16 (via SQLAlchemy async + asyncpg) — three-schema: `public`, `warehouse`, `compliance_audit` |
| Source data | SQL Server (read-only, `origin_authority: sql_server_authoritative`, via pyodbc) |
| Scheduler | APScheduler (daily batch, governance-safe orchestration coordination) |
| LLM | Anthropic Claude API (advisory only; outputs labeled `ai_governance_tier`) |
| Container | Docker Compose |
| Frontend | Single-page dashboard (`frontend/index.html`) — governance-safe visibility surface |

---

## Quick Start

```bash
# 1. Copy env template and fill in credentials
cp .env.example .env
# edit .env — fill MSSQL_HOST, MSSQL_USER, MSSQL_PASS, MSSQL_DATABASE

# 2. Build and start (SHADOW mode — all outbound calls suppressed)
docker compose up -d --build

# 3. Open dashboard
open http://localhost:8080
```

The platform starts in SHADOW mode by default. SQL Server sync and eligibility evaluation run normally. All outbound provider calls are suppressed — no real communications occur.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | Set automatically by Docker Compose (`postgresql+asyncpg://ssip:ssip@db:5432/ssip`) |
| `MSSQL_HOST` | Yes | SQL Server hostname or IP |
| `MSSQL_PORT` | No | Default: `1433` |
| `MSSQL_USER` | Yes | SQL Server login — read-only account; no write grants (FAD-5) |
| `MSSQL_PASS` | Yes | SQL Server password |
| `MSSQL_DATABASE` | Yes | Database name containing source student data |
| `ANTHROPIC_API_KEY` | No | Claude API key for LLM advisory generation (suppressed in SHADOW mode) |
| `GHL_API_KEY` | No | GoHighLevel API key (suppressed in SHADOW mode) |
| `GHL_BASE_URL` | No | GHL base URL |
| `GHL_LOCATION_ID` | No | GHL location ID |
| `SYNTHFLOW_API_KEY` | No | Synthflow API key (suppressed in SHADOW mode) |
| `SYNTHFLOW_PHONE_NUMBER` | No | Outbound caller ID for Synthflow |
| `EXECUTION_MODE` | No | `SHADOW` (default) or `LIVE`. LIVE requires Governance Administrator authorization and Phase 12 certification. |

---

## Governance-Safe Certification Suite

Tests certify governance invariants and containment behavior — not feature outputs. All test files are self-contained and require no imports of production implementation modules.

| File | What it certifies | Certified tests |
|---|---|---|
| `tests/test_shadow_safety.py` | SHADOW containment (SVL-1–3), replay isolation (ROS-1–2, INV-4, AP-RT2), SHADOW→LIVE transition governance (CV2-4, AP-RT7), provider containment, attribution continuity | 74 |
| `tests/test_dashboard.py` | Observability governance, correlation/causation propagation, governance transition visibility, AI telemetry governance, replay observability (ROG-1–7), provider authority (PSG-2–5, DVG-1) | 87 |
| `tests/test_sync.py` | SQL Server sync governance, data quality quarantine, origin authority attribution, dedup gate, no outbound HTTP | 12 |
| `tests/test_actions.py` | Manual action state-machine guards, Config V2 ceiling enforcement, rejection path visibility | 8 |
| `tests/test_work_queue.py` | Priority engine governance, source router, work queue, batch preview | 14 |

**Run the certification suite:**

```bash
docker compose run --rm api python -m pytest tests/ -v
```

---

## Implementation Status

### Governance Architecture — Stabilized

The full governance contract layer has been stabilized as of 2026-05-27. No implementation service may be moved to LIVE mode without satisfying Phase 12 certification checkpoints (`execution/build_phases.md`).

| Contract | Status |
|---|---|
| Requirements, 10 operational domains, 6 FADs, NFRs | Stabilized — `spec/01_requirements.md` |
| State transition rules — all 6 domains, INV-1–INV-7 | Stabilized — `spec/03_state_transition_rules.md` |
| Idempotency and concurrency model | Stabilized — `spec/04_idempotency_concurrency.md` |
| External integrations governance | Stabilized — `spec/05_external_integrations.md` |
| Observability and operational governance | Stabilized — `spec/06_observability_operations.md` |
| API contracts — all 6 API domains | Stabilized — `spec/07_api_contracts.md` |
| Data model — warehouse architecture, three-schema | Stabilized — `spec/08_data_model.md` |
| Security and privacy governance | Stabilized — `spec/09_security_privacy.md` |
| Runtime orchestration architecture | Stabilized — `runtime/system_loop.md` |
| Scheduler governance | Stabilized — `runtime/scheduler_design.md` |
| Daily outreach flow governance | Stabilized — `runtime/daily_outreach_flow.md` |
| Retry cycle governance | Stabilized — `runtime/retry_cycle_flow.md` |
| Resilience: canonical parent contract | Stabilized — `failure/failure_playbook.md` |
| Resilience: scheduler, GHL, LLM failure domains | Stabilized — `failure/scheduling_failures.md`, `failure/ghl_failures.md`, `failure/llm_failures.md` |
| UX governance contract | Stabilized — `ux/user_experience.md` |
| Operator workflow governance | Stabilized — `ux/operator_workflows.md` |
| Dashboard visibility architecture | Stabilized — `ux/admin_dashboard.md` |
| Governance-safe SHADOW/replay certification | Stabilized — `tests/test_shadow_safety.py` (74 tests) |
| Governance-safe observability certification | Stabilized — `tests/test_dashboard.py` (87 tests) |
| Build phases (governance-first sequencing) | Stabilized — `execution/build_phases.md` |
| Implementation plan (service implementation order) | Stabilized — `execution/implementation_plan.md` |

### Execution Services (Phases 1–5) — Operational in SHADOW Mode

The following services were delivered in Phases 1–5 and are operational in SHADOW mode. They predate the stabilized governance architecture and require alignment with finalized governance contracts before LIVE activation:

- SQL Server ingestion and sync service
- Eligibility, priority, and decision engine services
- Outreach service (all outbound suppressed in SHADOW mode)
- Student outreach tracking and APScheduler-based state machine
- AI insights and LLM integration service (advisory; `ai_governance_tier` labeling pending)
- Unified timeline, student notes, and lifecycle drawer
- Source routing, batch processing, work queue, and priority scoring
- Six lifecycle tabs with action bars

### Next Phase — Governance-Architecture Alignment

Per `execution/implementation_plan.md §5`, implementation services are next for governance alignment in the following order: SQL Server ingestion (lineage fields), unified timeline ingestion (append-only enforcement), snapshot orchestration (DRAFT→VALIDATING), AI enrichment (AI_REVIEWED gate), snapshot finalization (FINALIZED boundary), report publication, config governance activation, compliance workflow, observability validation, operational dashboards alignment, production governance readiness.

---

## Canonical References

### Governance Specifications

| Document | Contents |
|---|---|
| `spec/01_requirements.md` | Platform purpose, 10 operational domains, 6 FADs, NFRs, success metrics |
| `spec/03_state_transition_rules.md` | Valid/invalid transitions across all 6 lifecycle domains; INV-1–INV-7 |
| `spec/04_idempotency_concurrency.md` | Multi-domain idempotency model, concurrency governance |
| `spec/05_external_integrations.md` | Provider governance boundaries, SQL Server authority, GHL supplementary model |
| `spec/06_observability_operations.md` | Two-category telemetry, governance-aware observability, universal log schema |
| `spec/07_api_contracts.md` | API contracts across all 6 API domains; idempotency patterns; governance isolation |
| `spec/08_data_model.md` | Warehouse entity model, three-schema architecture, lineage attribution fields |
| `spec/09_security_privacy.md` | Security governance, compliance access model |

### Runtime Contracts

| Document | Contents |
|---|---|
| `runtime/system_loop.md` | Six runtime modes, AP-RT7, degradation governance, canonical orchestration lifecycle |
| `runtime/scheduler_design.md` | Scheduler governance, recovery cycle attribution |
| `runtime/daily_outreach_flow.md` | Daily orchestration cycle governance, SHADOW mode behavior |
| `runtime/retry_cycle_flow.md` | Retry governance, Config V2 Group A, retry orchestration lifecycle |

### Resilience Contracts

| Document | Contents |
|---|---|
| `failure/failure_playbook.md` | Canonical parent resilience contract; AP-FP1–AP-FP8; SUPPRESSED vs UNAVAILABLE |
| `failure/scheduling_failures.md` | Scheduler failure governance |
| `failure/ghl_failures.md` | Provider failure governance |
| `failure/llm_failures.md` | AI governance failure context |

### UX Governance Contracts

| Document | Contents |
|---|---|
| `ux/user_experience.md` | Canonical UX governance contract; interaction model; UX governance invariants |
| `ux/operator_workflows.md` | Operator workflow governance; governed manual actions; replay investigation |
| `ux/admin_dashboard.md` | Governance-safe dashboard visibility architecture; §16–21 governance invariant mapping |

### Execution Sequencing

| Document | Contents |
|---|---|
| `execution/build_phases.md` | Governance-first phase architecture; 12-phase dependency map; validation checkpoints |
| `execution/implementation_plan.md` | Service implementation order; governance blocker analysis; SHADOW→LIVE rollout model |
