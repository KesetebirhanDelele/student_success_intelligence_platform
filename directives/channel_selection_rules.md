# directives/channel_selection_rules.md

---

## LAYER 3 — DIRECTIVES (CHANNEL SELECTION RULES)

---

## 1. PURPOSE

This directive defines:

* Which communication channel to use (Call, SMS, Email)
* When to switch channels
* Priority and fallback logic

The goal is to ensure:

* Optimal student engagement
* Consistent multi-channel behavior
* Controlled fallback strategy

---

## 2. INPUTS

---

### Student Context

| Field        | Type   | Description    |
| ------------ | ------ | -------------- |
| phone_number | string | Contact number |
| email        | string | Email address  |

---

### Outreach Context

| Field             | Type    | Description                     |
| ----------------- | ------- | ------------------------------- |
| contact_attempt   | integer | Current attempt number          |
| call_connected    | boolean | Whether previous call connected |
| last_channel_used | string  | CALL / SMS / EMAIL              |
| state             | string  | Current state                   |

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
  "selected_channel": "CALL | SMS | EMAIL | NONE",
  "fallback_required": boolean,
  "reason_codes": ["string"]
}
```

---

## 4. CORE RULES (ORDERED)

---

### RULE 1 — NO VALID CHANNEL

IF:

* phone_number is NULL
  AND
* email is NULL

THEN:

```json
{
  "selected_channel": "NONE",
  "fallback_required": false,
  "reason_codes": ["NO_AVAILABLE_CHANNEL"]
}
```

STOP

---

---

### RULE 2 — FIRST ATTEMPT

IF:

* contact_attempt = 0

THEN:

```json
{
  "selected_channel": "CALL",
  "fallback_required": false,
  "reason_codes": ["INITIAL_CALL"]
}
```

STOP

---

---

### RULE 3 — CALL FAILED (NO RESPONSE)

IF:

* contact_attempt ≥ 1
  AND
* call_connected = FALSE

THEN:

Proceed to fallback logic

---

---

### RULE 4 — FALLBACK TO SMS

IF:

* phone_number exists
  AND
* last_channel_used = CALL

THEN:

```json
{
  "selected_channel": "SMS",
  "fallback_required": true,
  "reason_codes": ["FALLBACK_TO_SMS"]
}
```

STOP

---

---

### RULE 5 — FALLBACK TO EMAIL

IF:

* email exists
  AND
* last_channel_used = SMS

THEN:

```json
{
  "selected_channel": "EMAIL",
  "fallback_required": true,
  "reason_codes": ["FALLBACK_TO_EMAIL"]
}
```

STOP

---

---

### RULE 6 — NO MORE CHANNELS

IF:

* all channels attempted

THEN:

```json
{
  "selected_channel": "NONE",
  "fallback_required": false,
  "reason_codes": ["CHANNELS_EXHAUSTED"]
}
```

STOP

---

---

## 5. CHANNEL PRIORITY

---

### Default Order (PRODUCTION)

```plaintext
CALL → SMS → EMAIL
```

---

---

## 6. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Only CALL channel used
* No fallback

---

---

### STANDARD

* CALL → SMS
* Email optional

---

---

### PRODUCTION

* Full channel sequence
* Strict fallback enforcement
* Channel availability validation

---

---

## 7. CONSTRAINTS

---

* Do not use channel if contact info missing
* Do not repeat same channel consecutively
* Must follow priority order
* Must respect retry policy

---

---

## 8. FAILURE HANDLING

---

### Missing Contact Info

* Skip channel
* Log issue
* Add reason: `"MISSING_CONTACT_INFO"`

---

---

### Invalid Channel State

* Default to safe fallback
* Log anomaly

---

---

## 9. INVARIANTS

---

* First attempt must always be CALL (if available)
* No duplicate channel use in same attempt
* Channel fallback must follow defined order

---

---

## 10. ACCEPTANCE CRITERIA

---

### Case 1 — First Attempt

**Given** contact_attempt = 0
**When** evaluated
**Then** selected_channel = CALL

---

---

### Case 2 — Call Failed

**Given** call not connected
**When** next attempt
**Then** fallback to SMS

---

---

### Case 3 — SMS Failed

**Given** SMS already used
**When** next attempt
**Then** fallback to EMAIL

---

---

### Case 4 — No Channels

**Given** no contact info
**When** evaluated
**Then** selected_channel = NONE

---

---

## 11. REFERENCES

---

Depends on:

* directives/core_decision_engine.md
* directives/outreach_retry_policy.md
* state/system_state_model.md
* runtime/system_loop.md
* meta/project_classification.md

---

## END OF FILE
