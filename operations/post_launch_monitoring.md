# Post-Launch Monitoring

**Document ID:** LIVE-MON-001  
**Status:** ACTIVE  
**Classification:** Operational Monitoring Plan  
**Governs:** Monitoring cadence, escalation conditions, and reporting after LIVE enablement  
**Reference:** LIVE-GOV-001 Section 5  
**Last Updated:** 2026-05-29

---

> This document defines the monitoring posture for every time window after LIVE activation.  
> It is active from the moment the activation configuration change is applied.  
> It does not expire. Ongoing monitoring is not optional.

---

## Section 1 — First-Hour Monitoring

The first hour after activation is the highest-risk window. A dedicated operator must be present and actively watching the observability surfaces defined below for the full 60-minute window. This is not passive — it requires active attention.

---

### 1.1 Required Operator

- An operator who has read and can execute LIVE-DIS-001 within 2 minutes must be present
- The operator must not be performing other tasks during the first-hour window
- If the assigned operator becomes unavailable, activation must be paused or a replacement designated before proceeding

---

### 1.2 First-Hour Monitoring Checklist (check every 5 minutes)

| # | Check | Required Result | Action if Fails |
|---|---|---|---|
| 1 | `authorized_scope_count` in operator report | Matches expected authorized population count | Immediate emergency disable |
| 2 | `live_effects_produced` in operator report | Matches expected (non-zero only for intended communications) | Emergency disable if unexpected |
| 3 | `provider_dispatch_count` | Matches expected | Emergency disable if unexpected |
| 4 | `attribution_gap_count` | `0` | Emergency disable |
| 5 | `finalized_violation_count` | `0` | Emergency disable |
| 6 | `replay_leakage_count` | `0` | Emergency disable |
| 7 | `governance_invariant_violations` | `0` | Emergency disable |
| 8 | INV-3 violation count | `0` | Immediate emergency disable |
| 9 | INV-4 violation count | `0` | Immediate emergency disable |
| 10 | Structured logs emitting | Log events visible in last 5 minutes | Alert + investigate |
| 11 | `certification_outcome` | `CERTIFICATION_PASSED` or `CERTIFICATION_DEGRADED` | Emergency disable if `CERTIFICATION_FAILED` |
| 12 | AUTHORIZED scope only for intended population | No records with unexpected identity receiving AUTHORIZED scope | Emergency disable |
| 13 | Replay scope intact | Replay records show `REPLAY_ONLY` | Emergency disable if replay records show `AUTHORIZED` |

---

### 1.3 First-Hour Summary Report

At the end of the first hour, produce and retain a summary report:

```
FIRST-HOUR MONITORING REPORT
------------------------------
Activation record ID: ________________________________
Monitoring operator: ________________________________
Start time: ISO-8601
End time: ISO-8601

Summary metrics:
  Total records processed: ___
  AUTHORIZED scope count: ___  (expected: ___)
  SHADOW_ONLY scope count: ___
  REPLAY_ONLY scope count: ___
  Live effects produced: ___  (expected: ___)
  Provider dispatches: ___  (expected: ___)
  Attribution gaps: ___  (must be 0)
  Invariant violations: ___  (must be 0)
  Certification outcome: ___

Incidents during first hour: [ ] None  [ ] See attached incident log

Operator assessment: [ ] All nominal  [ ] Concerns noted below
Notes: ________________________________

Signed: ________________________________
Date: YYYY-MM-DD
Time: HH:MM UTC
```

---

## Section 2 — First-Day Monitoring

The first 24 hours after activation requires more frequent than normal monitoring but less intensive than the first hour. An on-call operator must be reachable at all times during this window.

---

### 2.1 Monitoring Cadence (hours 1–24)

| Window | Check Frequency | Who |
|---|---|---|
| Hours 1–4 | Every 15 minutes | Dedicated on-call operator |
| Hours 4–8 | Every 30 minutes | On-call operator |
| Hours 8–16 | Every 60 minutes | On-call operator |
| Hours 16–24 | Every 60 minutes (or per alerting) | On-call operator |

---

### 2.2 First-Day Monitoring Checks

These checks apply at every monitoring interval during hours 1–24:

| Check | Required Result | Action if Fails |
|---|---|---|
| Operator report `certification_outcome` | `CERTIFICATION_PASSED` or `CERTIFICATION_DEGRADED` | Emergency disable if `CERTIFICATION_FAILED` |
| `attribution_gap_count` | `0` | Emergency disable |
| `governance_invariant_violations` | `0` | Emergency disable |
| `authorized_scope_count` vs expected | Within ±10% of expected count | Investigate; disable if unexpectedly large |
| `live_effects_produced` vs expected | Within ±10% of expected | Investigate; disable if much higher than expected |
| Structured log health | Log events visible, all 21 fields present in sample | Alert + investigate |
| Config V2 active version count | Exactly 1 ACTIVE | Alert + investigate; do not disable unless effects observed |
| Degradation events | Any degradation: deterministic, attributed, observable | Alert if degradation count rising; disable if unattributed degradation |

---

### 2.3 First-Day Summary Report

At the end of the first 24 hours, produce and retain a first-day report. The format follows the first-hour report but covers the full 24-hour window with hourly breakdowns of key metrics.

---

## Section 3 — First-Week Monitoring

Hours 24–168 (days 2–7). The platform is considered stable enough for the normal on-call rotation but not yet in steady-state. Monitoring continues at elevated cadence.

---

### 3.1 Monitoring Cadence (hours 24–168)

| Window | Check Frequency | Who |
|---|---|---|
| Hours 24–48 | Every 2 hours | On-call rotation |
| Hours 48–168 | Every 4 hours or per alerting | On-call rotation |

---

### 3.2 First-Week Monitoring Checks

| Check | Required Result | Action if Fails |
|---|---|---|
| Daily operator report | `certification_outcome == CERTIFICATION_PASSED` | Investigate; escalate if FAILED |
| Daily governance certification run | `GovernanceCertResult.total_violations == 0` | Investigate; escalate if >0 |
| Daily attribution check | `attribution_gap_count == 0` for daily batch | Investigate; escalate if >0 |
| Weekly load certification | 1000-record campaign shows all zeros | Escalate if any violations |
| AUTHORIZED scope count trend | Stable, no unexpected spikes | Investigate; disable if spike > 2× expected |
| Degradation trend | Degradation rate not rising week-over-week | Investigate if rising |
| Replay operation safety | Any replay runs show zero leakage, zero violations | Emergency disable if replay violations |

---

### 3.3 First-Week Summary Report

At the end of day 7, produce a weekly summary report including:

- Total records processed by scope (AUTHORIZED, SHADOW_ONLY, REPLAY_ONLY, MAINTENANCE, UNAVAILABLE)
- Total live effects produced vs expected
- Invariant violation count (must be 0)
- FAD violation count (must be 0)
- Degradation event breakdown by failure mode
- Attribution gap count (must be 0)
- Any incidents during the week with resolution summary
- Recommendation: continue, investigate further, or disable

This report is retained as part of the LIVE operational record.

---

## Section 4 — Escalation Conditions

---

### 4.1 Immediate Emergency Disable (no approval required)

Escalate to emergency disable procedure (LIVE-DIS-001) immediately for:

| Condition | Observable Signal |
|---|---|
| INV-3 violation | Replay record with `live_effects_produced > 0` |
| INV-4 violation | SHADOW_ONLY record with `provider_dispatch_count > 0` |
| FAD-1 violation | FINALIZED record with `is_mutable == True` |
| FAD-4 violation | Lineage record missing or modified |
| Attribution gap count > 0 | `attribution_gap_count > 0` in operator report |
| Unexpected AUTHORIZED recipients | AUTHORIZED scope for identities outside the authorized population |
| Replay records in AUTHORIZED scope | Any replay record with `governance_scope == AUTHORIZED` |
| `live_effects_produced` much higher than expected | > 2× expected volume in any 15-minute window |
| Structured logs completely stopped | No log events for > 5 minutes during active execution |

---

### 4.2 Escalate to On-Call Lead (within 15 minutes)

| Condition | Observable Signal |
|---|---|
| `certification_outcome == CERTIFICATION_FAILED` | Operator report with CERTIFICATION_FAILED outcome |
| Governance invariant violations > 0 | `GovernanceCertResult.total_violations > 0` |
| Config V2 active version count ≠ 1 | Config resolution producing UNKNOWN_V0 unexpectedly |
| Degradation count rising | 3 consecutive monitoring intervals showing increasing degradation |
| Any INV-5 through INV-7 violation | Any violation count > 0 in governance certification |
| Attribution fields missing in > 1% of records | Attribution completeness check below 99% |

---

### 4.3 Escalate to Platform Owner (within 1 hour)

| Condition | Observable Signal |
|---|---|
| Any post-disable (system was disabled and re-enabled required) | Disable record written |
| Weekly metrics show downward trend in certification passing rate | Operator report trend over 7 days |
| Any open CRITICAL governance defect | Defect register |
| Any external complaint about unexpected communications | Support ticket, direct contact |

---

### 4.4 Escalation Contacts

| Role | Contact | Response SLA |
|---|---|---|
| On-call operator | [defined in on-call rotation] | Immediate |
| Operations Lead | [defined in team directory] | 15 minutes |
| Technical Lead | [defined in team directory] | 30 minutes |
| Platform Owner | ali@colaberry.com | 1 hour |

---

## Section 5 — Reporting Cadence

---

### 5.1 Automated Reports

| Report | Frequency | Trigger | Retained |
|---|---|---|---|
| Operator report | Every 6 hours | Scheduled | Yes (append-only) |
| Governance certification run | Daily | Scheduled | Yes |
| Attribution continuity check | Every worker cycle | Automatic | Sampled (1 per hour retained) |
| Invariant spot check | Every scheduler cycle | Automatic | Violations retained; passing not persisted |
| Load certification | Weekly | Scheduled | Yes |

---

### 5.2 Manual Reports

| Report | Frequency | Owner | Retained |
|---|---|---|---|
| First-hour monitoring report | Once (post-activation) | On-call operator | Yes |
| First-day summary report | Once (24h post-activation) | Operations Lead | Yes |
| First-week summary report | Once (7d post-activation) | Operations Lead | Yes |
| Monthly governance health review | Monthly | Platform Owner | Yes |
| Post-disable audit report | After any emergency disable | Operations Lead | Yes |

---

### 5.3 Report Retention Requirements

All monitoring reports are governance artifacts. They must be retained for a minimum of 2 years after the final LIVE execution they cover. They are append-only. No report may be edited after it is signed.

---

## Section 6 — Steady-State Monitoring (Post Week 1)

After the first-week monitoring period, the platform enters steady-state monitoring. The following minimum requirements apply indefinitely.

| Check | Minimum Frequency | Required Result |
|---|---|---|
| Operator report review | Daily | `certification_outcome ∈ {PASSED, DEGRADED}` |
| Governance certification | Weekly | `total_violations == 0` |
| Attribution check | Weekly | `attribution_gap_count == 0` |
| Load certification | Monthly | All zeros at 1000 records |
| Emergency disable test | Quarterly | Dry-run completes in < 2 minutes |
| Full approval chain review | Annually | Authorization still valid for current scope |

If the authorized population, communication types, or volume changes significantly from what was defined in go_live_certification.md Section 3.2, the activation scope must be updated with a new activation decision and a new approval chain completion.

---

## Section 7 — Monitoring Infrastructure Requirements

The following infrastructure must be operational before LIVE is enabled and must remain operational during all LIVE execution.

| Infrastructure | Requirement |
|---|---|
| Structured log collection | All 21 required fields collected and queryable |
| Metric pipeline | `success_rate`, `failure_rate`, `latency_p50/p95/p99`, `volume` collected for all long-running operations |
| Alerting | Triggers within 5 minutes of CRITICAL invariant violation |
| Correlation trace store | End-to-end traces queryable by `correlation_id` |
| Operator report storage | Append-only storage for all generated reports |
| Activation and disable record storage | Immutable storage for activation and disable records |
| On-call rotation | At least one person with emergency disable authority available at all times |

If any monitoring infrastructure becomes unavailable during LIVE execution:

1. Classify as `OBSERVABILITY_DEGRADATION` (LOW severity per degradation map)
2. Investigate root cause within 30 minutes
3. If infrastructure unavailable for > 2 hours: execute emergency disable (the system cannot be operated safely without observability)

---

*This document governs monitoring from the moment of LIVE activation. It is append-only. Updates add requirements; they do not remove them. Each update is dated and versioned.*
