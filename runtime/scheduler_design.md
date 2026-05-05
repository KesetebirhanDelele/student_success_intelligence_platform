# runtime/scheduler_design.md

---

## LAYER 7 — RUNTIME (SCHEDULER DESIGN)

---

## 1. PURPOSE

This file defines:

* How scheduling works
* When system processes are triggered
* Scheduling guarantees and constraints
* Recovery mechanisms for missed runs

The goal is to ensure:

* Reliable execution timing
* No missed outreach cycles
* Deterministic system behavior

---

## 2. SCHEDULER ARCHITECTURE

---

### Model

The system uses a:

> **Time-based scheduler with recovery support**

---

### Components

```plaintext
Scheduler Service  
   ↓
Trigger Engine  
   ↓
System Loop Execution  
```

---

## 3. PRIMARY SCHEDULE

---

### Daily Outreach Scheduler

| Parameter      | Value                               |
| -------------- | ----------------------------------- |
| Execution Time | 6:00 PM CST                         |
| Frequency      | Daily                               |
| Purpose        | Trigger outreach + retry evaluation |

---

---

### Retry Evaluation Scheduler

| Parameter      | Value                      |
| -------------- | -------------------------- |
| Execution Time | Daily                      |
| Purpose        | Evaluate retry eligibility |

---

---

## 4. EXECUTION FLOW

---

```plaintext
Scheduler Trigger
   ↓
Validate Environment
   ↓
Check Previous Run
   ↓
Trigger System Loop
   ↓
Log Execution
```

---

---

## 5. SCHEDULER RULES

---

### RULE 1 — SINGLE EXECUTION PER WINDOW

* Scheduler must run only once per scheduled time
* Duplicate executions must be blocked

---

---

### RULE 2 — MISSED RUN DETECTION

IF:

* scheduled run not recorded

THEN:

* mark as missed
* trigger recovery run

---

---

### RULE 3 — TIMEZONE CONSISTENCY

* All scheduling must use **CST**
* Internal system should normalize timestamps

---

---

### RULE 4 — EXECUTION LOCK

* Prevent concurrent scheduler runs
* Use lock mechanism per execution window

---

---

## 6. RECOVERY MECHANISM

---

### Missed Run Recovery

---

#### Detection

* No log entry for scheduled run

---

#### Recovery Flow

```plaintext
Detect Missed Run  
   ↓
Trigger Immediate Execution  
   ↓
Process Pending Students  
   ↓
Log Recovery Execution  
```

---

---

### Constraints

* Recovery must not duplicate work
* Must respect idempotency

---

---

## 7. CONCURRENCY CONTROL

---

### Limits

* Max 50 concurrent outreach executions

---

### Enforcement

* Batch processing
* Queue-based execution

---

---

## 8. SCHEDULER FAILURE HANDLING

---

### Scenario 1 — Scheduler Crash

* Restart scheduler
* Detect missed run
* Trigger recovery

---

---

### Scenario 2 — Partial Execution

* Resume from last successful state
* Skip completed records

---

---

### Scenario 3 — Time Drift

* Sync system time
* Validate scheduler timing

---

---

## 9. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Single daily scheduler
* No recovery automation
* Manual monitoring

---

---

### STANDARD

* Daily scheduler + retry evaluation
* Basic missed-run detection

---

---

### PRODUCTION

* Full scheduler system
* Missed-run recovery
* Concurrency control
* Monitoring + alerting

---

---

## 10. INVARIANTS

---

* Scheduler must not execute twice in same window
* All executions must be logged
* Missed runs must be recoverable

---

---

## 11. ACCEPTANCE CRITERIA

---

### Case 1 — Scheduled Execution

**Given** 6 PM reached
**When** scheduler runs
**Then** system loop triggered

---

---

### Case 2 — Missed Run

**Given** scheduler missed execution
**When** detected
**Then** recovery run triggered

---

---

### Case 3 — Duplicate Prevention

**Given** scheduler already ran
**When** triggered again
**Then** execution blocked

---

---

## 12. REFERENCES

---

Depends on:

* runtime/system_loop.md
* failure/failure_playbook.md
* directives/core_decision_engine.md
* meta/project_classification.md

---

## END OF FILE
