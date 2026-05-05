# spec/07_api_contracts.md

---

## LAYER 2 — SPECIFICATIONS (API CONTRACTS)

---

## 1. PURPOSE

This file defines:

* All external and internal API contracts
* Request/response formats
* Validation rules
* Error handling behavior

The goal is to ensure:

* Strict, predictable API behavior
* Clear integration boundaries
* No ambiguity between services

---

## 2. API DESIGN PRINCIPLES

---

### 2.1 Deterministic Responses

* Same request MUST produce same response (given same state)
* No hidden side effects

---

### 2.2 Idempotency

* Safe retries MUST NOT create duplicate effects
* POST endpoints must enforce idempotency where applicable

---

### 2.3 Validation First

* All inputs MUST be validated before processing
* Invalid requests MUST fail fast

---

### 2.4 Consistent Structure

All responses MUST follow:

```json id="z2w4gd"
{
  "status": "success | error",
  "data": {},
  "error": null
}
```

---

## 3. CORE ENDPOINTS

---

## 3.1 Health Check

---

### Endpoint

```plaintext id="n2u7ov"
GET /health
```

---

### Response

```json id="0xj6o9"
{
  "status": "success",
  "data": {
    "service": "running",
    "scheduler_status": "active",
    "timestamp": "ISO8601"
  },
  "error": null
}
```

---

---

## 3.2 Trigger Outreach

---

### Endpoint

```plaintext id="fg6d2m"
POST /outreach/trigger
```

---

### Request

```json id="5tq2pe"
{
  "checkpoint_type": "SQL | SSRS | SSIS | POST_COMPLETION"
}
```

---

### Validation Rules

* checkpoint_type MUST be valid enum
* Request must not trigger duplicate execution

---

### Response

```json id="r7t9nm"
{
  "status": "success",
  "data": {
    "triggered": true
  },
  "error": null
}
```

---

---

## 3.3 Get Student Details

---

### Endpoint

```plaintext id="l5v4c8"
GET /students/{user_id}
```

---

### Response

```json id="u1k3hp"
{
  "status": "success",
  "data": {
    "user_id": 123,
    "state": "CONTACTED",
    "attempt_count": 1,
    "history": []
  },
  "error": null
}
```

---

---

## 3.4 Get Metrics

---

### Endpoint

```plaintext id="y8h2zd"
GET /metrics
```

---

### Response

```json id="1k8a6b"
{
  "status": "success",
  "data": {
    "total_outreach": 100,
    "success_rate": 0.7,
    "meeting_rate": 0.2,
    "sentiment_distribution": {}
  },
  "error": null
}
```

---

---

## 3.5 Manual Action Trigger

---

### Endpoint

```plaintext id="7d4z1r"
POST /actions/manual
```

---

### Request

```json id="q3r6x9"
{
  "user_id": 123,
  "action_type": "TRIGGER_OUTREACH | RETRY | CLOSE_CASE | BOOK_MEETING"
}
```

---

### Validation Rules

* action_type must be valid
* Must respect state constraints

---

### Response

```json id="v6m2f1"
{
  "status": "success",
  "data": {
    "executed": true
  },
  "error": null
}
```

---

---

## 3.6 GHL Webhook Endpoint

---

### Endpoint

```plaintext id="o2g9k4"
POST /webhook/ghl-update
```

---

### Purpose

* Receive updates from GHL:

  * Call status
  * SMS responses
  * Contact updates

---

### Request (Example)

```json id="9w5x2n"
{
  "user_id": 123,
  "event_type": "CALL_COMPLETED",
  "call_connected": true,
  "duration": 120,
  "transcript": "string"
}
```

---

### Response

```json id="6u3v8q"
{
  "status": "success",
  "data": {},
  "error": null
}
```

---

---

## 4. ERROR HANDLING

---

### Error Response Format

```json id="8j2k4m"
{
  "status": "error",
  "data": null,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message"
  }
}
```

---

---

### Common Error Codes

| Code              | Description              |
| ----------------- | ------------------------ |
| INVALID_INPUT     | Validation failed        |
| NOT_FOUND         | Resource not found       |
| DUPLICATE_REQUEST | Duplicate operation      |
| INTERNAL_ERROR    | Unexpected error         |
| STATE_VIOLATION   | Invalid state transition |

---

---

## 5. IDEMPOTENCY RULES

---

### Required For:

* Outreach trigger
* Manual actions

---

### Mechanism

* Unique request keys
* Duplicate detection

---

---

## 6. AUTHENTICATION

---

### MVP

* Basic token or simple auth

---

---

### STANDARD

* API key authentication

---

---

### PRODUCTION

* Secure auth (JWT / OAuth)
* Role-based access control

---

---

## 7. RATE LIMITING

---

### Rules

* Limit API requests per user
* Protect system from overload

---

### Scope Behavior

* MVP: No strict limits
* STANDARD: Basic limits
* PRODUCTION: Strict enforcement

---

---

## 8. VALIDATION RULES

---

* All inputs MUST be validated
* Reject malformed requests
* Enforce data types and ranges

---

---

## 9. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Minimal endpoints
* Limited validation

---

---

### STANDARD

* Full endpoints
* Basic validation

---

---

### PRODUCTION

* Full API coverage
* Strict validation
* Idempotency + rate limiting

---

---

## 10. ACCEPTANCE CRITERIA

---

### Case 1 — Valid Request

**Given** valid input
**When** API called
**Then** correct response returned

---

---

### Case 2 — Invalid Input

**Given** invalid request
**When** API called
**Then** error returned

---

---

### Case 3 — Duplicate Request

**Given** duplicate request
**When** processed
**Then** no duplicate effect occurs

---

---

## 11. REFERENCES

---

Depends on:

* spec/02_system_specifications.md
* directives/core_decision_engine.md
* state/system_state_model.md
* runtime/system_loop.md
* meta/project_classification.md

---

## END OF FILE
