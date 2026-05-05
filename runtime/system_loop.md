# runtime/system_loop.md

---

## LAYER 7 — SYSTEM LOOP (RUNTIME MODEL)

---

## 1. PURPOSE

The **System Loop** defines:

* When the system executes
* What processes run
* How decisions are triggered
* How retries and follow-ups are orchestrated

This is the **runtime backbone** of the system.

---

## 2. RUNTIME ARCHITECTURE

---

### 2.1 Execution Model

The system operates using a **hybrid model**:

* Scheduled batch processing (primary)
* Event-driven updates (secondary)

---

### 2.2 Core Loop Flow

```plaintext id="u3wh1g"
Scheduler Trigger
   ↓
Fetch Eligible Students
   ↓
Evaluate State
   ↓
Run Decision Engine
   ↓
Execute Action (GHL / Internal)
   ↓
Update State
   ↓
Log + Persist
```

---

## 3. PRIMARY TRIGGERS

---

### 3.1 Daily Scheduler (Main Trigger)

* Runs at: **6:00 PM CST daily**
* Responsible for:

  * Eligibility detection
  * Initial outreach
  * Retry evaluation

---

### 3.2 Retry Scheduler

* Runs daily
* Evaluates retry eligibility
* Re-queues students

---

### 3.3 Event-Based Trigger (Optional)

Triggered by:

* GHL webhook updates
* Transcript availability
* Meeting booking events

---

## 4. LOOP EXECUTION STEPS

---

### STEP 1 — LOAD CANDIDATES

Fetch students where:

* state = ELIGIBLE
  OR
* state = NO_RESPONSE (retry eligible)

---

### STEP 2 — VALIDATE STATE

For each student:

* Ensure valid state
* Skip CLOSED cases
* Enforce invariants

---

### STEP 3 — RUN DECISION ENGINE

Call:

```plaintext id="cqntpq"
core_decision_engine(student_context, outreach_state, llm_output)
```

---

### STEP 4 — EXECUTE ACTION

Based on decision output:

| Action           | Execution           |
| ---------------- | ------------------- |
| TRIGGER_OUTREACH | Send payload to GHL |
| RETRY_OUTREACH   | Send retry trigger  |
| SEND_SMS         | GHL SMS             |
| SEND_EMAIL       | GHL Email           |
| BOOK_MEETING     | Calendar API        |
| CLOSE_CASE       | Mark state          |

---

---

### STEP 5 — UPDATE STATE

* Transition state based on action
* Increment attempt count if applicable
* Record timestamps

---

### STEP 6 — LOG & STORE

Persist:

* Decision output
* State transition
* Reason codes
* Execution results

---

## 5. RETRY ORCHESTRATION

---

### Retry Logic Flow

```plaintext id="k34o0n"
NO_RESPONSE → Check attempt_count  
   ↓
IF attempt_count < MAX_ATTEMPTS  
   ↓
Wait retry window  
   ↓
Requeue → QUEUED  
   ↓
Trigger RETRY_OUTREACH  
```

---

### Scope Behavior

---

#### MVP

* No retry loop
* Single execution only

---

#### STANDARD

* Limited retries (1–2)
* Simple next-day retry

---

#### PRODUCTION

* Multi-day retry cycle (up to 3 attempts)
* Strict timing windows
* Channel fallback after final attempt

---

## 6. CONCURRENCY CONTROL

---

### Rules

* Max 50 concurrent outreach triggers
* Batch size must be controlled
* No duplicate execution per student

---

### Enforcement

* Lock per (user_id, checkpoint_type)
* Skip already processed entries

---

## 7. IDEMPOTENCY GUARANTEES

---

### Requirements

Each loop execution MUST:

* Produce same result for same inputs
* Avoid duplicate outreach
* Prevent double state transitions

---

### Mechanisms

* Unique outreach keys
* State validation before execution
* Transactional updates

---

## 8. FAILURE HANDLING (RUNTIME LEVEL)

---

### GHL Trigger Failure

* Log failure
* Retry within same loop (if safe)
* Mark for retry next cycle

---

### LLM Processing Delay

* Skip ANALYZED step
* Retry later via event trigger

---

### Scheduler Failure

* Detect missed run
* Trigger recovery execution

---

## 9. EVENT-DRIVEN EXTENSIONS

---

### Transcript Received

```plaintext id="48ytfa"
RESPONDED → ANALYZED → Decision Engine → Update State
```

---

### Meeting Booked

```plaintext id="6hf82q"
INTERVENTION_REQUIRED → MEETING_SCHEDULED → RESOLVED
```

---

## 10. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Single daily loop
* No retry orchestration
* Minimal state transitions

---

### STANDARD

* Daily loop + retry loop
* Basic event triggers

---

### PRODUCTION

* Full orchestration
* Multi-trigger system
* Retry + fallback + event sync
* Full state enforcement

---

## 11. LOOP INVARIANTS

---

* No execution on CLOSED state
* No duplicate outreach
* State must always be valid
* All actions must be logged

---

## 12. ACCEPTANCE CRITERIA

---

### Case 1 — Daily Execution

**Given** scheduler runs
**When** eligible students exist
**Then** outreach is triggered

---

### Case 2 — Retry Execution

**Given** NO_RESPONSE state
**When** retry window passed
**Then** retry occurs

---

### Case 3 — Concurrency Control

**Given** multiple students
**When** processed
**Then** no more than 50 concurrent triggers

---

### Case 4 — Idempotency

**Given** duplicate execution
**When** loop runs again
**Then** no duplicate outreach occurs

---

## 13. REFERENCES

---

Depends on:

* directives/core_decision_engine.md
* state/system_state_model.md
* meta/project_classification.md

---

## END OF FILE
