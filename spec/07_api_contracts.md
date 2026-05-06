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

```plaintext
GET /students/{user_id}
```

---

### Response (success)

```json
{
  "status": "success",
  "data": {
    "user_id": 123,
    "state": "CONTACTED",
    "checkpoint_type": "SQL",
    "current_attempt": 1,
    "last_contact_at": "ISO8601 | null",
    "next_retry_at": "ISO8601 | null",
    "profile": {
      "first_name": "Jane",
      "last_name": "Doe",
      "email": "jane@example.com",
      "phone": "+15550001001",
      "path": "Data Analytics",
      "risk_level": "HIGH | MEDIUM | LOW",
      "hws_behind": 3,
      "avg_eff_rating": 2.1,
      "last_activity_days": 8
    },
    "history": [
      {
        "created_at": "ISO8601",
        "attempt_number": 1,
        "channel": "CALL",
        "action": "CALL_SIMULATED",
        "execution_mode": "SHADOW",
        "state_before": "QUEUED",
        "state_after": "CONTACTED"
      }
    ],
    "transitions": [
      {
        "created_at": "ISO8601",
        "from_state": "QUEUED",
        "to_state": "CONTACTED",
        "trigger": "scheduler",
        "actor": "system"
      }
    ]
  },
  "error": null
}
```

### Response (not found — HTTP 404)

```json
{
  "status": "error",
  "data": null,
  "error": {
    "code": "NOT_FOUND",
    "message": "No tracking record for student 123"
  }
}
```

> `risk_level` is derived server-side: HIGH if hws_behind ≥ 3 OR avg_eff_rating < 2.5 OR last_activity_days > 7; MEDIUM if hws_behind ≥ 2 OR avg_eff_rating < 3.0 OR last_activity_days ≥ 5; else LOW.

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

```plaintext
POST /actions/manual
```

---

### Request

```json
{
  "user_id": 123,
  "action_type": "CLOSE_CASE | FORCE_RETRY | BOOK_MEETING | ESCALATE",
  "notes": "optional free-text reason"
}
```

---

### Action Map

| action_type  | Transitions to       | Guard                                           |
| ------------ | -------------------- | ----------------------------------------------- |
| CLOSE_CASE   | CLOSED               | Blocked if already CLOSED                       |
| FORCE_RETRY  | RETRY                | Blocked if current_attempt ≥ MAX_ATTEMPTS       |
| BOOK_MEETING | RESOLVED             | Must be valid state machine transition          |
| ESCALATE     | INTERVENTION_REQUIRED | Only from CONTACTED, NO_RESPONSE, RETRY, RESPONDED |

---

### Response (success)

```json
{
  "status": "success",
  "data": {
    "from_state": "NO_RESPONSE",
    "to_state": "RETRY",
    "current_attempt": 2
  },
  "error": null
}
```

### Response (student not found — HTTP 200 with error)

```json
{
  "status": "error",
  "data": null,
  "error": { "code": "NOT_FOUND", "message": "No tracking record for student 999" }
}
```

### Response (MAX_ATTEMPTS reached)

```json
{
  "status": "error",
  "data": null,
  "error": {
    "code": "MAX_ATTEMPTS_REACHED",
    "message": "Cannot retry: student has reached the maximum of 3 attempts (current: 3)."
  }
}
```

### Response (invalid state transition)

```json
{
  "status": "error",
  "data": null,
  "error": { "code": "STATE_VIOLATION", "message": "Transition CLOSED → RETRY is not permitted." }
}
```

### Response (unknown action)

```json
{
  "status": "error",
  "data": null,
  "error": { "code": "INVALID_ACTION", "message": "Unknown action type: DO_SOMETHING_WEIRD" }
}
```

---

---

## 3.6 Dashboard Endpoints

---

> All dashboard endpoints return `{ "status": "success", "data": {...}, "error": null }` on success and require no request body unless noted.

---

### GET /dashboard/health

Returns system component status. Used to populate the System Health card.

```json
{
  "status": "success",
  "data": {
    "execution_mode": "SHADOW | LIVE",
    "outbound_enabled": false,
    "db": { "connected": true },
    "mssql": { "configured": false, "host": "" },
    "scheduler": { "status": "active | idle", "last_run": "ISO8601 | null" },
    "channels": { "call": false, "sms": false, "email": false }
  }
}
```

---

### GET /dashboard/alerts

Returns prioritised operational alerts. Used to populate the Operational Alerts card.

```json
{
  "status": "success",
  "data": {
    "count": 2,
    "alerts": [
      {
        "severity": "CRITICAL | WARNING | INFO",
        "message": "SQL Server is not configured.",
        "recommended_action": "Add MSSQL_HOST, MSSQL_USER, MSSQL_PASS to .env",
        "student_id": null
      },
      {
        "severity": "WARNING",
        "message": "Student 1001 has been CONTACTED for over 48 hours without response.",
        "recommended_action": "Manually escalate or close the case.",
        "student_id": 1001
      }
    ]
  }
}
```

Alert trigger conditions:

| Severity | Trigger |
| -------- | ------- |
| CRITICAL | MSSQL not configured |
| WARNING  | Student stuck in CONTACTED > 48 hours |
| WARNING  | Student in NO_RESPONSE with missed retry window |
| WARNING  | Scheduler has never run |
| INFO     | System running in SHADOW mode |
| INFO     | Synthflow or GHL API key missing |

---

### GET /dashboard/summary

Returns funnel KPIs, conversion ratios, and state-by-state counts. Used to populate KPI Summary and State Distribution cards.

```json
{
  "status": "success",
  "data": {
    "total_tracked": 152,
    "shadow_executions": 48,
    "funnel": {
      "tracked": 152,
      "contacted": 48,
      "responded": 15,
      "no_response": 22,
      "intervention_required": 4,
      "resolved": 9,
      "closed": 11,
      "shadow_executions": 48
    },
    "conversion": {
      "contacted_rate": 0.315,
      "response_rate": 0.312,
      "resolution_rate": 0.692
    },
    "by_state": {
      "ELIGIBLE": 80,
      "QUEUED": 12,
      "CONTACTED": 18,
      "NO_RESPONSE": 22,
      "RETRY": 5,
      "RESPONDED": 15,
      "ANALYZED": 3,
      "INTERVENTION_REQUIRED": 4,
      "RESOLVED": 9,
      "CLOSED": 11
    }
  }
}
```

---

### GET /dashboard/channel-performance

Returns per-channel outreach breakdown. Used to populate the Channel Performance card.

```json
{
  "status": "success",
  "data": {
    "shadow_mode": true,
    "note": "All simulated",
    "channels": [
      {
        "channel": "CALL",
        "attempts": 30,
        "shadow_count": 30,
        "responses": 8,
        "no_response": 22,
        "success_rate": 0.267
      },
      {
        "channel": "SMS",
        "attempts": 12,
        "shadow_count": 12,
        "responses": 5,
        "no_response": 7,
        "success_rate": 0.417
      },
      {
        "channel": "EMAIL",
        "attempts": 6,
        "shadow_count": 6,
        "responses": 2,
        "no_response": 4,
        "success_rate": 0.333
      }
    ]
  }
}
```

---

### GET /dashboard/recent-activity?limit=N

Returns the most recent N OutreachHistory rows. Default limit 20, max 100. Used to populate the Recent Activity card.

```json
{
  "status": "success",
  "data": {
    "items": [
      {
        "created_at": "ISO8601",
        "user_id": 1001,
        "checkpoint_type": "SQL",
        "channel": "CALL",
        "action": "CALL_SIMULATED",
        "execution_mode": "SHADOW",
        "state_before": "QUEUED",
        "state_after": "CONTACTED"
      }
    ]
  }
}
```

---

## 3.7 GHL Webhook Endpoint

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

| Code                 | Description                                        |
| -------------------- | -------------------------------------------------- |
| INVALID_INPUT        | Validation failed                                  |
| NOT_FOUND            | Resource not found                                 |
| DUPLICATE_REQUEST    | Duplicate operation                                |
| INTERNAL_ERROR       | Unexpected error                                   |
| STATE_VIOLATION      | Invalid state transition                           |
| MAX_ATTEMPTS_REACHED | FORCE_RETRY blocked — current_attempt ≥ MAX_ATTEMPTS |
| INVALID_ACTION       | Unknown action_type supplied to /actions/manual    |

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
