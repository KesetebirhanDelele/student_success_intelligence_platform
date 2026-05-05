# meta/project_classification.md

---

## LAYER 1 — META (PROJECT CLASSIFICATION)

---

## 1. PURPOSE

This file defines:

* System scope (MVP / STANDARD / PRODUCTION)
* Feature gating across the entire system
* Behavioral constraints per scope
* Execution boundaries

This file is the **global control layer** for:

> What the system is allowed to do

---

## 2. CURRENT SYSTEM MODE

---

```plaintext
SYSTEM_SCOPE = PRODUCTION
```

---

## 3. SCOPE DEFINITIONS

---

### 3.1 MVP (Minimum Viable Product)

---

#### Purpose

* Fast validation
* Minimal working system

---

#### Characteristics

* Single outreach attempt
* No retry cycle
* No LLM dependency
* Minimal logging
* Basic dashboard

---

---

### 3.2 STANDARD

---

#### Purpose

* Stable functional system
* Intermediate capability

---

#### Characteristics

* Limited retry (1–2 attempts)
* Basic LLM integration
* Partial failure handling
* Structured logging
* Functional dashboard

---

---

### 3.3 PRODUCTION

---

#### Purpose

* Fully operational system
* Scalable and reliable

---

#### Characteristics

* Full retry cycle (multi-day)
* Full LLM integration
* Complete failure handling
* Observability + alerting
* Multi-channel outreach (CALL → SMS → EMAIL)
* Role-based access control
* Concurrency control

---

---

## 4. FEATURE GATING MATRIX

---

| Feature             | MVP        | STANDARD   | PRODUCTION |
| ------------------- | ---------- | ---------- | ---------- |
| Single Outreach     | ✅          | ✅          | ✅          |
| Retry Cycle         | ❌          | ⚠️ Limited | ✅ Full     |
| LLM Processing      | ❌          | ⚠️ Partial | ✅ Full     |
| Channel Fallback    | ❌          | ⚠️ Partial | ✅ Full     |
| Escalation Rules    | ❌          | ⚠️ Basic   | ✅ Full     |
| Failure Handling    | ❌          | ⚠️ Partial | ✅ Full     |
| Observability       | ❌          | ⚠️ Basic   | ✅ Full     |
| Dashboard           | ⚠️ Minimal | ✅ Standard | ✅ Advanced |
| RBAC                | ❌          | ⚠️ Basic   | ✅ Full     |
| Concurrency Control | ❌          | ⚠️ Basic   | ✅ Strict   |

---

## 5. GLOBAL RULES

---

### RULE 1 — SCOPE ENFORCEMENT

* All directives MUST respect SYSTEM_SCOPE
* Features not allowed in scope MUST NOT execute

---

---

### RULE 2 — DOWNGRADE SAFETY

* Higher-scope features must degrade safely in lower scopes
* No feature should break system when disabled

---

---

### RULE 3 — NO PARTIAL FEATURES

* Features must be fully enabled or fully disabled per scope
* No undefined behavior allowed

---

---

## 6. SYSTEM-WIDE PARAMETERS

---

### MAX_ATTEMPTS

| Scope      | Value |
| ---------- | ----- |
| MVP        | 1     |
| STANDARD   | 2     |
| PRODUCTION | 3     |

---

---

### RETRY_INTERVAL

| Scope      | Value    |
| ---------- | -------- |
| MVP        | N/A      |
| STANDARD   | 24 hours |
| PRODUCTION | 24 hours |

---

---

### CONCURRENCY_LIMIT

| Scope      | Value |
| ---------- | ----- |
| MVP        | 10    |
| STANDARD   | 25    |
| PRODUCTION | 50    |

---

---

## 7. FEATURE FLAGS (GLOBAL)

---

These flags must align with scope:

```plaintext
ENABLE_RETRY  
ENABLE_LLM  
ENABLE_CHANNEL_FALLBACK  
ENABLE_ESCALATION  
ENABLE_OBSERVABILITY  
```

---

### Enforcement Rule

* Flags MUST NOT contradict SYSTEM_SCOPE
* Example:

  * MVP → ENABLE_RETRY = false

---

---

## 8. EXECUTION CONTROL

---

### Rule

Every major system component MUST check:

```plaintext
IF feature_enabled(scope) THEN execute  
ELSE skip  
```

---

---

## 9. MIGRATION BETWEEN SCOPES

---

### Upgrade Path

```plaintext
MVP → STANDARD → PRODUCTION
```

---

### Rules

* Must validate system at each level
* Must not skip levels
* Must ensure compatibility

---

---

### Downgrade Path

* Must disable features safely
* Must not corrupt data
* Must preserve system integrity

---

---

## 10. INVARIANTS

---

* SYSTEM_SCOPE must be defined at all times
* All components must respect scope
* No feature may execute outside its scope

---

---

## 11. ACCEPTANCE CRITERIA

---

### Case 1 — Scope Enforcement

**Given** SYSTEM_SCOPE = MVP
**When** retry logic evaluated
**Then** retry must not execute

---

---

### Case 2 — Production Features

**Given** SYSTEM_SCOPE = PRODUCTION
**When** system runs
**Then** all features enabled

---

---

### Case 3 — Feature Consistency

**Given** feature disabled by scope
**When** system executes
**Then** feature not triggered

---

---

## 12. REFERENCES

---

This file governs ALL:

* directives/*
* runtime/*
* state/*
* failure/*
* execution/*
* ux/*
* spec/*

---

## END OF FILE
