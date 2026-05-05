# failure/llm_failures.md

---

## LAYER 8 — FAILURE HANDLING (LLM-SPECIFIC FAILURES)

---

## 1. PURPOSE

This file defines:

* All LLM-specific failure scenarios
* Detection mechanisms
* Recovery strategies
* Safe fallback behavior

This is a **specialized extension** of:

> failure/failure_playbook.md

---

## 2. FAILURE TYPES

---

### 2.1 Invalid Output Structure

Occurs when:

* Response is not valid JSON
* Required fields missing
* Incorrect schema format

---

---

### 2.2 Invalid Field Values

Occurs when:

* sentiment not in allowed enum
* meeting_recommended not boolean
* ipbc_interest_level invalid

---

---

### 2.3 Timeout / No Response

Occurs when:

* LLM does not respond within timeout window

---

---

### 2.4 Hallucinated / Irrelevant Output

Occurs when:

* Output unrelated to transcript
* Fabricated or nonsensical data

---

---

### 2.5 Partial Output

Occurs when:

* Some fields present but incomplete

---

---

## 3. DETECTION METHODS

---

### Structure Validation

* JSON parsing fails
* Missing required keys

---

---

### Schema Validation

* Type mismatch
* Enum mismatch

---

---

### Semantic Validation (Basic)

* Empty issues list when clearly issues exist
* Inconsistent sentiment vs transcript

---

---

### Timeout Detection

* No response within configured timeout

---

---

## 4. FAILURE HANDLING

---

### 4.1 Invalid Structure

---

#### Steps

1. Reject output
2. Retry LLM call (once)
3. If still invalid:

   * Discard output
   * Proceed without LLM

---

---

### 4.2 Invalid Field Values

---

#### Steps

1. Reject invalid fields
2. Retry LLM call (once)
3. If still invalid:

   * Discard output
   * Use fallback logic

---

---

### 4.3 Timeout / No Response

---

#### Steps

1. Retry once
2. If still no response:

   * Skip LLM processing
   * Continue system flow

---

---

### 4.4 Hallucinated Output

---

#### Steps

1. Detect anomaly (basic validation)
2. Discard output
3. Proceed with rule-based logic

---

---

### 4.5 Partial Output

---

#### Steps

1. Attempt to validate usable fields
2. If insufficient:

   * Treat as invalid
   * Retry or discard

---

---

## 5. RETRY STRATEGY

---

| Failure Type    | Retry              |
| --------------- | ------------------ |
| Invalid JSON    | 1 retry            |
| Schema mismatch | 1 retry            |
| Timeout         | 1 retry            |
| Hallucination   | No retry (discard) |

---

---

## 6. FALLBACK BEHAVIOR

---

### Rule

If LLM fails:

```plaintext
Use deterministic rule-based decision engine only
```

---

### State Impact

```plaintext
RESPONDED → INTERVENTION_REQUIRED (if needed)
```

Reason code:

```plaintext
LLM_FAILED
```

---

---

## 7. LOGGING REQUIREMENTS

---

Each failure MUST log:

```plaintext id="6mz9yx"
failure_type  
user_id  
checkpoint_type  
timestamp  
raw_output (if safe)  
validation_error  
recovery_action  
```

---

---

## 8. TIMEOUT CONFIGURATION

---

| Parameter   | Value        |
| ----------- | ------------ |
| LLM Timeout | 5–10 seconds |
| Retry Delay | Immediate    |

---

---

## 9. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* LLM disabled or optional
* No failure handling required

---

---

### STANDARD

* Basic validation
* Single retry

---

---

### PRODUCTION

* Full validation
* Strict schema enforcement
* Retry + fallback
* Logging + monitoring
* Integration with decision engine

---

---

## 10. ALERTING CONDITIONS (PRODUCTION)

---

Trigger alerts when:

* High LLM failure rate
* Repeated invalid outputs
* Timeout frequency exceeds threshold

---

---

## 11. INVARIANTS

---

* LLM failure must not block system flow
* LLM must not produce actions directly
* Invalid output must not enter system

---

---

## 12. ACCEPTANCE CRITERIA

---

### Case 1 — Invalid JSON

**Given** malformed response
**When** processed
**Then** retry executed

---

---

### Case 2 — Timeout

**Given** no response
**When** retry fails
**Then** fallback logic used

---

---

### Case 3 — Valid Output

**Given** correct response
**When** processed
**Then** stored and used

---

---

### Case 4 — Hallucination

**Given** irrelevant output
**When** detected
**Then** discarded

---

---

## 13. REFERENCES

---

Depends on:

* failure/failure_playbook.md
* directives/llm_processing_contract.md
* runtime/system_loop.md
* meta/project_classification.md

---

## END OF FILE
