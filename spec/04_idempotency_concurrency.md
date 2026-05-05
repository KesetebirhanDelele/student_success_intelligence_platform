# spec/04_idempotency_concurrency.md

---

## LAYER 2 — SPECIFICATIONS (IDEMPOTENCY & CONCURRENCY)

---

## 1. PURPOSE

This file defines:

* Idempotency rules across the system
* Concurrency control mechanisms
* Duplicate prevention strategies
* Race condition handling

The goal is to ensure:

* No duplicate outreach
* Safe retries and reprocessing
* Consistent behavior under parallel execution

---

## 2. CORE PRINCIPLES

---

### 2.1 Idempotency First

* Repeated operations MUST NOT create duplicate effects
* Same request → same outcome

---

---

### 2.2 Concurrency Safety

* Parallel execution must not corrupt state
* Only one valid operation per entity per cycle

---

---

### 2.3 Deterministic Conflict Resolution

* When conflicts occur → system must resolve predictably

---

---

## 3. IDEMPOTENCY DEFINITIONS

---

### Idempotent Operation

An operation where:

```plaintext
Same input + same state → same result (no duplication)
```

---

---

## 4. IDEMPOTENCY KEYS

---

### 4.1 Key Structure

```plaintext id="e6lqkz"
idempotency_key = user_id + checkpoint_type + contact_attempt
```

---

---

### 4.2 Scope

Used for:

* Outreach trigger
* Retry execution
* Webhook processing

---

---

### 4.3 Storage Requirement

* Keys must be stored per execution
* Duplicate key = reject operation

---

---

## 5. DUPLICATE PREVENTION RULES

---

### RULE 1 — OUTREACH TRIGGER

```plaintext id="8u3m8m"
IF idempotency_key exists → BLOCK execution
```

---

---

### RULE 2 — RETRY EXECUTION

```plaintext id="mrk0e1"
Same (user_id, attempt) must not execute twice
```

---

---

### RULE 3 — WEBHOOK EVENTS

```plaintext id="3rfv2q"
Same event_id must be processed once
```

---

---

## 6. CONCURRENCY CONTROL

---

### 6.1 Concurrency Limit

```plaintext id="4m1g4k"
MAX_CONCURRENT_EXECUTIONS = 50 (Production)
```

---

---

### 6.2 Execution Model

* Batch-based processing
* Queue-controlled execution

---

---

### 6.3 Locking Strategy

---

#### Per-User Lock

```plaintext id="1z6nyk"
Lock on user_id during processing
```

---

#### Purpose

* Prevent duplicate processing of same student

---

---

### 6.4 Global Scheduler Lock

```plaintext id="7kn3hv"
One scheduler run per execution window
```

---

---

## 7. RACE CONDITION HANDLING

---

### Scenario 1 — Duplicate Processing

---

**Given:**

* Same student picked by multiple workers

---

**Resolution:**

```plaintext id="l0xsh1"
First execution wins  
Others skipped
```

---

---

### Scenario 2 — Concurrent Retry + New Trigger

---

**Given:**

* Retry cycle and daily run overlap

---

**Resolution:**

* State-based validation prevents duplicate
* Idempotency key blocks duplication

---

---

### Scenario 3 — Webhook + Scheduler Conflict

---

**Given:**

* Webhook updates state during processing

---

**Resolution:**

* State check before execution
* Abort if state already advanced

---

---

## 8. IDEMPOTENT API DESIGN

---

### Requirement

All critical endpoints MUST support idempotency:

---

#### Applies To:

* POST /outreach/trigger
* POST /actions/manual
* POST /webhook/ghl-update

---

---

### Mechanism

* Accept idempotency key (header or payload)
* Store and validate

---

---

## 9. DATABASE ENFORCEMENT

---

### Unique Constraint

```sql id="tx8gk0"
UNIQUE (user_id, checkpoint_type, contact_attempt)
```

---

---

### Optional Event Table

```plaintext id="dr4e6y"
ProcessedEvents
  - event_id
  - user_id
  - timestamp
```

---

---

## 10. FAILURE HANDLING

---

### Duplicate Detection

---

**Behavior:**

1. Reject duplicate
2. Log event
3. Do NOT retry

---

---

### Lock Timeout

---

**Behavior:**

* Release lock
* Retry safely

---

---

### Partial Execution

---

**Behavior:**

* Resume safely
* Skip completed operations

---

---

## 11. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Minimal idempotency
* No strict concurrency control

---

---

### STANDARD

* Basic idempotency keys
* Limited concurrency control

---

---

### PRODUCTION

* Full idempotency enforcement
* Strict concurrency limits
* Locking + queue system
* Race condition handling

---

---

## 12. INVARIANTS

---

* No duplicate outreach per attempt
* No concurrent execution on same user
* All idempotent operations must be safe to retry
* State must remain consistent

---

---

## 13. ACCEPTANCE CRITERIA

---

### Case 1 — Duplicate Trigger

**Given** same idempotency key
**When** request repeated
**Then** second request blocked

---

---

### Case 2 — Concurrent Execution

**Given** parallel processing
**When** same user processed
**Then** only one succeeds

---

---

### Case 3 — Webhook Duplication

**Given** duplicate webhook
**When** processed
**Then** second ignored

---

---

### Case 4 — Retry Safety

**Given** retry triggered
**When** executed multiple times
**Then** no duplicate effect

---

---

## 14. REFERENCES

---

Depends on:

* spec/03_state_transition_rules.md
* spec/07_api_contracts.md
* runtime/system_loop.md
* runtime/scheduler_design.md
* failure/failure_playbook.md
* meta/project_classification.md

---

## END OF FILE
