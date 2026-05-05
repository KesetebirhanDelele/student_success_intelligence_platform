# directives/outreach_retry_policy.md

---

## LAYER 3 — DIRECTIVES (RETRY POLICY)

---

## 1. PURPOSE

This directive defines:

* When retries are allowed
* How many retries can occur
* Timing between retries
* Channel fallback behavior

The goal is to ensure:

* No excessive outreach
* Consistent retry behavior
* Controlled escalation across attempts

---

## 2. INPUTS

---

### Required Inputs

| Field             | Type                        | Description               |
| ----------------- | --------------------------- | ------------------------- |
| contact_attempt   | integer                     | Current attempt number    |
| last_contact_time | datetime                    | Last outreach timestamp   |
| call_connected    | boolean                     | Whether student responded |
| current_time      | datetime                    | Current system time       |
| scope_mode        | MVP / STANDARD / PRODUCTION | Scope from meta file      |

---

## 3. OUTPUT

---

```json
{
  "retry_allowed": boolean,
  "next_action": "RETRY_CALL | SEND_SMS | SEND_EMAIL | STOP",
  "next_retry_time": "datetime | null",
  "reason_codes": ["string"]
}
```

---

## 4. CORE RULES (ORDERED)

---

### RULE 1 — NO RETRY IF CONNECTED

IF:

* call_connected = TRUE

THEN:

```json
{
  "retry_allowed": false,
  "next_action": "STOP",
  "reason_codes": ["RESPONSE_RECEIVED"]
}
```

STOP

---

---

### RULE 2 — MAX ATTEMPTS REACHED

IF:

* contact_attempt ≥ MAX_ATTEMPTS(scope_mode)

THEN:

```json
{
  "retry_allowed": false,
  "next_action": "FALLBACK_CHANNEL",
  "reason_codes": ["MAX_ATTEMPTS_REACHED"]
}
```

STOP

---

---

### RULE 3 — RETRY WINDOW NOT PASSED

IF:

* current_time - last_contact_time < RETRY_INTERVAL(scope_mode)

THEN:

```json
{
  "retry_allowed": false,
  "next_action": "WAIT",
  "reason_codes": ["RETRY_WINDOW_NOT_MET"]
}
```

STOP

---

---

### RULE 4 — RETRY CALL

IF:

* contact_attempt < MAX_ATTEMPTS(scope_mode)
  AND
* retry window passed

THEN:

```json
{
  "retry_allowed": true,
  "next_action": "RETRY_CALL",
  "next_retry_time": current_time,
  "reason_codes": ["RETRY_CALL_ALLOWED"]
}
```

STOP

---

---

## 5. CHANNEL FALLBACK RULES

---

Triggered when:

* Max attempts reached
* No successful contact

---

### Fallback Order (PRODUCTION)

```plaintext
CALL → SMS → EMAIL
```

---

### Rules

* SMS must be attempted before email
* Email is final fallback
* No further retries after email

---

---

## 6. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

```plaintext
MAX_ATTEMPTS = 1  
RETRY_INTERVAL = N/A  
```

Behavior:

* No retry allowed
* Single outreach attempt only

---

---

### STANDARD

```plaintext
MAX_ATTEMPTS = 2  
RETRY_INTERVAL = 24 hours  
```

Behavior:

* One retry allowed
* No channel fallback beyond retry

---

---

### PRODUCTION

```plaintext
MAX_ATTEMPTS = 3  
RETRY_INTERVAL = 24 hours  
```

Behavior:

* Up to 3 attempts
* Retry across multiple days
* Channel fallback after final attempt
* Strict enforcement of timing

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

### RETRY_INTERVAL(scope_mode)

| Scope      | Value    |
| ---------- | -------- |
| MVP        | N/A      |
| STANDARD   | 24 hours |
| PRODUCTION | 24 hours |

---

---

## 8. CONSTRAINTS

---

* No retry after successful contact
* No retry after fallback channels exhausted
* No retry beyond max attempts
* Timing must be strictly enforced

---

---

## 9. FAILURE HANDLING

---

### Missing last_contact_time

* Do not retry
* Log error
* Add reason code: `"MISSING_TIMESTAMP"`

---

---

### Invalid attempt count

* Default to safe behavior (no retry)
* Log anomaly

---

---

## 10. INVARIANTS

---

* Retry attempts must increment sequentially
* No duplicate retries for same attempt
* Retry timing must not overlap

---

---

## 11. ACCEPTANCE CRITERIA

---

### Case 1 — No Retry (MVP)

**Given** contact_attempt = 1
**When** evaluated
**Then** retry_allowed = false

---

---

### Case 2 — Retry Allowed (PRODUCTION)

**Given** contact_attempt = 1
**And** 24 hours passed
**When** evaluated
**Then** retry_allowed = true

---

---

### Case 3 — Max Attempts

**Given** contact_attempt = 3
**When** evaluated
**Then** fallback channel triggered

---

---

### Case 4 — Connected Call

**Given** call_connected = TRUE
**When** evaluated
**Then** retry not allowed

---

---

## 12. REFERENCES

---

Depends on:

* directives/core_decision_engine.md
* runtime/system_loop.md
* state/system_state_model.md
* meta/project_classification.md

---

## END OF FILE
