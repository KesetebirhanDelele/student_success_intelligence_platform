# /spec/01_requirements.md

---

## LAYER 1 — REQUIREMENTS (INTENT)

---

## 1. SYSTEM PURPOSE

The **Student Operational Intelligence Platform with Outreach Automation (SSIP)** is an enterprise intelligence system for monitoring, analyzing, and acting on the full operational lifecycle of enrolled students.

Outreach automation is a **subsystem**, not the primary architectural identity.

The platform is responsible for:

* **Operational student intelligence** — real-time risk classification, priority scoring, and alerting
* **Lifecycle intelligence** — enrollment transitions, cohort membership, velocity metrics
* **Coursework engagement intelligence** — homework pace, effort ratings, curriculum progress
* **Financial and payment intelligence** — balance reconciliation, bundle deal detection, payment risk
* **Placement-readiness intelligence** — interview prep, portfolio status, placement pipeline tracking
* **Communication telemetry** — unified chronological timeline across all channels and sources
* **AI-generated insights** — risk summaries, progress summaries, intervention recommendations, monthly narratives
* **Immutable monthly reporting** — append-only student snapshots and enterprise cohort reports
* **Operational dashboards** — role-differentiated views for operators and mentors
* **Historical analytics** — longitudinal trend analysis and point-in-time report regeneration

The outreach automation subsystem:

* Identifies students requiring intervention
* Triggers outreach via GHL (GoHighLevel)
* Analyzes interaction outcomes using an LLM engine
* Applies deterministic decision rules
* Orchestrates follow-ups, meeting booking, resource delivery, and IPBC conversion tracking

The platform acts as the **central intelligence and orchestration layer**. GHL executes communication workflows. SQL Server is the authoritative read-only source of student academic and operational data. PostgreSQL is the exclusively platform-owned intelligence, operations, and reporting database.

---

## 2. BUSINESS OBJECTIVES

---

### 2.1 Primary Objectives

1. Increase student engagement and reduce academic risk
2. Improve retention and program completion rates
3. Detect academic, financial, and engagement risk early
4. Automate outreach at scale, with deterministic safeguards
5. Drive IPBC conversion and track attribution
6. Provide full operational visibility for operators and mentors
7. Deliver immutable monthly enterprise reports per student cohort
8. Maintain append-only historical records enabling point-in-time reconstruction of any student's state
9. Surface placement readiness signals to reduce time-to-hire
10. Enable mentor and operator access to actionable intelligence without requiring direct database access
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
* Operator time-to-identify top 10 at-risk students ≤ 30 seconds

---

### 2.3 Operational Domains

The platform recognizes and tracks the following nine operational domains. Each domain is a first-class platform concept with distinct eligibility rules, intervention triggers, reporting requirements, and dashboard representation.

| # | Domain | Description | Primary Signal |
|---|---|---|---|
| 1 | **New Signups / Newcomers** | Students newly enrolled; orientation and onboarding tracking | StudentStartDate, ClassStartDate, days since signup |
| 2 | **Coursework Engagement** | Students actively progressing through curriculum modules | HWsBehind, AvgEffRating, CurrentSection, LastActivityDays |
| 3 | **Homework Risk** | Students with overdue assignments or declining effort rating | HWsBehind ≥ 1, AvgEffRating < 3.0 |
| 4 | **CAP Hopefuls** | Students approaching CAP program eligibility | PerComp_Act threshold, program start date flags |
| 5 | **Launch Hopefuls** | Students in CAP, approaching launch preparation eligibility | PerComp_Act threshold, CAP enrollment confirmed |
| 6 | **Placement Hopefuls** | Students in launch phase, actively in job search or interview pipeline | CurrentSection pattern, launch enrollment |
| 7 | **Payment & Financial Tracking** | Students with outstanding balances or payment plan deviations | PaymentBalance, ClassFeesPaid, bundle deal flags |
| 8 | **Access Revocation & Restoration** | Students whose platform access has been revoked or restored | Access state, trigger event, resolution time |
| 9 | **Communication & Campaign Activity** | Aggregated outreach and campaign history per student | Last contact date, channel stats, response rate |

---

### 2.4 Cohort Identification Rules

The following rules define cohort membership based on operational heuristics derived from SQL Server data.

**These rules are CONFIGURABLE OPERATIONAL HEURISTICS.** They represent the current best-known derivation logic, not permanent hard-coded thresholds. All field references are read from the SQL Server mirror in PostgreSQL.

---

#### CAP Hopeful

A student is classified CAP Hopeful when ALL of the following are true:

* `PerComp_Act > 0.30`
* `CAP_StartDate IS NULL`
* `LaunchStartDate IS NULL`
* `CurrentSection NOT LIKE '%launch%'` (case-insensitive)
* `CurrentSection NOT LIKE '%CAP%'` (case-insensitive)

---

#### Launch Hopeful

A student is classified Launch Hopeful when ALL of the following are true:

* `PerComp_Act >= 0.59`
* `CAP_StartDate IS NOT NULL`
* `LaunchStartDate IS NULL`
* `CurrentSection LIKE '%CAP%'` (case-insensitive)
* `CurrentSection NOT LIKE '%launch%'` (case-insensitive)

---

#### Placement Hopeful

A student is classified Placement Hopeful when:

* `CurrentSection LIKE '%launch%'` (case-insensitive)

---

#### Configurable Rule Governance

* Threshold values (`0.30`, `0.59`) are configurable; any change requires a documented operational decision
* Section name patterns (`'%launch%'`, `'%CAP%'`) depend on SQL Server curriculum data conventions; they must be reviewed when curriculum naming changes
* New cohort rules must be proposed as documented operational decisions before implementation begins
* The platform MUST NOT hardcode these values in business logic; they must be resolved from a configurable rule store

---

#### Acceptance Criteria

* **Given** a student satisfies all CAP Hopeful conditions
* **When** cohort classification runs
* **Then** the student is assigned to the CAP Hopeful cohort and this cohort membership is stored with timestamp

* **Given** cohort threshold values change in configuration
* **When** the next classification run executes
* **Then** cohort membership is re-evaluated against the new thresholds without requiring a code deployment

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
* **PRODUCTION:** Full rule set + priority scoring + cohort-aware eligibility

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
* GHL is the execution layer for all outreach communication

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

The communication provider is configurable; GHL is the current default.

---

#### Scope Behavior

* **MVP:** Call only
* **STANDARD:** Call + SMS fallback
* **PRODUCTION:** Call → SMS → Email fallback sequence

---

### 3.4 LLM-Based Analysis

The system MUST:

* Process conversation transcripts
* Send data to LLM provider (provider is configurable; see Section 12)
* Enforce strict structured output
* Validate all structured output before storage

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

#### Required Output — Trend Interpretation

* trend_direction (IMPROVING / STABLE / DECLINING)
* trend_summary (plain text, ≤ 100 words)
* trend_period_weeks
* key_trend_drivers (list)

---

#### Required Output — Monthly Narrative

* executive_summary (plain text, ≤ 200 words)
* cohort_highlights (list)
* intervention_summary (list)
* placement_pipeline_status

---

#### Scope Behavior

* **MVP:** Basic sentiment only
* **STANDARD:** Sentiment + issues + risk summarization + trend interpretation
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

* Combine academic metrics and LLM output
* Apply deterministic rules
* Override LLM recommendations when deterministic rule conditions are met

---

#### Scope Behavior

* **MVP:** Simplified rules
* **STANDARD:** Full rules without overrides
* **PRODUCTION:** Full rules + override logic

---

#### Acceptance Criteria

* **Given** conflicting data between LLM output and deterministic rules
* **When** evaluated
* **Then** deterministic rules prevail; LLM recommendation is logged but not applied

---

### 3.6 Retry Logic

The system MUST:

* Track outreach attempts per student per checkpoint
* Retry when no response within configurable window

---

#### Scope Behavior

* **MVP:** No retry
* **STANDARD:** 1–2 retries
* **PRODUCTION:** 3-day retry cycle with configurable backoff

---

#### Acceptance Criteria

* **Given** no response to outreach
* **When** retry conditions are met
* **Then** next attempt is scheduled; the student is not re-triggered if max attempts have been reached

---

### 3.7 Meeting Booking

The system MUST:

* Integrate with Google Calendar
* Book meetings when decision engine criteria are met

---

#### Scope Behavior

* **MVP:** Manual or disabled
* **STANDARD:** Basic booking
* **PRODUCTION:** Automated booking + confirmation

---

#### Acceptance Criteria

* **Given** a meeting is recommended
* **When** booking is triggered
* **Then** a calendar event is created and associated with the student's outreach record

---

### 3.8 Transcript Storage

The system MUST:

* Store transcripts in PostgreSQL
* Associate each transcript with the originating outreach record
* Redact or exclude PII from any transcript segment passed to the LLM

---

#### Scope Behavior

* **MVP:** Store minimal transcript
* **STANDARD:** Store full transcript
* **PRODUCTION:** Store + index + analyze; PII minimization enforced

---

### 3.9 Dashboard Support

The system MUST expose role-differentiated API endpoints for all dashboard tabs. All data served through dashboard APIs is read from PostgreSQL; no dashboard endpoint queries SQL Server directly.

---

#### Dashboard Tabs

| Tab | Primary Audience | Data Source |
|---|---|---|
| Overview | Operator | Operational DB + AI insights |
| Lifecycle | Operator / Mentor | SQL Server mirror + transitions |
| Coursework | Mentor | SQL Server mirror |
| Payments | Operator | SQL Server mirror |
| Placement | Mentor / Operator | SQL Server mirror + cohort flags |
| Communication | Operator | GHL messages + campaign activity + outreach history |
| History | Operator | Append-only snapshot store (`warehouse` schema) |
| AI Insights | Operator / Mentor | `ai_insights` table |

---

#### Scope Behavior

* **MVP:** Minimal endpoints
* **STANDARD:** Core dashboards (overview, lifecycle, coursework)
* **PRODUCTION:** Full analytics (all tabs + historical + AI)

---

### 3.10 Data Architecture & Source System Separation

The system MUST enforce a strict and inviolable boundary between the source system and the intelligence database.

---

#### Source System: SQL Server (READ-ONLY)

* SQL Server is the authoritative source for all student academic, enrollment, and operational data
* The system MUST NOT write to SQL Server under any circumstances, for any reason
* Data is read via `AI_ChatBot_TriggerData` and any additional approved read-only views
* SQL Server may evolve independently; the platform must tolerate additive schema changes
* Schema drift (missing or renamed columns) is detected at sync time, logged, and reported; partial sync completes for intact columns

---

#### Intelligence Database: PostgreSQL (READ-WRITE)

PostgreSQL is the exclusively platform-owned database. ALL of the following must live ONLY in PostgreSQL and NEVER in SQL Server:

* AI outputs (all insight types, sentiment, narratives)
* Monthly snapshots
* Historical reports
* Operational intelligence (outreach state, tracking, history)
* Communication history (GHL messages, campaign activity, outreach log)
* Analytics and cohort classification records
* Access history events (mirrored from SQL Server; extended by platform)
* Student notes, operator actions, quick action logs

---

#### Schema Separation

* Operational schema (default `public`): live mutable operational data
* Reporting schema (`warehouse`): append-only snapshots and reports; no live table joins at report time

---

#### Acceptance Criteria

* **Given** a sync job runs
* **When** SQL Server is unreachable
* **Then** the platform serves cached mirror data; a CRITICAL alert is raised; no write to SQL Server is attempted

* **Given** a new column appears in SQL Server that the mirror model does not define
* **When** the sync job executes
* **Then** the new column is ignored; existing mapped columns sync normally; a schema drift warning is logged

---

#### Scope Behavior

* **MVP:** Single-schema PostgreSQL; SQL Server read via sync job
* **STANDARD:** Schema separation (operational vs. warehouse); sync validation and drift detection
* **PRODUCTION:** Full schema isolation; incremental sync with change detection; automated drift alerting

---

### 3.11 Student Lifecycle Intelligence

The system MUST:

* Track and surface the following lifecycle states for every student:

  * Active / Inactive / Paused / Dropped / Graduated / Placed
* Detect lifecycle state changes by comparing consecutive SQL Server sync snapshots
* Record all detected lifecycle transitions with: timestamp, detected prior state, new state, sync job ID
* Expose lifecycle history as an ordered timeline per student
* Derive lifecycle velocity metrics: days in current state, days since last transition, total days enrolled

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
* **PRODUCTION:** Full timeline + velocity metrics + AI lifecycle summary + cohort membership history

---

#### Acceptance Criteria

* **Given** a student's `ActiveStatus` changes between two sync runs
* **When** the sync comparison runs
* **Then** a lifecycle transition event is recorded with the detected prior and new state, timestamped at sync time

---

### 3.12 Coursework Engagement Intelligence

The system MUST:

* Track homework submission pace against expected curriculum velocity
* Flag students whose HWsBehind exceeds configurable thresholds (see Section 12)
* Track AvgEffRating trends over time; detect consecutive declining readings
* Surface last submitted assignment with days-since metric
* Surface current section and curriculum progress percentage

---

#### Homework Risk Classification

These thresholds are configurable (see Section 12).

| Classification | Default Condition |
|---|---|
| ON_TRACK | HWsBehind = 0 AND AvgEffRating ≥ 3.0 |
| AT_RISK | HWsBehind ≥ 1 OR AvgEffRating < 3.0 |
| CRITICAL | HWsBehind ≥ 3 OR AvgEffRating < 2.0 |

---

#### Scope Behavior

* **MVP:** HWsBehind + AvgEffRating display
* **STANDARD:** Trend tracking + risk classification
* **PRODUCTION:** Trend + classification + AI engagement summary + proactive outreach eligibility trigger

---

#### Acceptance Criteria

* **Given** a student has HWsBehind ≥ 3 (or the configured CRITICAL threshold)
* **When** the eligibility engine runs
* **Then** the student is classified CRITICAL and included in the next outreach cycle

---

### 3.13 Financial & Payment Intelligence

The system MUST:

* Reconcile payment data sourced from SQL Server
* Detect and correctly handle bundle deal payment structures
* Classify each student's payment risk (CLEAR / MEDIUM / HIGH) — thresholds are configurable (see Section 12)
* Surface payment history including total payments, credits, class value, and computed actual balance
* Flag students whose actual balance deviates from stored `PaymentBalance` by more than a configurable threshold

---

#### Payment Risk Classification

These thresholds are configurable (see Section 12).

| Classification | Default Condition |
|---|---|
| CLEAR | Actual balance ≤ $0 |
| MEDIUM | $0 < Actual balance ≤ $1,000 |
| HIGH | Actual balance > $1,000 |

---

#### Bundle Deal Detection

* A bundle deal is detected when: `Total_Credits > 0 AND PaymentBalance = 0 AND ClassValue > 0`
* In this case: `actual_balance = ClassValue − Total_Payments − Total_Credits`
* This logic compensates for a known SQL Server data characteristic; it is not an error in the source data

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

* **Given** a student's actual balance exceeds the HIGH threshold
* **When** the payment intelligence endpoint is queried
* **Then** the student is classified HIGH risk

---

### 3.14 Placement Readiness Intelligence

The system MUST:

* Classify students into placement cohorts (CAP Hopeful, Launch Hopeful, Placement Hopeful) using the rules in Section 2.4
* Track placement readiness indicators per student:

  * Interview prep completion status
  * Portfolio / GitHub activity flag
  * Resume submission status
  * Active cohort membership (CAP / Launch / Placement)
* Surface a composite placement readiness score
* Track time-in-placement-pipeline from first Placement Hopeful classification to job offer
* Alert operators when a Placement Hopeful has been inactive for ≥ 7 days

---

#### Scope Behavior

* **MVP:** Cohort classification display only
* **STANDARD:** Composite readiness score + pipeline tracking
* **PRODUCTION:** Full placement intelligence + AI readiness assessment + operator alerts

---

#### Acceptance Criteria

* **Given** a student satisfies Placement Hopeful conditions (Section 2.4)
* **When** cohort classification runs
* **Then** a composite readiness score is returned based on available indicators

* **Given** a Placement Hopeful student has no recorded activity for ≥ 7 days
* **When** the daily intelligence job runs
* **Then** an operator alert is generated

---

### 3.15 Operational Access-History Intelligence

Access revocation and restoration events originate from SQL Server operational tables. The platform ingests and mirrors these events. The platform does not own the authoritative source initially; platform-owned access event extensions may be supported in a future phase.

The system MUST:

* Sync access revocation and restoration events from SQL Server on each sync cycle
* Record each event with: timestamp, trigger event type, actor (operator or system), prior access state, new access state, **origin_source**
* Extend event records with platform-originated context (operator notes, manual restorations) where applicable; these extensions carry `origin_source: platform_manual` or `origin_source: platform_system`
* Surface a chronological access history per student ordered by event timestamp
* Alert operators when a student's access is revoked for > 48 hours without restoration or explicit closure

---

#### Access Event Origin Classification

Every access event carries an `origin_source` field with one of three values:

| origin_source | Description |
|---|---|
| `mirrored_sql_server` | Event read from SQL Server on a sync cycle; SQL Server is the authoritative record |
| `platform_manual` | Event created by an operator action within the platform (e.g., manual access restoration note) |
| `platform_system` | Event created by platform automated logic (e.g., automatic access flag on payment delinquency detection) |

Platform-originated event types (`platform_manual`, `platform_system`) are introduced only in the PRODUCTION tier when a specific platform access management capability is explicitly approved as an architectural decision. Until then, all access events are `mirrored_sql_server`.

---

#### Access Event Conflict Resolution

* SQL Server is the authoritative source for a student's **current access status** for all eligibility decisions, outreach gating, and operational alerts (see FAD-5)
* Platform-originated access events (`platform_manual`, `platform_system`) are contextual supplementary records; they are displayed in the timeline with clear source attribution but do NOT override the SQL Server-mirrored current state for eligibility purposes
* The access history timeline is chronologically ordered by event timestamp; events from all origin sources are displayed together with `origin_source` always visible
* If SQL Server shows a student as revoked and the platform has a manual restoration event with no corresponding SQL Server restoration, the student remains operationally treated as revoked until SQL Server confirms restoration

---

#### Scope Behavior

* **MVP:** Current access status display (from SQL Server mirror)
* **STANDARD:** Access event timeline (mirrored from SQL Server)
* **PRODUCTION:** Full history + platform-extended events + alerting + AI access pattern analysis

---

#### Acceptance Criteria

* **Given** a student's access is revoked in SQL Server
* **When** the sync job runs
* **Then** the event is mirrored into PostgreSQL and appears in the access history timeline

* **Given** a student has been in a revoked access state for > 48 hours with no restoration
* **When** the daily alert job runs
* **Then** an operator alert is generated

---

### 3.16 Unified Communication Telemetry

The system MUST maintain a unified, immutable, chronological communication record per student aggregating ALL of the following sources:

* GHL inbound and outbound messages (synced from GHL API)
* Campaign activity records (email, SMS, campaign-triggered messages)
* Platform-initiated outreach attempts (from `outreach_history`)
* Operator-logged actions (calls, manual outreach notes)
* AI-generated summaries (linked to the communication event that triggered them)
* Student notes flagged as communication records
* Future sources: direct SMS, direct email, call events (extensible by source type)

---

#### Timeline Architecture Requirements

* Events from all sources are merged into a single chronological timeline per student
* Each event carries an immutable `source` attribution tag (ghl / campaign / platform / operator / ai)
* Communication events are append-only; no existing event record is updated or deleted
* Channel analytics are derived from the timeline: total contacts, response rate, last contact date, days since last contact, breakdown by channel

---

#### Communication Record Fields

| Field | Source |
|---|---|
| direction | INBOUND / OUTBOUND / INTERNAL |
| channel | CALL / SMS / EMAIL / CAMPAIGN / NOTE / AI_SUMMARY |
| body / subject | Message content |
| status | DELIVERED / FAILED / NO_RESPONSE / LOGGED |
| activity_date | Event timestamp |
| source | platform / ghl / campaign / operator / ai |

---

#### Scope Behavior

* **MVP:** Platform-initiated outreach only
* **STANDARD:** Platform + GHL message sync + campaign activity
* **PRODUCTION:** Full unified timeline + channel analytics + AI communication summary + immutable event log

---

#### Acceptance Criteria

* **Given** a GHL message is received for a known student
* **When** the communication timeline endpoint is queried
* **Then** the message appears in chronological order with correct channel, direction, and source attribution

* **Given** a communication event is recorded
* **When** any code path attempts to update or delete the event record
* **Then** the operation is rejected; a new corrective event may be appended instead

---

### 3.17 AI-Generated Student Insights

The system MUST generate, store, and serve AI insights per student covering all responsibility areas defined in Section 9.

---

#### Insight Types

| Type | Trigger | Consumer |
|---|---|---|
| `risk_summary` | Daily or on-demand | Operator, Mentor |
| `progress_summary` | Daily or on-demand | Mentor |
| `intervention_recommendation` | Post-outreach + daily | Operator |
| `communication_sentiment` | Post-GHL sync | Operator |
| `trend_interpretation` | Weekly or on-demand | Operator, Mentor |
| `monthly_narrative` | Month-end scheduler | Admin |

---

#### Output Properties (apply to all insight types)

* **Versioned:** each generation creates a new record; prior versions are retained
* **Attributable:** model used, prompt version, generated_at timestamp stored on every record
* **Reviewable:** operators can view the full insight record including metadata
* **Reproducible:** same input metrics + same prompt version → same output (subject to LLM non-determinism tolerance)

---

#### Constraints

* AI insight prompts MUST NOT include PII; only anonymized student metrics and program context are permitted
* AI insight generation MUST be idempotent for the same `(student_id, insight_type, date, prompt_version)` tuple
* Cached insights are served until TTL expires (default: 24 hours; configurable)
* Force-refresh is supported via an explicit API parameter
* AI insight text captured in a finalized monthly snapshot is a physical copy at snapshot generation time; subsequent force-refresh or regeneration of insights MUST NOT affect finalized snapshot AI content (see FAD-1)

---

#### Scope Behavior

* **MVP:** No AI insights
* **STANDARD:** Risk summary + intervention recommendation
* **PRODUCTION:** Full insight suite + versioning + monthly narrative + trend interpretation

---

#### Acceptance Criteria

* **Given** an insight request for a student and a valid cached insight within TTL
* **When** the endpoint is queried without `force_refresh`
* **Then** the cached insight is returned; no LLM call is made

* **Given** an insight request with `force_refresh=true`
* **When** a cached insight exists
* **Then** a new insight is generated with a new version record; the prior insight is retained in history

* **Given** AI insight generation fails after max retries
* **When** the endpoint is queried
* **Then** the last valid cached insight is returned with a `stale: true` flag; the failure is logged

---

### 3.18 Monthly Snapshot & Enterprise Reporting

The system MUST take an immutable monthly snapshot of every active student's full operational state on a scheduled month-end trigger.

---

#### Snapshot Content Requirements

Each snapshot MUST preserve the following — the snapshot is self-contained and must not require live table joins at report generation time:

* **Lifecycle position:** active status, cohort memberships, days enrolled, current section
* **Academic metrics:** HWsBehind, AvgEffRating, LastActivityDays, curriculum progress percentage
* **Communication summary:** total outreach attempts, response count, last contact date, days since last contact, channel breakdown
* **Financial summary:** actual balance, payment risk classification, class fees paid, bundle deal flag
* **Placement summary:** current cohort (CAP / Launch / Placement), readiness score, interview prep status
* **AI summaries:** last risk summary text, last progress summary text, monthly narrative text
* **Snapshot metadata:** snapshot_month, generated_at, schema_version, configuration_registry_version, ai_prompt_version (per insight type), ai_model_version (per insight type), report_template_version — collectively forming the **Snapshot Reproducibility Fingerprint** (see Section 4.8)

---

#### Snapshot Integrity Rules

* Snapshots are append-only: no existing snapshot row is updated or deleted after finalization
* Keyed by `(student_id, snapshot_month)` — exactly one snapshot per student per month
* Students with no activity in the snapshot month still receive a snapshot (zero-activity metrics; not silently excluded)
* Snapshot finalization is a two-phase operation: draft → finalized; only finalized snapshots are used for reports
* DRAFT snapshots are mutable and may be replaced or discarded before finalization; the immutability guarantee applies only to FINALIZED snapshots

---

#### AI Content Physical Copy Rule

* AI-generated summaries and narratives (risk summary text, progress summary text, monthly narrative text) captured in a snapshot are stored as physical point-in-time text copies in the snapshot row
* Snapshots MUST NOT store live references or foreign key references to `ai_insights` rows; text is embedded directly in the snapshot record
* Post-finalization regeneration of AI insights, force-refresh, or LLM provider changes have NO effect on finalized snapshot AI content
* This design guarantees that historical report regeneration (Section 3.19) reproduces AI content identical to the original, regardless of any subsequent AI operations (see FAD-1)

---

#### Report Generation

The system MUST generate enterprise monthly reports that:

* Are generated entirely from finalized snapshot data; no live operational table queries at report time
* Cover all students active in the snapshot month, segmented by cohort
* Surface aggregate statistics: engagement rate, payment compliance rate, homework risk rate, placement pipeline count
* Include a system-generated AI narrative summarizing cohort health
* Are available as a structured API response and as a PDF-renderable JSON payload
* Are versioned; a new report version is created if the report template changes after a report was generated

---

#### Scope Behavior

* **MVP:** No snapshots
* **STANDARD:** Automated monthly snapshots; API endpoint for report retrieval
* **PRODUCTION:** Full report generation + PDF rendering + cohort segmentation + AI narrative + version history

---

#### Acceptance Criteria

* **Given** the month-end scheduler fires
* **When** the snapshot job runs
* **Then** exactly one finalized snapshot per active student exists for that month; rerunning produces no duplicates

* **Given** a finalized snapshot exists for month M
* **When** the monthly report endpoint is queried for month M
* **Then** the report is generated exclusively from snapshot data; no SQL Server query is made

---

### 3.19 On-Demand Historical Report Regeneration

The system MUST allow authorized operators to regenerate a monthly report for any prior month.

The system MUST:

* Use only the finalized snapshot data stored for the requested month
* Use finalized snapshot data exclusively for trend interpretation in historical reports; live SQL Server mirror data MUST NOT be used for historical trend analytics (see FAD-2)
* Reproduce AI narrative content from the physical text copy stored in the snapshot; MUST NOT make new LLM calls to regenerate AI content for historical reports
* Produce output deterministically identical to the original report for the same snapshot data and report template version
* NEVER re-query SQL Server or live operational tables when generating a historical report
* Maintain an audit log of every historical regeneration request: who requested it, when, for which month, which report version was produced, and the Snapshot Reproducibility Fingerprint of the source snapshot (see FAD-6)

---

#### Scope Behavior

* **MVP:** Not available
* **STANDARD:** Historical report retrieval (read-only; regeneration not yet supported)
* **PRODUCTION:** On-demand regeneration with idempotency guarantee + audit log + version selection

---

#### Acceptance Criteria

* **Given** a finalized snapshot exists for month M
* **When** a historical report is regenerated for month M
* **Then** the output matches the original report byte-for-byte when using the same report template version

* **Given** a historical report is regenerated after the AI model or prompt version has changed
* **When** the regeneration runs
* **Then** the AI narrative content is reproduced from the physical text copy stored in the snapshot; no new LLM call is made; the output is identical to the original AI content

* **Given** trend interpretation data is requested for a historical report for month M
* **When** the report is generated
* **Then** trend analytics are derived exclusively from the finalized snapshots available at or before month M; live operational data is not used

* **Given** no finalized snapshot exists for month M
* **When** a historical report is requested for month M
* **Then** the system returns `NOT_AVAILABLE`; it does not attempt reconstruction from live data

---

### 3.20 Mentor & Operator Operational Visibility

---

#### Mentor Assignment Model

The current assignment model is:

* **One primary mentor** per student (1:N relationship — one mentor may have many students)
* **One optional super mentor** per student (oversight role; access to all assigned students of supervised mentors)
* **One optional instructor** per student (curriculum support role)

A student has at most one active assignment per role at any given time. Role assignments are managed externally and provided to the platform via configuration or a future assignment management API.

Future architecture may evolve to a many-to-many assignment history model. The current data model must be designed to accommodate this evolution without a breaking schema change.

---

#### Access Rules

* Operators: full student roster, outreach state, payment risk, alert queue, system health, all quick actions
* Primary Mentors: assigned students only, coursework engagement, lifecycle status, placement readiness, AI insights, communication history
* Super Mentors: all students assigned to their supervised mentors; same data access as primary mentor per student
* Instructors: assigned students only; coursework and lifecycle data; no payment or outreach data
* Mentors and Instructors: read-only; no quick actions

---

#### Role Permissions Matrix

| Feature | Operator | Super Mentor | Primary Mentor | Instructor |
|---|---|---|---|---|
| Full student roster | ✓ | ✗ (supervised only) | ✗ (assigned only) | ✗ (assigned only) |
| Payment details | ✓ | ✗ | ✗ | ✗ |
| Outreach queue | ✓ | ✗ | ✗ | ✗ |
| AI insights | ✓ | ✓ | ✓ | ✗ |
| Communication history | ✓ | ✓ | ✓ | ✗ |
| Lifecycle timeline | ✓ | ✓ | ✓ | ✓ |
| Coursework engagement | ✓ | ✓ | ✓ | ✓ |
| Placement readiness | ✓ | ✓ | ✓ | ✗ |
| Quick actions | ✓ | ✗ | ✗ | ✗ |
| System alerts | ✓ | ✗ | ✗ | ✗ |
| Historical reports | ✓ | ✗ | ✗ | ✗ |

---

#### Scope Behavior

* **MVP:** Single operator role; no mentor or instructor views
* **STANDARD:** Operator + primary mentor role separation; filtered student roster for mentors
* **PRODUCTION:** Full RBAC + super mentor + instructor + assignment management + operator action audit log

---

#### Acceptance Criteria

* **Given** a primary mentor is authenticated
* **When** the student roster endpoint is queried
* **Then** only students with an active primary mentor assignment pointing to this mentor are returned

* **Given** a student has no primary mentor assignment
* **When** a mentor role user queries the student roster
* **Then** the unassigned student is excluded from the response

---

## 4. NON-FUNCTIONAL REQUIREMENTS

---

### 4.1 Performance

* Eligibility processing ≤ 5 seconds (500 students)
* API latency ≤ 500 ms (p95) for operational endpoints
* Historical report generation ≤ 60 seconds
* Monthly snapshot job completion ≤ 10 minutes for 2,000 active students
* AI insight generation ≤ 10 seconds per student
* Cohort classification job ≤ 30 seconds for full student population

---

### 4.2 Scalability

* Initial: 100–500 students/day
* Target: 2,000+ students/day
* Snapshot store: designed to retain at least 36 months of student snapshots without query degradation

---

### 4.3 Reliability

* Uptime ≥ 99.5%
* No missed scheduler runs
* All scheduled operations are idempotent
* Month-end snapshot job must self-recover from partial failure and resume from last successful checkpoint; no data loss on restart

---

### 4.4 Concurrency

* Max 50 concurrent outreach triggers
* No duplicate outreach per student per checkpoint
* Snapshot writes are serialized per student; concurrent month-end jobs for different months are permitted
* Cohort classification is a read-then-write operation; concurrent runs must not produce duplicate classification records

---

### 4.5 Observability

System MUST log:

* Scheduler runs: start, end, duration, student count processed, outcome
* Outreach attempts and outcomes
* LLM outputs: model used, token count, latency, outcome
* Snapshot job: progress per student, finalization status, total duration
* Failures: error class, correlation ID, student ID if applicable, full context
* SQL Server sync: rows synced, schema drifts detected, duration
* Cohort classification: counts per cohort, threshold values used, run timestamp
* All operator actions on student records: actor identity, action type, timestamp, student ID

---

### 4.6 Security

* No secrets in code or LLM prompts
* Secure API communication (TLS required)
* Data protection enforced at rest and in transit
* PII excluded from LLM prompts; only anonymized metrics and program context are permitted
* Role-based access control enforced at the API layer for every endpoint
* All operator actions on student records are logged with actor identity and timestamp
* Future compliance readiness must remain possible: FERPA, enterprise data contracts, audit requirements
* The platform must be designed such that adding a data deletion path (for FERPA compliance) does not require a fundamental architectural change

---

### 4.7 Reporting Warehouse Immutability

* Snapshot rows, once finalized, MUST NOT be updated or deleted by any application code path
* The `warehouse` schema exposes only SELECT access to the application service layer
* Any code path that would issue an UPDATE or DELETE against a finalized snapshot row is a production defect, not a feature
* Report records are similarly immutable after publication; a new report version must be created rather than modifying an existing one

---

#### Compliance Governance Pathway

The operational immutability guarantee does not preclude compliance-driven deletion or anonymization. Such actions are governed by a defined pathway, not ad-hoc DBA access. Any deletion or anonymization of finalized snapshot or report records that bypasses this pathway is a compliance defect.

A compliance action on a finalized snapshot or report record requires ALL of the following before execution:

* **Authorization:** approval from a designated compliance authority (defined by the organization)
* **Scope definition:** explicit enumeration of all records affected across all tables, derived from the compliance scope manifest
* **Pre-action audit entry:** a record in the Compliance Audit Area (see below) created before any deletion or anonymization executes

**Required audit entry fields:**

| Field | Description |
|---|---|
| authorization_timestamp | When authorization was granted |
| authorized_by | Identity of the approving compliance authority |
| executed_by | Identity of the operator executing the action |
| affected_student_id | Student record being acted upon |
| affected_tables | Explicit list of all tables from which records are removed or anonymized |
| action_type | `DELETE` or `ANONYMIZE` |
| audit_rationale | Legal or compliance basis for the action (e.g., FERPA request, contract term) |
| affected_record_count | Number of records removed or anonymized per table |

---

#### Compliance Audit Area

* The compliance audit area is a logically isolated domain (`compliance_audit` schema) with no foreign key dependencies on the operational or warehouse schemas
* Initial implementation resides within PostgreSQL; a future evolution may move it to an external compliance system; the logical isolation design accommodates this without architectural change
* The `compliance_audit` schema is append-only; no audit record is modified or deleted after creation; audit records survive the operational deletions they document
* Application service accounts MUST NOT have INSERT, UPDATE, or DELETE privileges on the `compliance_audit` schema; only a dedicated compliance pathway service account has write access

---

### 4.8 Historical Reproducibility

* A report generated for month M using snapshot data MUST produce identical output regardless of when it is run and who runs it
* Snapshots are self-contained: all fields required to render a report are captured at snapshot time; no live table joins are permitted at report generation time
* Snapshot schema changes require a versioning mechanism: new columns are nullable with defaults; prior snapshots remain valid and renderable
* Report template changes that would alter historical output MUST create a new template version; existing reports reference their original template version

---

#### Snapshot Reproducibility Fingerprint

The Snapshot Reproducibility Fingerprint is a first-class concept in the SSIP data model. Every finalized snapshot carries a fingerprint that captures the complete versioned context under which the snapshot was generated. The fingerprint enables future auditors to determine exactly which rules, models, and templates produced any given historical report without requiring live interrogation of current system state.

**Fingerprint components:**

| Component | Description |
|---|---|
| `schema_version` | Version of the snapshot row schema (column definitions) at generation time |
| `configuration_registry_version` | Version of the Configuration Version Registry active at snapshot generation time (see Section 12.8) |
| `ai_prompt_version` | Map of insight type → prompt version used to generate each AI summary captured in the snapshot |
| `ai_model_version` | Map of insight type → AI model identifier used to generate each AI summary |
| `report_template_version` | Version of the report template active when the snapshot was first used to generate a report |

**Fingerprint guarantees:**

* A finalized snapshot's fingerprint is immutable; it is set at finalization time and MUST NOT be modified after finalization
* Historical report regeneration logs the source snapshot's fingerprint alongside the regeneration audit entry
* If a regenerated report's source snapshot fingerprint differs from the original report's source snapshot fingerprint, the mismatch is logged as an audit warning; the report is marked `POTENTIALLY_DIVERGENT` from the original
* If any fingerprint component version is unknown at finalization time (e.g., Configuration Version Registry not yet implemented), it is recorded as `UNKNOWN_V0` to preserve fingerprint structure; this does not block snapshot finalization

---

## 5. ASSUMPTIONS

---

ASSUMPTION: GHL handles all outreach execution
Alternative: Backend-controlled communication layer

ASSUMPTION: LLM provider returns structured output reliably; rate limits and timeouts are possible
Alternative: Implement fallback to last cached insight on provider failure

ASSUMPTION: Transcript is available post-call; may not be available for all call outcomes
Alternative: Gracefully handle missing transcript; sentiment analysis is skipped, not errored

ASSUMPTION: SQL Server schema for `AI_ChatBot_TriggerData` is stable with respect to column removals; additive changes (new columns) may occur without advance notice
Alternative: Implement schema drift detection and column-level fallbacks (already designed in 3.10)

ASSUMPTION: Month-end is the last calendar day of each month; snapshot generation triggers on the 1st of the following month at a configured time; this cutoff is configurable
Alternative: Business-defined fiscal month-end date

ASSUMPTION: GHL message sync retrieves all messages via the GHL API, including messages not originated by this platform; completeness of GHL message history is subject to GHL API capabilities
Alternative: Unified timeline reflects only platform-originated messages if GHL API cannot provide full history

ASSUMPTION: Placement readiness data is derivable from fields already available in SQL Server (interview prep, portfolio flags, section name); no external placement tracking system integration is required in the current phase
Alternative: Integrate a separate placement tracking system in a future phase

ASSUMPTION: Access revocation and restoration events originate from SQL Server operational tables; the platform mirrors these events; the authoritative source is SQL Server
Alternative: A future phase may introduce platform-owned access management extensions

ASSUMPTION: Mentor assignment follows a 1:N model with one primary mentor, one optional super mentor, and one optional instructor per student; at most one active assignment per role at any time; management is external to the platform initially
Alternative: Build in-platform mentor assignment management in a future phase

ASSUMPTION: Financial data sourced from SQL Server represents the complete payment record; no independent verification against an external payment processor is required in the current phase
Alternative: Integrate a payment processor API for independent reconciliation in a future phase

---

## 6. CONSTRAINTS

---

* Must be local-first deployable; must be Azure-ready
* SQL Server is READ-ONLY; any write to SQL Server by this platform is a critical defect
* Must not modify any source table in SQL Server
* Must enforce deterministic logic; LLM outputs are advisory, never authoritative for eligibility or state transitions
* PostgreSQL is the exclusively owned database for all platform-generated data, AI outputs, snapshots, and reports
* Operational and reporting concerns MUST occupy separate database schemas (`public` and `warehouse`)
* Compliance audit records MUST occupy a logically isolated schema (`compliance_audit`); no operational or warehouse code paths may write to this schema
* Snapshot tables are append-only; update and delete operations are prohibited at the application layer; compliance-governed deletion requires the Compliance Governance Pathway (Section 4.7)
* Snapshot AI content MUST be stored as physical point-in-time text copies in snapshot rows; live references or foreign key references to `ai_insights` records in snapshot tables are prohibited
* Trend interpretation for historical reports MUST use finalized snapshot data exclusively; live SQL Server mirror data MUST NOT be used for historical trend analytics
* Configuration rule changes are prospective only; they MUST NOT retroactively modify finalized snapshots, published reports, or historical cohort classification records
* SQL Server-mirrored access state is authoritative for operational eligibility decisions; platform-originated access events are supplementary context only
* LLM prompts MUST NOT contain PII; only anonymized student metrics and program context are permitted
* Historical reports MUST be generated from snapshot data alone; live table queries at report generation time are prohibited
* Role-based access control is mandatory for any multi-user deployment; unauthenticated access to student data is prohibited
* Cohort identification thresholds, scoring formulas, and risk thresholds are configurable; they must not be hardcoded in business logic
* Communication provider (GHL) is configurable; the platform must not be architecturally coupled to a single provider

---

## 7. EDGE CASES

---

* Missing contact information — student excluded from outreach; alert surfaced
* GHL trigger failure — logged; retry scheduled; no duplicate trigger
* Transcript missing — sentiment analysis skipped; outreach record remains valid
* LLM invalid response — retry up to 2 times; fallback to last valid cached insight; staleness flag set
* Duplicate scheduler execution — idempotency keys prevent duplicate records for all scheduler-managed operations
* Student becomes ineligible mid-cycle — state machine handles gracefully; no redundant outreach
* SQL Server unreachable at sync time — cached mirror data served; CRITICAL alert raised; sync retried on next cycle
* SQL Server schema drift at sync time — partial sync proceeds on intact columns; drift logged; operator alerted
* Month-end snapshot job interrupted mid-run — job resumes from last successful student checkpoint; no duplicate finalized snapshots created
* Student has no activity in snapshot month — snapshot created with zero-activity metrics; student not silently excluded
* Bundle deal payment detected with inconsistent credit and payment fields — platform computes actual balance; record flagged for operator review
* Historical report requested for a month before snapshots were introduced — `NOT_AVAILABLE` returned; no fallback to live data
* AI insight generation fails after max retries — last valid cached insight served with `stale: true`; failure logged with correlation ID
* Student has no mentor assignment — student visible to operators only; no error surfaced to mentor endpoints
* Two snapshot jobs for the same month triggered concurrently — idempotency key prevents duplicate finalized rows; second job exits cleanly
* GHL message sync returns a message for an unrecognized student ID — stored with NULL user reference; flagged for manual review
* Cohort threshold configuration is updated mid-month — reclassification runs on next daily job; prior cohort records are retained as history; new classification is appended; finalized snapshots already taken this month are not retroactively affected
* LLM provider is switched (configurable) — prior insights retain the `model_used` attribution from the original generation; new insights use the new provider; finalized snapshot AI content is unaffected by the provider change
* Compliance deletion request received while snapshot is in DRAFT state — draft is discarded without invoking the Compliance Governance Pathway; a discard audit entry is created in the compliance audit area documenting the student ID, discard timestamp, and rationale; the student is treated as if no snapshot was taken for that month
* Historical trend interpretation requested for a period prior to snapshot introduction — trend interpretation returns `NOT_AVAILABLE` for the historical period; no live data fallback; trend analysis covers only periods with available finalized snapshots
* Snapshot Reproducibility Fingerprint mismatch detected during historical report regeneration — regeneration completes using stored snapshot data; mismatch is logged as an audit warning with both fingerprints (original and current); operator is notified; regenerated report is marked `POTENTIALLY_DIVERGENT`
* Compliance action executed on a student whose snapshot contributed to published aggregate cohort reports — compliance deletion proceeds on the student-level snapshot; published aggregate report statistics are not retroactively recalculated; the report record is annotated with a compliance-action flag indicating that a student's records were removed after original publication
* Configuration Version Registry version active at snapshot time is later purged or unavailable — fingerprint notes the version as `ARCHIVED`; report regeneration proceeds using stored snapshot data; a warning is logged; the missing version is an audit concern, not a blocking error

---

## 8. SUCCESS CRITERIA

---

System is successful when:

* Outreach runs daily without failure; no duplicate outreach occurs; decisions are deterministic
* Meetings are booked correctly and associated with student records
* Dashboard accurately reflects real-time operational state for operators and filtered state for mentors
* Monthly snapshots are generated automatically with zero manual intervention
* Historical reports for any prior month are reproducible and output-identical across regenerations
* AI insights are available for every active student within 24 hours of the nightly job
* Operators can identify and act on the top 10 at-risk students in under 30 seconds
* Mentors can review their assigned students' full lifecycle and engagement history without contacting operations
* Payment reconciliation discrepancies are surfaced automatically; operators do not discover them manually
* SQL Server sync failures are detected and alerted within 5 minutes
* Cohort membership is correctly computed for CAP, Launch, and Placement Hopefuls using the configured rules
* Access revocation events from SQL Server are mirrored and visible in the access history timeline within one sync cycle

---

## 9. AI AUGMENTATION RESPONSIBILITIES

AI is an augmentation layer. It is never the final authority on student state, eligibility, financial decisions, or historical records.

---

### 9.1 Responsibilities

| Responsibility | Trigger | Output Storage |
|---|---|---|
| **Transcript summarization** | Post-call transcript stored | `outreach_history.llm_analysis` |
| **Sentiment analysis** | Post-call or post-GHL sync | `outreach_history.llm_analysis`; rolled up to `communication_sentiment` insight |
| **Risk summarization** | Daily for all active students | `ai_insights` (type: `risk_summary`) |
| **Progress summarization** | Daily for students on active program | `ai_insights` (type: `progress_summary`) |
| **Intervention recommendation** | Post-outreach + on-demand | `ai_insights` (type: `intervention_recommendation`) |
| **Trend interpretation** | Weekly or on-demand | `ai_insights` (type: `trend_interpretation`) |
| **Operator assistance** | On-demand via dashboard quick action | Real-time; persisted to `ai_insights` only if operator saves |
| **Monthly narrative generation** | Month-end scheduler | Stored in monthly snapshot + report record |
| **Communication sentiment aggregation** | Post GHL-sync | `ai_insights` (type: `communication_sentiment`) |

---

### 9.2 Explicit Non-Responsibilities

The AI layer MUST NOT:

* Autonomously change any student state in the database
* Autonomously trigger any financial action (payments, fee assessments, refunds)
* Overwrite or bypass deterministic eligibility or decision rules
* Mutate a historical snapshot or published report after finalization
* Expose PII in prompt construction; prompts use only anonymized metrics and program context
* Replace operator or mentor judgment; all AI output is advisory

---

### 9.3 AI Output Quality and Validation

* All structured AI outputs are validated against the declared output schema before storage; invalid outputs trigger up to 2 retries
* After max retries, the last valid cached insight is served with a `stale: true` flag
* AI output schema changes require a versioned migration; old records are not invalidated and remain readable

---

### 9.4 AI Output Governance Properties

Every stored AI output MUST carry the following metadata:

| Property | Description |
|---|---|
| **Versioned** | Each generation creates a new record; prior versions are retained in history |
| **Attributable** | `model_used`, `prompt_version`, `generated_at` stored on every record |
| **Reviewable** | Full insight record including metadata is accessible via the AI insights API |
| **Reproducible** | Same input metrics + same prompt version → same output (within LLM non-determinism tolerance) |
| **Snapshot-isolated** | AI outputs captured in finalized snapshots are physical point-in-time text copies; they are NOT live references to `ai_insights` rows; subsequent regeneration, force-refresh, or provider changes MUST NOT alter finalized snapshot AI content (see FAD-1) |

---

## 10. SYSTEM LAYERS & SEPARATION OF CONCERNS

---

| Concern | Owned By | Storage | Update Pattern |
|---|---|---|---|
| **Source student data** | SQL Server (read-only) | SQL Server; mirrored to PostgreSQL `public` | Synced read-only; no platform writes |
| **Operational outreach state** | Platform | PostgreSQL `public` | Mutable; state machine governs transitions |
| **GHL communication records** | Platform | PostgreSQL `public` | Append-only on sync |
| **Campaign activity** | Platform | PostgreSQL `public` | Append-only on record |
| **Access history events** | SQL Server (source) + Platform (extensions) | PostgreSQL `public` | Append-only mirror + platform extensions |
| **AI insights** | Platform | PostgreSQL `public` | Append + TTL-based staleness flag; prior versions retained |
| **Operator / mentor notes** | Platform | PostgreSQL `public` | Mutable; author and timestamp recorded |
| **Monthly snapshots** | Platform | PostgreSQL `warehouse` | Append-only; immutable after finalization |
| **Historical reports** | Platform | PostgreSQL `warehouse` | Append-only; versioned; immutable after publication |

---

### Operational Outreach

Identity: GHL-integrated outreach automation subsystem.
Concerns: eligibility classification, state machine transitions, GHL trigger, retry logic, shadow/live mode.
Bounded scope: `student_outreach_tracking`, `outreach_history`, `state_transition_log`.

### Operational Intelligence

Identity: Real-time student intelligence layer.
Concerns: priority scoring, risk classification, lifecycle tracking, cohort membership, payment reconciliation, placement readiness, communication telemetry.
Bounded scope: SQL Server mirror + platform-generated operational records.

### Reporting Intelligence

Identity: Immutable historical record and enterprise reporting layer.
Concerns: monthly snapshots, historical reports, longitudinal analytics, cohort trends.
Bounded scope: `warehouse` schema — append-only; no live table joins at report generation time.

### AI Augmentation

Identity: Advisory intelligence layer.
Concerns: insight generation, sentiment analysis, trend interpretation, narrative generation, intervention recommendations.
Bounded scope: `ai_insights` table; prompts use non-PII metrics only; all outputs are versioned and attributable.

### Future Automation

Identity: Not yet implemented.
Concerns: mentor assignment automation, payment escalation automation, placement pipeline automation.
Bounded scope: Requires explicit business requirement sign-off before any implementation begins.

---

## 11. RESOLVED AND OPEN BUSINESS ASSUMPTIONS

---

### 11.1 Resolved Assumptions

| # | Original Assumption | Resolution | Authority |
|---|---|---|---|
| U-1 | CAP / Launch / Placement hopeful cohorts cannot be auto-derived | **RESOLVED.** Explicit SQL-derived heuristic rules now defined in Section 2.4. Rules are configurable and marked as operational heuristics. | Architecture decision |
| U-3 | Access revocation/restoration source is unclear (platform vs. SQL Server) | **RESOLVED.** Events originate from SQL Server operational tables. Platform mirrors them into PostgreSQL. Platform does not own the authoritative source initially. Platform-owned extensions are a future-phase option. | Architecture decision |
| U-5 | Mentor assignment model unclear (1:N vs. M:N) | **RESOLVED.** Current model: one primary mentor per student, one optional super mentor, one optional instructor. At most one active assignment per role per student. Future evolution to M:N history-based model must not require breaking schema change. | Architecture decision |
| D-1 | When a configuration threshold changes, do historical snapshots and cohort classifications change retroactively? | **RESOLVED.** Configuration changes are prospective only. Historical snapshots, finalized reports, and prior cohort classification records are immutable and remain attributed to the configuration version that generated them. Reclassification runs only from the next execution forward. | FAD-3 |
| D-3 | If SQL Server shows access as REVOKED and the platform has a manual restoration event with no SQL Server confirmation, what is the operational access status? | **RESOLVED.** SQL Server-mirrored state is authoritative for operational access status and eligibility decisions. Platform-originated access events are contextual additions displayed in the timeline but do not override SQL Server state for operational purposes. | FAD-5 |
| D-4 | Are AI outputs in snapshots stored as physical copies or as live references to `ai_insights` records? | **RESOLVED.** Physical copy semantics. Snapshot rows physically embed AI-generated text at finalization time. No live references to `ai_insights` rows. Post-finalization AI regeneration has no effect on snapshot AI content. | FAD-1 |
| D-5 | Where is the audit trail for compliance-driven deletions stored? | **RESOLVED.** Logically isolated compliance audit area, initially in PostgreSQL as a dedicated `compliance_audit` schema with no foreign key dependencies on operational or warehouse schemas. Audit records are append-only and survive the deletion they audit. | FAD-4 |
| D-6 | Does trend interpretation for historical reports use live data or snapshot data? | **RESOLVED.** Historical trend interpretation uses finalized snapshot data exclusively. Live SQL Server mirror data is not used for historical trend analytics, preserving full reproducibility. | FAD-2 |

---

### 11.2 Remaining Open Assumptions

These assumptions require external input before dependent features can be built. Each is classified by the type of input required.

| # | Open Assumption | Dependent Features | Decision Needed From | Urgency | Category |
|---|---|---|---|---|---|
| U-4 | "Month-end" default cutoff: is last calendar day of month correct? What happens for students enrolled on the final day of a month? | Monthly snapshot trigger, report period boundaries | Product / Operations | HIGH — needed before snapshot scheduler goes live (not a warehouse schema blocker) | Business-owner |
| U-6 | Is SQL Server the complete financial record? No external payment processor (Stripe, etc.) needs to be reconciled? | Payment intelligence scope, HIGH risk alerting completeness | Finance / Operations | HIGH — determines scope of payment intelligence STANDARD tier | Business-owner |
| U-7 | Is the AI monthly narrative for internal operator use only, or is any version delivered to students or external stakeholders? | Narrative prompt design, PII policies, tone guidelines | Product / Legal | MEDIUM — needed before monthly narrative generation is built | Business-owner |
| U-8 | Does the GHL API provide complete message history including messages not initiated by this platform? What is the API's lookback limit? | Unified communication telemetry completeness, channel analytics accuracy | Engineering (GHL API audit required) | HIGH — determines whether unified timeline is complete or partial | Implementation |
| U-9 | What is the snapshot retention policy? Are there FERPA or contract-based requirements to delete student records after a defined period? | Compliance scope manifest, compliance_audit schema scope, warehouse schema retention design | Legal / Compliance | HIGH — must be resolved before first production snapshot is finalized; does NOT block warehouse schema creation | Business-owner / Legal |
| U-10 | Is UserID a reliable 1:1 key across SQL Server, GHL, and the platform? Are there known cases of duplicate or merged student records? | Unified communication timeline accuracy, deduplication layer requirement | Engineering / IT | HIGH — if UserID is not reliable, unified timeline cannot be trusted without a deduplication layer | Implementation |
| D-2 | Who provides the super mentor → supervised mentor supervision graph, and via what mechanism? Is it the same external assignment management interface as student assignments or a separate input? | Super mentor RBAC enforcement, transitive roster visibility, Assignment Hierarchy Model | Engineering / Operations | HIGH — must be resolved before PRODUCTION-tier RBAC is implemented; does NOT block STANDARD tier | Implementation |

---

## 12. CONFIGURABLE OPERATIONAL RULES

The following values and rules MUST be externalized from business logic into a configurable rule store. No implementation may hardcode these values. Any change to a configurable rule must be documented as an operational decision.

---

### 12.1 Cohort Identification Thresholds

| Rule | Default Value | Notes |
|---|---|---|
| CAP Hopeful: minimum PerComp_Act | 0.30 | Derived from SQL report heuristic |
| Launch Hopeful: minimum PerComp_Act | 0.59 | Derived from SQL report heuristic |
| CAP Hopeful: section name exclusion patterns | `%launch%`, `%CAP%` | Depends on SQL Server curriculum naming conventions |
| Launch Hopeful: section inclusion pattern | `%CAP%` | Depends on SQL Server curriculum naming conventions |
| Placement Hopeful: section inclusion pattern | `%launch%` | Depends on SQL Server curriculum naming conventions |

---

### 12.2 Homework Risk Thresholds

| Rule | Default Value |
|---|---|
| AT_RISK: minimum HWsBehind | 1 |
| AT_RISK: maximum AvgEffRating | 3.0 |
| CRITICAL: minimum HWsBehind | 3 |
| CRITICAL: maximum AvgEffRating | 2.0 |

---

### 12.3 Payment Risk Thresholds

| Rule | Default Value |
|---|---|
| MEDIUM threshold (lower bound) | $0.01 |
| HIGH threshold (lower bound) | $1,000.00 |
| Payment deviation alert threshold | Configurable; default TBD |

---

### 12.4 Priority Scoring Formula

The additive priority score (0–135) used by the outreach eligibility engine is configurable:

| Component | Default Weight | Default Cap |
|---|---|---|
| HWsBehind × weight | ×10 | 50 |
| EffRating deficit × weight | ×7 | 35 |
| InactivityDays × weight | ×2 | 50 |

---

### 12.5 Operational Scheduling and Timing

| Rule | Default Value |
|---|---|
| Month-end snapshot trigger time | 1st of following month, 02:00 local |
| AI insight TTL (default) | 24 hours |
| Outreach retry window | 3 days |
| Placement Hopeful inactivity alert threshold | 7 days |
| Access revocation unresolved alert threshold | 48 hours |

---

### 12.6 Provider Selection

| Component | Default Provider | Notes |
|---|---|---|
| AI / LLM provider | Configurable (currently Anthropic / OpenAI) | Prompt versioning must account for provider changes |
| Outreach / communication provider | GHL (GoHighLevel) | Communication layer abstracted for future provider substitution |

---

### 12.7 Report and Template Versioning

* Report templates are versioned; each monthly report records the template version used at generation time
* Prompt versions are stored with every AI insight; changing a prompt creates a new prompt version, not a modification of an existing one
* Mentor hierarchy model configuration (role labels, assignment depth) is externalized for future evolution

---

### 12.8 Configuration Version Registry

The Configuration Version Registry is a platform-managed, append-only record of all changes to configurable operational rules. It gives every classification run, snapshot, and AI insight generation a verifiable historical anchor in the Snapshot Reproducibility Fingerprint (Section 4.8).

---

#### Governance Principles

* Every change to any value in Sections 12.1–12.7 creates a new version record; the prior version is retained and never overwritten or modified
* Version records are append-only; no existing version record is modified after creation
* A version change requires a documented operational decision and authorization before the new version is activated; undocumented changes are prohibited
* The registry records both the proposing identity and the activating identity
* Configuration changes are **prospective only**: historical snapshots, finalized reports, and prior cohort classification records remain attributed to the version active when they were generated (see FAD-3)

---

#### Version Record Fields (conceptual)

| Field | Description |
|---|---|
| version_id | Unique version identifier (monotonically increasing) |
| effective_from | Timestamp when this version became the active version |
| activated_by | Identity of the operator who activated this version |
| change_rationale | Required free-text description of why this change was made |
| rule_set_snapshot | Complete snapshot of all configurable rule values at this version (not just the diff) |
| prior_version_id | Reference to the immediately preceding version |

---

#### Lifecycle of a Configuration Change

1. **Propose:** operator documents the proposed change with rationale
2. **Review:** change is reviewed and approved by designated authority
3. **Activate:** new version record is created in the registry; activation timestamp is recorded
4. **Classify:** next classification run uses the new version; prior runs attributed to the old version remain unchanged
5. **Snapshot:** next monthly snapshot captures the active version in its fingerprint
6. **Audit:** version history is queryable; any classification run or snapshot can be traced to its active version

---

#### Acceptance Criteria

* **Given** a configurable threshold is changed
* **When** a new version is created in the registry
* **Then** all subsequent classification runs use the new version; all prior snapshots retain their original version attribution unchanged

* **Given** a historical snapshot is queried with its Reproducibility Fingerprint
* **When** the `configuration_registry_version` in the fingerprint is looked up
* **Then** the complete rule set active at snapshot generation time is retrievable

---

## 13. FINALIZED ARCHITECTURE DECISIONS

These decisions are authoritative and binding. They resolve the architecture-blocking open questions identified during the harmonization analysis and provide the foundation for warehouse schema design. No implementation may contradict these decisions without explicit re-opening and documented resolution.

---

### FAD-1 — Snapshot AI Content: Physical Copy Semantics

**Decision:** Finalized snapshots physically store AI-generated summaries and narratives as point-in-time text. Snapshots do NOT store live references or foreign key references to `ai_insights` rows. Post-finalization AI regeneration, force-refresh, or LLM provider changes MUST NOT mutate historical snapshots.

**Rationale:** Historical reproducibility is prioritized over storage minimization. A reproducibility guarantee for historical reports including AI content cannot be satisfied by reference semantics, because the referenced `ai_insights` record may have been updated, versioned, or deleted by the time of regeneration.

**Resolves:** D-4

**Implementation implications:**
- Snapshot warehouse table columns must include AI text fields (risk_summary_text, progress_summary_text, monthly_narrative_text) as text storage, not foreign keys
- Snapshot row size grows proportionally with AI text length; benchmark representative output lengths before finalizing schema
- Compliance deletion of an `ai_insights` record does not orphan snapshot AI content (no FK dependency exists to orphan)

---

### FAD-2 — Historical Trend Interpretation: Snapshot Data Only

**Decision:** Trend analytics for historical reports derive exclusively from immutable finalized snapshots. Live SQL Server mirror data is not used for historical trend regeneration. Historical reports remain reproducible regardless of subsequent changes to operational data.

**Rationale:** Trend interpretation that queries live operational data produces different results when regenerated on different dates, violating the Historical Reproducibility guarantee in Section 4.8. Snapshot data provides the only stable foundation for reproducible historical analytics.

**Resolves:** D-6

**Implementation implications:**
- Trend interpretation service must support a `historical_mode` flag that restricts input data to snapshots at or before the target month
- Trend interpretation for current (non-historical) use may continue to use live data; the two modes are distinct code paths
- A minimum snapshot history depth (to be determined by the product team) must exist before trend interpretation can be computed; the platform must return `INSUFFICIENT_HISTORY` when fewer than the required months of snapshots are available

---

### FAD-3 — Configuration Changes: Prospective Only

**Decision:** Configuration Version Registry changes affect future classification runs only. Historical snapshots retain their original `configuration_registry_version` attribution. Finalized reports and prior cohort classification records are immutable with respect to configuration changes. Retroactive reprocessing under a new configuration version is prohibited.

**Rationale:** Retroactive reclassification would invalidate historical records and undermine the trust of archived reports. The append-only philosophy applies to configuration versions precisely as it applies to snapshot rows — past data reflects the rules that governed it at the time.

**Resolves:** D-1

**Implementation implications:**
- Configuration changes must not trigger retroactive reprocessing of any historical data
- The Configuration Version Registry activates a new version at a defined timestamp; all runs after that timestamp use the new version
- Any migration or backfill that reprocesses historical records under a new configuration version requires explicit business owner sign-off and a compliance audit entry

---

### FAD-4 — Compliance Auditability: Separate Append-Only Compliance Audit Area

**Decision:** Compliance deletion and anonymization actions require an audit trail in a logically isolated compliance audit area. Initial implementation resides within PostgreSQL as a `compliance_audit` schema with no foreign key dependencies on operational or warehouse schemas. Compliance audit records survive the operational deletions they document.

**Required audit fields:** authorization_timestamp, authorized_by, executed_by, affected_student_id, affected_tables (list), action_type (DELETE or ANONYMIZE), audit_rationale, affected_record_count

**Rationale:** An audit trail that can itself be deleted by the same operation it documents provides no compliance assurance. Logical isolation (separate schema, no FK coupling) ensures audit records remain intact after the deletion completes. A future evolution may move the compliance audit area to an external compliance system (object storage, dedicated audit service); the logical isolation design accommodates this without architectural change.

**Resolves:** D-5

**Implementation implications:**
- `compliance_audit` schema must be created in the same Alembic migration as the `warehouse` schema (Step 1 of the dependency sequence)
- Application service accounts must NOT have write privileges on `compliance_audit`; only a dedicated compliance pathway service account may write audit records
- The compliance scope manifest (which tables are in scope for compliance deletion per record type) must be defined as a living operational document and reviewed when any new table storing student-identifiable data is introduced

---

### FAD-5 — Access Event Authority: SQL Server Authoritative for Current State

**Decision:** SQL Server is the authoritative source for a student's current access status for all eligibility decisions, outreach gating, and operational alerts. Platform-originated access events (`platform_manual`, `platform_system`) are contextual supplementary records displayed in the timeline with clear source attribution. They do NOT override SQL Server-mirrored state for operational purposes unless platform-owned access control is explicitly introduced as a separate and approved architectural decision.

**Rationale:** The platform does not write to SQL Server. SQL Server may be updated by processes outside the platform's visibility. Using platform events to override SQL Server state without a confirmed bidirectional synchronization channel would create operationally divergent decisions based on unverified platform-side state.

**Resolves:** D-3

**Implementation implications:**
- Dashboard display of "current access status" must use the most recent `mirrored_sql_server` event, not the most recent event regardless of origin
- Platform access event types (`platform_manual`, `platform_system`) are introduced only when a specific platform access management capability is designed and explicitly approved; they are not speculative placeholder features
- Access history timeline UI must display `origin_source` clearly so operators can distinguish SQL Server-authoritative events from platform-supplementary events

---

### FAD-6 — Snapshot Reproducibility Fingerprint: First-Class Concept

**Decision:** Every finalized snapshot carries a Snapshot Reproducibility Fingerprint comprising five components: `schema_version`, `configuration_registry_version`, `ai_prompt_version` (per insight type), `ai_model_version` (per insight type), `report_template_version`. The fingerprint is immutable after snapshot finalization and is included in all historical report regeneration audit log entries.

**Rationale:** Historical explainability requires that future auditors can determine exactly which rules, models, and templates produced any given historical report. The fingerprint is the complete answer to the question "what governed the generation of this snapshot?" without requiring live interrogation of current system state — which may have changed.

**Resolves:** Identified as a new first-class architectural requirement during the harmonization analysis.

**Implementation implications:**
- All five fingerprint components must be known and available at snapshot finalization time
- If any component version is unknown at finalization (e.g., Configuration Version Registry not yet implemented), the unknown component is recorded as `UNKNOWN_V0` to preserve fingerprint structure without blocking finalization
- Fingerprint mismatch during regeneration (current system versions differ from fingerprint) is a warning with logging, not a blocking error; regeneration proceeds using stored snapshot data

---

## 14. ARCHITECTURE READINESS ASSESSMENT

### 14.1 Warehouse Schema Design: Readiness Status

**Assessment: READY — warehouse schema design may begin. All architecture-blocking decisions are resolved.**

---

#### Resolved blockers

| Blocker | Decision | Status |
|---|---|---|
| Snapshot AI content storage model | Physical copy semantics (FAD-1) | ✓ RESOLVED |
| Historical trend data source | Snapshot data only (FAD-2) | ✓ RESOLVED |
| Configuration version change semantics | Prospective only (FAD-3) | ✓ RESOLVED |
| Compliance audit trail architecture | Separate `compliance_audit` schema (FAD-4) | ✓ RESOLVED |
| Access event authority model | SQL Server authoritative for current state (FAD-5) | ✓ RESOLVED |
| Reproducibility fingerprint concept | First-class fingerprint (FAD-6) | ✓ RESOLVED |
| D-1: threshold change retroactivity | Prospective only | ✓ RESOLVED |
| D-3: access event conflict resolution | SQL Server wins for operational state | ✓ RESOLVED |
| D-4: snapshot AI copy semantics | Physical text copy | ✓ RESOLVED |
| D-5: compliance audit location | `compliance_audit` schema | ✓ RESOLVED |
| D-6: trend interpretation data source | Snapshot data only | ✓ RESOLVED |

---

#### Provisional decisions for warehouse schema (acceptable defaults; review when resolved)

| Assumption | Provisional Default | Schema Risk if Wrong |
|---|---|---|
| U-4: Month-end cutoff definition | Last calendar day of month | **Low** — configurable at scheduler level; schema column types unaffected |
| U-9: Snapshot retention period | Retain indefinitely; deletion policy TBD | **Medium** — `compliance_audit` schema is built regardless; scope manifest may need expansion when U-9 is resolved |

---

#### Open items that do NOT block warehouse schema design

These must be resolved before their dependent feature tiers are implemented but do not affect the warehouse schema itself.

| Item | Category | Feature Dependency | When to Resolve |
|---|---|---|---|
| U-6: Financial data completeness | Business-owner | Payment intelligence STANDARD tier | Before STANDARD payment features |
| U-7: AI narrative audience | Business-owner | Monthly narrative prompt design | Before monthly narrative generation |
| U-8: GHL API history coverage | Implementation | Communication telemetry PRODUCTION tier | Before unified timeline PRODUCTION tier |
| U-10: UserID cross-system reliability | Implementation | Unified timeline deduplication | Before communication telemetry STANDARD tier |
| D-2: Super mentor supervision graph | Implementation | PRODUCTION-tier RBAC for super mentor | Before PRODUCTION multi-role deployment |

---

### 14.2 Dependency Sequencing (Authoritative)

This sequencing supersedes all prior provisional sequencing.

**Step 1 — Warehouse and compliance schemas (now unblocked):**
Write `alembic/versions/0002_warehouse_schema.py`
- New schema: `warehouse` (append-only; SELECT-only for application service accounts)
- New tables: `warehouse.student_snapshots` (with all Fingerprint columns and inline AI text fields), `warehouse.monthly_reports`, `warehouse.report_audit_log`
- New schema: `compliance_audit` (append-only; restricted write access)
- New table: `compliance_audit.deletion_log`

**Step 2 — Configuration Version Registry (concurrent with Step 1 or immediately after):**
Write `alembic/versions/0003_config_version_registry.py`
- New table: `public.config_version_registry` (append-only version records)
- Populate seed record capturing all current Section 12 default values as version `V1`
- Service: `app/services/config_registry.py` — `get_active_version()`, `create_version()`

**Step 3 — Snapshot scheduler service (after Steps 1 and 2):**
Design `app/services/snapshot.py`
- Requires: warehouse schema (Step 1), config registry (Step 2), `ai_insights` service (already exists)
- Month-end trigger via APScheduler; draft → finalized two-phase; fingerprint computed at finalization
- Prerequisite gate: U-4 (month-end definition) and U-9 (retention policy) must be resolved before Step 3 goes to production

**Step 4 — Historical report generation (after Step 3):**
Design `app/routers/reports.py`, `app/services/trend_interpretation.py` (historical mode)
- Requires: finalized snapshots; no live data queries at report time
- Trend analytics module uses snapshot-only data path

**Step 5 — Compliance pathway implementation (prerequisite for Step 3 go-live):**
`compliance_audit` schema created in Step 1; service design for compliance pathway
- Compliance scope manifest defined as a living operational document
- Required before first production snapshot is finalized

---

### 14.3 Outstanding Risk Register

| Risk | Severity | Mitigation |
|---|---|---|
| U-9 unresolved at snapshot go-live | **HIGH** — first production snapshot creates immutable records without a defined deletion scope | Escalate U-9 to Legal/Compliance immediately; resolve before Step 3 goes to production |
| U-10 UserID unreliability | **HIGH** — unified timeline may have attribution errors or duplicates | Conduct cross-system UserID audit before STANDARD-tier timeline; design deduplication layer if audit reveals mismatches |
| D-2 super mentor supervision graph undefined | **HIGH** for PRODUCTION RBAC | Acceptable at STANDARD tier (primary mentor only); must resolve before PRODUCTION deployment |
| AI text volume in snapshots (FAD-1 physical copy) | **Medium** — inline text inflates snapshot row size | Benchmark representative AI output lengths before finalizing warehouse schema column types; evaluate a linked AI snapshot content table if row size exceeds acceptable threshold |
| Compliance scope manifest incomplete at first compliance request | **Medium** — scope may omit newly added tables | Mandate compliance scope manifest review as a Definition of Done item for every new table storing student-identifiable data |

---

## END OF FILE
