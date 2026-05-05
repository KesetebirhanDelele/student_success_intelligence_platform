# spec/08_data_model.md

---

## LAYER 2 — SPECIFICATIONS (DATA MODEL)

---

## 1. PURPOSE

This file defines:

* Database schema
* Table structures
* Relationships
* Constraints
* Indexing strategy

The goal is to ensure:

* Data consistency
* Query performance
* Clear ownership of data

---

## 2. DATABASE OVERVIEW

---

### Database Type

* SQL Server

---

### Data Sources

| Source                  | Ownership               |
| ----------------------- | ----------------------- |
| AI_ChatBot_TriggerData  | External (Read-Only)    |
| StudentOutreachTracking | Internal (System-Owned) |

---

## 3. CORE TABLES

---

## 3.1 AI_ChatBot_TriggerData (READ-ONLY)

---

### Description

Source table containing student academic and engagement data.

---

### Key Fields

| Field            | Type    | Description              |
| ---------------- | ------- | ------------------------ |
| UserID           | INT     | Primary identifier       |
| FirstName        | VARCHAR | Student first name       |
| LastName         | VARCHAR | Student last name        |
| Email            | VARCHAR | Email address            |
| PhoneNumber      | VARCHAR | Contact number           |
| PathName         | VARCHAR | Learning path            |
| HWsBehind        | INT     | Assignments behind       |
| AvgEffRating     | FLOAT   | Effort rating            |
| LastActivityDays | INT     | Days since last activity |

---

### Constraints

* Table is read-only
* Must not be modified by system

---

---

## 3.2 StudentOutreachTracking (PRIMARY SYSTEM TABLE)

---

### Description

Tracks all outreach activity, states, and outcomes.

---

### Schema

```plaintext id="r1k9dh"
OutreachID (PK)  
UserID (FK)  
CheckpointType  
State  
ContactDate  
ContactAttempt  
CallConnected  
CallDuration  
Transcript  
Sentiment  
MeetingBooked  
IPBCInterest  
CreatedAt  
UpdatedAt  
```

---

### Field Details

| Field          | Type     | Description             |
| -------------- | -------- | ----------------------- |
| OutreachID     | INT (PK) | Unique record ID        |
| UserID         | INT      | Student ID              |
| CheckpointType | VARCHAR  | Context of outreach     |
| State          | VARCHAR  | Current lifecycle state |
| ContactDate    | DATETIME | Last contact time       |
| ContactAttempt | INT      | Attempt count           |
| CallConnected  | BOOLEAN  | Call outcome            |
| CallDuration   | INT      | Duration in seconds     |
| Transcript     | TEXT     | Call transcript         |
| Sentiment      | VARCHAR  | LLM sentiment           |
| MeetingBooked  | BOOLEAN  | Meeting status          |
| IPBCInterest   | VARCHAR  | Interest level          |
| CreatedAt      | DATETIME | Record creation         |
| UpdatedAt      | DATETIME | Last update             |

---

---

## 4. RELATIONSHIPS

---

### Primary Relationship

```plaintext id="vl8u5r"
AI_ChatBot_TriggerData.UserID  
    ↓  
StudentOutreachTracking.UserID
```

---

### Rules

* One student can have multiple outreach records
* Each record tied to a checkpoint

---

---

## 5. UNIQUE CONSTRAINTS

---

### Prevent Duplicate Outreach

```plaintext id="7e9q2n"
UNIQUE (UserID, CheckpointType, ContactAttempt)
```

---

---

## 6. INDEXING STRATEGY

---

### Required Indexes

| Index          | Purpose            |
| -------------- | ------------------ |
| UserID         | Fast lookup        |
| State          | Filtering          |
| ContactDate    | Sorting            |
| CheckpointType | Query segmentation |

---

---

## 7. DATA TYPES & VALIDATION

---

### Rules

* UserID must be valid integer
* ContactAttempt ≥ 0
* State must be valid enum
* Sentiment must match allowed values

---

---

## 8. STATE FIELD ENUM

---

```plaintext id="3l2b9v"
ELIGIBLE  
QUEUED  
CONTACTED  
NO_RESPONSE  
RESPONDED  
ANALYZED  
INTERVENTION_REQUIRED  
MEETING_SCHEDULED  
RESOLVED  
CLOSED  
```

---

---

## 9. AUDIT FIELDS

---

Each record MUST include:

```plaintext id="x0k2p8"
CreatedAt  
UpdatedAt  
```

---

---

## 10. DATA CONSISTENCY RULES

---

* No null UserID
* No invalid states
* No duplicate attempts
* All updates must be timestamped

---

---

## 11. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Minimal fields required
* Limited tracking

---

---

### STANDARD

* Core fields enforced
* Partial indexing

---

---

### PRODUCTION

* Full schema enforced
* Full indexing
* Strict constraints
* Audit fields required

---

---

## 12. MIGRATION CONSIDERATIONS

---

* Schema changes must be backward compatible
* Additive changes preferred
* Avoid destructive changes

---

---

## 13. ACCEPTANCE CRITERIA

---

### Case 1 — Insert Record

**Given** outreach triggered
**When** record inserted
**Then** all required fields present

---

---

### Case 2 — Duplicate Prevention

**Given** same UserID + Checkpoint + Attempt
**When** insert attempted
**Then** rejected

---

---

### Case 3 — State Validity

**Given** invalid state
**When** insert/update attempted
**Then** rejected

---

---

## 14. REFERENCES

---

Depends on:

* spec/02_system_specifications.md
* state/system_state_model.md
* data/data_lifecycle.md
* meta/project_classification.md

---

## END OF FILE
