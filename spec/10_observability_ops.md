# spec/10_observability_ops.md

---

## LAYER 2 — SPECIFICATIONS (OBSERVABILITY & OPERATIONS)

---

## 1. PURPOSE

This file defines:

* Logging standards
* Monitoring requirements
* Alerting mechanisms
* Operational visibility

The goal is to ensure:

* Full system transparency
* Fast issue detection
* Reliable operations

---

## 2. OBSERVABILITY PRINCIPLES

---

### 2.1 Full Visibility

* All critical actions MUST be observable
* No silent failures

---

### 2.2 Structured Logging

* Logs MUST be structured (JSON format)
* Must support querying and filtering

---

### 2.3 Traceability

* Every action must be traceable across the system

---

### 2.4 Real-Time Awareness

* Critical failures must trigger alerts

---

## 3. LOGGING REQUIREMENTS

---

### 3.1 Log Types

| Type     | Description           |
| -------- | --------------------- |
| INFO     | Normal operations     |
| WARNING  | Non-critical issues   |
| ERROR    | Failures              |
| CRITICAL | System-level failures |

---

---

### 3.2 Required Log Fields

```plaintext
timestamp  
log_level  
service_name  
user_id  
checkpoint_type  
action_type  
state  
reason_codes  
message  
```

---

---

### 3.3 Logging Scope

Log all:

* Scheduler executions
* Outreach attempts
* Decision outputs
* State transitions
* Failures
* External API calls

---

---

## 4. MONITORING

---

### 4.1 Key Metrics

| Metric            | Description          |
| ----------------- | -------------------- |
| Scheduler Runs    | Successful vs failed |
| Outreach Attempts | Count per day        |
| Success Rate      | Contact success      |
| Retry Rate        | Retry frequency      |
| Failure Rate      | System failures      |
| API Latency       | Response times       |

---

---

### 4.2 System Health Indicators

* Scheduler active
* Database connectivity
* External API availability

---

---

## 5. ALERTING

---

### 5.1 Alert Triggers

* Scheduler failure
* High failure rate
* Repeated GHL failures
* LLM failures above threshold
* State violations

---

---

### 5.2 Alert Channels

* Email
* Dashboard notifications
* Logging system integration

---

---

## 6. TRACING

---

### Purpose

Track request flow across system components

---

### Requirements

* Assign unique trace_id per request
* Propagate trace_id across services

---

---

## 7. OPERATIONAL DASHBOARD

---

### Must Display

* System health
* Active processes
* Failure summaries
* Performance metrics

---

---

## 8. INCIDENT MANAGEMENT

---

### Steps

1. Detect issue (alert/log)
2. Investigate logs
3. Identify root cause
4. Apply fix or recovery
5. Log incident

---

---

## 9. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Basic logging
* Minimal monitoring
* No alerting

---

---

### STANDARD

* Structured logging
* Basic monitoring
* Limited alerts

---

---

### PRODUCTION

* Full observability
* Real-time monitoring
* Alerting system
* Traceability across services

---

---

## 10. PERFORMANCE MONITORING

---

### Targets

* API latency ≤ 500 ms
* Scheduler execution within defined window
* No backlog accumulation

---

---

## 11. LOG RETENTION

---

| Type             | Retention  |
| ---------------- | ---------- |
| Application logs | 30–90 days |
| Error logs       | 90 days    |
| Audit logs       | 12 months  |

---

---

## 12. ACCEPTANCE CRITERIA

---

### Case 1 — Logging

**Given** system action occurs
**When** executed
**Then** log is created

---

---

### Case 2 — Alerting

**Given** critical failure
**When** detected
**Then** alert triggered

---

---

### Case 3 — Monitoring

**Given** system running
**When** metrics queried
**Then** accurate data returned

---

---

## 13. REFERENCES

---

Depends on:

* failure/failure_playbook.md
* runtime/system_loop.md
* spec/07_api_contracts.md
* meta/project_classification.md

---

## END OF FILE
