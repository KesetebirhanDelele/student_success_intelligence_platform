# environment/configuration.md

---

## LAYER 9 — ENVIRONMENT & CONFIGURATION

---

## 1. PURPOSE

This file defines:

* Environment structure
* Configuration variables
* Secrets management
* Feature flags
* Environment-specific behavior

The goal is to ensure:

* Secure configuration
* Consistent deployments
* Environment isolation

---

## 2. ENVIRONMENT DEFINITIONS

---

### 2.1 Development Environment

Purpose:

* Local development
* MVP implementation
* Rapid iteration

Characteristics:

* Debug logging enabled
* No strict rate limits
* Mock or sandbox integrations allowed

---

---

### 2.2 Staging Environment

Purpose:

* Pre-production validation
* STANDARD scope testing

Characteristics:

* Real integrations (GHL, LLM, Calendar)
* Controlled data
* Partial observability

---

---

### 2.3 Production Environment

Purpose:

* Live system execution

Characteristics:

* Full PRODUCTION scope
* Strict logging and monitoring
* Secure secrets management
* Rate limits enforced

---

---

## 3. CONFIGURATION CATEGORIES

---

### 3.1 Application Configuration

| Variable  | Description                    |
| --------- | ------------------------------ |
| APP_ENV   | Environment (dev/staging/prod) |
| APP_PORT  | Service port                   |
| LOG_LEVEL | Logging level                  |

---

---

### 3.2 Database Configuration

| Variable    | Description   |
| ----------- | ------------- |
| DB_HOST     | Database host |
| DB_PORT     | Database port |
| DB_NAME     | Database name |
| DB_USER     | Username      |
| DB_PASSWORD | Password      |

---

---

### 3.3 GHL Integration

| Variable        | Description         |
| --------------- | ------------------- |
| GHL_API_KEY     | API key             |
| GHL_BASE_URL    | API endpoint        |
| GHL_WORKFLOW_ID | Workflow trigger ID |

---

---

### 3.4 LLM Configuration

| Variable     | Description       |
| ------------ | ----------------- |
| LLM_PROVIDER | OpenAI / Claude   |
| LLM_API_KEY  | API key           |
| LLM_MODEL    | Model name        |
| LLM_TIMEOUT  | Timeout (seconds) |

---

---

### 3.5 Scheduler Configuration

| Variable             | Description                      |
| -------------------- | -------------------------------- |
| SCHEDULER_TIME       | Daily run time (e.g., 18:00 CST) |
| RETRY_INTERVAL_HOURS | Retry window                     |
| MAX_ATTEMPTS         | Max outreach attempts            |

---

---

### 3.6 Concurrency Configuration

| Variable                | Description             |
| ----------------------- | ----------------------- |
| MAX_CONCURRENT_OUTREACH | Max concurrent triggers |
| BATCH_SIZE              | Processing batch size   |

---

---

### 3.7 Calendar Integration

| Variable         | Description         |
| ---------------- | ------------------- |
| CALENDAR_API_KEY | API key             |
| CALENDAR_ID      | Calendar identifier |

---

---

## 4. FEATURE FLAGS

---

### Purpose

Enable/disable features without code changes

---

### Flags

| Flag                   | Description           |
| ---------------------- | --------------------- |
| ENABLE_LLM             | Enable LLM processing |
| ENABLE_RETRY           | Enable retry logic    |
| ENABLE_SMS             | Enable SMS fallback   |
| ENABLE_EMAIL           | Enable Email fallback |
| ENABLE_MEETING_BOOKING | Enable booking        |

---

---

## 5. SECRETS MANAGEMENT

---

### Rules

* Secrets MUST NOT be stored in code
* Use environment variables or secure vault
* Rotate keys periodically

---

### Storage Options

* .env file (dev only)
* Cloud secret manager (production)

---

---

## 6. ENVIRONMENT-SPECIFIC BEHAVIOR

---

### MVP

* Simplified configuration
* Limited environment separation
* Local-only setup

---

---

### STANDARD

* Separate dev + staging
* Basic secrets handling

---

---

### PRODUCTION

* Full environment separation
* Secure secret storage
* Strict configuration validation
* Fail-fast on missing config

---

---

## 7. VALIDATION RULES

---

At startup, system MUST:

1. Validate required variables exist
2. Validate values are within acceptable ranges
3. Fail if critical config missing

---

---

## 8. CONFIGURATION CONSTRAINTS

---

* No hardcoded values
* All critical values must be configurable
* Default values must be safe

---

---

## 9. ACCEPTANCE CRITERIA

---

### Case 1 — Missing Config

**Given** required variable missing
**When** system starts
**Then** startup fails

---

---

### Case 2 — Environment Isolation

**Given** staging environment
**When** system runs
**Then** production data is not accessed

---

---

### Case 3 — Feature Flag

**Given** ENABLE_RETRY = false
**When** system runs
**Then** retry logic disabled

---

---

## 10. REFERENCES

---

Depends on:

* runtime/system_loop.md
* directives/core_decision_engine.md
* failure/failure_playbook.md
* meta/project_classification.md

---

## END OF FILE
