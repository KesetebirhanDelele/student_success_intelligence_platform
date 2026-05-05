# directives/ghl_integration_contract.md

---

## LAYER 3 — DIRECTIVES (GHL INTEGRATION CONTRACT)

---

## 1. PURPOSE

This directive defines:

* How the system interacts with GHL (GoHighLevel)
* Data exchange format
* Triggering rules
* Validation and safeguards

The goal is to ensure:

* Reliable outreach execution
* Consistent data mapping
* No duplicate or invalid triggers

---

## 2. INTEGRATION MODEL

---

### Role of GHL

* GHL is the **execution layer**
* Handles:

  * Calls
  * SMS
  * Emails

---

### Role of This System

* Decision-making
* Data preparation
* Trigger orchestration

---

## 3. INPUT TO GHL

---

### Required Payload

```json
{
  "user_id": 123,
  "first_name": "string",
  "last_name": "string",
  "email": "string",
  "phone_number": "string",
  "checkpoint_type": "SQL | SSRS | SSIS | POST_COMPLETION",
  "hws_behind": 2,
  "avg_eff_rating": 3.5,
  "last_activity_days": 5,
  "contact_attempt": 1
}
```

---

### Optional Fields

```json
{
  "priority": "LOW | MEDIUM | HIGH",
  "reason_codes": ["string"]
}
```

---

## 4. CORE RULES

---

### RULE 1 — VALID CONTACT DATA

IF:

* email AND phone_number are both missing

THEN:

* DO NOT send to GHL
* Log error
* Abort trigger

---

---

### RULE 2 — IDENTITY CONSISTENCY

* user_id MUST match system record
* No transformation allowed
* Must be consistent across attempts

---

---

### RULE 3 — SINGLE TRIGGER PER ATTEMPT

* Only one GHL trigger allowed per attempt
* Duplicate triggers MUST be blocked

---

---

### RULE 4 — METADATA INJECTION

System MUST include:

* checkpoint_type
* contact_attempt
* academic metrics

---

---

### RULE 5 — STATE ALIGNMENT

* Only trigger when state = QUEUED
* After trigger → state MUST become CONTACTED

---

---

## 5. RESPONSE HANDLING

---

### Expected GHL Behavior

* Accept trigger request
* Execute workflow
* Send updates via webhook

---

---

### System Expectations

* Assume success only on confirmed response
* Log all responses

---

---

## 6. WEBHOOK CONTRACT

---

### Endpoint

```plaintext
POST /webhook/ghl-update
```

---

### Incoming Data (Example)

```json
{
  "user_id": 123,
  "event_type": "CALL_COMPLETED",
  "call_connected": true,
  "call_duration": 120,
  "transcript": "string"
}
```

---

### Supported Events

| Event            | Description          |
| ---------------- | -------------------- |
| CALL_COMPLETED   | Call finished        |
| SMS_RESPONSE     | SMS reply received   |
| EMAIL_RESPONSE   | Email engagement     |
| TRANSCRIPT_READY | Transcript available |

---

---

## 7. WEBHOOK PROCESSING RULES

---

### RULE 1 — VALIDATE USER

* user_id must exist
* Reject unknown users

---

---

### RULE 2 — UPDATE STATE

| Event                        | State Transition        |
| ---------------------------- | ----------------------- |
| CALL_COMPLETED (no response) | CONTACTED → NO_RESPONSE |
| CALL_COMPLETED (connected)   | CONTACTED → RESPONDED   |
| TRANSCRIPT_READY             | RESPONDED → ANALYZED    |

---

---

### RULE 3 — STORE DATA

* Save:

  * call_connected
  * call_duration
  * transcript

---

---

## 8. ERROR HANDLING

---

### GHL Trigger Failure

* Retry once immediately
* If still fails → defer to retry cycle

---

---

### Webhook Failure

* Log failure
* Retry processing if possible

---

---

### Missing Webhook

* Detect via timeout
* Mark as NO_RESPONSE

---

---

## 9. IDEMPOTENCY RULES

---

* Same (user_id, attempt) cannot trigger twice
* Webhook events must be processed once

---

---

## 10. CONSTRAINTS

---

* System MUST NOT directly initiate calls
* All outreach must go through GHL
* Payload must be validated before sending

---

---

## 11. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Basic payload
* Single trigger
* Minimal webhook handling

---

---

### STANDARD

* Full payload
* Basic webhook processing

---

---

### PRODUCTION

* Full payload + metadata
* Complete webhook handling
* Strict validation
* Failure recovery

---

---

## 12. ACCEPTANCE CRITERIA

---

### Case 1 — Valid Trigger

**Given** eligible student
**When** trigger sent
**Then** GHL workflow starts

---

---

### Case 2 — Duplicate Prevention

**Given** same attempt
**When** trigger attempted
**Then** second trigger blocked

---

---

### Case 3 — Webhook Processing

**Given** webhook received
**When** processed
**Then** state updated correctly

---

---

### Case 4 — Missing Contact

**Given** no contact info
**When** trigger attempted
**Then** request blocked

---

---

## 13. REFERENCES

---

Depends on:

* directives/core_decision_engine.md
* state/system_state_model.md
* runtime/system_loop.md
* failure/failure_playbook.md
* meta/project_classification.md

---

## END OF FILE
