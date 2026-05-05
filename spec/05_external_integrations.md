# spec/05_external_integrations.md

---

## LAYER 2 — SPECIFICATIONS (EXTERNAL INTEGRATIONS)

---

## 1. PURPOSE

This file defines:

* System-level guarantees for external integrations
* Reliability expectations (SLA, retries, timeouts)
* Dependency classification
* Integration boundaries

The goal is to ensure:

* Predictable behavior with external systems
* Controlled failure impact
* Clear separation between system logic and external dependencies

---

## 2. INTEGRATION OVERVIEW

---

### External Systems

| System                       | Role                | Criticality  |
| ---------------------------- | ------------------- | ------------ |
| GHL (GoHighLevel)            | Outreach execution  | CRITICAL     |
| LLM Provider (Claude/OpenAI) | Transcript analysis | NON-CRITICAL |
| Synthflow (optional)         | Orchestration layer | CONDITIONAL  |

---

---

## 3. DEPENDENCY CLASSIFICATION

---

### 3.1 Critical Dependencies

---

#### GHL

* Required for outreach execution
* System cannot perform core function without it

---

**Rules:**

* Must retry on failure
* Must detect missing responses
* Must not silently fail

---

---

### 3.2 Non-Critical Dependencies

---

#### LLM

* Enhances decision-making
* System must function without it

---

**Rules:**

* Failure must NOT block system
* Must fallback to deterministic logic

---

---

### 3.3 Conditional Dependencies

---

#### Synthflow (if used)

* Handles orchestration outside GHL
* Optional abstraction layer

---

**Rules:**

* Must not duplicate system logic
* Must not bypass core decision engine

---

---

## 4. SERVICE LEVEL EXPECTATIONS (SLA)

---

### GHL

| Metric            | Expectation                 |
| ----------------- | --------------------------- |
| API Response Time | ≤ 10 seconds                |
| Webhook Delivery  | ≤ 30 minutes                |
| Availability      | High (assumed external SLA) |

---

---

### LLM

| Metric          | Expectation       |
| --------------- | ----------------- |
| Response Time   | ≤ 5–10 seconds    |
| Output Validity | Must match schema |
| Availability    | Best-effort       |

---

---

## 5. TIMEOUT RULES

---

### GHL API

```plaintext id="8q7gxt"
Timeout = 10 seconds
```

---

---

### Webhook Expectation

```plaintext id="v2lz8p"
Expected within 5–30 minutes
```

---

---

### LLM Processing

```plaintext id="y3dc7r"
Timeout = 5–10 seconds
```

---

---

## 6. RETRY STRATEGY (SYSTEM LEVEL)

---

### GHL

* Immediate retry (1x)
* If failure persists → defer to retry cycle

---

---

### LLM

* Retry once on failure
* If still fails → skip and fallback

---

---

### Webhooks

* Retry processing if recoverable
* Ignore duplicates

---

---

## 7. FAILURE ISOLATION

---

### RULE 1 — ISOLATE FAILURES

* Failure in one integration must not break system

---

---

### RULE 2 — NO CASCADING FAILURES

* GHL failure must not trigger LLM failure
* LLM failure must not block outreach

---

---

### RULE 3 — SAFE FALLBACK

```plaintext id="v7t0ml"
If integration fails → continue with reduced capability
```

---

---

## 8. DATA CONTRACT GUARANTEES

---

### Outbound (to GHL)

* Must include required fields
* Must be validated before sending

---

---

### Inbound (from GHL)

* Must validate schema
* Must reject malformed payloads

---

---

### LLM Input/Output

* Must follow strict schema
* Must be validated before use

---

---

## 9. RATE LIMITING

---

### Rules

* Respect external API limits
* Queue requests when limit reached

---

---

### Behavior

```plaintext id="7x0vbo"
IF rate limit reached → delay + retry
```

---

---

## 10. VERSIONING (INTEGRATIONS)

---

### Rules

* Integration changes must be backward compatible
* Payload schema changes must be versioned

---

---

### Example

```plaintext id="k2d4n7"
v1 → current  
v2 → new fields added (non-breaking)
```

---

---

## 11. SECURITY REQUIREMENTS

---

* All external calls must use HTTPS
* API keys must be secured
* No sensitive data in logs

---

---

## 12. MONITORING REQUIREMENTS

---

Track:

* API success/failure rate
* Latency
* Timeout frequency
* Webhook delivery success

---

---

## 13. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Basic integration
* Minimal validation
* No strict SLA enforcement

---

---

### STANDARD

* Retry logic
* Basic monitoring
* Partial validation

---

---

### PRODUCTION

* Full SLA enforcement
* Retry + fallback
* Monitoring + alerting
* Rate limiting
* Strict validation

---

---

## 14. INVARIANTS

---

* External failures must not corrupt system state
* System must remain operational without non-critical dependencies
* All integration calls must be validated

---

---

## 15. ACCEPTANCE CRITERIA

---

### Case 1 — GHL Failure

**Given** API fails
**When** retry executed
**Then** system recovers or defers

---

---

### Case 2 — LLM Failure

**Given** LLM unavailable
**When** processing occurs
**Then** system continues without LLM

---

---

### Case 3 — Rate Limit

**Given** API limit reached
**When** requests sent
**Then** system queues and retries

---

---

### Case 4 — Invalid Payload

**Given** malformed response
**When** received
**Then** rejected and logged

---

---

## 16. REFERENCES

---

Depends on:

* directives/ghl_integration_contract.md
* directives/llm_processing_contract.md
* spec/04_idempotency_concurrency.md
* failure/ghl_failures.md
* failure/llm_failures.md
* meta/project_classification.md

---

## END OF FILE
