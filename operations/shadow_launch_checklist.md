# PRODUCTION-SHADOW Launch Checklist

**Document ID:** SLC-001  
**Status:** ACTIVE — TO BE COMPLETED BEFORE SHADOW LAUNCH  
**Classification:** Operational Checklist  
**Governs:** Final gate before PRODUCTION-SHADOW activation with real infrastructure and real data  
**Reference:** PRR-001, ORR-001, LIVE-CHK-001  
**Last Updated:** 2026-05-29  

---

> **This checklist governs PRODUCTION-SHADOW launch only.**  
> PRODUCTION-SHADOW means real PostgreSQL, real SQL Server data, real scheduler cycles — but ZERO outbound communications.  
> EXECUTION_MODE=SHADOW must be confirmed set and must not be changed during or after this checklist.  
> Completing this checklist does NOT authorize LIVE enablement. It authorizes SHADOW operation only.  
> Each item must be verified with a concrete artifact before it is checked.

---

## SECTION A — Prerequisites Resolved

These are the two CRITICAL risks from ORR-001 that block any SHADOW launch.

| # | Item | Evidence Required | Status | Evidence Ref | Verified By | Date |
|---|---|---|---|---|---|---|
| A-1 | PostgreSQL is running | `docker compose ps` shows `db (healthy)` or equivalent health signal | `[ ]` | | | |
| A-2 | All 3 Alembic migrations applied | `alembic current` output shows `0003 (head)` with no pending migrations | `[ ]` | | | |
| A-3 | V1 Config record present and ACTIVE | `SELECT version_number, status FROM config_version_registry WHERE status='ACTIVE'` returns 1 row with `version_number=1` | `[ ]` | | | |
| A-4 | Config V2 startup query wired | Application startup log shows `"config_version_id"` value that is NOT `"UNKNOWN_V0"` | `[ ]` | | | |
| A-5 | API container starts cleanly | `docker compose up -d api` + startup log event `"event": "application_started"` with `"degradation_state": false` | `[ ]` | | | |

---

## SECTION B — Security Verification

| # | Item | Evidence Required | Status | Evidence Ref | Verified By | Date |
|---|---|---|---|---|---|---|
| B-1 | `.env` is NOT tracked by git | `git check-ignore -v .env` outputs `.env` (excluded) OR `git ls-files .env` outputs nothing | `[ ]` | | | |
| B-2 | `.env` is in `.gitignore` | `grep -n ".env" .gitignore` returns a matching line | `[ ]` | | | |
| B-3 | EXECUTION_MODE is SHADOW | `grep EXECUTION_MODE .env` returns `EXECUTION_MODE=SHADOW` | `[ ]` | | | |
| B-4 | No AUTHORIZED scope in startup log | Startup log does not contain `"governance_scope": "AUTHORIZED"` | `[ ]` | | | |

---

## SECTION C — Connectivity Verification

| # | Item | Evidence Required | Status | Evidence Ref | Verified By | Date |
|---|---|---|---|---|---|---|
| C-1 | PostgreSQL connection confirmed | API startup log shows no `asyncpg` connection errors; health endpoint `/health` returns 200 | `[ ]` | | | |
| C-2 | SQL Server connectivity confirmed | Smoke test `SELECT 1` against `hypv8669.hostedbyappliedi.net:1433` succeeds within 10 seconds; result logged with timestamp | `[ ]` | | | |
| C-3 | SQL Server returns student records | `SELECT TOP 1 * FROM <student_table>` returns at least 1 row (confirm table name from sync service) | `[ ]` | | | |
| C-4 | GHL credentials noted as absent (acceptable for SHADOW) | `.env` confirms `GHL_API_KEY=` is empty; no GHL dispatch expected in SHADOW | `[ ]` | | | |

---

## SECTION D — Governance Containment Verification

These checks confirm that the governance containment layer is active and correct in the real runtime environment.

| # | Item | Evidence Required | Status | Evidence Ref | Verified By | Date |
|---|---|---|---|---|---|---|
| D-1 | SHADOW scope on startup | Startup log shows `"governance_scope": "SHADOW_ONLY"` | `[ ]` | | | |
| D-2 | Phase-12 cert gate active | Startup log shows `"shadow_containment_active": true` | `[ ]` | | | |
| D-3 | Zero live effects on startup | Startup log does NOT contain `"live_effects_produced"` > 0 | `[ ]` | | | |
| D-4 | Attribution fields in startup log | Startup log contains `"startup_correlation_id"` (non-empty UUID) | `[ ]` | | | |
| D-5 | AUTHORIZED scope unreachable | Health endpoint or runtime log confirms AUTHORIZED scope is not in scope derivation output | `[ ]` | | | |
| D-6 | Scheduler starts with governance context | Startup log shows scheduler configured with execution_mode and config_version_id fields | `[ ]` | | | |

---

## SECTION E — First Orchestration Cycle Verification

This section must be completed after the first real scheduler-triggered orchestration cycle runs.

| # | Item | Evidence Required | Status | Evidence Ref | Verified By | Date |
|---|---|---|---|---|---|---|
| E-1 | First cycle completes without error | Scheduler log shows first cycle completion; no unhandled exception | `[ ]` | | | |
| E-2 | First cycle scope is SHADOW_ONLY | Log records for first cycle show `"governance_scope": "SHADOW_ONLY"` | `[ ]` | | | |
| E-3 | First cycle attribution complete | Log records show `correlation_id`, `execution_mode`, `config_version_id` all present and non-empty | `[ ]` | | | |
| E-4 | First cycle live effects = 0 | Log or metrics show `live_effects_produced=0` for the cycle | `[ ]` | | | |
| E-5 | First cycle provider dispatches = 0 | Log or metrics show `provider_dispatch_count=0` for the cycle | `[ ]` | | | |
| E-6 | Outbound suppressed for all records | Structured log shows `"outbound_suppressed": true` for all records in cycle | `[ ]` | | | |
| E-7 | Config V2 version_id in cycle records | Cycle records carry a real `config_version_id` (not UNKNOWN_V0) | `[ ]` | | | |

---

## SECTION F — Observability Baseline

| # | Item | Evidence Required | Status | Evidence Ref | Verified By | Date |
|---|---|---|---|---|---|---|
| F-1 | Structured logs emitting to stdout | `docker compose logs api` shows JSON-structured log lines | `[ ]` | | | |
| F-2 | All log lines have `timestamp` and `event` fields | Sample 10 log lines — all contain `timestamp` and `event` | `[ ]` | | | |
| F-3 | No PII in log output | Sample 50 log lines — none contain field names: `phone_number`, `email`, `first_name`, `last_name`, `transcript` | `[ ]` | | | |
| F-4 | Metrics endpoint accessible | `GET /metrics` returns HTTP 200 with measurable data | `[ ]` | | | |
| F-5 | Manual monitoring procedure documented | A written procedure exists describing how to query logs for the prior 1 hour | `[ ]` | | | |
| F-6 | Log query for governance scope confirmed | Operator can filter logs by `governance_scope` and retrieve results within 2 minutes | `[ ]` | | | |

---

## SECTION G — Risk Register Review

| # | Item | Evidence Required | Status | Evidence Ref | Verified By | Date |
|---|---|---|---|---|---|---|
| G-1 | RISK-001 resolved | Config V2 startup query wired (see A-4) | `[ ]` | | | |
| G-2 | RISK-003 resolved | PostgreSQL running (see A-1 through A-5) | `[ ]` | | | |
| G-3 | RISK-007 tracked | pytest-asyncio issue documented; fix scheduled | `[ ]` | | | |
| G-4 | RISK-008 assessed | `.env` git tracking status verified (see B-1, B-2) | `[ ]` | | | |
| G-5 | RISK-009 tracked | Mandrill audit scheduled within first week of SHADOW | `[ ]` | | | |
| G-6 | RISK-010 partially mitigated | At least one named on-call contact identified for SHADOW monitoring period | `[ ]` | | | |
| G-7 | All CRITICAL risks in ORR-001 resolved | RISK-001 and RISK-003 both RESOLVED | `[ ]` | | | |

---

## SECTION H — Pre-Launch Final Checks

These checks are performed immediately before opening the first real SHADOW orchestration cycle.

| # | Item | Evidence Required | Status | Evidence Ref | Verified By | Date |
|---|---|---|---|---|---|---|
| H-1 | All sections A–G complete | This checklist shows 100% of items checked | `[ ]` | | | |
| H-2 | EXECUTION_MODE confirmed SHADOW within last 1 hour | Fresh `grep EXECUTION_MODE .env` output with timestamp | `[ ]` | | | |
| H-3 | PostgreSQL health confirmed within last 1 hour | `docker compose ps` output with timestamp | `[ ]` | | | |
| H-4 | No new HIGH-severity risks since checklist started | ORR-001 reviewed; no new CRITICAL or HIGH risks added since A-1 was checked | `[ ]` | | | |
| H-5 | Named contact available for first 2 hours | A person who has read LIVE-DIS-001 is reachable and available to disable if needed | `[ ]` | | | |

---

## Checklist Completion Record

```
SHADOW LAUNCH AUTHORIZATION
-----------------------------
Checklist version: SLC-001
Completed by: ________________________________
Role: ________________________________
Date: YYYY-MM-DD
Time: HH:MM UTC

Sections complete:
  A (Prerequisites Resolved):        [ ] ALL CHECKED
  B (Security Verification):         [ ] ALL CHECKED
  C (Connectivity Verification):     [ ] ALL CHECKED
  D (Governance Containment):        [ ] ALL CHECKED
  E (First Cycle Verification):      [ ] ALL CHECKED  [complete post-launch]
  F (Observability Baseline):        [ ] ALL CHECKED
  G (Risk Register Review):          [ ] ALL CHECKED
  H (Final Pre-Launch Checks):       [ ] ALL CHECKED

Total items: 41
Items checked at launch: ___ (H-1 through H-5 confirmed after E is skipped pre-launch)
Items post-launch pending: ___ (Section E — filled after first cycle completes)

IMPORTANT: This checklist authorizes SHADOW operation only.
           SHADOW mode must remain active. EXECUTION_MODE=SHADOW must not be changed.
           Authorizing LIVE requires a separate process: LIVE-GOV-001 + LIVE-CERT-001.

Declaration:
I confirm that all items above have been verified with concrete artifacts as of the date and time
above, and that EXECUTION_MODE=SHADOW is set and will not be changed without completing the full
LIVE enablement governance process (LIVE-GOV-001).

Signature: ________________________________
Date: YYYY-MM-DD
```

---

## Post-Launch Monitoring (First 24 Hours)

Once SHADOW operation begins, the following minimum monitoring applies. This is less intensive than the first-hour LIVE monitoring in LIVE-MON-001 but establishes the SHADOW baseline.

| Window | Check | Required Result | Action if Fails |
|---|---|---|---|
| First 30 minutes | `governance_scope` in all cycle records | `SHADOW_ONLY` or `REPLAY_ONLY` only | Investigate immediately |
| First 30 minutes | `live_effects_produced` in any cycle record | `0` | Immediately investigate; disable if nonzero |
| First 30 minutes | `attribution_gap_count` | `0` | Investigate; check correlation_id generation |
| Hourly (first 8 hours) | Structured logs emitting | JSON log events visible | Alert + investigate |
| Hourly (first 8 hours) | Config V2 version_id in cycle records | Not UNKNOWN_V0 | Investigate RISK-001 |
| Daily | Full test suite | 2947+ passing, 0 new failures | Investigate any new failure immediately |
| Daily | SQL Server sync completing | Sync log shows success or documented degradation | Investigate if silent |

---

*This checklist is a governance artifact. It must be signed and retained as part of the SHADOW operational record. Once signed, it is immutable. Updates require a new SLC-002 instance.*
