# directives/llm_processing_contract.md

---

## LAYER 3 — DIRECTIVES (LLM PROCESSING CONTRACT)

---

## 1. PURPOSE

This directive defines:

* How LLMs are used in the system
* Input/output structure
* Validation rules
* Boundaries of LLM influence

The goal is to ensure:

* Safe and controlled use of AI
* Deterministic system behavior
* No uncontrolled decision-making by LLM

---

## 2. ROLE OF LLM

---

### LLM Responsibilities

* Analyze transcripts
* Extract structured insights
* Provide recommendations

---

### LLM MUST NOT:

* Make final decisions
* Override deterministic rules
* Trigger actions directly

---

## 3. INPUT CONTRACT

---

### Required Input

```json
{
  "transcript": "string",
  "student_context": {
    "hws_behind": number,
    "avg_eff_rating": number,
    "last_activity_days": number,
    "checkpoint_type": "string"
  }
}
```

---

### Constraints

* transcript MUST NOT be empty
* student_context must include required fields
* Input must be sanitized

---

---

## 4. OUTPUT CONTRACT

---

### Required Output Schema

```json
{
  "sentiment": "positive | neutral | negative | critical",
  "issues": ["string"],
  "meeting_recommended": boolean,
  "ipbc_interest_level": "Interested | Undecided | Not Interested | Wants Break"
}
```

---

### Field Rules

* sentiment must match enum
* issues must be list of strings
* meeting_recommended must be boolean
* ipbc_interest_level must match enum

---

---

## 5. VALIDATION RULES

---

### RULE 1 — STRUCTURE VALIDATION

* Output must match schema exactly
* Missing fields = invalid

---

---

### RULE 2 — TYPE VALIDATION

* Validate data types strictly
* Reject incorrect types

---

---

### RULE 3 — ENUM VALIDATION

* Reject values outside allowed enums

---

---

### RULE 4 — CONFIDENCE (OPTIONAL FUTURE)

* May include confidence score
* Not required for current version

---

---

## 6. PROCESSING FLOW

---

```plaintext
Receive Transcript
   ↓
Prepare Input
   ↓
Send to LLM
   ↓
Validate Output
   ↓
IF valid → store + pass to decision engine
IF invalid → retry or fallback
```

---

---

## 7. RETRY STRATEGY

---

### Retry Conditions

* Invalid JSON
* Missing fields
* Timeout

---

### Rules

* Retry once
* If still invalid:

  * Discard LLM output
  * Use rule-based logic

---

---

## 8. FAILURE HANDLING

---

### Invalid Output

* Ignore output
* Add reason code: "LLM_INVALID"

---

---

### No Response / Timeout

* Retry once
* If failure persists:

  * Skip LLM processing

---

---

### Malformed Transcript

* Skip LLM processing
* Log issue

---

---

## 9. SAFETY CONSTRAINTS

---

* LLM output MUST NOT trigger actions directly
* LLM output must pass through decision engine
* No free-form decisions allowed

---

---

## 10. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* LLM usage optional or disabled
* Minimal analysis (sentiment only or skipped)

---

---

### STANDARD

* Basic LLM processing
* Partial schema enforcement

---

---

### PRODUCTION

* Full schema enforcement
* Strict validation
* Retry + fallback handling
* Full integration with decision engine

---

---

## 11. INVARIANTS

---

* LLM output cannot override deterministic rules
* Invalid LLM output must not break system
* Same input should produce consistent structured output (within tolerance)

---

---

## 12. ACCEPTANCE CRITERIA

---

### Case 1 — Valid Output

**Given** valid transcript
**When** processed
**Then** structured output returned

---

---

### Case 2 — Invalid Output

**Given** malformed response
**When** validated
**Then** rejected and retried

---

---

### Case 3 — Failure Fallback

**Given** LLM fails twice
**When** processing continues
**Then** system uses rule-based logic

---

---

## 13. REFERENCES

---

Depends on:

* directives/core_decision_engine.md
* failure/failure_playbook.md
* runtime/system_loop.md
* meta/project_classification.md

---

## END OF FILE
