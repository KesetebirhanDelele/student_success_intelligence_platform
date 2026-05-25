# /spec/01_requirements.md

---

## LAYER 1 — REQUIREMENTS (INTENT)

---

## 1. SYSTEM PURPOSE

The **Student Success Intelligence Platform (SSIP)** is designed to:

* Identify students requiring intervention
* Trigger outreach via GHL (GoHighLevel)
* Analyze interaction outcomes using an LLM engine
* Apply deterministic decision rules
* Orchestrate interventions such as:

  * Follow-ups
  * Meeting booking
  * Resource delivery
  * IPBC conversion tracking

* Maintain an immutable historical record of every student's academic, financial, and engagement state over time
* Generate enterprise monthly reports and on-demand historical analyses
* Surface AI-generated insights and intervention recommendations to operators and mentors
* Support longitudinal analytics across student cohorts (IPBC, CAP, Launch, Placement)

The system acts as the **central decision, orchestration, and intelligence layer**, while GHL executes communication workflows. SQL Server is the authoritative source of student academic and operational data; PostgreSQL is the system-owned intelligence database.

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
7. Deliver monthly enterprise reports for each enrolled student cohort
8. Maintain append-only historical records enabling point-in-time reconstruction of any student's state
9. Surface placement readiness signals to reduce time-to-hire
10. Enable mentor and operator access to actionable intelligence without requiring database access
11. Augment operator decision-making with AI-generated risk summaries and intervention recommendations

---

### 2.2 Success Metrics

* Outreach success rate ≥ 70%
* Meeting booking rate ≥ 20% of contacted students
* Reduction in inactive students ≥ 30%
* IPBC conversion measurable and attributable
* System uptime ≥ 99.5%
* Monthly reports generated automatically by the 1st of each month with zero manual intervention
* Historical report regeneration for any prior month completes in ≤ 60 seconds
* AI insight generation latency ≤ 10 seconds per student
* Payment reconciliation discrepancy rate ≤ 0.1%

---

### 2.3 Operational Domains

The platform recognizes and tracks the following student program cohorts. Each cohort has distinct eligibility rules, intervention triggers, and reporting requirements.

| Domain | Description | Primary Risk Signal |
|---|---|---|
| **IPBC Enrollment** | Students enrolled in the Income-Based Payment Contract program | Payment balance deviations, attendance gaps |
| **Coursework Engagement** | Students actively progressing through curriculum modules | HWsBehind, AvgEffRating, LastActivityDays |
| **Homework Risk** | Students with ≥ 1 overdue assignment or falling EffRating | HWsBehind ≥ 1, AvgEffRating < 3.0 |
| **CAP Hopefuls** | Students identified as candidates for the CAP program | Academic performance thresholds, mentor flags |
| **Launch Hopefuls** | Students in late curriculum, ready for job launch preparation | Section completion percentage, mentor assessment |
| **Placement Hopefuls** | Students actively in job search or interview pipeline | Interview prep completion, portfolio status |
| **Payment Tracking** | Students with outstanding balances or payment plan deviations | PaymentBalance, ClassFeesPaid, bundle deal status |
| **Access History** | Students whose platform access has been revoked or restored | Access state transitions, trigger events |

---

## 3. FUNCTIONAL REQUIREMENTS

---

### 3.1 Student Eligibility Detection

The system MUST:

* Retrieve student data from `AI_ChatBot_TriggerData` (SQL Server — read-only)
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

#### Required Output — Conversational Analysis

* sentiment
* issues
* meeting_recommended
* ipbc_interest_level

---

#### Required Output — Student Risk Summarization

* risk_level (HIGH / MEDIUM / LOW)
* primary_risk_factors (list)
* recommended_action
* confidence_score

---

#### Required Output — Progress Summarization

* weeks_in_program
* estimated_completion_date
* completion_trajectory (ON_TRACK / AT_RISK / OFF_TRACK)
* key_accomplishments (list)

---

#### Required Output — Monthly Narrative

* executive_summary (plain text, ≤ 200 words)
* cohort_highlights (list)
* intervention_summary (list)
* placement_pipeline_status

---

#### Scope Behavior

* **MVP:** Basic sentiment only
* **STANDARD:** Sentiment + issues + risk summarization
* **PRODUCTION:** Full structured output + validation + progress + monthly narrative

---

#### Acceptance Criteria

* **Given** a transcript exists
* **When** analyzed
* **Then** valid structured output is stored

* **Given** a student record exists
* **When** risk summarization is requested
* **Then** a deterministic risk summary is returned with no PII in the LLM prompt

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

* Student history and outreach logs
* Academic metrics and sentiment trends
* Payment reconciliation and balance tracking
* Lifecycle status and cohort membership
* Placement readiness indicators
* Campaign activity and GHL communication history
* AI-generated insights per student
* Operator and mentor operational views (filtered by role)

---

#### Dashboard Tabs

| Tab | Primary Audience | Data Source |
|---|---|---|
| Overview | Operator | Operational DB + AI insights |
| Lifecycle | Operator / Mentor | SQL Server mirror + transitions |
| Coursework | Mentor | SQL Server mirror |
| Payments | Operator | SQL Server mirror |
| Placement | Mentor / Operator | SQL Server mirror + placement flags |
| Communication | Operator | GHL messages + campaign activity |
| History | Operator | Append-only snapshot store |
| AI Insights | Operator / Mentor | AI insights table |

---

#### Scope Behavior

* **MVP:** Minimal endpoints
* **STANDARD:** Core dashboards (overview, lifecycle, coursework)
* **PRODUCTION:** Full analytics (all tabs + historical + AI)

---

---

### 3.10 Data Architecture & Source System Separation

The system MUST enforce a strict boundary between source systems and the intelligence database.

#### Source System: SQL Server (READ-ONLY)

* SQL Server is the authoritative source for all student academic and operational data
* The system MUST NOT write to SQL Server under any circumstances
* Data is read via the `AI_ChatBot_TriggerData` view and any additional approved read-only views
* SQL Server data is mirrored into PostgreSQL on a scheduled sync cycle
* Schema drift between SQL Server and the mirror table is detected and logged; the system does not fail silently on schema mismatch

#### Intelligence Database: PostgreSQL (READ-WRITE)

* PostgreSQL is the system-owned database for all operational intelligence, outreach state, AI insights, and reporting data
* All writes originate from the platform; no external system writes directly to PostgreSQL
* Operational tables and reporting (snapshot) tables occupy separate schemas
* Operational schema: live outreach state, GHL messages, campaign activity, student notes
* Reporting schema (warehouse): append-only snapshots, never updated in-place

---

#### Acceptance Criteria

* **Given** a sync job runs
* **When** SQL Server is unreachable
* **Then** the platform continues serving cached data and logs a CRITICAL alert; no writes to SQL Server are attempted

* **Given** a schema mismatch is detected between SQL Server columns and the mirror model
* **When** the sync job executes
* **Then** the mismatch is logged, the affected columns are skipped, and partial sync completes for intact columns

---

#### Scope Behavior

* **MVP:** Single-schema PostgreSQL, SQL Server read via sync job
* **STANDARD:** Schema separation (operational vs. warehouse); sync validation
* **PRODUCTION:** Full schema isolation, mismatch alerting, incremental sync with change detection

---

### 3.11 Student Lifecycle Intelligence

The system MUST:

* Track and surface the following lifecycle states for every student:

  * Active / Inactive / Paused / Dropped / Graduated / Placed
* Record all lifecycle state transitions with timestamp, trigger, and actor
* Expose lifecycle history as an ordered timeline per student
* Derive lifecycle velocity metrics: days in current state, days since last transition

---

#### Required Fields (sourced from SQL Server mirror)

* `ActiveStatus` — current enrollment status string
* `StatusI`, `StatusII` — secondary status flags
* `StudentStartDate`, `ClassStartDate`, `IPBCStartDate`
* `ClassName`, `ClassSignupsID`
* `LastActivitySection`, `LastLoginDays`

---

#### Scope Behavior

* **MVP:** Current status display only
* **STANDARD:** Status history + transition log
* **PRODUCTION:** Full timeline + velocity metrics + AI lifecycle summary

---

#### Acceptance Criteria

* **Given** a student's ActiveStatus changes in SQL Server
* **When** the sync job runs
* **Then** a lifecycle transition event is recorded with the prior and new state

---

### 3.12 Coursework Engagement Intelligence

The system MUST:

* Track homework submission pace against expected curriculum velocity
* Flag students whose HWsBehind exceeds configurable thresholds
* Track AvgEffRating trends over time (not just current snapshot)
* Surface last submitted assignment with days-since metric
* Surface current section and estimated section completion percentage

---

#### Homework Risk Classification

| Classification | Condition |
|---|---|
| AT_RISK | HWsBehind ≥ 1 OR AvgEffRating < 3.0 |
| CRITICAL | HWsBehind ≥ 3 OR AvgEffRating < 2.0 |
| ON_TRACK | HWsBehind = 0 AND AvgEffRating ≥ 3.0 |

---

#### Scope Behavior

* **MVP:** HWsBehind + AvgEffRating display
* **STANDARD:** Trend tracking + risk classification
* **PRODUCTION:** Trend + classification + AI engagement summary + proactive alerting

---

#### Acceptance Criteria

* **Given** a student has HWsBehind ≥ 3
* **When** the eligibility engine runs
* **Then** the student is classified CRITICAL and included in the next outreach cycle

---

### 3.13 Financial & Payment Intelligence

The system MUST:

* Reconcile payment data sourced from SQL Server against expected class fee schedules
* Detect and correctly handle bundle deal payment structures where `PaymentBalance = 0` but credits exist
* Classify each student's payment risk (CLEAR / MEDIUM / HIGH)
* Surface payment history including total payments, credits, class value, and computed actual balance
* Flag students whose actual balance deviates from the stored `PaymentBalance` by more than a configurable threshold

---

#### Payment Risk Classification

| Classification | Condition |
|---|---|
| CLEAR | Actual balance ≤ 0 |
| MEDIUM | 0 < Actual balance ≤ $1,000 |
| HIGH | Actual balance > $1,000 |

---

#### Bundle Deal Detection

* A bundle deal is detected when: `Total_Credits > 0 AND PaymentBalance = 0 AND ClassValue > 0`
* In this case, actual balance = `ClassValue − Total_Payments − Total_Credits`

---

#### Scope Behavior

* **MVP:** Balance display only
* **STANDARD:** Risk classification + bundle detection
* **PRODUCTION:** Full reconciliation + deviation alerting + IPBC linkage

---

#### Acceptance Criteria

* **Given** a student has bundle deal indicators
* **When** payment reconciliation runs
* **Then** the system computes the correct actual balance, not the stored `PaymentBalance`

* **Given** a student's actual balance > $1,000
* **When** the payment intelligence endpoint is queried
* **Then** the student is classified HIGH risk

---

### 3.14 Placement Readiness Intelligence

The system MUST:

* Track placement readiness indicators per student:

  * Interview prep completion status
  * Portfolio / GitHub activity flag
  * Resume submission status
  * Placement hopeful flag
  * Launch hopeful flag
* Surface a composite placement readiness score
* Track time-in-placement-pipeline from first placement flag to job offer
* Alert when a placement hopeful has been inactive for ≥ 7 days

---

#### Scope Behavior

* **MVP:** Placement flag display only
* **STANDARD:** Composite readiness score + pipeline tracking
* **PRODUCTION:** Full placement intelligence + AI readiness assessment + operator alerts

---

#### Acceptance Criteria

* **Given** a student is flagged as a placement hopeful
* **When** placement intelligence is queried
* **Then** a composite readiness score is returned based on available indicators

---

### 3.15 Operational Access-History Intelligence

The system MUST:

* Record every access revocation and restoration event with:

  * Timestamp
  * Trigger event (manual, automated, payment failure, graduation)
  * Actor (operator username or system)
  * Prior state and new state
* Surface a chronological access history per student
* Alert operators when a student's access is revoked for > 48 hours without restoration or explicit closure

---

#### Scope Behavior

* **MVP:** Current access status display
* **STANDARD:** Access event log + timeline
* **PRODUCTION:** Full history + alerting + AI access pattern analysis

---

#### Acceptance Criteria

* **Given** a student's access is revoked
* **When** the access history endpoint is queried
* **Then** the event appears with timestamp, trigger, and actor

---

### 3.16 Unified Communication Telemetry

The system MUST:

* Maintain a unified communication record per student that aggregates:

  * Outreach history (platform-initiated via GHL)
  * GHL inbound/outbound messages (synced from GHL API)
  * Campaign activity log (email/SMS campaigns)
  * Manual operator notes flagged as communication
* Surface a chronological communication timeline per student
* Surface aggregated channel statistics: total contacts, response rate, last contact date, days since last contact

---

#### Communication Record Fields

| Field | Source |
|---|---|
| direction | INBOUND / OUTBOUND |
| channel | CALL / SMS / EMAIL / CAMPAIGN |
| body / subject | Message content |
| status | DELIVERED / FAILED / NO_RESPONSE |
| activity_date | Event timestamp |
| source | platform / ghl / campaign / operator |

---

#### Scope Behavior

* **MVP:** Platform-initiated outreach only
* **STANDARD:** Platform + GHL message sync
* **PRODUCTION:** Full unified timeline + channel analytics + AI communication summary

---

#### Acceptance Criteria

* **Given** a GHL message is received for a known student
* **When** the communication timeline endpoint is queried
* **Then** the message appears in chronological order with the correct channel and direction

---

### 3.17 AI-Generated Student Insights

The system MUST:

* Generate and store AI insights per student covering:

  * Risk summary (academic, financial, engagement)
  * Progress summary (curriculum velocity, estimated completion)
  * Intervention recommendation (specific next action with rationale)
  * Communication sentiment summary (aggregated from recent interactions)
* Cache insights with a configurable TTL (default: 24 hours)
* Allow on-demand refresh of any insight type
* Store insight generation metadata: model used, generated_at, expires_at

---

#### Insight Types

| Type | Trigger | Consumer |
|---|---|---|
| `risk_summary` | Daily or on-demand | Operator, Mentor |
| `progress_summary` | Daily or on-demand | Mentor |
| `intervention_recommendation` | Post-outreach + daily | Operator |
| `communication_sentiment` | Post-GHL sync | Operator |
| `monthly_narrative` | Month-end scheduler | Admin |

---

#### Constraints

* AI insight prompts MUST NOT include PII beyond student ID and program context
* AI insight generation MUST be idempotent for the same (student_id, insight_type, date) tuple
* Cached insights are served until TTL; the requester can force refresh via an explicit parameter

---

#### Scope Behavior

* **MVP:** No AI insights
* **STANDARD:** Risk summary + intervention recommendation
* **PRODUCTION:** Full insight suite + monthly narrative + sentiment analysis

---

#### Acceptance Criteria

* **Given** an insight request for a student
* **When** a cached insight exists within TTL
* **Then** the cached insight is returned without calling the LLM provider

* **Given** an insight request with `force_refresh=true`
* **When** a cached insight exists
* **Then** a new insight is generated, stored, and returned; the prior insight is retained in history

---

### 3.18 Monthly Snapshot & Enterprise Reporting

The system MUST:

* Take an immutable monthly snapshot of every active student's full state on a scheduled month-end trigger
* Each snapshot MUST include:

  * Lifecycle state at snapshot time
  * Academic engagement metrics (HWsBehind, AvgEffRating, LastActivityDays, CurrentSection)
  * Financial state (actual balance, payment risk, class fees paid)
  * Outreach summary (attempts, responses, last contact date)
  * Placement readiness indicators
  * AI-generated monthly narrative
* Snapshots are append-only: no existing snapshot row is updated or deleted after creation
* Snapshots are keyed by `(student_id, snapshot_month)` — exactly one snapshot per student per month

---

#### Report Generation

The system MUST generate enterprise monthly reports that:

* Cover all students active in the snapshot month
* Segment students by cohort (IPBC, CAP, Launch, Placement)
* Surface aggregate statistics: engagement rate, payment compliance rate, placement pipeline count
* Include a system-generated AI narrative summarizing cohort health
* Are available as a structured API response and as a PDF-renderable JSON payload

---

#### Scope Behavior

* **MVP:** No snapshots
* **STANDARD:** Automated monthly snapshots; API endpoint for report retrieval
* **PRODUCTION:** Full report generation + PDF rendering + cohort segmentation + AI narrative

---

#### Acceptance Criteria

* **Given** the month-end scheduler fires
* **When** the snapshot job runs
* **Then** exactly one snapshot row per active student exists for that month; rerunning the job produces no duplicate rows

* **Given** a snapshot exists for month M
* **When** the monthly report endpoint is queried for month M
* **Then** the report is generated from immutable snapshot data, not from live operational tables

---

### 3.19 On-Demand Historical Report Regeneration

The system MUST:

* Allow authorized operators to request regeneration of a monthly report for any prior month
* Historical report regeneration MUST use only the immutable snapshot data stored for that month
* Regenerated reports MUST be deterministically identical to the original report for the same snapshot data
* The system MUST NOT re-query SQL Server or live operational tables when generating a historical report

---

#### Scope Behavior

* **MVP:** Not available
* **STANDARD:** Historical report retrieval (read-only; no regeneration)
* **PRODUCTION:** On-demand regeneration with idempotency guarantee + audit log of regeneration requests

---

#### Acceptance Criteria

* **Given** a snapshot exists for month M
* **When** a historical report is regenerated for month M
* **Then** the output is byte-equivalent to the original report for the same snapshot data

* **Given** no snapshot exists for month M (month was before snapshots were introduced)
* **When** a historical report is requested for month M
* **Then** the system returns a clear error indicating no snapshot data is available for that period; it does not attempt to reconstruct from operational tables

---

### 3.20 Mentor & Operator Operational Visibility

The system MUST:

* Provide role-differentiated views for operators and mentors
* Operators MUST see: full student list, outreach state, payment risk, alert queue, system health
* Mentors MUST see: assigned students only, coursework engagement, lifecycle status, placement readiness, AI insights, communication history
* Mentors MUST NOT see: payment details, other mentors' students, raw system alerts
* All views are read-only for mentors; operators may initiate quick actions

---

#### Role Permissions Matrix

| Feature | Operator | Mentor |
|---|---|---|
| Full student roster | ✓ | ✗ (assigned only) |
| Payment details | ✓ | ✗ |
| Outreach queue | ✓ | ✗ |
| AI insights | ✓ | ✓ |
| Communication history | ✓ | ✓ |
| Lifecycle timeline | ✓ | ✓ |
| Coursework engagement | ✓ | ✓ |
| Placement readiness | ✓ | ✓ |
| Quick actions | ✓ | ✗ |
| System alerts | ✓ | ✗ |
| Historical reports | ✓ | ✗ |

---

#### Scope Behavior

* **MVP:** Single operator role; no mentor views
* **STANDARD:** Operator + mentor role separation; filtered student list for mentors
* **PRODUCTION:** Full RBAC + mentor assignment management + audit log of all operator actions

---

#### Acceptance Criteria

* **Given** a mentor is authenticated
* **When** the student roster endpoint is queried
* **Then** only students assigned to that mentor are returned

---

## 4. NON-FUNCTIONAL REQUIREMENTS

---

### 4.1 Performance

* Eligibility processing ≤ 5 seconds (500 students)
* API latency ≤ 500 ms (p95) for operational endpoints
* Historical report generation ≤ 60 seconds
* Monthly snapshot job completion ≤ 10 minutes for 2,000 active students
* LLM response ≤ 10 seconds per insight generation request

---

### 4.2 Scalability

* Initial: 100–500 students/day
* Target: 2,000+ students/day
* Snapshot store: designed to retain at least 36 months of student snapshots without degradation

---

### 4.3 Reliability

* Uptime ≥ 99.5%
* No missed scheduler runs
* Idempotent operations required
* Month-end snapshot job must self-recover from partial failure and resume without data loss

---

### 4.4 Concurrency

* Max 50 concurrent outreach triggers
* No duplicate outreach
* Snapshot writes are serialized per student; concurrent month-end jobs for different months are allowed

---

### 4.5 Observability

System MUST log:

* Scheduler runs (start, end, duration, student count processed)
* Outreach attempts and outcomes
* LLM outputs and token counts
* Snapshot job progress and completion
* Failures with full context (error class, correlation ID, student ID if applicable)
* All SQL Server sync operations (rows synced, schema mismatches, duration)

---

### 4.6 Security

* No secrets in code
* Secure API communication
* Data protection enforced
* PII excluded from LLM prompts
* Role-based access control enforced at the API layer
* All operator actions on student records logged with actor identity and timestamp

---

### 4.7 Reporting Warehouse Immutability

* Snapshot rows, once written, MUST NOT be updated or deleted by any application code path
* Delete operations on snapshot tables require a manual DBA action with documented justification
* The reporting schema exposes only SELECT access to the application service layer
* Any process that would modify a snapshot row is a production defect, not a feature

---

### 4.8 Historical Reproducibility

* A report generated for month M using snapshot data MUST produce identical output regardless of when it is run
* The snapshot MUST capture all fields required to render the report at generation time; reports do not rely on live table joins
* Snapshot schema changes require a versioning mechanism: new columns are nullable with defaults; prior snapshots remain valid
* Any change to the report rendering logic that would change historical output MUST produce a new report version, not silently alter existing output

---

## 5. ASSUMPTIONS

---

ASSUMPTION: GHL handles all outreach execution
Alternative: Backend-controlled communication layer

ASSUMPTION: LLM provider returns structured output
Alternative: Implement validation and retry

ASSUMPTION: Transcript is available post-call
Alternative: Handle missing transcript

ASSUMPTION: SQL Server schema for `AI_ChatBot_TriggerData` is stable; new columns may be added but existing columns are not renamed or removed without advance notice
Alternative: Implement schema drift detection and column-level fallbacks

ASSUMPTION: Month-end is defined as the last calendar day of each month; report generation triggers on the 1st of the following month
Alternative: Configurable month-end cutoff date

ASSUMPTION: GHL message sync retrieves all messages via the GHL API, not only platform-initiated messages
Alternative: Track only platform-initiated outreach

ASSUMPTION: Placement readiness data is derivable from fields already in SQL Server (interview prep completion, portfolio flags) with no additional external data source required
Alternative: Integrate a separate placement tracking system

ASSUMPTION: Access revocation/restoration events are tracked within this platform, not sourced from SQL Server
Alternative: SQL Server contains an access history table that can be mirrored

ASSUMPTION: Mentor-to-student assignment is managed externally (e.g., manually configured) and passed to the platform via configuration
Alternative: Build mentor assignment management within the platform

ASSUMPTION: Financial data sourced from SQL Server represents the complete payment record; no reconciliation against an external payment processor (Stripe, etc.) is required
Alternative: Integrate with payment processor API for independent verification

---

## 6. CONSTRAINTS

---

* Must be local-first
* Must be Azure-ready
* Must use SQL Server as READ-ONLY source; direct writes to SQL Server are prohibited
* Must not modify source table
* Must enforce deterministic logic
* PostgreSQL is the exclusive system-of-record for all platform-generated data
* Operational and reporting concerns MUST occupy separate database schemas
* Snapshot tables are append-only; update and delete operations are prohibited at the application layer
* LLM prompts MUST NOT contain PII beyond student program context and anonymized metrics
* Historical reports MUST be generatable from snapshot data alone, with no dependency on live operational tables
* Role-based access control is non-negotiable for any multi-user deployment

---

## 7. EDGE CASES

---

* Missing contact information
* GHL trigger failure
* Transcript missing
* LLM invalid response
* Duplicate scheduler execution
* Student becomes ineligible mid-cycle
* SQL Server unreachable at sync time — cached data served; sync retried on next cycle
* SQL Server schema mismatch detected at sync time — partial sync proceeds; mismatch logged; operator alerted
* Month-end snapshot job interrupted mid-run — job resumes from last successful student checkpoint; no duplicate snapshots created
* Student has no activity in the snapshot month — snapshot is still created with zero-activity metrics; student is not silently excluded
* Payment bundle deal detected with inconsistent credit and payment fields — system computes actual balance; flags record for operator review
* Historical report requested for a month before snapshots were introduced — system returns explicit NOT_AVAILABLE response; does not fallback to live data
* AI insight generation fails (LLM timeout, provider error) — last valid cached insight is served with a staleness flag; error is logged; retry is scheduled
* Mentor assignment is undefined for a student — student appears in operator view only; mentor view does not surface unassigned students
* Two snapshot jobs for the same month are triggered concurrently — idempotency key prevents duplicate rows; second job detects existing snapshots and exits cleanly
* GHL message sync returns a message for an unknown student (no matching UserID) — message is stored with a NULL user reference and flagged for manual review

---

## 8. SUCCESS CRITERIA

---

System is successful when:

* Outreach runs daily without failure
* No duplicate outreach occurs
* Decisions are deterministic
* Meetings are booked correctly
* Dashboard reflects accurate data
* Monthly snapshots are generated automatically with zero manual intervention
* Historical reports for any prior month are reproducible and deterministically identical on each generation
* AI insights are available for every active student within 24 hours
* Operators can identify and act on the top 10 at-risk students in under 30 seconds
* Mentors can review their assigned students' full lifecycle and engagement history without contacting operations
* Payment reconciliation discrepancies are surfaced automatically, not discovered manually
* SQL Server sync failures are detected and alerted within 5 minutes of occurrence

---

## 9. AI AUGMENTATION RESPONSIBILITIES

This section defines what the AI layer is responsible for, and what it is explicitly NOT responsible for.

---

### 9.1 Responsibilities

| Responsibility | Trigger | Output |
|---|---|---|
| **Sentiment analysis** | Post-call transcript available | Structured sentiment object stored in `outreach_history.llm_analysis` |
| **Risk summarization** | Daily for all active students | Stored in `ai_insights` with TTL |
| **Progress summarization** | Daily for students on active program | Stored in `ai_insights` with TTL |
| **Intervention recommendation** | Post-outreach + on-demand | Stored in `ai_insights`; surfaced to operator |
| **Operator assistance** | On-demand via dashboard quick action | Real-time response; not persisted unless operator saves |
| **Monthly narrative generation** | Month-end scheduler | Stored as part of monthly report record |
| **Communication sentiment aggregation** | Post GHL-sync | Rolled up into `communication_sentiment` insight |

---

### 9.2 Explicit Non-Responsibilities

The AI layer MUST NOT:

* Execute any outreach action directly (GHL is the execution layer)
* Make final eligibility decisions (deterministic rules govern; AI informs only)
* Modify student records in any database
* Contain PII in model prompts beyond what is explicitly permitted
* Replace operator judgment — AI output is advisory, not authoritative

---

### 9.3 AI Output Validation

* All structured AI outputs are validated against the declared schema before storage
* Invalid AI outputs trigger a retry (max 2 retries), then a fallback to the last valid cached insight
* AI output schema changes require a migration to the `ai_insights` table; old records are not invalidated

---

## 10. SYSTEM LAYERS & SEPARATION OF CONCERNS

---

| Concern | Owned By | Storage | Update Pattern |
|---|---|---|---|
| **Source student data** | SQL Server | SQL Server (read-only mirror in PostgreSQL) | Synced read-only |
| **Operational outreach state** | Platform | PostgreSQL `public` schema | Mutable; state machine governs transitions |
| **GHL communication records** | Platform | PostgreSQL `public` schema | Append on sync |
| **AI insights** | Platform | PostgreSQL `public` schema | Append + TTL-based invalidation |
| **Monthly snapshots** | Platform | PostgreSQL `warehouse` schema | Append-only; never updated |
| **Historical reports** | Platform | PostgreSQL `warehouse` schema | Append-only; versioned |
| **Operator / mentor notes** | Platform | PostgreSQL `public` schema | Mutable |

---

### Operational Outreach

Concerns: eligibility, state machine, GHL trigger, retry logic, attempt tracking, shadow/live mode.
Bounded scope: `student_outreach_tracking`, `outreach_history`, `state_transition_log`.

### Operational Intelligence

Concerns: priority scoring, risk classification, lifecycle tracking, payment reconciliation, placement readiness, communication telemetry.
Bounded scope: Live reads of SQL Server mirror + platform-generated records.

### Reporting Intelligence

Concerns: monthly snapshots, historical reports, longitudinal analytics, cohort trends.
Bounded scope: `warehouse` schema — append-only, never joined against live operational tables in report generation.

### AI Augmentation

Concerns: insight generation, sentiment analysis, narrative generation, intervention recommendations.
Bounded scope: `ai_insights` table; prompts draw from non-PII metrics only.

### Future Automation

Concerns: mentor assignment automation, payment escalation automation, placement pipeline automation.
Bounded scope: Not yet implemented; requires explicit business requirement sign-off before implementation begins.

---

## 11. UNRESOLVED BUSINESS ASSUMPTIONS

The following assumptions require explicit business clarification before the features that depend on them are built.

---

| # | Assumption | Impact if Wrong | Decision Needed From |
|---|---|---|---|
| U-1 | "CAP hopeful," "launch hopeful," and "placement hopeful" are derivable from existing SQL Server fields | These cohorts cannot be automatically segmented without new data | Product / Operations |
| U-2 | Placement readiness is fully determined by fields already in SQL Server (`student_interview_prep`, `ActiveStatus`, etc.) | May require integration with a separate placement tracking system | Product |
| U-3 | Access revocation/restoration events are tracked in this platform, not sourced from SQL Server | If sourced from SQL Server, a new read-only view is needed | Engineering / IT |
| U-4 | "Month-end" is always the last calendar day; edge cases (student enrolled on the 31st, snapshot month with 28 days) are handled by the platform | Incorrect snapshot boundary causes reporting inaccuracies | Product |
| U-5 | Mentor-to-student assignment is a 1:N relationship (one mentor, many students); a student has at most one mentor at a time | Many-to-many assignment requires a different data model | Operations |
| U-6 | Financial data in SQL Server is the complete record; no external payment processor reconciliation is required | Bundle deal detection may be insufficient without payment processor confirmation | Finance / Operations |
| U-7 | AI monthly narrative is for internal operator use only, not delivered to students | If student-facing, privacy review and tone guidelines are required | Product / Legal |
| U-8 | All GHL message history is accessible via GHL API, including messages not initiated by this platform | If GHL API does not expose full message history, the unified communication timeline will be incomplete | Engineering |
| U-9 | Snapshot retention policy is "indefinitely" (36+ months); there is no legal or compliance requirement to delete historical snapshots | If FERPA or contract terms require data deletion, the append-only model needs a compliant deletion path | Legal / Compliance |
| U-10 | A "student" maps 1:1 to a `UserID` across all systems (SQL Server, GHL, platform); there are no duplicate or merged student records | Duplicate student handling requires explicit deduplication logic before intelligence can be trusted | Engineering / IT |

---

## END OF FILE
