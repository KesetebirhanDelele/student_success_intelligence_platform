# directives/agent_ownership_matrix.md

---

## LAYER 3 — DIRECTIVES (AGENT OWNERSHIP MATRIX)

---

## 1. PURPOSE

This directive defines:

* Ownership boundaries between system components (agents)
* Responsibility for each action in the system
* Prevention of overlapping or conflicting behavior

The goal is to ensure:

* Clear separation of concerns
* No duplicated responsibilities
* Deterministic execution across agents

---

## 2. AGENT DEFINITIONS

---

### 2.1 Scheduler Agent

Responsible for:

* Triggering system loop
* Initiating daily execution
* Initiating retry cycles

---

---

### 2.2 Eligibility Agent

Responsible for:

* Evaluating student eligibility
* Applying eligibility rules
* Assigning priority

---

---

### 2.3 Decision Engine Agent

Responsible for:

* Determining next action
* Combining inputs (data + LLM)
* Producing final decisions

---

---

### 2.4 Outreach Agent

Responsible for:

* Triggering outreach via GHL
* Managing outreach attempts
* Enforcing idempotency

---

---

### 2.5 GHL Integration Agent

Responsible for:

* Sending payloads to GHL
* Receiving webhook updates
* Mapping responses to system

---

---

### 2.6 LLM Processing Agent

Responsible for:

* Sending transcript to LLM
* Validating output
* Providing structured insights

---

---

### 2.7 State Management Agent

Responsible for:

* Managing state transitions
* Enforcing invariants
* Preventing invalid transitions

---

---

### 2.8 Failure Handling Agent

Responsible for:

* Detecting failures
* Applying recovery strategies
* Logging and alerting

---

---

### 2.9 Analytics Agent

Responsible for:

* Computing metrics
* Providing dashboard data

---

---

### 2.10 Operator (Human Agent)

Responsible for:

* Monitoring system
* Triggering manual actions
* Investigating issues

---

---

## 3. OWNERSHIP MATRIX

---

| Action                 | Owner                 | Secondary       |
| ---------------------- | --------------------- | --------------- |
| Scheduler Trigger      | Scheduler Agent       | None            |
| Eligibility Evaluation | Eligibility Agent     | Decision Engine |
| Decision Generation    | Decision Engine Agent | None            |
| Outreach Trigger       | Outreach Agent        | GHL Integration |
| GHL API Call           | GHL Integration Agent | None            |
| Webhook Processing     | GHL Integration Agent | State Agent     |
| LLM Processing         | LLM Agent             | Decision Engine |
| State Transition       | State Agent           | Decision Engine |
| Retry Decision         | Decision Engine       | Retry Policy    |
| Failure Handling       | Failure Agent         | All Agents      |
| Metrics Calculation    | Analytics Agent       | None            |
| Manual Action          | Operator              | Backend         |

---

---

## 4. OWNERSHIP RULES

---

### RULE 1 — SINGLE OWNER PER ACTION

* Each action MUST have exactly one primary owner
* No shared ownership allowed

---

---

### RULE 2 — NO DIRECT CROSS-ACTION

* Agents must not perform actions outside their domain
* All actions must follow defined flow

---

---

### RULE 3 — CONTROL FLOW

```plaintext id="q7n0xw"
Scheduler → Eligibility → Decision → Outreach → GHL → State → Analytics
```

---

---

### RULE 4 — DECISION AUTHORITY

* Only Decision Engine can determine actions
* Other agents MUST NOT override decisions

---

---

### RULE 5 — STATE AUTHORITY

* Only State Management Agent can change state
* All transitions must be validated

---

---

## 5. CONFLICT PREVENTION

---

### Rules

* No two agents can trigger outreach
* No agent can bypass decision engine
* No direct state mutation outside State Agent

---

---

## 6. FAILURE OWNERSHIP

---

### Assignment

| Failure Type      | Owner                 |
| ----------------- | --------------------- |
| GHL Failure       | GHL Integration Agent |
| LLM Failure       | LLM Agent             |
| Scheduler Failure | Scheduler Agent       |
| State Violation   | State Agent           |
| System Failure    | Failure Agent         |

---

---

## 7. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Fewer active agents
* Some responsibilities combined

---

---

### STANDARD

* Core agents separated
* Partial enforcement

---

---

### PRODUCTION

* Full agent separation
* Strict ownership enforcement
* No overlap allowed

---

---

## 8. INVARIANTS

---

* Every action has exactly one owner
* Decision Engine is the only decision authority
* State Agent is the only state authority

---

---

## 9. ACCEPTANCE CRITERIA

---

### Case 1 — Ownership Clarity

**Given** system action
**When** executed
**Then** owner is clearly defined

---

---

### Case 2 — Conflict Prevention

**Given** multiple agents
**When** action triggered
**Then** no duplication occurs

---

---

### Case 3 — State Control

**Given** state transition
**When** executed
**Then** only State Agent performs update

---

---

## 10. REFERENCES

---

Depends on:

* directives/core_decision_engine.md
* runtime/system_loop.md
* state/system_state_model.md
* failure/failure_playbook.md
* meta/project_classification.md

---

## END OF FILE
