# runtime/daily_outreach_flow.md

---

## LAYER 7 — RUNTIME (DAILY OUTREACH FLOW)

---

## 1. PURPOSE

This file defines:

* The exact daily execution sequence
* How students move through the system during a run
* Ordering of operations within the system loop

The goal is to ensure:

* Consistent daily behavior
* Predictable outreach execution
* No ambiguity in runtime flow

---

## 2. DAILY FLOW OVERVIEW

---

```plaintext
Scheduler Trigger (6 PM CST)
   ↓
Load Eligible Students
   ↓
Filter + Validate
   ↓
Evaluate Eligibility Rules
   ↓
Queue Students
   ↓
Run Decision Engine
   ↓
Select Channel
   ↓
Trigger Outreach (GHL)
   ↓
Update State
   ↓
Log + Persist
```

---

## 3. STEP-BY-STEP FLOW

---

### STEP 1 — SCHEDULER TRIGGER

---

**Trigger:**

* Daily at 6 PM CST

---

**Action:**

* Start system loop

---

---

### STEP 2 — LOAD STUDENTS

---

**Source:**

* AI_ChatBot_TriggerData

---

**Filter:**

* Relevant checkpoint types
* Active students only

---

---

### STEP 3 — VALIDATE DATA

---

For each student:

* Ensure required fields exist
* Validate contact info
* Skip invalid records

---

---

### STEP 4 — ELIGIBILITY EVALUATION

---

Call:

```plaintext
outreach_eligibility_rules(student_data, outreach_history)
```

---

**Output:**

* eligible = true/false
* priority level

---

---

### STEP 5 — QUEUE ELIGIBLE STUDENTS

---

IF:

* eligible = true

THEN:

* Add to processing queue
* Assign priority

---

---

### STEP 6 — DECISION ENGINE

---

Call:

```plaintext
core_decision_engine(context)
```

---

**Output:**

* action_type
* retry_allowed
* escalation_required

---

---

### STEP 7 — CHANNEL SELECTION

---

Call:

```plaintext
channel_selection_rules(context)
```

---

**Output:**

* selected_channel

---

---

### STEP 8 — OUTREACH EXECUTION

---

IF:

* action_type = TRIGGER_OUTREACH OR RETRY_OUTREACH

THEN:

* Send payload to GHL

---

---

### STEP 9 — STATE UPDATE

---

Based on outcome:

| Action             | State Transition        |
| ------------------ | ----------------------- |
| Outreach triggered | QUEUED → CONTACTED      |
| No response        | CONTACTED → NO_RESPONSE |
| Response received  | CONTACTED → RESPONDED   |

---

---

### STEP 10 — LOGGING

---

Log:

* Decision output
* Channel used
* State transition
* Reason codes

---

---

## 4. PRIORITY PROCESSING

---

### Rule

* HIGH priority students processed first
* MEDIUM next
* LOW last

---

---

## 5. BATCH PROCESSING

---

### Rules

* Process in batches (size configurable)
* Max 50 concurrent executions

---

---

## 6. FAILURE CHECKPOINTS

---

At each step:

| Step         | Failure Action          |
| ------------ | ----------------------- |
| Load         | Skip invalid records    |
| Eligibility  | Default to not eligible |
| Decision     | Fallback logic          |
| Outreach     | Retry or defer          |
| State Update | Rollback                |

---

---

## 7. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Simplified flow
* No retry
* No channel fallback
* Minimal validation

---

---

### STANDARD

* Full flow
* Basic retry
* Limited fallback

---

---

### PRODUCTION

* Full orchestration
* Retry + fallback
* Priority processing
* Failure handling at each step

---

---

## 8. INVARIANTS

---

* No duplicate outreach per run
* No processing of CLOSED cases
* All actions must be logged
* State must always be valid

---

---

## 9. ACCEPTANCE CRITERIA

---

### Case 1 — Daily Execution

**Given** scheduler runs
**When** flow executes
**Then** eligible students are processed

---

---

### Case 2 — Eligibility Filtering

**Given** invalid student
**When** evaluated
**Then** skipped

---

---

### Case 3 — Outreach Execution

**Given** eligible + valid decision
**When** executed
**Then** outreach triggered

---

---

### Case 4 — State Update

**Given** outreach executed
**When** completed
**Then** state updated correctly

---

---

## 10. REFERENCES

---

Depends on:

* runtime/system_loop.md
* runtime/scheduler_design.md
* directives/core_decision_engine.md
* directives/outreach_eligibility_rules.md
* directives/channel_selection_rules.md
* state/system_state_model.md
* meta/project_classification.md

---

## END OF FILE
