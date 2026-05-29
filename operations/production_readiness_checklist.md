# Production Readiness Checklist

**Document ID:** LIVE-CHK-001  
**Status:** ACTIVE — TO BE COMPLETED BEFORE ACTIVATION  
**Classification:** Operational Checklist  
**Governs:** Final production gate before AUTHORIZED scope becomes reachable  
**Reference:** LIVE-GOV-001 Section 9  
**Last Updated:** 2026-05-29

---

> **Instructions:** Each item must be verified independently and checked only when the evidence artifact exists.  
> Checking an item without a concrete artifact is a governance violation.  
> This checklist must be signed and dated by the Operations Lead before Step 3 approval (LIVE-GOV-001 Section 2.1).

---

## A — Certification Evidence

These items confirm that the phased certification program has been completed.

| # | Item | Evidence Required | Status | Evidence Ref | Verified By | Date |
|---|---|---|---|---|---|---|
| A-1 | Phase 53 test suite passes | `pytest` output: 225 passed, 0 failures | `[ ]` | | | |
| A-2 | Phase 54 test suite passes | `pytest` output: 274 passed, 0 failures | `[ ]` | | | |
| A-3 | Phase 55 test suite passes | `pytest` output: 307 passed, 0 failures | `[ ]` | | | |
| A-4 | Phase 56 test suite passes | `pytest` output: 287 passed, 0 failures | `[ ]` | | | |
| A-5 | Full test suite passes | `pytest tests/` with zero unexpected failures | `[ ]` | | | |
| A-6 | Shadow campaign certification PASSED | `OperatorReport.certification_outcome == CERTIFICATION_PASSED` | `[ ]` | | | |
| A-7 | Replay campaign certification passed | `ReplayCertResult.certification_passed == True` for 1000-record run | `[ ]` | | | |
| A-8 | Degradation campaign certification passed | All 5 failure modes certified, `certification_passed == True` | `[ ]` | | | |
| A-9 | Governance invariant certification passed | `GovernanceCertResult.total_violations == 0` for 1000-record run | `[ ]` | | | |
| A-10 | Attribution continuity certified | `AttributionCertResult.attribution_gap_count == 0` for 1000-record run | `[ ]` | | | |

---

## B — Operational Evidence

These items confirm that operations infrastructure is in place and functioning.

| # | Item | Evidence Required | Status | Evidence Ref | Verified By | Date |
|---|---|---|---|---|---|---|
| B-1 | Monitoring infrastructure live | Metrics visible in monitoring surface for ≥ 24 hours of shadow operation | `[ ]` | | | |
| B-2 | Structured logs collecting in production | 100-record sample from PRODUCTION-SHADOW with all 21 required fields | `[ ]` | | | |
| B-3 | Alerting wired up | Test alert fired and received within expected time window | `[ ]` | | | |
| B-4 | Correlation tracing operational | One end-to-end trace demonstrable in production | `[ ]` | | | |
| B-5 | Operator report generation working | Most recent operator report generated successfully with `certification_outcome` field | `[ ]` | | | |
| B-6 | Emergency disable capability tested | Dry-run log with timestamp within last 7 days | `[ ]` | | | |
| B-7 | Post-launch monitoring plan operational | `operations/post_launch_monitoring.md` reviewed and first-hour procedures confirmed | `[ ]` | | | |
| B-8 | All 4 environments isolated and certified | Environment isolation evidence for LOCAL, STAGING, PRODUCTION-SHADOW, PRODUCTION-LIVE | `[ ]` | | | |

---

## C — Attribution Evidence

These items confirm that the attribution chain is intact and observable end-to-end.

| # | Item | Evidence Required | Status | Evidence Ref | Verified By | Date |
|---|---|---|---|---|---|---|
| C-1 | `correlation_id` present in all production records | Zero attribution gaps in 1000-record attribution check | `[ ]` | | | |
| C-2 | `causation_id` present in all production records | Zero gaps in causation chain check | `[ ]` | | | |
| C-3 | `config_version_id` non-UNKNOWN_V0 for all non-degraded records | Config resolution check in PRODUCTION-SHADOW | `[ ]` | | | |
| C-4 | `orchestration_cycle_id` present in all orchestration records | Orchestration cycle attribution verified | `[ ]` | | | |
| C-5 | Attribution chain traceable end-to-end | GINV-4 zero violations in governance visibility test | `[ ]` | | | |
| C-6 | Attribution preserved through all 5 degradation failure modes | `attribution_preserved == True` in degradation certification | `[ ]` | | | |
| C-7 | Attribution preserved through replay operations | `AttributionCertResult` from replay campaign shows zero gaps | `[ ]` | | | |

---

## D — Replay Evidence

These items confirm that replay protections are intact and will remain intact after LIVE activation.

| # | Item | Evidence Required | Status | Evidence Ref | Verified By | Date |
|---|---|---|---|---|---|---|
| D-1 | Replay records produce `REPLAY_ONLY` scope | `ReplayCertResult` showing all replay records in REPLAY_ONLY scope | `[ ]` | | | |
| D-2 | Replay records produce zero live effects | `live_effects_total == 0` in replay campaign result | `[ ]` | | | |
| D-3 | Replay records produce zero provider dispatches | `ReplayCertResult.zero_dispatches == True` | `[ ]` | | | |
| D-4 | Fingerprint continuity verified | Zero fingerprint violations in 1000-record run | `[ ]` | | | |
| D-5 | Historical config resolution verified | All replay records reference non-UNKNOWN_V0 historical config | `[ ]` | | | |
| D-6 | AUTHORIZED scope never produced for replay records | `CampaignAuditResult.authorized_scope_count == 0` in replay campaign | `[ ]` | | | |
| D-7 | FAD-5 verified: replay uses historical config, not current ACTIVE | FAD-5 zero violations in governance certification | `[ ]` | | | |

---

## E — Observability Evidence

These items confirm that the platform is observable at the level required to detect and respond to any post-launch anomaly.

| # | Item | Evidence Required | Status | Evidence Ref | Verified By | Date |
|---|---|---|---|---|---|---|
| E-1 | Structured log completeness verified | All 21 required fields present in 100% of log records | `[ ]` | | | |
| E-2 | PII exclusion verified | Zero PII field names in log output for 1000-record bulk check | `[ ]` | | | |
| E-3 | Scope visible in all log records | `governance_scope` field present in all log records | `[ ]` | | | |
| E-4 | Suppression visible in all suppressed records | `outbound_suppressed` field present and correct | `[ ]` | | | |
| E-5 | Degradation not silent | Degradation records surface `degradation_cause`, `degradation_class`, `degradation_severity` and emit `level=WARN` | `[ ]` | | | |
| E-6 | Metrics emitting at required cadence | `success_rate`, `failure_rate`, `latency_p50/p95/p99` visible for all long-running operations | `[ ]` | | | |
| E-7 | Invariant violation alerting wired | INV-3 or INV-4 violation in test environment triggers observable alert | `[ ]` | | | |

---

## F — Governance Evidence

These items confirm that the governance framework is sound and no defects are open.

| # | Item | Evidence Required | Status | Evidence Ref | Verified By | Date |
|---|---|---|---|---|---|---|
| F-1 | Zero open HIGH-severity governance defects | Defect register with empty HIGH and CRITICAL sections | `[ ]` | | | |
| F-2 | AUTHORIZED scope never produced in any campaign | `authorized_scope_count == 0` across all campaign audit results | `[ ]` | | | |
| F-3 | Zero live effects produced in any campaign | `live_effects_produced == 0` across all campaign audit results | `[ ]` | | | |
| F-4 | Zero provider dispatches produced in any campaign | `provider_dispatch_count == 0` across all campaign audit results | `[ ]` | | | |
| F-5 | INV-1 through INV-7 zero violations in production shadow | 1000-record governance certification run in PRODUCTION-SHADOW | `[ ]` | | | |
| F-6 | FAD-1 through FAD-6 zero violations in production shadow | 1000-record governance certification run in PRODUCTION-SHADOW | `[ ]` | | | |
| F-7 | Rollback governance understood | Platform Owner written acknowledgment of forward-only rollback requirement | `[ ]` | | | |
| F-8 | Emergency disable authority established | Documented who holds emergency disable authority (LIVE-DIS-001 Section 2.1) | `[ ]` | | | |

---

## G — Approval Evidence

These items confirm that the approval chain (LIVE-GOV-001 Section 2) is complete.

| # | Item | Evidence Required | Status | Evidence Ref | Verified By | Date |
|---|---|---|---|---|---|---|
| G-1 | Step 1 approval (Technical Lead) obtained | Signed approval record with evidence artifacts | `[ ]` | | | |
| G-2 | Step 2 approval (Governance Certifier) obtained | Signed approval record with certification artifacts | `[ ]` | | | |
| G-3 | Step 3 approval (Operations Lead) obtained | Signed approval record (this checklist being the primary artifact) | `[ ]` | | | |
| G-4 | Step 4 authorization (Platform Owner) obtained | Signed authorization record | `[ ]` | | | |
| G-5 | Activation record pre-written | `activation_record_id` written before Step 7 of activation process | `[ ]` | | | |

---

## H — Pre-Activation Final Verification

These items are verified immediately before the runtime configuration change that makes AUTHORIZED scope reachable. They must all be true at the moment of activation.

| # | Item | Evidence Required | Status | Evidence Ref | Verified By | Date |
|---|---|---|---|---|---|---|
| H-1 | All A–G items checked | This checklist 100% complete | `[ ]` | | | |
| H-2 | No new HIGH-severity defects since last certification | Defect register reviewed within last 24 hours | `[ ]` | | | |
| H-3 | Monitoring confirmed live within last 1 hour | Metrics visible in real time | `[ ]` | | | |
| H-4 | Emergency disable confirmed operational within last 1 hour | Dry-run successful | `[ ]` | | | |
| H-5 | On-call team notified of activation window | Notification record or message log | `[ ]` | | | |
| H-6 | Rollback plan (Section 8 of LIVE-GOV-001) confirmed understood | Verbal or written confirmation from Operations Lead | `[ ]` | | | |
| H-7 | First-hour monitoring team in place | Team assigned and available for 1 hour post-activation | `[ ]` | | | |

---

## Checklist Completion Record

```
Checklist completed by: ________________________________
Role: ________________________________
Date: YYYY-MM-DD
Time: HH:MM UTC

Sections complete:
  A (Certification):    [ ] ALL CHECKED
  B (Operational):      [ ] ALL CHECKED
  C (Attribution):      [ ] ALL CHECKED
  D (Replay):           [ ] ALL CHECKED
  E (Observability):    [ ] ALL CHECKED
  F (Governance):       [ ] ALL CHECKED
  G (Approval):         [ ] ALL CHECKED
  H (Pre-Activation):   [ ] ALL CHECKED

Total items: 55
Items checked: ___
Items with waivers: ___ (waivers must be attached as separate document with Platform Owner authorization)
Items blocked: ___ (if any blocked, activation must not proceed)

Declaration:
I certify that all items above have been verified with concrete artifacts, and that this checklist
represents an accurate picture of production readiness as of the date and time above.

Signature: ________________________________
```

---

*This checklist is a governance artifact. Once signed, it is immutable. Any subsequent changes require a new checklist instance (append-only). The signed checklist is retained as part of the activation record.*
