# state/outreach_lifecycle.md

---

## LAYER 5 — STATE MODEL (OUTREACH LIFECYCLE)

---

## 1. PURPOSE

This file defines:

* The **end-to-end lifecycle** of a student outreach case
* How a student progresses through the system over time
* How state, retry, decision, and escalation interact

The goal is to provide:

* A **human-readable lifecycle view** (vs system_state_model = strict rules)
* Clear understanding of system behavior across days
* Alignment between runtime, directives, and state

---

## 2. LIFECYCLE OVERVIEW

---

```plaintext
ELIGIBLE  
   ↓
QUEUED  
   ↓
CONTACTED  
   ↓
(NO RESPONSE) → RETRY CYCLE → CONTACTED  
   ↓
(RESPONDED)  
   ↓
ANALYZED  
   ↓
INTERVENTION_REQUIRED  
   ↓
MEETING_SCHEDULED  
   ↓
RESOLVED  
   ↓
CLOSED
```

---

## 3. PHASE BREAKDOWN

---

## PHASE 1 — ELIGIBILITY

---

### Entry Condition

* Student meets eligibility criteria
* Not recently contacted
* Has valid contact information

---

### Output

```plaintext
State → ELIGIBLE
```

---

---

## PHASE 2 — QUEUEING

---

### Purpose

* Prepare student for outreach execution

---

### Entry Condition

* eligible = TRUE

---

### Output

```plaintext
ELIGIBLE → QUEUED
```

---

---

## PHASE 3 — OUTREACH EXECUTION

---

### Action

* System triggers outreach via GHL

---

### Output

```plaintext
QUEUED → CONTACTED
```

---

---

## PHASE 4 — RESPONSE HANDLING

---

### Path A — No Response

---

```plaintext
CONTACTED → NO_RESPONSE
```

---

Triggers:

* Call not connected
* No reply via SMS/Email

---

---

### Path B — Response Received

---

```plaintext
CONTACTED → RESPONDED
```

---

Triggers:

* Call connected
* Student engagement

---

---

## PHASE 5 — RETRY CYCLE (IF NO RESPONSE)

---

### Condition

* state = NO_RESPONSE
* attempts < MAX_ATTEMPTS

---

### Flow

```plaintext
NO_RESPONSE  
   ↓
WAIT (Retry Window)  
   ↓
QUEUED  
   ↓
CONTACTED  
```

---

### Channel Progression

```plaintext
CALL → SMS → EMAIL
```

---

### Exit Conditions

* Response received
* Max attempts reached

---

---

## PHASE 6 — ANALYSIS

---

### Entry Condition

* state = RESPONDED
* Transcript available

---

### Action

* LLM processes transcript

---

### Output

```plaintext
RESPONDED → ANALYZED
```

---

---

## PHASE 7 — INTERVENTION

---

### Trigger Conditions

* High-risk metrics
* LLM recommends meeting
* Negative sentiment

---

### Output

```plaintext
ANALYZED → INTERVENTION_REQUIRED
```

---

---

## PHASE 8 — MEETING

---

### Action

* Meeting scheduled

---

### Output

```plaintext
INTERVENTION_REQUIRED → MEETING_SCHEDULED
```

---

---

## PHASE 9 — RESOLUTION

---

### Conditions

* Meeting completed
  OR
* Issue resolved without meeting

---

### Output

```plaintext
MEETING_SCHEDULED → RESOLVED
```

---

---

## PHASE 10 — CLOSURE

---

### Final State

```plaintext
RESOLVED → CLOSED
```

---

### Rules

* No further actions allowed
* Lifecycle ends

---

---

## 4. LIFECYCLE VARIANTS BY SCOPE

---

### MVP

```plaintext
ELIGIBLE → CONTACTED → NO_RESPONSE → CLOSED
```

* No retry
* No LLM
* No intervention

---

---

### STANDARD

```plaintext
ELIGIBLE → CONTACTED → NO_RESPONSE → RETRY → CONTACTED  
                       ↓  
                  RESPONDED → ANALYZED → INTERVENTION
```

* Limited retry
* Basic LLM usage

---

---

### PRODUCTION

Full lifecycle:

```plaintext
ELIGIBLE → QUEUED → CONTACTED → NO_RESPONSE → RETRY LOOP  
                              ↓  
                         RESPONDED → ANALYZED → INTERVENTION  
                                              ↓  
                                      MEETING → RESOLVED → CLOSED
```

---

---

## 5. CROSS-SYSTEM INTERACTIONS

---

### With Decision Engine

* Determines next step in lifecycle

---

---

### With Retry Policy

* Controls re-entry into QUEUED

---

---

### With Channel Selection

* Determines outreach method

---

---

### With GHL

* Executes CONTACTED phase

---

---

### With LLM

* Enables ANALYZED phase

---

---

## 6. FAILURE PATHS

---

### GHL Failure

```plaintext
QUEUED → (FAIL) → RETRY / DEFER
```

---

---

### LLM Failure

```plaintext
RESPONDED → INTERVENTION_REQUIRED (fallback)
```

---

---

### Missing Data

```plaintext
ELIGIBLE → SKIPPED
```

---

---

## 7. INVARIANTS

---

* A student must follow valid lifecycle order
* No skipping critical states (except defined fallback paths)
* CLOSED is final
* Retry only occurs from NO_RESPONSE

---

---

## 8. ACCEPTANCE CRITERIA

---

### Case 1 — Full Lifecycle

**Given** eligible student
**When** system runs across days
**Then** student progresses through lifecycle correctly

---

---

### Case 2 — Retry Lifecycle

**Given** no response
**When** retry conditions met
**Then** student re-enters queue

---

---

### Case 3 — Closure

**Given** resolved case
**When** lifecycle completes
**Then** state = CLOSED

---

---

## 9. REFERENCES

---

Depends on:

* state/system_state_model.md
* runtime/daily_outreach_flow.md
* runtime/retry_cycle_flow.md
* directives/core_decision_engine.md
* meta/project_classification.md

---

## END OF FILE
