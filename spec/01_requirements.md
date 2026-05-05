# /spec/01_requirements.md

---

## LAYER 1 — REQUIREMENTS (INTENT)

---

## 1. SYSTEM PURPOSE

The **Student Success Multi-Agent Outreach System** is designed to:

* Identify students requiring intervention
* Trigger outreach via GHL (GoHighLevel)
* Analyze interaction outcomes using an LLM engine
* Apply deterministic decision rules
* Orchestrate interventions such as:

  * Follow-ups
  * Meeting booking
  * Resource delivery
  * IPBC conversion tracking

The system acts as the **central decision and orchestration layer**, while GHL executes communication workflows.

---

## 2. BUSINESS OBJECTIVES

---

### 2.1 Primary Objectives

1. Increase student engagement
2. Improve retention and completion rates
3. Detect academic risk early
4. Automate outreach at scale
5. Drive IPBC conversion
6. Provide full operational visibility

---

### 2.2 Success Metrics

* Outreach success rate ≥ 70%
* Meeting booking rate ≥ 20% of contacted students
* Reduction in inactive students ≥ 30%
* IPBC conversion measurable and attributable
* System uptime ≥ 99.5%

---

## 3. FUNCTIONAL REQUIREMENTS

---

### 3.1 Student Eligibility Detection

The system MUST:

* Retrieve student data from `AI_ChatBot_TriggerData`
* Identify eligible students based on:

  * Checkpoints (SQL, SSRS, SSIS/IPBC, Post-completion)
  * Academic metrics (HWsBehind, AvgEffRating, LastActivityDays)
* Exclude:

  * Students contacted within last 30 days (same checkpoint)
  * Students already enrolled in IPBC
  * Students without valid contact info

---

#### Scope Behavior

* **MVP:** Basic eligibility filters only
* **STANDARD:** Add checkpoint-specific thresholds
* **PRODUCTION:** Full rule set + priority scoring

---

#### Acceptance Criteria

* **Given** a student meets eligibility conditions
* **When** eligibility logic runs
* **Then** the student is included exactly once

---

### 3.2 Outreach Trigger (GHL Integration)

The system MUST:

* Update student contact in GHL
* Inject metadata:

  * UserID
  * CheckpointType
  * Academic metrics
  * Attempt number
* Trigger GHL workflow

---

#### Constraints

* System MUST NOT directly initiate calls
* GHL is the execution layer

---

#### Scope Behavior

* **MVP:** Single outreach trigger
* **STANDARD:** Trigger + retry attempts
* **PRODUCTION:** Full orchestration with fallback channels

---

#### Acceptance Criteria

* **Given** a student is eligible
* **When** outreach is triggered
* **Then** exactly one GHL workflow is initiated

---

### 3.3 Multi-Channel Communication

The system MUST support:

* Voice calls (primary via GHL)
* SMS fallback
* Email fallback

---

#### Scope Behavior

* **MVP:** Call only
* **STANDARD:** Call + SMS fallback
* **PRODUCTION:** Call → SMS → Email fallback sequence

---

---

### 3.4 LLM-Based Analysis

The system MUST:

* Process conversation transcripts
* Send data to LLM provider
* Enforce strict structured output

---

#### Required Output

* sentiment
* issues
* meeting_recommended
* ipbc_interest_level

---

#### Scope Behavior

* **MVP:** Basic sentiment only
* **STANDARD:** Sentiment + issues
* **PRODUCTION:** Full structured output + validation

---

#### Acceptance Criteria

* **Given** a transcript exists
* **When** analyzed
* **Then** valid structured output is stored

---

### 3.5 Decision Engine

The system MUST:

* Combine:

  * Academic metrics
  * LLM output
* Apply deterministic rules
* Override LLM when necessary

---

#### Scope Behavior

* **MVP:** Simplified rules
* **STANDARD:** Full rules without overrides
* **PRODUCTION:** Full rules + override logic

---

#### Acceptance Criteria

* **Given** conflicting data
* **When** evaluated
* **Then** deterministic rules prevail

---

### 3.6 Retry Logic

The system MUST:

* Track outreach attempts
* Retry when no response

---

#### Scope Behavior

* **MVP:** No retry
* **STANDARD:** 1–2 retries
* **PRODUCTION:** 3-day retry cycle

---

#### Acceptance Criteria

* **Given** no response
* **When** retry conditions met
* **Then** next attempt is scheduled

---

### 3.7 Meeting Booking

The system MUST:

* Integrate with Google Calendar
* Book meetings when criteria met

---

#### Scope Behavior

* **MVP:** Manual or disabled
* **STANDARD:** Basic booking
* **PRODUCTION:** Automated booking + confirmation

---

#### Acceptance Criteria

* **Given** meeting required
* **When** booking triggered
* **Then** calendar event is created

---

### 3.8 Transcript Storage

The system MUST:

* Store transcripts in database
* Associate with outreach record

---

#### Scope Behavior

* **MVP:** Store minimal transcript
* **STANDARD:** Store full transcript
* **PRODUCTION:** Store + index + analyze

---

---

### 3.9 Dashboard Support

The system MUST expose APIs for:

* Student history
* Outreach logs
* Metrics
* Sentiment trends

---

#### Scope Behavior

* **MVP:** Minimal endpoints
* **STANDARD:** Core dashboards
* **PRODUCTION:** Full analytics

---

---

## 4. NON-FUNCTIONAL REQUIREMENTS

---

### 4.1 Performance

* Eligibility processing ≤ 5 seconds (500 students)
* API latency ≤ 500 ms (p95)
* LLM response ≤ 5 seconds

---

### 4.2 Scalability

* Initial: 100–500 students/day
* Target: 2000+ students/day

---

### 4.3 Reliability

* Uptime ≥ 99.5%
* No missed scheduler runs
* Idempotent operations required

---

### 4.4 Concurrency

* Max 50 concurrent outreach triggers
* No duplicate outreach

---

### 4.5 Observability

System MUST log:

* Scheduler runs
* Outreach attempts
* LLM outputs
* Failures

---

### 4.6 Security

* No secrets in code
* Secure API communication
* Data protection enforced

---

## 5. ASSUMPTIONS

---

ASSUMPTION: GHL handles all outreach execution
Alternative: Backend-controlled communication layer

ASSUMPTION: LLM provider returns structured output
Alternative: Implement validation and retry

ASSUMPTION: Transcript is available post-call
Alternative: Handle missing transcript

---

## 6. CONSTRAINTS

---

* Must be local-first
* Must be Azure-ready
* Must use SQL Server
* Must not modify source table
* Must enforce deterministic logic

---

## 7. EDGE CASES

---

* Missing contact information
* GHL trigger failure
* Transcript missing
* LLM invalid response
* Duplicate scheduler execution
* Student becomes ineligible mid-cycle

---

## 8. SUCCESS CRITERIA

---

System is successful when:

* Outreach runs daily without failure
* No duplicate outreach occurs
* Decisions are deterministic
* Meetings are booked correctly
* Dashboard reflects accurate data

---

## END OF FILE
