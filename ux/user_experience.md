# ux/user_experience.md

---

## LAYER 12 — USER EXPERIENCE & INTERACTION MODEL

---

## 1. PURPOSE

This file defines:

* User personas
* System-user interaction boundaries
* User journeys
* UX constraints
* Dashboard interaction patterns

The goal is to ensure:

* Clear operator visibility
* Efficient workflows
* No business logic leakage into UI
* Consistent and predictable interactions

---

## 2. USER PERSONAS

---

### 2.1 Admin / Operator

Responsibilities:

* Monitor outreach performance
* Review student cases
* Track system activity
* Investigate failures

---

---

### 2.2 Program Manager

Responsibilities:

* Analyze engagement metrics
* Track student outcomes
* Review intervention effectiveness

---

---

### 2.3 System (Automated Actor)

* Executes decisions
* Triggers outreach
* Processes data

---

---

## 3. INTERACTION MODEL

---

### Core Principle

> UI is a **read + control layer only**
> All logic lives in backend directives

---

### UI MUST NOT:

* Contain business logic
* Make independent decisions
* Modify system state outside APIs

---

### UI MUST:

* Display system state
* Trigger backend actions via API
* Provide visibility into decisions

---

---

## 4. PRIMARY USER JOURNEYS

---

### 4.1 Monitor Daily Outreach

---

**Steps:**

1. Operator opens dashboard
2. Views:

   * Total students processed
   * Outreach attempts
   * Success rates
3. Reviews flagged students

---

---

### 4.2 Investigate Student Case

---

**Steps:**

1. Search or select student
2. View:

   * Outreach history
   * State transitions
   * Decision outputs
   * Transcript + sentiment
3. Identify issues

---

---

### 4.3 Review Failures

---

**Steps:**

1. Navigate to failure dashboard
2. View:

   * Failed outreach attempts
   * System errors
3. Drill down into logs

---

---

### 4.4 Trigger Manual Action (Optional)

---

**Steps:**

1. Select student
2. Trigger:

   * Manual outreach
   * Retry attempt
3. System validates and executes

---

---

## 5. DASHBOARD COMPONENTS

---

### 5.1 Overview Dashboard

Displays:

* Total outreach attempts
* Success rate
* Meeting bookings
* Sentiment distribution

---

---

### 5.2 Student Detail View

Displays:

* Student profile
* Outreach history
* Current state
* Decision outputs
* Transcript data

---

---

### 5.3 Activity Log

Displays:

* All system actions
* Timestamps
* Reason codes

---

---

### 5.4 Failure Panel

Displays:

* Failure types
* Affected students
* Recovery status

---

---

## 6. UX CONSTRAINTS

---

### 6.1 No Hidden State

* UI must reflect actual system state
* No derived UI-only state

---

---

### 6.2 Deterministic Display

* Same data → same display
* No random ordering

---

---

### 6.3 Read-Only Priority

* Most views are read-only
* Actions require explicit confirmation

---

---

### 6.4 Performance

* Dashboard load ≤ 2 seconds
* API calls ≤ 500 ms

---

---

## 7. ACCESS CONTROL

---

### MVP

* Simple login
* Single user role

---

---

### STANDARD

* Basic role separation

---

---

### PRODUCTION

* Role-based access (RBAC)
* Permissions:

  * View only
  * Operator actions
  * Admin control

---

---

## 8. ERROR HANDLING (UX)

---

### Display Rules

* Show clear error messages
* Do not expose internal errors
* Provide retry options where applicable

---

---

### Example

```plaintext id="x8y1gh"
"Outreach trigger failed. Please retry."
```

---

---

## 9. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Minimal dashboard
* Basic metrics only
* Limited interaction

---

---

### STANDARD

* Full dashboard
* Core workflows enabled

---

---

### PRODUCTION

* Full analytics
* Failure dashboards
* Advanced filtering
* Role-based UI

---

---

## 10. ACCEPTANCE CRITERIA

---

### Case 1 — Dashboard Load

**Given** dashboard opened
**When** data loaded
**Then** display within performance limits

---

---

### Case 2 — Student View

**Given** student selected
**When** data retrieved
**Then** full history displayed

---

---

### Case 3 — Action Trigger

**Given** operator triggers action
**When** API called
**Then** backend executes action

---

---

## 11. REFERENCES

---

Depends on:

* spec/07_api_contracts.md
* runtime/system_loop.md
* state/system_state_model.md
* directives/core_decision_engine.md
* meta/project_classification.md

---

## END OF FILE
