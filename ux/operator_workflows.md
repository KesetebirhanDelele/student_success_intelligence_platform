# ux/operator_workflows.md

---

## LAYER 12 — USER EXPERIENCE (OPERATOR WORKFLOWS)

---

## 1. PURPOSE

This file defines:

* Step-by-step workflows for system operators
* How users interact with the system during daily operations
* Decision-support processes (NOT decision-making logic)
* Standard operating procedures (SOPs)

The goal is to ensure:

* Consistent operations
* Fast issue resolution
* Clear interaction boundaries
* No ambiguity in user actions

---

## 2. CORE PRINCIPLES

---

### 2.1 System-Driven Decisions

* Operators DO NOT make system decisions
* Operators only:

  * Observe
  * Trigger approved actions
  * Investigate anomalies

---

### 2.2 API-First Interaction

* All actions must go through backend APIs
* No direct database access
* UI acts as control surface only

---

### 2.3 Auditability

* Every operator action MUST be logged
* Include:

  * user_id
  * action
  * timestamp
  * reason

---

---

## 3. DAILY OPERATION WORKFLOW

---

### 3.1 Daily Monitoring

---

**Steps:**

1. Open dashboard
2. Review Overview:

   * Total outreach attempts
   * Success rate
   * Failures
3. Check:

   * High-risk students
   * Pending retries

---

### Expected Outcome

* System health verified
* No critical issues missed

---

---

## 4. STUDENT CASE REVIEW WORKFLOW

---

### 4.1 Investigate Student

---

**Steps:**

1. Search for student
2. Open student detail view
3. Review:

   * Current state
   * Outreach history
   * Decision outputs
   * Transcript (if available)

---

### Decision Support

Operator may determine:

* If system behaved correctly
* If manual intervention is needed

---

---

## 5. FAILURE INVESTIGATION WORKFLOW

---

### 5.1 Identify Failure

---

**Steps:**

1. Open Failure Dashboard
2. Filter by failure type:

   * GHL failure
   * LLM failure
   * Scheduler issue
3. Select failure case

---

---

### 5.2 Investigate Details

---

**Steps:**

1. Review logs
2. Check:

   * Last action attempted
   * Recovery action taken
3. Confirm system behavior

---

---

### 5.3 Take Action (if needed)

---

Allowed actions:

* Retry outreach
* Trigger manual outreach
* Escalate issue

---

---

## 6. MANUAL INTERVENTION WORKFLOW

---

### 6.1 Trigger Manual Outreach

---

**Steps:**

1. Select student
2. Click “Trigger Outreach”
3. Confirm action

---

### Constraints

* Must validate:

  * State is not CLOSED
  * Max attempts not exceeded

---

---

### 6.2 Retry Outreach

---

**Steps:**

1. Select failed outreach
2. Click “Retry”
3. Confirm action

---

---

### 6.3 Force Close Case

---

**Steps:**

1. Select student
2. Click “Close Case”
3. Provide reason
4. Confirm

---

---

## 7. ESCALATION WORKFLOW

---

### 7.1 Identify High-Risk Case

---

**Triggers:

* High-risk flag from decision engine
* Multiple failed attempts
* Negative sentiment

---

---

### 7.2 Escalate

---

**Steps:**

1. Mark case for escalation
2. Notify program manager
3. Log escalation

---

---

## 8. MEETING MANAGEMENT WORKFLOW

---

### 8.1 Review Scheduled Meetings

---

**Steps:**

1. Open meeting dashboard
2. View upcoming meetings
3. Verify scheduling

---

---

### 8.2 Manual Booking (Override)

---

**Steps:**

1. Select student
2. Click “Book Meeting”
3. Choose time
4. Confirm

---

---

## 9. SYSTEM VALIDATION WORKFLOW

---

### 9.1 Validate Daily Execution

---

**Steps:**

1. Confirm scheduler ran
2. Verify:

   * Outreach triggered
   * States updated
3. Check logs

---

---

### 9.2 Validate Retry Cycle

---

**Steps:**

1. Identify retry-eligible students
2. Confirm retry executed
3. Verify state transitions

---

---

## 10. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Minimal workflows
* Manual monitoring
* Limited intervention options

---

---

### STANDARD

* Structured workflows
* Basic failure handling
* Limited escalation

---

---

### PRODUCTION

* Full workflows
* Complete failure handling
* Escalation + monitoring
* Strict auditability

---

---

## 11. CONSTRAINTS

---

* No direct DB edits
* No bypassing API
* No manual override of core decision logic

---

---

## 12. ACCEPTANCE CRITERIA

---

### Case 1 — Daily Monitoring

**Given** operator opens dashboard
**When** reviewing metrics
**Then** system health is visible

---

---

### Case 2 — Failure Handling

**Given** failure occurs
**When** operator investigates
**Then** correct recovery action identified

---

---

### Case 3 — Manual Action

**Given** operator triggers action
**When** executed
**Then** system processes and logs action

---

---

## 13. REFERENCES

---

Depends on:

* ux/admin_dashboard.md
* spec/07_api_contracts.md
* runtime/system_loop.md
* directives/core_decision_engine.md
* meta/project_classification.md

---

## END OF FILE
