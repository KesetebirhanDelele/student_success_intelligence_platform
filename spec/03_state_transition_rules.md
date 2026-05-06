# spec/03_state_transition_rules.md

---

## LAYER 2 — SPECIFICATIONS (STATE TRANSITION RULES)

---

## 1. PURPOSE

This file defines:

* All **valid and invalid state transitions**
* Enforcement rules at system and database level
* Guardrails to prevent state corruption

The goal is to ensure:

* Deterministic lifecycle progression
* No invalid or out-of-order transitions
* System integrity across retries, failures, and manual actions

---

## 2. SOURCE OF TRUTH

---

This file is the **authoritative source** for:

> What state transitions are allowed

---

### Relationship to Other Files

| File                        | Role                 |
| --------------------------- | -------------------- |
| state/system_state_model.md | Defines states       |
| state/outreach_lifecycle.md | Explains lifecycle   |
| ✅ THIS FILE                 | Enforces transitions |

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

## END OF FILE
