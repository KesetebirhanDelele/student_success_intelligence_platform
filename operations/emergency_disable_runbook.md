# Emergency Disable Runbook

**Document ID:** LIVE-DIS-001  
**Status:** ACTIVE  
**Classification:** Operational Runbook — Emergency Procedure  
**Governs:** Emergency disable of LIVE execution and AUTHORIZED scope  
**Reference:** LIVE-GOV-001 Section 4  
**Last Updated:** 2026-05-29

---

> **This runbook must be executable within 2 minutes of a disable decision.**  
> It must be reviewed and dry-run before LIVE is enabled (see production readiness checklist item B-6).  
> When in doubt, disable first. Investigate after.

---

## Section 1 — Emergency Disable Conditions

Any of the following conditions requires immediate execution of this runbook. No approval is required to disable. Disabling is always safer than waiting.

---

### 1.1 Automatic Disable Conditions

Disable immediately, without waiting for approval, if ANY of the following is observed:

| Condition | Observable Signal | Severity |
|---|---|---|
| INV-3 violated: replay record produced `live_effects_produced > 0` | Structured log: `event=invariant_violation`, `invariant_id=INV-3` | CRITICAL |
| INV-4 violated: SHADOW_ONLY record produced `provider_dispatch_count > 0` | Structured log: `event=invariant_violation`, `invariant_id=INV-4` | CRITICAL |
| FAD-1 violated: FINALIZED record mutated | Structured log: `event=invariant_violation`, `invariant_id=FAD-1` | CRITICAL |
| FAD-4 violated: lineage record deleted or modified | Structured log: `event=invariant_violation`, `invariant_id=FAD-4` | CRITICAL |
| Attribution gap count non-zero in production | `attribution_gap_count > 0` in operator report | CRITICAL |
| AUTHORIZED scope produced for unexpected population | `authorized_scope_count` exceeds expected count in any 1-minute window | CRITICAL |
| Live effects observed for replay records | `live_effects_total > 0` in any replay campaign run | CRITICAL |
| Structured logs stopped emitting | No log events for > 5 minutes during active execution | HIGH |
| Governance invariant violation count rising | `inv_violation_count > 0` in any governance certification run | HIGH |
| Operator report `certification_outcome == CERTIFICATION_FAILED` | `OperatorReport.certification_outcome == CERTIFICATION_FAILED` | HIGH |

---

### 1.2 Investigation-Triggered Disable Conditions

Disable within 15 minutes of confirming any of the following:

| Condition | Observable Signal |
|---|---|
| Unexpected external communications sent to recipients | External complaint, delivery notification, or monitoring alert |
| Config V2 active version count > 1 | Config resolution log shows multiple ACTIVE versions |
| Attribution fields corrupted or missing at scale | > 1% of records missing attribution fields in any 10-minute window |
| Scope derivation producing unexpected results | Governance scope in log records does not match expected scope for given inputs |
| Emergency by operator judgment | Operator believes something is wrong even if specific condition not listed above |

---

### 1.3 Conditions That Do NOT Require Disable

The following conditions should be investigated but do not require immediate disable:

- Individual degradation events (missing config, provider unavailable, scheduler unavailable) with deterministic classification and `attribution_preserved == True`
- Operator report `certification_outcome == CERTIFICATION_DEGRADED` (investigate, monitor, do not disable unless worsening)
- Single INV-5 through INV-7 violation in an isolated record (investigate immediately, disable if pattern)

---

## Section 2 — Disable Authority

---

### 2.1 Who May Execute a Disable

Emergency disable may be executed by any of the following, without requiring prior approval:

1. **On-call operator** — any person currently on the on-call rotation
2. **Platform owner** (Ali Muwwakkil)
3. **Operations Lead**
4. **Technical Lead**
5. **Any engineer who has been briefed on this runbook** — if a higher-authority person cannot be reached within 2 minutes

The rule: if you observe an automatic disable condition (Section 1.1) and cannot reach a higher-authority person within 2 minutes, **execute the disable yourself**. Do not wait. You will not be penalized for a disable that turns out to have been unnecessary. You will be accountable for a delay that allowed production impact to continue.

---

### 2.2 Who Must Be Notified After a Disable

Within 5 minutes of executing the disable, notify:

1. Platform Owner (Ali Muwwakkil) — immediately
2. Operations Lead — immediately
3. Technical Lead — within 5 minutes
4. On-call team — immediately

Notification must include: what was observed, when it was observed, what action was taken, and the correlation_id or record_id of the triggering event.

---

## Section 3 — Disable Process

Execute these steps in order. Do not skip steps. Document each step as you execute it.

---

### Step 1 — Identify and Record the Triggering Condition (< 30 seconds)

Before disabling, capture:

```
DISABLE EVENT RECORD
--------------------
Operator: <name>
Timestamp: ISO-8601
Correlation ID (if available): <uuid>
Triggering condition: <condition from Section 1.1 or 1.2>
Observable signal: <log excerpt, metric value, or observation>
Severity: CRITICAL | HIGH
```

Write this to `/tmp/emergency_disable_event_TIMESTAMP.json` immediately. This is the audit trail.

---

### Step 2 — Execute the Runtime Disable (< 1 minute)

The disable mechanism depends on how LIVE was enabled. The mechanism must be documented at activation time (LIVE-GOV-001 Section 3.3, `activation_config_version_id`). In all cases, the disable must:

1. Make AUTHORIZED scope unreachable by reverting the runtime configuration that enabled it
2. Confirm the Phase-12 certification gate is re-active (LIVE execution mode → SHADOW_ONLY scope)
3. Stop any in-flight AUTHORIZED-scope operations if the platform supports graceful stop

**The runtime disable is NOT:**
- Deleting the activation record (append-only, must not be deleted)
- Deleting any lineage or audit records (FAD-4: append-only)
- Reverting code commits
- Dropping database tables

**The runtime disable IS:**
- A configuration change that makes AUTHORIZED scope unreachable
- A new Config V2 version that blocks AUTHORIZED scope derivation
- A feature flag toggle that re-activates the Phase-12 certification gate

---

### Step 3 — Verify the Disable (< 2 minutes from Step 2)

Verify that the disable took effect:

| Verification | Required Result |
|---|---|
| Execute a governance scope check for a previously-AUTHORIZED record | Record now produces `SHADOW_ONLY` scope, not `AUTHORIZED` |
| Check operator report | `certification_outcome` should be CERTIFICATION_PASSED or CERTIFICATION_DEGRADED (not FAILED with live effects) |
| Check structured logs | `event=live_activation_disabled` or equivalent observable event in logs |
| Check `authorized_scope_count` | Should be 0 for newly-processed records |
| Check `live_effects_produced` | Should be 0 for all records processed after the disable |

If any verification check fails: escalate immediately. The disable may not have taken effect.

---

### Step 4 — Write the Disable Record (< 1 minute from Step 3)

```json
{
  "disable_record_id": "<uuid>",
  "disable_timestamp": "ISO-8601",
  "correlation_id": "<uuid>",
  "disabled_by": "<operator name>",
  "triggering_condition": "<condition text>",
  "triggering_signal": "<log excerpt or metric>",
  "activation_record_id": "<id from activation record>",
  "disable_mechanism": "<description of what was changed>",
  "verification_passed": true,
  "authorized_scope_count_after": 0,
  "live_effects_after": 0,
  "is_mutable": false,
  "is_append_only": true
}
```

This record is immutable and append-only. It must be retained alongside the activation record.

---

### Step 5 — Notify (< 5 minutes from Step 1)

Notify all parties listed in Section 2.2. Include the disable record ID and a brief description of the triggering condition.

---

## Section 4 — Disable Verification

After the disable is confirmed, the following verification steps must be completed before any investigation begins.

---

### 4.1 Immediate Verification (within 5 minutes of disable)

- [ ] Structured logs confirm AUTHORIZED scope is no longer being produced
- [ ] Operator report shows `authorized_scope_count == 0` for records processed after disable
- [ ] `live_effects_produced == 0` for all records processed after disable
- [ ] Phase-12 certification gate confirmed re-active (LIVE mode → SHADOW_ONLY scope)
- [ ] Disable record written and retained

---

### 4.2 Extended Verification (within 30 minutes of disable)

- [ ] All in-flight requests from the LIVE window have completed or been safely terminated
- [ ] No delayed effects (queued emails, queued API calls) are still executing
- [ ] Full governance certification run (`run_governance_certification`) passes with 0 violations for records processed after disable
- [ ] Attribution continuity verified for records processed after disable
- [ ] Operator report generated post-disable and shows `certification_outcome ∈ {CERTIFICATION_PASSED, CERTIFICATION_DEGRADED}`

---

## Section 5 — Post-Disable Audit Requirements

A post-disable audit must be completed before LIVE can be re-enabled. The audit is not optional.

---

### 5.1 Required Audit Artifacts

| Artifact | Content | Required By |
|---|---|---|
| Triggering event log | The log entry or metric that triggered the disable | 1 hour post-disable |
| Impact assessment | How many records were processed in AUTHORIZED scope before the disable | 4 hours post-disable |
| Root cause analysis | The specific code path, configuration change, or data condition that caused the triggering event | 24 hours post-disable |
| Forward-only remediation plan | What changes will be made to prevent recurrence — expressed as new Config V2 versions or code changes, not record restoration | 24 hours post-disable |
| Invariant violation report | If any INV or FAD was violated: which ones, how many records, what the violation means in terms of actual or potential production impact | 24 hours post-disable |

---

### 5.2 Re-enablement Gate

LIVE may NOT be re-enabled until:

1. Post-disable audit is complete (all 5 artifacts in Section 5.1 are on file)
2. Root cause is identified and a fix is deployed
3. The fix is verified to not introduce any new governance defects
4. All governance certification tests pass against the fix
5. The full approval chain (LIVE-GOV-001 Section 2) is completed again from Step 1
6. A new activation record is written (the original activation record is not modified or reused)

The only valid re-enablement path is to treat it as a first-time enablement: complete the full prerequisites, approval chain, and activation process from the beginning. There is no "fast path" re-enablement after an emergency disable.

---

## Section 6 — Expected Recovery Path

The expected post-disable state is a fully governed SHADOW execution, identical to the pre-LIVE state. This is not a degraded state — it is the intended safe state.

| System State | Expected Value Post-Disable |
|---|---|
| `governance_scope` for standard records | `SHADOW_ONLY` |
| `governance_scope` for replay records | `REPLAY_ONLY` |
| `live_effects_produced` | `0` |
| `provider_dispatch_count` | `0` |
| `outbound_suppressed` | `True` |
| Campaign `certification_outcome` | `CERTIFICATION_PASSED` |
| INV violation count | `0` |
| FAD violation count | `0` |

When the system is in this state, it is operating normally under SHADOW governance. It can be used to investigate the root cause, verify fixes, and run the re-enablement process. It is not an emergency state. It is the baseline state.

---

## Dry-Run Checklist

This checklist must be completed before LIVE is enabled (item B-6 in production readiness checklist).

```
DRY-RUN RECORD
--------------
Operator: ________________________________
Date: YYYY-MM-DD
Time: HH:MM UTC

Steps executed:
  Step 1 (record triggering event):        [ ] Completed  Duration: ___s
  Step 2 (execute runtime disable):         [ ] Completed  Duration: ___s
  Step 3 (verify disable):                  [ ] Completed  Duration: ___s
  Step 4 (write disable record):            [ ] Completed  Duration: ___s
  Step 5 (notify):                          [ ] Simulated  Duration: ___s

Total time from Step 1 to Step 4 completion: ___s  (must be < 120 seconds)

Verification results:
  Authorized scope = 0 after disable:        [ ] Yes  [ ] No
  Live effects = 0 after disable:            [ ] Yes  [ ] No
  Disable record written:                    [ ] Yes  [ ] No

Runbook gaps identified: ________________________________
Actions taken to close gaps: ________________________________

Dry-run approved by: ________________________________
Date: YYYY-MM-DD
```

---

*This runbook is operational documentation. It must be reviewed and updated whenever the activation mechanism changes. Each update is a new version (append-only). Prior versions are retained.*
