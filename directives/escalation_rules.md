# directives/escalation_rules.md

---

## LAYER 3 — DIRECTIVES (ESCALATION RULES)

---

## 1. PURPOSE

This directive defines:

* When a student case must be escalated
* Types of escalation
* Escalation triggers and thresholds
* Escalation actions and outcomes

The goal is to ensure:

* High-risk students receive timely human intervention
* Critical cases are not missed
* Escalation is consistent and deterministic

---

## 2. INPUTS

---

### Student Context

| Field              | Type    | Description              |
| ------------------ | ------- | ------------------------ |
| user_id            | integer | Student identifier       |
| hws_behind         | integer | Assignments behind       |
| avg_eff_rating     | float   | Effort rating            |
| last_activity_days | integer | Days since last activity |

---

### Outreach Context

| Field           | Type    | Description    |
| --------------- | ------- | -------------- |
| contact_attempt | integer | Attempt count  |
| call_connected  | boolean | Call result    |
| meeting_booked  | boolean | Meeting status |
| state           | string  | Current state  |

---

### LLM Output

| Field               | Type    |
| ------------------- | ------- |
| sentiment           | string  |
| meeting_recommended | boolean |
| issues              | list    |

---

### System Context

| Field      | Type                        |
| ---------- | --------------------------- |
| scope_mode | MVP / STANDARD / PRODUCTION |

---

## 3. OUTPUT

---

```json
{
  "escalation_required": boolean,
  "escalation_type": "NONE | HIGH_RISK | NO_RESPONSE | NEGATIVE_SENTIMENT | MANUAL",
  "priority": "LOW | MEDIUM | HIGH",
  "action": "NOTIFY_OPERATOR | FLAG_CASE | NONE",
  "reason_codes": ["string"]
}
```

---

## 4. CORE RULES (ORDERED)

---

### RULE 1 — MEETING ALREADY BOOKED

IF:

* meeting_booked = TRUE

THEN:

```json
{
  "escalation_required": false,
  "escalation_type": "NONE",
  "action": "NONE",
  "reason_codes": ["MEETING_ALREADY_SCHEDULED"]
}
```

STOP

---

---

### RULE 2 — HIGH-RISK STUDENT

IF:

* hws_behind ≥ 3
  OR
* avg_eff_rating < 2.5
  OR
* last_activity_days > 7

THEN:

```json
{
  "escalation_required": true,
  "escalation_type": "HIGH_RISK",
  "priority": "HIGH",
  "action": "FLAG_CASE",
  "reason_codes": ["HIGH_RISK_METRICS"]
}
```

CONTINUE

---

---

### RULE 3 — NO RESPONSE AFTER MAX ATTEMPTS

IF:

* contact_attempt ≥ MAX_ATTEMPTS(scope_mode)
  AND
* call_connected = FALSE

THEN:

```json
{
  "escalation_required": true,
  "escalation_type": "NO_RESPONSE",
  "priority": "MEDIUM",
  "action": "NOTIFY_OPERATOR",
  "reason_codes": ["NO_RESPONSE_MAX_ATTEMPTS"]
}
```

CONTINUE

---

---

### RULE 4 — NEGATIVE OR CRITICAL SENTIMENT

IF:

* sentiment = "negative"
  OR
* sentiment = "critical"

THEN:

```json
{
  "escalation_required": true,
  "escalation_type": "NEGATIVE_SENTIMENT",
  "priority": "HIGH",
  "action": "FLAG_CASE",
  "reason_codes": ["NEGATIVE_SENTIMENT_DETECTED"]
}
```

CONTINUE

---

---

### RULE 5 — LLM RECOMMENDS INTERVENTION

IF:

* meeting_recommended = TRUE

THEN:

```json
{
  "escalation_required": true,
  "escalation_type": "MANUAL",
  "priority": "MEDIUM",
  "action": "NOTIFY_OPERATOR",
  "reason_codes": ["LLM_RECOMMENDED_INTERVENTION"]
}
```

CONTINUE

---

---

### RULE 6 — DEFAULT

IF no escalation rules triggered:

```json
{
  "escalation_required": false,
  "escalation_type": "NONE",
  "action": "NONE",
  "reason_codes": ["NO_ESCALATION_REQUIRED"]
}
```

---

## 5. PRIORITY DEFINITIONS

---

### HIGH

* Immediate attention required
* High-risk or critical sentiment

---

### MEDIUM

* Follow-up required
* No response or LLM recommendation

---

### LOW

* Informational only
* No immediate action required

---

## 6. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Minimal escalation
* Only high-risk detection
* No automated notifications

---

---

### STANDARD

* High-risk + no-response escalation
* Basic operator notifications

---

---

### PRODUCTION

* Full escalation rules
* Multi-condition escalation
* Priority-based handling
* Integration with operator workflows
* Alerting enabled

---

---

## 7. HELPER FUNCTIONS

---

### MAX_ATTEMPTS(scope_mode)

| Scope      | Value |
| ---------- | ----- |
| MVP        | 1     |
| STANDARD   | 2     |
| PRODUCTION | 3     |

---

---

## 8. CONSTRAINTS

---

* Escalation must not override decision engine actions
* Escalation must not trigger duplicate actions
* Escalation must be logged

---

---

## 9. FAILURE HANDLING

---

### Missing Data

* Do not escalate
* Add reason: `"MISSING_DATA"`

---

---

### Invalid LLM Output

* Ignore LLM-based escalation
* Proceed with rule-based checks

---

---

## 10. INVARIANTS

---

* Escalation cannot occur for CLOSED cases
* Escalation must be tied to valid state
* Escalation must include reason codes

---

---

## 11. ACCEPTANCE CRITERIA

---

### Case 1 — High Risk

**Given** hws_behind ≥ 3
**When** evaluated
**Then** escalation_required = true

---

---

### Case 2 — No Response

**Given** max attempts reached
**When** evaluated
**Then** escalation triggered

---

---

### Case 3 — Negative Sentiment

**Given** sentiment = negative
**When** evaluated
**Then** escalation triggered

---

---

### Case 4 — No Escalation

**Given** no conditions met
**When** evaluated
**Then** escalation_required = false

---

---

## 12. REFERENCES

---

Depends on:

* directives/core_decision_engine.md
* directives/outreach_retry_policy.md
* state/system_state_model.md
* runtime/system_loop.md
* meta/project_classification.md

---

## END OF FILE
