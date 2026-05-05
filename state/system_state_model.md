# state/system_state_model.md

---

## LAYER 5 — STATE MODEL

---

## 1. PURPOSE

This file defines the **complete system state model**, including:

* All valid states
* State transitions
* Invalid transitions
* Invariants
* State-based constraints

The state model ensures:

* Deterministic behavior
* No conflicting actions
* Clear lifecycle tracking for each student

---

## 2. CORE ENTITY

The state model applies to:

> **Student Outreach Lifecycle**

Each student exists in exactly **one primary state per checkpoint** at any time.

---

## 3. STATE DEFINITIONS

---

### 3.1 Primary States

| State                 | Description                                         |
| --------------------- | --------------------------------------------------- |
| ELIGIBLE              | Student meets criteria for outreach                 |
| QUEUED                | Student selected for outreach but not yet triggered |
| CONTACTED             | Outreach initiated (GHL triggered)                  |
| NO_RESPONSE           | Outreach attempt completed but no response          |
| RESPONDED             | Student engaged via call/SMS                        |
| ANALYZED              | LLM processing completed                            |
| INTERVENTION_REQUIRED | Action required (meeting, escalation, etc.)         |
| MEETING_SCHEDULED     | Meeting booked                                      |
| RESOLVED              | Case successfully handled                           |
| CLOSED                | No further action allowed                           |

---

## 4. STATE TRANSITIONS

---

### 4.1 Valid Transitions

```plaintext id="prkbb1"
ELIGIBLE → QUEUED  
QUEUED → CONTACTED  
CONTACTED → NO_RESPONSE  
CONTACTED → RESPONDED  
RESPONDED → ANALYZED  
ANALYZED → INTERVENTION_REQUIRED  
INTERVENTION_REQUIRED → MEETING_SCHEDULED  
INTERVENTION_REQUIRED → RESOLVED  
NO_RESPONSE → QUEUED (retry cycle)  
MEETING_SCHEDULED → RESOLVED  
RESOLVED → CLOSED  
```

---

### 4.2 Terminal States

```plaintext id="6g1rzt"
CLOSED  
RESOLVED (transitions to CLOSED automatically)
```

No transitions allowed after CLOSED.

---

## 5. INVALID TRANSITIONS (STRICTLY FORBIDDEN)

---

```plaintext id="ub9evu"
CLOSED → ANY_STATE  
MEETING_SCHEDULED → CONTACTED  
RESPONDED → QUEUED  
ANALYZED → CONTACTED  
NO_RESPONSE → ANALYZED (no transcript available)  
```

---

### Enforcement Rule

Any invalid transition MUST:

* Be blocked
* Be logged
* Trigger a warning

---

## 6. STATE INVARIANTS

---

### 6.1 Global Invariants

* A student cannot exist in multiple primary states simultaneously
* A student cannot re-enter CONTACTED without passing through QUEUED
* CLOSED state is irreversible

---

### 6.2 Outreach Invariants

* No outreach after CLOSED
* No retry after MAX_ATTEMPTS reached
* No meeting booking if already scheduled

---

### 6.3 Data Invariants

* Each state transition must be recorded
* Transitions must be timestamped
* State must always be derivable from data

---

## 7. STATE ATTRIBUTES

---

Each state MUST track:

| Field                | Description                    |
| -------------------- | ------------------------------ |
| state                | Current state                  |
| last_transition_time | Timestamp of last state change |
| attempt_count        | Number of outreach attempts    |
| checkpoint_type      | Context of outreach            |
| reason_codes         | Why state was entered          |

---

## 8. RETRY STATE LOGIC

---

### Rule

```plaintext id="ljcgir"
IF state = NO_RESPONSE  
AND attempt_count < MAX_ATTEMPTS  
THEN transition → QUEUED  
```

---

### Scope Behavior

---

#### MVP

* No retry transitions
* NO_RESPONSE → CLOSED

---

#### STANDARD

* Max 2 attempts
* Limited retry cycle

---

#### PRODUCTION

* Max 3 attempts
* Multi-day retry cycle
* Retry transitions strictly enforced

---

## 9. LLM-DEPENDENT STATES

---

### ANALYZED State

Requirements:

* Transcript must exist
* LLM output must be valid

---

### Transition Rule

```plaintext id="4oh2lq"
RESPONDED → ANALYZED  
```

---

### Failure Case

If LLM fails:

```plaintext id="kc7d82"
RESPONDED → INTERVENTION_REQUIRED  
(reason: LLM_FAILED)
```

---

## 10. ESCALATION STATES

---

### INTERVENTION_REQUIRED

Triggered when:

* High-risk student detected
* LLM recommends meeting
* Academic thresholds exceeded

---

### Possible Transitions

```plaintext id="37qggb"
INTERVENTION_REQUIRED → MEETING_SCHEDULED  
INTERVENTION_REQUIRED → RESOLVED  
```

---

## 11. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Limited states used:

```plaintext id="7oj2dp"
ELIGIBLE → CONTACTED → NO_RESPONSE → CLOSED
```

* No ANALYZED or INTERVENTION_REQUIRED states

---

### STANDARD

* Adds:

```plaintext id="4exal4"
RESPONDED → ANALYZED → INTERVENTION_REQUIRED
```

* Limited retry

---

### PRODUCTION

* Full state model
* Full retry cycles
* Full escalation paths
* Strict enforcement of invariants

---

## 12. STATE TRANSITION VALIDATION

---

Every transition MUST:

1. Be valid according to defined transitions
2. Respect invariants
3. Be logged
4. Include reason_codes

---

## 13. ACCEPTANCE CRITERIA

---

### Case 1 — Valid Transition

**Given** state = ELIGIBLE
**When** queued for outreach
**Then** state = QUEUED

---

### Case 2 — Retry Flow

**Given** state = NO_RESPONSE
**And** attempts < MAX_ATTEMPTS
**When** retry triggered
**Then** state = QUEUED

---

### Case 3 — Invalid Transition

**Given** state = CLOSED
**When** transition attempted
**Then** transition is blocked

---

### Case 4 — LLM Flow

**Given** student responded
**When** transcript processed
**Then** state = ANALYZED

---

## 14. REFERENCES

---

This file depends on:

* directives/core_decision_engine.md
* runtime/system_loop.md
* meta/project_classification.md

---

## END OF FILE
