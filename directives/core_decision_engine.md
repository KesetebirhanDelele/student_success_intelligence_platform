# directives/core_decision_engine.md

---

## LAYER 3 — DIRECTIVES (BEHAVIOR)

---

## 1. PURPOSE

The **Core Decision Engine** is the central authority responsible for:

* Determining what action to take for each student
* Combining academic data, outreach state, and LLM output
* Producing deterministic, auditable decisions
* Ensuring system behavior is consistent, predictable, and rule-driven

This directive is the **single source of truth** for all decision-making logic.

---

## 2. INPUTS

---

### 2.1 Student Context

| Field              | Type    | Description                         |
| ------------------ | ------- | ----------------------------------- |
| user_id            | integer | Unique student identifier           |
| checkpoint_type    | string  | SQL / SSRS / SSIS / Post-completion |
| hws_behind         | integer | Number of assignments behind        |
| avg_eff_rating     | float   | Average effort rating               |
| last_activity_days | integer | Days since last activity            |

---

### 2.2 Outreach State

| Field             | Type     | Description                       |
| ----------------- | -------- | --------------------------------- |
| contact_attempt   | integer  | Number of attempts made           |
| last_contact_time | datetime | Last outreach timestamp           |
| call_connected    | boolean  | Whether call was answered         |
| meeting_booked    | boolean  | Whether meeting already scheduled |
| ipbc_enrolled     | boolean  | Whether student enrolled in IPBC  |

---

### 2.3 LLM Output (Optional)

| Field               | Type    |
| ------------------- | ------- |
| sentiment           | string  |
| issues              | list    |
| meeting_recommended | boolean |
| ipbc_interest_level | string  |

---

### 2.4 System Context

| Field        | Type                        |
| ------------ | --------------------------- |
| current_time | datetime                    |
| scope_mode   | MVP / STANDARD / PRODUCTION |

---

## 3. OUTPUT

---

```json
{
  "action_type": "NO_ACTION | TRIGGER_OUTREACH | RETRY_OUTREACH | SEND_SMS | SEND_EMAIL | BOOK_MEETING | CLOSE_CASE",
  "priority": "LOW | MEDIUM | HIGH",
  "channel": "CALL | SMS | EMAIL | NONE",
  "retry_allowed": boolean,
  "escalation_required": boolean,
  "reason_codes": ["string"]
}
```

---

## 4. DECISION RULES (ORDERED — MANDATORY)

Evaluation MUST occur in this order.
Stop at the first matching rule unless otherwise specified.

---

### RULE 1 — TERMINATION CONDITIONS

IF:

* ipbc_enrolled = TRUE
  OR
* meeting_booked = TRUE

THEN:

```json
{
  "action_type": "CLOSE_CASE",
  "channel": "NONE",
  "retry_allowed": false,
  "reason_codes": ["CASE_RESOLVED"]
}
```

STOP

---

### RULE 2 — MAX ATTEMPTS REACHED

IF:

* contact_attempt ≥ MAX_ATTEMPTS(scope_mode)

THEN:

```json
{
  "action_type": "SEND_SMS_OR_EMAIL",
  "channel": "SMS_OR_EMAIL",
  "retry_allowed": false,
  "reason_codes": ["MAX_ATTEMPTS_REACHED"]
}
```

STOP

---

### RULE 3 — FIRST OUTREACH

IF:

* contact_attempt = 0

THEN:

```json
{
  "action_type": "TRIGGER_OUTREACH",
  "channel": "CALL",
  "retry_allowed": true,
  "reason_codes": ["INITIAL_CONTACT"]
}
```

STOP

---

### RULE 4 — RETRY ELIGIBILITY

IF:

* call_connected = FALSE
  AND
* retry_window_passed(last_contact_time, current_time, scope_mode)

THEN:

```json
{
  "action_type": "RETRY_OUTREACH",
  "channel": "CALL",
  "retry_allowed": true,
  "reason_codes": ["RETRY_ELIGIBLE"]
}
```

STOP

---

### RULE 5 — LLM-DRIVEN INTERVENTION

IF:

* LLM output exists
  AND
* meeting_recommended = TRUE

THEN:

```json
{
  "action_type": "BOOK_MEETING",
  "channel": "NONE",
  "retry_allowed": false,
  "reason_codes": ["LLM_MEETING_TRIGGER"]
}
```

STOP

---

### RULE 6 — HIGH-RISK STUDENT

IF:

* hws_behind ≥ 3
  OR
* avg_eff_rating < 2.5
  OR
* last_activity_days > 7

THEN:

```json
{
  "action_type": "ESCALATE",
  "priority": "HIGH",
  "escalation_required": true,
  "reason_codes": ["HIGH_RISK_STUDENT"]
}
```

CONTINUE (may combine with other actions)

---

### RULE 7 — DEFAULT

IF no rules triggered:

```json
{
  "action_type": "NO_ACTION",
  "channel": "NONE",
  "retry_allowed": false,
  "reason_codes": ["NO_ELIGIBLE_ACTION"]
}
```

---

## 5. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* MAX_ATTEMPTS = 1
* No retry cycle
* No escalation
* LLM usage limited

---

### STANDARD

* MAX_ATTEMPTS = 2
* Basic retry logic
* Limited escalation

---

### PRODUCTION

* MAX_ATTEMPTS = 3
* Full retry cycle (multi-day)
* Channel fallback (CALL → SMS → EMAIL)
* Full escalation rules
* Full LLM integration

---

## 6. HELPER FUNCTIONS

---

### retry_window_passed()

Definition depends on scope:

* MVP: always FALSE
* STANDARD: 24 hours
* PRODUCTION: 24-hour intervals across 3 days

---

## 7. CONSTRAINTS

---

* Decisions MUST be deterministic
* No randomness allowed
* LLM output MUST NOT override hard rules
* Same input MUST produce same output

---

## 8. FAILURE HANDLING

---

### Invalid LLM Output

* Ignore LLM fields
* Proceed with rule-based logic
* Add reason code: `"LLM_INVALID"`

---

### Missing Data

* Use conservative defaults
* Add reason code: `"MISSING_DATA"`

---

## 9. INVARIANTS

---

* No outreach after case closed
* No retries after max attempts
* No meeting booking if already booked

---

## 10. ACCEPTANCE CRITERIA

---

### Case 1 — First Contact

**Given** contact_attempt = 0
**When** decision engine runs
**Then** action = TRIGGER_OUTREACH

---

### Case 2 — Max Attempts

**Given** contact_attempt = 3 (PRODUCTION)
**When** decision engine runs
**Then** action = fallback (SMS/Email)

---

### Case 3 — Meeting Trigger

**Given** LLM recommends meeting
**When** decision runs
**Then** BOOK_MEETING is triggered

---

### Case 4 — Closed Case

**Given** meeting_booked = TRUE
**When** decision runs
**Then** CLOSE_CASE

---

## 11. REFERENCES

---

This directive depends on:

* meta/project_classification.md
* state/system_state_model.md
* runtime/system_loop.md

---

## END OF FILE
