# runtime/retry_cycle_flow.md

---

## LAYER 7 — RUNTIME (RETRY CYCLE FLOW)

---

## 1. PURPOSE

This file defines:

* How retry cycles are executed
* When retries occur
* How students re-enter the system loop
* Interaction with retry policy + channel fallback

The goal is to ensure:

* Controlled follow-up attempts
* No over-contacting
* Deterministic retry behavior across days

---

## 2. RETRY FLOW OVERVIEW

---

```plaintext id="0q7f6r"
Initial Outreach Attempt
   ↓
No Response Detected
   ↓
Evaluate Retry Policy
   ↓
Wait Retry Window
   ↓
Requeue Student
   ↓
Run Decision Engine
   ↓
Select Channel (Fallback if needed)
   ↓
Trigger Retry Outreach
   ↓
Update State
```

---

## 3. ENTRY CONDITIONS

---

A student enters retry flow IF:

* state = NO_RESPONSE
  AND
* contact_attempt < MAX_ATTEMPTS
  AND
* retry_allowed = TRUE

---

---

## 4. STEP-BY-STEP FLOW

---

### STEP 1 — DETECT NO RESPONSE

---

Triggered when:

* GHL webhook indicates no connection
  OR
* No response within defined timeout

---

### State Transition

```plaintext id="3hl1z6"
CONTACTED → NO_RESPONSE
```

---

---

### STEP 2 — EVALUATE RETRY POLICY

---

Call:

```plaintext id="4r8n1w"
outreach_retry_policy(context)
```

---

**Output:**

* retry_allowed
* next_action
* next_retry_time

---

---

### STEP 3 — WAIT RETRY WINDOW

---

Condition:

```plaintext id="r4l4ke"
current_time - last_contact_time ≥ RETRY_INTERVAL
```

---

### Behavior

* Do NOT requeue before window passes
* Enforced strictly

---

---

### STEP 4 — REQUEUE STUDENT

---

IF retry_allowed = TRUE:

```plaintext id="8l6yt3"
NO_RESPONSE → QUEUED
```

---

---

### STEP 5 — DECISION ENGINE

---

Call:

```plaintext id="m6i3xw"
core_decision_engine(context)
```

---

**Determines:**

* RETRY_OUTREACH
* Fallback channel
* Escalation

---

---

### STEP 6 — CHANNEL FALLBACK

---

Call:

```plaintext id="9p3y8b"
channel_selection_rules(context)
```

---

### Example Progression

```plaintext id="o9j2vt"
Attempt 1 → CALL  
Attempt 2 → SMS  
Attempt 3 → EMAIL  
```

---

---

### STEP 7 — EXECUTE RETRY

---

IF action_type = RETRY_OUTREACH:

* Trigger GHL with updated attempt count
* Include channel context

---

---

### STEP 8 — UPDATE STATE

---

```plaintext id="m0e8r2"
QUEUED → CONTACTED
```

---

Increment:

```plaintext id="l8h3pc"
contact_attempt += 1
```

---

---

## 5. TERMINATION CONDITIONS

---

Retry cycle stops when:

---

### CONDITION 1 — MAX ATTEMPTS

```plaintext id="h8mq7x"
contact_attempt ≥ MAX_ATTEMPTS
```

---

### CONDITION 2 — RESPONSE RECEIVED

```plaintext id="r8x2wn"
call_connected = TRUE
```

---

### CONDITION 3 — CASE CLOSED

```plaintext id="z1t6qj"
state = CLOSED
```

---

---

## 6. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* No retry cycle
* Flow ends after first attempt

---

---

### STANDARD

* One retry allowed
* Simple next-day retry
* Limited channel fallback

---

---

### PRODUCTION

* Multi-day retry cycle (up to 3 attempts)
* Strict timing enforcement
* Full channel fallback (CALL → SMS → EMAIL)
* Integrated escalation rules

---

---

## 7. RETRY TIMELINE (PRODUCTION)

---

Example:

```plaintext id="y3s7wz"
Day 1 (6 PM) → Attempt 1 (CALL)  
Day 2 (6 PM) → Attempt 2 (SMS)  
Day 3 (6 PM) → Attempt 3 (EMAIL)  
Day 4 → Stop / Escalate  
```

---

---

## 8. FAILURE HANDLING

---

### Retry Trigger Failure

* Retry immediately once
* If fails → defer to next cycle

---

---

### Missing Timestamp

* Do not retry
* Log error
* Add reason: "MISSING_TIMESTAMP"

---

---

### Duplicate Retry

* Detect via unique constraint
* Skip execution

---

---

## 9. INVARIANTS

---

* Retry must not exceed MAX_ATTEMPTS
* Retry must respect timing window
* Retry must increment attempt count
* No duplicate retry per attempt

---

---

## 10. ACCEPTANCE CRITERIA

---

### Case 1 — Retry Allowed

**Given** NO_RESPONSE
**And** retry window passed
**When** evaluated
**Then** retry executed

---

---

### Case 2 — Retry Blocked

**Given** retry window not passed
**When** evaluated
**Then** retry not executed

---

---

### Case 3 — Max Attempts

**Given** attempts = MAX_ATTEMPTS
**When** evaluated
**Then** retry stopped

---

---

### Case 4 — Response Received

**Given** call connected
**When** evaluated
**Then** retry stopped

---

---

## 11. REFERENCES

---

Depends on:

* runtime/system_loop.md
* directives/outreach_retry_policy.md
* directives/channel_selection_rules.md
* directives/core_decision_engine.md
* state/system_state_model.md
* meta/project_classification.md

---

## END OF FILE
