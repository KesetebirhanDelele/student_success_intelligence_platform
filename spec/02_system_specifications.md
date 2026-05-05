# spec/02_system_specifications.md

---

## LAYER 2 — SPECIFICATIONS (STRUCTURE)

---

## 1. SYSTEM ARCHITECTURE OVERVIEW

The system is a **centralized backend orchestration platform** with external execution handled by GHL.

### Core Flow

Scheduler → Eligibility Engine → Decision Engine → GHL Trigger → GHL Execution → Data Sync → LLM Processing → Decision Update → Database → Dashboard API

---

## 2. ARCHITECTURAL COMPONENTS

---

### 2.1 Backend Service (FastAPI)

Responsibilities:

* API routing
* Business logic orchestration
* Decision execution
* Scheduler control
* Integration with external systems
* Observability and logging

---

### 2.2 Scheduler Layer

Responsibilities:

* Daily execution (6:00 PM CST)
* Retry scheduling
* Follow-up scheduling
* Idempotency enforcement

---

### 2.3 Service Layer

Core services:

* Eligibility Service
* Outreach Service
* Decision Engine
* LLM Processing Service
* Meeting Service
* GHL Integration Service
* Analytics Service

---

### 2.4 Database Layer (SQL Server)

Tables:

* AI_ChatBot_TriggerData (read-only)
* StudentOutreachTracking (system-owned)

---

### 2.5 External Systems

* GHL (GoHighLevel) → Outreach execution
* LLM Provider (OpenAI / Claude) → Analysis
* Google Calendar → Scheduling

---

### 2.6 Frontend (React Dashboard)

* Consumes backend APIs
* Displays analytics and operational data

---

## 3. MODULE SPECIFICATIONS

---

### 3.1 Eligibility Service

Inputs:

* Student dataset from database

Outputs:

* Eligible student list

Responsibilities:

* Apply checkpoint filters
* Enforce 30-day exclusion rule
* Validate contact data

---

#### Scope Behavior

* MVP: Basic filtering
* STANDARD: Add threshold-based filtering
* PRODUCTION: Full rule set + prioritization

---

---

### 3.2 Outreach Service

Inputs:

* Eligible student list

Outputs:

* GHL trigger execution

Responsibilities:

* Create outreach record
* Track attempts
* Ensure idempotency

---

#### Scope Behavior

* MVP: Single attempt
* STANDARD: Retry attempts
* PRODUCTION: Full retry + channel orchestration

---

---

### 3.3 GHL Integration Service

Responsibilities:

* Update contact records
* Inject metadata
* Trigger workflows

---

#### Payload Structure

```json
{
  "user_id": 123,
  "checkpoint_type": "SQL",
  "hws_behind": 2,
  "avg_eff_rating": 3.5,
  "last_activity_days": 5,
  "attempt": 1
}
```

---

#### Scope Behavior

* MVP: Basic payload
* STANDARD: Add attempt tracking
* PRODUCTION: Full metadata + validation

---

---

### 3.4 LLM Processing Service

Responsibilities:

* Send transcript to LLM
* Validate structured response
* Retry if invalid

---

#### Input Schema

```json
{
  "transcript": "string",
  "student_context": {
    "hws_behind": number,
    "avg_eff_rating": number,
    "last_activity_days": number
  }
}
```

---

#### Output Schema

```json
{
  "sentiment": "positive | neutral | negative | critical",
  "issues": ["string"],
  "meeting_recommended": boolean,
  "ipbc_interest_level": "Interested | Undecided | Not Interested | Wants Break"
}
```

---

#### Scope Behavior

* MVP: Sentiment only
* STANDARD: Partial schema
* PRODUCTION: Full schema + validation

---

---

### 3.5 Decision Engine

Responsibilities:

* Combine LLM output + metrics
* Apply deterministic rules
* Produce final decisions

---

#### Output Example

```json
{
  "final_sentiment": "negative",
  "meeting_required": true,
  "restart_recommended": false,
  "ipbc_interest": "Undecided"
}
```

---

#### Scope Behavior

* MVP: Simplified logic
* STANDARD: Full logic
* PRODUCTION: Full logic + overrides

---

---

### 3.6 Meeting Service

Responsibilities:

* Check availability
* Book meetings
* Store booking details

---

#### Scope Behavior

* MVP: Disabled/manual
* STANDARD: Basic booking
* PRODUCTION: Automated booking + confirmation

---

---

### 3.7 Analytics Service

Responsibilities:

* Compute KPIs
* Provide dashboard data

Metrics:

* Call success rate
* Meeting conversion rate
* Sentiment distribution

---

#### Scope Behavior

* MVP: Minimal metrics
* STANDARD: Core metrics
* PRODUCTION: Full analytics

---

---

## 4. API SPECIFICATIONS

---

### 4.1 Health Check

GET /health

Response:

```json
{
  "status": "healthy",
  "scheduler_running": true
}
```

---

### 4.2 Trigger Outreach

POST /outreach/trigger

Request:

```json
{
  "checkpoint_type": "SQL"
}
```

---

### 4.3 Student History

GET /students/{user_id}

---

### 4.4 Metrics

GET /metrics

---

### 4.5 GHL Webhook (Optional)

POST /webhook/ghl-update

---

## 5. DATA MODEL OVERVIEW

---

### 5.1 AI_ChatBot_TriggerData (Read-Only)

Key Fields:

* UserID
* FirstName
* LastName
* Email
* PhoneNumber
* PathName
* HWsBehind
* AvgEffRating
* LastActivityDays

---

---

### 5.2 StudentOutreachTracking

Fields:

* OutreachID (PK)
* UserID
* CheckpointType
* ContactDate
* ContactAttempt
* CallConnected
* CallDuration
* Transcript
* Sentiment
* MeetingBooked
* IPBCInterest

---

---

## 6. CONCURRENCY & RATE CONTROL

---

* Max 50 concurrent outreach triggers
* Batch processing required
* Prevent duplicate triggers

---

#### Scope Behavior

* MVP: Basic batching
* STANDARD: Controlled batching
* PRODUCTION: Full concurrency control

---

---

## 7. AUTHENTICATION

---

### Current

* Simple login

---

### Future

* Role-based access

---

---

## 8. CONFIGURATION

---

* Environment variables
* Secrets management
* No hardcoded values

---

---

## 9. SYSTEM BOUNDARIES

---

### Internal

* Decision engine
* Scheduler
* Data storage

---

### External

* GHL
* LLM provider
* Google Calendar

---

## 10. ASSUMPTIONS

---

ASSUMPTION: GHL workflows trigger reliably
Alternative: Add verification

ASSUMPTION: LLM returns structured output
Alternative: Add repair logic

---

## END OF FILE
