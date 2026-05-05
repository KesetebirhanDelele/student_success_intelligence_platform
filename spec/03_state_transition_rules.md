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
RESPONDED  
ANALYZED  
INTERVENTION_REQUIRED  
MEETING_SCHEDULED  
RESOLVED  
CLOSED  
```

---

---

## 4. VALID TRANSITIONS

---

### Core Transition Map

```plaintext
ELIGIBLE → QUEUED  

QUEUED → CONTACTED  

CONTACTED → NO_RESPONSE  
CONTACTED → RESPONDED  

NO_RESPONSE → QUEUED  
NO_RESPONSE → CLOSED  

RESPONDED → ANALYZED  

ANALYZED → INTERVENTION_REQUIRED  
ANALYZED → RESOLVED  

INTERVENTION_REQUIRED → MEETING_SCHEDULED  
INTERVENTION_REQUIRED → RESOLVED  

MEETING_SCHEDULED → RESOLVED  

RESOLVED → CLOSED  
```

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
```

---

---

### 5.3 Skip-Level Transitions

```plaintext
ELIGIBLE → CONTACTED ❌  
QUEUED → RESPONDED ❌  
CONTACTED → ANALYZED ❌ (must pass RESPONDED)  
```

---

---

### 5.4 Retry Violations

```plaintext
RESPONDED → NO_RESPONSE ❌  
ANALYZED → NO_RESPONSE ❌  
```

---

---

## 6. CONDITIONAL TRANSITIONS

---

### 6.1 Retry Loop

---

Allowed ONLY IF:

* contact_attempt < MAX_ATTEMPTS
* retry_policy allows

```plaintext
NO_RESPONSE → QUEUED
```

---

---

### 6.2 Forced Closure

---

Allowed ONLY via manual action:

```plaintext
ANY_STATE → CLOSED
```

---

### Constraints

* Must include reason
* Must be logged

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

* CLOSED is terminal
* No backward transitions
* No skipped states (unless explicitly allowed)
* Retry only from NO_RESPONSE
* State must always be valid enum

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
