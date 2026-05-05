# spec/11_runbook.md

---

## LAYER 2 — SPECIFICATIONS (RUNBOOK)

---

## 1. PURPOSE

This runbook defines:

* Operational procedures
* Standard response actions
* System startup and shutdown processes
* Troubleshooting steps

The goal is to ensure:

* Reliable day-to-day operations
* Fast issue resolution
* Consistent handling of incidents

---

## 2. SYSTEM STARTUP

---

### Steps

1. Verify environment configuration loaded
2. Confirm database connectivity
3. Validate required environment variables
4. Start backend service
5. Start scheduler
6. Verify health endpoint

---

### Validation Checklist

* /health returns success
* Scheduler status = active
* No critical errors in logs

---

---

## 3. SYSTEM SHUTDOWN

---

### Steps

1. Stop scheduler
2. Allow in-progress jobs to complete
3. Stop backend service
4. Ensure no partial writes

---

### Constraints

* Do not terminate active transactions abruptly
* Ensure data integrity before shutdown

---

---

## 4. DAILY OPERATIONS

---

### 4.1 Verify Scheduler Execution

* Confirm 6 PM run completed
* Check logs for errors
* Validate outreach triggered

---

---

### 4.2 Monitor System Health

* Review dashboard metrics
* Check failure panel
* Validate API responsiveness

---

---

### 4.3 Validate Data Flow

* Confirm outreach records created
* Confirm state transitions
* Verify no duplicate entries

---

---

## 5. INCIDENT RESPONSE

---

### 5.1 GHL Failure

---

**Steps:**

1. Check API response logs
2. Retry failed outreach
3. Verify GHL workflow status
4. Escalate if persistent

---

---

### 5.2 LLM Failure

---

**Steps:**

1. Check LLM response logs
2. Validate API connectivity
3. Retry processing
4. Confirm fallback logic executed

---

---

### 5.3 Scheduler Failure

---

**Steps:**

1. Check scheduler logs
2. Identify missed execution
3. Trigger manual run
4. Verify recovery

---

---

### 5.4 State Inconsistency

---

**Steps:**

1. Identify invalid state transition
2. Review logs
3. Correct state manually (if required)
4. Log correction

---

---

## 6. MANUAL OPERATIONS

---

### 6.1 Trigger Manual Outreach

* Use API endpoint: POST /outreach/trigger
* Confirm execution in logs

---

---

### 6.2 Retry Failed Outreach

* Identify failed record
* Trigger retry via API
* Validate state update

---

---

### 6.3 Close Case

* Validate case state
* Use manual action endpoint
* Provide reason

---

---

## 7. TROUBLESHOOTING GUIDE

---

### Issue: No Outreach Triggered

* Check eligibility logic
* Verify scheduler ran
* Confirm GHL integration

---

---

### Issue: Duplicate Outreach

* Check idempotency keys
* Verify state transitions
* Inspect logs

---

---

### Issue: Missing Transcript

* Check GHL webhook
* Verify transcript ingestion
* Retry processing

---

---

### Issue: High Failure Rate

* Check external systems
* Review logs
* Validate configurations

---

---

## 8. BACKUP & RECOVERY

---

### Backup

* Database backups daily
* Logs retained per policy

---

---

### Recovery

1. Restore database from backup
2. Validate data integrity
3. Resume system

---

---

## 9. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Manual monitoring
* Limited procedures

---

---

### STANDARD

* Defined procedures
* Partial automation

---

---

### PRODUCTION

* Full operational procedures
* Automated monitoring
* Incident management protocols

---

---

## 10. ACCEPTANCE CRITERIA

---

### Case 1 — Startup

**Given** system started
**When** initialization completes
**Then** all services running

---

---

### Case 2 — Incident Handling

**Given** failure occurs
**When** runbook followed
**Then** issue resolved

---

---

### Case 3 — Daily Operations

**Given** daily run
**When** completed
**Then** system operates correctly

---

---

## 11. REFERENCES

---

Depends on:

* spec/10_observability_ops.md
* failure/failure_playbook.md
* runtime/system_loop.md
* meta/project_classification.md

---

## END OF FILE
