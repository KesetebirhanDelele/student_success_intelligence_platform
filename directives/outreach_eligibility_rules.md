# directives/outreach_eligibility_rules.md

---

## LAYER 3 — DIRECTIVES (ELIGIBILITY RULES)

---

## 1. PURPOSE

This directive defines:

* Which students are eligible for outreach
* When eligibility is granted or denied
* Checkpoint-specific filtering rules
* Exclusion conditions

The goal is to ensure:

* Only valid students are contacted
* No duplicate or unnecessary outreach occurs
* Eligibility is deterministic and auditable

---

## 2. INPUTS

---

### Student Data

| Field              | Type    | Description                         |
| ------------------ | ------- | ----------------------------------- |
| user_id            | integer | Unique identifier                   |
| checkpoint_type    | string  | SQL / SSRS / SSIS / POST_COMPLETION |
| hws_behind         | integer | Assignments behind                  |
| avg_eff_rating     | float   | Effort rating                       |
| last_activity_days | integer | Days since last activity            |
| email              | string  | Email address                       |
| phone_number       | string  | Phone number                        |

---

### Outreach History

| Field             | Type     | Description             |
| ----------------- | -------- | ----------------------- |
| last_contact_time | datetime | Last outreach time      |
| contact_attempt   | integer  | Attempt count           |
| state             | string   | Current lifecycle state |

---

### System Context

| Field        | Type                        |
| ------------ | --------------------------- |
| current_time | datetime                    |
| scope_mode   | MVP / STANDARD / PRODUCTION |

---

## 3. OUTPUT

---

```json
{
  "eligible": boolean,
  "priority": "LOW | MEDIUM | HIGH",
  "checkpoint_type": "string",
  "reason_codes": ["string"]
}
```

---

## 4. CORE ELIGIBILITY RULES (ORDERED)

---

### RULE 1 — INVALID CONTACT DATA

IF:

* email is NULL AND phone_number is NULL

THEN:

```json
{
  "eligible": false,
  "reason_codes": ["NO_CONTACT_INFO"]
}
```

STOP

---

---

### RULE 2 — CLOSED OR RESOLVED CASE

IF:

* state = CLOSED
  OR
* state = RESOLVED

THEN:

```json
{
  "eligible": false,
  "reason_codes": ["CASE_ALREADY_CLOSED"]
}
```

STOP

---

---

### RULE 3 — RECENT CONTACT EXCLUSION

IF:

* last_contact_time exists
  AND
* current_time - last_contact_time < EXCLUSION_WINDOW(scope_mode)

THEN:

```json
{
  "eligible": false,
  "reason_codes": ["RECENTLY_CONTACTED"]
}
```

STOP

---

---

### RULE 4 — CHECKPOINT ELIGIBILITY

Each checkpoint has eligibility conditions.

---

#### SQL / SSRS / SSIS

IF:

* hws_behind ≥ MIN_HW_THRESHOLD(scope_mode)
  OR
* avg_eff_rating < MIN_EFFORT_THRESHOLD(scope_mode)
  OR
* last_activity_days > MAX_INACTIVITY(scope_mode)

THEN:

Eligible

---

---

#### POST_COMPLETION

IF:

* student completed program
  AND
* not enrolled in IPBC

THEN:

Eligible

---

---

### RULE 5 — DEFAULT ELIGIBILITY

IF no exclusion rules triggered:

```json
{
  "eligible": true,
  "priority": "MEDIUM",
  "reason_codes": ["ELIGIBLE_DEFAULT"]
}
```

---

## 5. PRIORITY ASSIGNMENT

---

### HIGH PRIORITY

IF:

* hws_behind ≥ 3
  OR
* avg_eff_rating < 2.5
  OR
* last_activity_days > 7

---

---

### MEDIUM PRIORITY

* Moderate deviation from thresholds

---

---

### LOW PRIORITY

* Minimal deviation

---

---

## 6. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

```plaintext
EXCLUSION_WINDOW = 30 days  
MIN_HW_THRESHOLD = 2  
MIN_EFFORT_THRESHOLD = 3.0  
MAX_INACTIVITY = 7 days  
```

Behavior:

* Basic eligibility rules
* No priority differentiation

---

---

### STANDARD

```plaintext
EXCLUSION_WINDOW = 30 days  
MIN_HW_THRESHOLD = 2  
MIN_EFFORT_THRESHOLD = 2.8  
MAX_INACTIVITY = 6 days  
```

Behavior:

* Adds priority classification
* Slightly stricter thresholds

---

---

### PRODUCTION

```plaintext
EXCLUSION_WINDOW = 30 days  
MIN_HW_THRESHOLD = 1–3 (checkpoint dependent)  
MIN_EFFORT_THRESHOLD = 2.5  
MAX_INACTIVITY = 5 days  
```

Behavior:

* Full rule set
* Checkpoint-specific thresholds
* Priority-based ordering
* Supports future scoring model

---

---

## 7. HELPER FUNCTIONS

---

### EXCLUSION_WINDOW(scope_mode)

| Scope      | Value   |
| ---------- | ------- |
| MVP        | 30 days |
| STANDARD   | 30 days |
| PRODUCTION | 30 days |

---

---

### MIN_HW_THRESHOLD(scope_mode)

| Scope      | Value         |
| ---------- | ------------- |
| MVP        | 2             |
| STANDARD   | 2             |
| PRODUCTION | 1–3 (dynamic) |

---

---

### MIN_EFFORT_THRESHOLD(scope_mode)

| Scope      | Value |
| ---------- | ----- |
| MVP        | 3.0   |
| STANDARD   | 2.8   |
| PRODUCTION | 2.5   |

---

---

### MAX_INACTIVITY(scope_mode)

| Scope      | Value  |
| ---------- | ------ |
| MVP        | 7 days |
| STANDARD   | 6 days |
| PRODUCTION | 5 days |

---

---

## 8. CONSTRAINTS

---

* Eligibility must be deterministic
* Same input must produce same output
* No randomness allowed
* Rules must be evaluated in order

---

---

## 9. FAILURE HANDLING

---

### Missing Data

* Default to NOT eligible
* Add reason: `"MISSING_DATA"`

---

---

### Invalid Values

* Log error
* Exclude student

---

---

## 10. INVARIANTS

---

* No student can be eligible if recently contacted
* No student without contact info can be eligible
* Closed cases cannot re-enter eligibility

---

---

## 11. ACCEPTANCE CRITERIA

---

### Case 1 — Valid Eligibility

**Given** student meets threshold
**When** evaluated
**Then** eligible = true

---

---

### Case 2 — Recent Contact

**Given** last_contact_time < 30 days
**When** evaluated
**Then** eligible = false

---

---

### Case 3 — No Contact Info

**Given** no email and no phone
**When** evaluated
**Then** eligible = false

---

---

### Case 4 — High Priority

**Given** high-risk metrics
**When** evaluated
**Then** priority = HIGH

---

---

## 12. REFERENCES

---

Depends on:

* directives/core_decision_engine.md
* state/system_state_model.md
* runtime/system_loop.md
* meta/project_classification.md

---

## END OF FILE
