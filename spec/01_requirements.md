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

## 12. CONFIG GOVERNANCE CATALOG

This section is the **authoritative canonical source** for all configurable operational rules in the Student Success Intelligence Platform. All directives, orchestration engines, rule-evaluation services, and migration seeds derive their variable names and default values exclusively from this catalog. Hardcoding any value defined here is a specification violation.

This catalog supersedes the V1 threshold table (previous Sections 12.1–12.8). It introduces the V2 governance model with formal variable classification, replay-safe semantics, and a complete supersession architecture.

---

### 12.1 Config V2 Governance Semantics

These semantics govern all records in the `config_version_registry` table regardless of version number.

---

#### 12.1.1 V1 Immutability

* The V1 record seeded by migration `0003_config_version_registry` is permanently immutable
* No column value in the V1 row may be modified after the migration completes
* V1 status transitions: `ACTIVE → SUPERSEDED` (when V2 activates); `SUPERSEDED → ARCHIVED` (after retention threshold)
* V1 is never deleted; it is permanently queryable for historical fingerprint lookups

---

#### 12.1.2 Append-Only Evolution

* Every configuration change creates a **new version record**; the prior record is never overwritten or modified
* New records enter at `PROPOSED` status; they advance through the supersession lifecycle before activation
* A version record is immutable after it reaches `ACTIVE` status
* The chain `prior_version_id → prior_version_id → …` is complete and linked back to V1 with no gaps

---

#### 12.1.3 Exactly-One-ACTIVE Invariant

* Exactly one version record has `status = 'ACTIVE'` at all times in the `config_version_registry`
* Enforced by the partial unique index: `CREATE UNIQUE INDEX uq_cvr_active_singleton ON config_version_registry ((1)) WHERE status = 'ACTIVE'`
* The atomic swap (`APPROVED → ACTIVE` for new; `ACTIVE → SUPERSEDED` for prior) is executed in a single transaction — there is no window where zero or two versions are simultaneously ACTIVE
* Any code path that attempts to produce zero or two ACTIVE versions is a governance defect

---

#### 12.1.4 Prospective-Only Activation

* A new ACTIVE version affects only classification runs, snapshot generations, and AI insight generations that begin **after** the activation timestamp (`effective_from`)
* Historical snapshots retain the `configuration_registry_version` fingerprint component from the version that was ACTIVE at their `DRAFT → VALIDATING` content lock time
* Activation of a new version MUST NOT trigger reprocessing of any historical snapshots, finalized reports, or prior cohort classification records
* Any backfill or migration that reprocesses historical data under a new version requires explicit business owner sign-off and a `compliance_audit` entry

---

#### 12.1.5 Rollback Prohibition

* Transitioning a `SUPERSEDED` or `ARCHIVED` version back to `ACTIVE` is **explicitly forbidden**
* `SUPERSEDED → ACTIVE` is an invalid state transition (see Domain 5 in `spec/03_state_transition_rules.md` §31.1)
* If a configuration error is discovered post-activation, the only lawful correction path is: create a new `PROPOSED` record with the corrected values → full supersession lifecycle → activate the new version
* Historical snapshots generated under an erroneous version retain their attribution to that version permanently; retroactive correction is not permitted

---

#### 12.1.6 Lineage Preservation

* Every version record carries `prior_version_id` linking it to its predecessor
* The lineage chain is queryable from any version back to V1
* `SUPERSEDED` and `ARCHIVED` records are permanently retained; no application code or scheduled job may delete them
* Fingerprint lookups referencing a `SUPERSEDED` or `ARCHIVED` version MUST succeed and return the full `rule_set_snapshot` for that version

---

#### 12.1.7 Version Record Fields (Authoritative)

| Field | Type | Description | Immutable After |
|---|---|---|---|
| `version_id` | UUID | Unique version identifier | Creation |
| `version_number` | INT | Monotonically increasing (V1=1, V2=2, …) | Creation |
| `status` | ENUM | `PROPOSED, UNDER_REVIEW, APPROVED, ACTIVE, SUPERSEDED, ARCHIVED` | ACTIVE |
| `effective_from` | TIMESTAMPTZ | When this version became ACTIVE; NULL until activation | ACTIVE |
| `activated_by` | TEXT | Identity of the operator who executed the activation | ACTIVE |
| `proposed_by` | TEXT | Identity who submitted the PROPOSED record | Creation |
| `approved_by` | TEXT | Identity who authorized APPROVED status | APPROVED |
| `change_rationale` | TEXT | Required free-text description of the change motivation | APPROVED |
| `rule_set_snapshot` | JSONB | Complete snapshot of **all** 41 canonical V2 variables; not a diff | ACTIVE |
| `prior_version_id` | UUID | FK to the immediately preceding version | Creation |
| `governance_approval_ref` | TEXT | Reference to the governance approval artifact | APPROVED |

---

### 12.2 Governance Classification Model

Every configurable variable in this catalog belongs to exactly one governance class. The class governs the approval process required before a variable's value may change.

| Class | Symbol | Approval Required | Replay Impact | Change Frequency |
|---|---|---|---|---|
| `ARCHITECTURAL_CONSTANT` | `AC` | Architecture board sign-off; rare | High — alters fundamental platform behavior | < 1/year |
| `GOVERNANCE_CONFIGURABLE` | `GC` | Designated governance authority; documented decision | High — affects student-facing eligibility and outreach policy | Occasional |
| `OPERATIONAL_TUNING` | `OT` | Operations lead approval; lighter process | Low-to-medium — affects operational mechanics, not policy | As needed |
| `REPLAY_SENSITIVE_THRESHOLD` | `RST` | Governance authority; replay impact assessment required | High — changing the value alters historical replay classification results | Governed |
| `AI_ADVISORY_THRESHOLD` | `AAT` | AI governance review; impact on AI context assessed | Medium — feeds AI prompt construction; alters AI output indirectly | Governed |
| `ESCALATION_THRESHOLD` | `ET` | Operations lead + academic team | Medium — affects escalation triggers and intervention routing | Infrequent |
| `PROVIDER_FAILURE_THRESHOLD` | `PFT` | Engineering + operations | Low — affects retry and cooldown mechanics; no student-facing policy | As needed |

**Hard rules:**
* A variable's classification is fixed at catalog publication; reclassification requires a governance decision documented in this file
* No variable may receive a lower-approval-requirement classification to bypass review — escalation of classification is always valid; de-escalation requires written justification
* `ARCHITECTURAL_CONSTANT` variables must appear in the `rule_set_snapshot` JSONB but changing them requires an architecture-level decision, not merely a new config version activation

---

### 12.3 Canonical V2 Variable Catalog

These 41 variables are the **sole authoritative source** for all configurable thresholds, timing parameters, provider selections, and governance settings in the platform. All directive Rule 3 tables, all migration seed records, and all orchestration service default lookups must reference these canonical names.

> **Unit abbreviations used:** `H` = integer hours, `C` = integer count, `D` = integer days, `DEC` = decimal (precision specified), `BOOL` = boolean, `TEXT` = string, `JSON` = JSON array/object, `NULL` = explicitly null (awaiting governance decision).

---

#### Group A — Outreach Timing (4 variables)

| Canonical Key | Default | Unit | Class | RST | AAT | ET | Description |
|---|---|---|---|---|---|---|---|
| `outreach_retry_window_hours` | `72` | H | GC | ✓ | — | — | Rolling or fixed window within which retry attempts are evaluated; canonical unit is HOURS (V1 used "3 days" — unit normalized per UG-2) |
| `outreach_exclusion_window_hours` | `NULL` | H | GC | ✓ | — | — | Hours after a successful contact during which re-outreach is suppressed; NULL = not configured |
| `outreach_max_attempts` | `3` | C | GC | ✓ | — | — | Maximum number of outreach attempts before the case is escalated or closed; recommended default = 3 (resolved per UG-5) |
| `retry_window_behavior` | `ROLLING` | TEXT | AC | ✓ | — | — | Semantics of the retry window: `ROLLING` (window resets from last attempt) or `FIXED` (window from first attempt); ROLLING is the resolved recommendation (UG-1); change requires architecture sign-off |

---

#### Group B — Homework Risk Thresholds (4 variables)

| Canonical Key | Default | Unit | Class | RST | AAT | ET | Description |
|---|---|---|---|---|---|---|---|
| `hws_behind_at_risk_threshold` | `1` | C | GC | ✓ | ✓ | — | Minimum `HWsBehind` count to classify a student as AT_RISK; V1 alias: `hw_at_risk_min_behind` (normalized per UG-4) |
| `hws_behind_high_risk_threshold` | `3` | C | GC | ✓ | ✓ | — | Minimum `HWsBehind` count to classify a student as HIGH_RISK; V1 alias: `hw_high_risk_min_behind` (normalized per UG-4) |
| `avg_eff_rating_at_risk_threshold` | `3.0` | DEC(3,1) | GC | ✓ | ✓ | — | Maximum `AvgEffRating` for AT_RISK classification; values AT or BELOW this threshold trigger risk signal; V1 alias: `avg_eff_rating_low_risk_threshold` (name corrected — V1 name was directionally misleading) |
| `avg_eff_rating_high_risk_threshold` | `2.0` | DEC(3,1) | GC | ✓ | ✓ | — | Maximum `AvgEffRating` for HIGH_RISK classification; values AT or BELOW this threshold trigger high-risk signal |

---

#### Group C — Activity Thresholds (3 variables)

| Canonical Key | Default | Unit | Class | RST | AAT | ET | Description |
|---|---|---|---|---|---|---|---|
| `last_activity_at_risk_days` | `NULL` | D | GC | ✓ | ✓ | — | Days of inactivity triggering AT_RISK classification; NULL = not configured in V1; governance decision required before activation |
| `last_activity_high_risk_days` | `NULL` | D | GC | ✓ | ✓ | — | Days of inactivity triggering HIGH_RISK classification; NULL = not configured in V1 |
| `placement_inactivity_alert_days` | `7` | D | OT | — | — | — | Days of inactivity on the placement pipeline before an alert is raised for a Placement Hopeful student |

---

#### Group D — Payment Risk Thresholds (3 variables)

| Canonical Key | Default | Unit | Class | RST | AAT | ET | Description |
|---|---|---|---|---|---|---|---|
| `payment_at_risk_balance_threshold` | `0.01` | DEC(10,2) | GC | ✓ | ✓ | — | Minimum outstanding balance (USD) to classify a student as AT_RISK for payment; V1 alias: `payment_balance_risk_threshold` lower tier (normalized per UG-3) |
| `payment_high_risk_balance_threshold` | `1000.00` | DEC(10,2) | GC | ✓ | ✓ | — | Minimum outstanding balance (USD) to classify a student as HIGH_RISK for payment; V1 alias: `payment_balance_risk_threshold` upper tier (normalized per UG-3) |
| `payment_deviation_alert_threshold` | `NULL` | DEC(10,2) | GC | ✓ | — | — | Payment deviation percentage or amount that triggers an alert; NULL = not configured in V1; governance decision required |

---

#### Group E — Escalation Thresholds (2 variables)

| Canonical Key | Default | Unit | Class | RST | AAT | ET | Description |
|---|---|---|---|---|---|---|---|
| `prior_escalation_repeat_threshold` | `NULL` | C | ET | ✓ | — | ✓ | Number of prior escalation events within the current enrollment before triggering an auto-escalation signal; NULL = not configured in V1 |
| `consecutive_no_response_escalation_threshold` | `NULL` | C | ET | ✓ | — | ✓ | Number of consecutive NO_RESPONSE events before triggering an escalation advisory; NULL = not configured in V1 |

---

#### Group F — Provider Failure Thresholds (2 variables)

| Canonical Key | Default | Unit | Class | RST | AAT | ET | Description |
|---|---|---|---|---|---|---|---|
| `provider_failure_cooldown_extension_hours` | `NULL` | H | PFT | — | — | — | Hours added to the standard outreach cooldown when a provider failure is detected; NULL = no extension |
| `provider_failure_retry_limit` | `NULL` | C | PFT | — | — | — | Maximum number of provider-failure retries before the outreach is deferred to human review; NULL = follows default retry policy |

---

#### Group G — Channel Advisory Thresholds (7 variables)

| Canonical Key | Default | Unit | Class | RST | AAT | ET | Description |
|---|---|---|---|---|---|---|---|
| `outreach_initial_channel_preference` | `NULL` | TEXT | GC | ✓ | ✓ | — | Preferred initial channel for outreach (`sms`, `email`, `call`); NULL = system default selection logic; all values LOWERCASE |
| `channel_delivery_failure_suspension_threshold` | `NULL` | C | GC | ✓ | — | — | Number of delivery failures on a channel before that channel is suspended for a student; NULL = no suspension logic |
| `call_engagement_score_threshold` | `NULL` | DEC(5,4) | GC | ✓ | ✓ | — | Engagement score (0.0000–1.0000) below which call channel is de-prioritized; NULL = engagement scoring not active |
| `sms_engagement_score_threshold` | `NULL` | DEC(5,4) | GC | ✓ | ✓ | — | Engagement score (0.0000–1.0000) below which SMS channel is de-prioritized; NULL = engagement scoring not active |
| `email_engagement_score_threshold` | `NULL` | DEC(5,4) | GC | ✓ | ✓ | — | Engagement score (0.0000–1.0000) below which email channel is de-prioritized; NULL = engagement scoring not active |
| `channel_specific_cooldown_hours` | `NULL` | H | OT | — | — | — | Per-channel cooldown hours after a contact attempt; NULL = global cooldown applies |
| `channel_opt_out_respect_period_hours` | `NULL` | H | GC | ✓ | — | — | Hours the platform respects a channel opt-out before re-evaluation; NULL = opt-out is permanent until reversed |

---

#### Group H — AI and Provider Configuration (3 variables)

| Canonical Key | Default | Unit | Class | RST | AAT | ET | Description |
|---|---|---|---|---|---|---|---|
| `ai_insight_ttl_hours` | `24` | H | OT | — | ✓ | — | Time-to-live in hours for a cached AI insight before it is considered stale and a refresh is triggered; classified OPERATIONAL (UG-6) |
| `ai_llm_provider` | `'anthropic'` | TEXT | AC | ✓ | ✓ | — | Active AI/LLM provider identifier; change requires architecture sign-off; value is stored in `rule_set_snapshot` and in the Reproducibility Fingerprint |
| `outreach_provider` | `'ghl'` | TEXT | AC | ✓ | — | — | Active outreach/communication provider identifier; change requires architecture sign-off |

---

#### Group I — System Timing (2 variables)

| Canonical Key | Default | Unit | Class | RST | AAT | ET | Description |
|---|---|---|---|---|---|---|---|
| `access_revocation_alert_hours` | `48` | H | OT | — | — | — | Hours after an access revocation event is detected before an unresolved alert is raised |
| `sql_server_max_sync_age_hours` | `4` | H | AC | ✓ | — | — | Maximum age (hours) of the last SQL Server sync before snapshot content lock is blocked; classified ARCHITECTURAL_CONSTANT (UG-10); recommended default = 4 hours |

---

#### Group J — Cohort Classification Parameters (5 variables)

| Canonical Key | Default | Unit | Class | RST | AAT | ET | Description |
|---|---|---|---|---|---|---|---|
| `cap_hopeful_min_percomp` | `0.30` | DEC(5,4) | GC | ✓ | ✓ | — | Minimum `PerComp_Act` for CAP Hopeful cohort classification; derived from SQL report heuristic |
| `launch_hopeful_min_percomp` | `0.59` | DEC(5,4) | GC | ✓ | ✓ | — | Minimum `PerComp_Act` for Launch Hopeful cohort classification |
| `cap_section_exclusion_patterns_json` | `["launch%","CAP%"]` | JSON | GC | ✓ | — | — | JSON array of SQL LIKE patterns for section names that exclude a student from CAP Hopeful classification |
| `launch_section_inclusion_pattern` | `'%CAP%'` | TEXT | GC | ✓ | — | — | SQL LIKE pattern for section names that qualify a student for Launch Hopeful classification |
| `placement_section_inclusion_pattern` | `'%launch%'` | TEXT | GC | ✓ | — | — | SQL LIKE pattern for section names that qualify a student for Placement Hopeful classification |

---

#### Group K — Priority Scoring Weights (6 variables)

| Canonical Key | Default | Unit | Class | RST | AAT | ET | Description |
|---|---|---|---|---|---|---|---|
| `priority_hw_weight` | `10.0` | DEC(5,1) | GC | ✓ | ✓ | — | Weight applied to `HWsBehind` in the additive priority score formula |
| `priority_hw_cap` | `50.0` | DEC(5,1) | GC | ✓ | ✓ | — | Maximum contribution of the HW component to the priority score |
| `priority_eff_weight` | `7.0` | DEC(5,1) | GC | ✓ | ✓ | — | Weight applied to `AvgEffRating` deficit in the priority score formula |
| `priority_eff_cap` | `35.0` | DEC(5,1) | GC | ✓ | ✓ | — | Maximum contribution of the efficiency-rating component to the priority score |
| `priority_inactivity_weight` | `2.0` | DEC(5,1) | GC | ✓ | ✓ | — | Weight applied to `InactivityDays` in the priority score formula |
| `priority_inactivity_cap` | `50.0` | DEC(5,1) | GC | ✓ | ✓ | — | Maximum contribution of the inactivity component to the priority score |

---

#### 12.3.1 V1→V2 Naming Migration Map

Variables renamed between V1 and V2. All directive Rule 3 tables must use the V2 canonical name. V1 names are preserved here as migration reference only; they MUST NOT appear in new code or directives.

| V1 Name (deprecated) | V2 Canonical Name | Normalization Reason |
|---|---|---|
| `hw_at_risk_min_behind` | `hws_behind_at_risk_threshold` | Canonical naming alignment per UG-4 |
| `hw_high_risk_min_behind` | `hws_behind_high_risk_threshold` | Canonical naming alignment per UG-4 |
| `avg_eff_rating_low_risk_threshold` | `avg_eff_rating_at_risk_threshold` | Directional correction: V1 name was misleading |
| `payment_balance_risk_threshold` | `payment_at_risk_balance_threshold` + `payment_high_risk_balance_threshold` | Semantic split: V1 had ambiguous single-tier reference; V2 has explicit two-tier names per UG-3 |
| `hws_behind_minimum_threshold` | `hws_behind_at_risk_threshold` | Alias used in eligibility directive; normalized |
| `avg_eff_rating_minimum_threshold` | `avg_eff_rating_at_risk_threshold` | Alias used in eligibility directive; normalized |
| `last_activity_max_days` | `last_activity_at_risk_days` | Alias used in eligibility directive; normalized |

> V1 seeded 24 variables (migration `0003`). V2 introduces 41 canonical variables — an expansion of 17 new variables covering escalation governance, provider failure, channel advisory, and replay-safe configuration. The V1→V2 migration seed (migration `0007`) must populate all 41 variables.

---

### 12.4 Replay-Safe Config Requirements

These requirements govern how the configuration registry is resolved during replay and historical regeneration operations. A replay is any execution with `execution_mode = SHADOW` and `is_replay = true` sourced from a historical `correlation_id`.

---

#### 12.4.1 Replay Threshold Resolution

* Replays MUST resolve thresholds from the `rule_set_snapshot` of the config version that was `ACTIVE` at the **original execution's content lock time** — not from the current `ACTIVE` version
* The config version reference is carried in the Snapshot Reproducibility Fingerprint (`configuration_registry_version` component)
* If the referenced version is `SUPERSEDED` or `ARCHIVED`, the `rule_set_snapshot` remains fully queryable; the replay proceeds using the historical snapshot without downgrade

---

#### 12.4.2 CONFIG_THRESHOLD_MISSING Behavior

When a threshold key is present in a directive's Rule 3 table but is absent from the resolved `rule_set_snapshot` (e.g., a V1 snapshot missing V2-only keys):

1. **Substitute** `UNKNOWN_V0` as the resolved value
2. **Log** a `WARN`-level event with the missing key name and the config version being resolved
3. **Add** the reason code `CONFIG_THRESHOLD_MISSING_{KEY}` to the evaluation's `reason_codes` array
4. **Exclude** all dependent rules that require this threshold from the evaluation pass
5. **Continue** evaluation with remaining independent rules
6. **Set** `degraded_evaluation: true` on the evaluation record

> `UNKNOWN_V0` is a governance-reserved sentinel value. It means "this key did not exist in the config version that governed this execution." It is not an error; it is a documented audit gap.

---

#### 12.4.3 Degraded Replay Semantics

When a replay execution resolves one or more `CONFIG_THRESHOLD_MISSING` conditions:

* The replay output is annotated with `degraded_evaluation: true`
* The `reason_codes` array enumerates all `CONFIG_THRESHOLD_MISSING_{KEY}` entries
* The replay result is classified as `REPLAY_PARTIAL` rather than `REPLAY_COMPLETE`
* Escalation advisory flags produced by the replay are logged but are NOT actioned in `SHADOW` mode (per UG-8)
* The audit log records both the historical config version reference and the specific keys that were missing

---

#### 12.4.4 Fingerprint Mismatch Handling

When the current system's config version fingerprint differs from the fingerprint recorded in a historical snapshot:

* The regeneration proceeds using the **physically stored snapshot data** — it does not re-evaluate under the current config
* The divergence is logged as `POTENTIALLY_DIVERGENT` with both fingerprint versions recorded
* The regenerated report is marked `POTENTIALLY_DIVERGENT` (see `spec/03_state_transition_rules.md` §22.3)
* A `SEVERITY: MEDIUM` governance alert is raised (see `spec/06_observability_operations.md` §10.9)

---

#### 12.4.5 Replay Determinism Requirements

The following invariants must hold for any replay or historical regeneration:

| Invariant | Requirement |
|---|---|
| R-EXEC-1 | Replay always executes in `SHADOW` mode; `LIVE` replay is prohibited |
| R-EXEC-2 | Replay resolves config from the historical version at original content lock time |
| R-EXEC-3 | Replay scope is limited to `REPLAY_CANDIDATE` students only; no new eligibility expansion |
| R-EXEC-4 | Replay does not create new idempotency keys; it references the original execution's keys |
| R-EXEC-5 | Replay output is annotated with `replay: true` and the source `correlation_id` |

---

### 12.5 AI Governance Requirements

AI behavior in this platform is governed by config-bound thresholds. These requirements define the boundaries of AI authority, the governance of stale AI serving, and the replay semantics for AI-generated content.

---

#### 12.5.1 AI Authority Boundaries

* AI outputs are **advisory only** — they do not override deterministic threshold evaluation, eligibility decisions, or state transitions
* No AI output may autonomously change student state, trigger financial actions, or bypass the Rule 3 config-bound threshold evaluation
* AI outputs that exceed their advisory ceiling (see §12.5.3) are flagged and not surfaced as actionable recommendations

---

#### 12.5.2 Stale AI Governance

* An AI insight is stale when its `generated_at` age exceeds `ai_insight_ttl_hours` (Group H)
* Stale AI serving is permitted but annotated: `stale: true`, `stale_for_hours: N` in the API response
* A snapshot finalized with stale AI content must carry `ai_content_stale: true` in the finalization record
* Unplanned staleness exceeding 48 hours triggers a `SEVERITY: HIGH` alert (see `spec/06_observability_operations.md` §10.4)
* The TTL threshold (`ai_insight_ttl_hours`) is classified `OPERATIONAL_TUNING`; changing it does not require replay impact assessment

---

#### 12.5.3 AI Advisory Ceilings

* AI advisory outputs must not be weighted above the deterministic rule outputs in any scoring or eligibility model
* The engagement score thresholds (Group G) that feed AI prompt context are classified `AI_ADVISORY_THRESHOLD`; changing them requires an AI governance review to assess downstream prompt context impact
* AI outputs that reference config-bound thresholds in their prompt context must use the threshold values from the ACTIVE config version at AI generation time — not hardcoded values

---

#### 12.5.4 FINALIZED Snapshot AI Immutability

* AI text physically copied into a FINALIZED snapshot (`warehouse.snapshot_ai_narratives`) is immutable
* Post-finalization operations — force-refresh, AI version archival, AI provider change, compliance deletion of `ai_insights` records — MUST NOT affect frozen snapshot AI text (FAD-1)
* The `ai_prompt_version` and `ai_model_version` components of the Snapshot Reproducibility Fingerprint are captured at finalization and are immutable thereafter

---

#### 12.5.5 AI Replay Semantics

* Historical report regeneration MUST NOT make new AI provider calls
* AI narrative content in regenerated reports is sourced exclusively from the physical text copies in `warehouse.snapshot_ai_narratives`
* Any regeneration path that calls an AI provider for content is a specification violation
* LIVE vs REPLAY behavioral distinction: in LIVE mode, fresh AI is generated; in REPLAY mode, frozen AI text is read from the snapshot row

---

### 12.6 Provider Failure Governance

Provider failure governance defines how the platform behaves when an outreach or AI provider is unavailable. These requirements are config-bound via Group F variables.

---

#### 12.6.1 Provider Outage Handling

* When `outreach_provider` (GHL) is unavailable, outreach transitions are placed in the platform retry queue; no data corruption occurs; in-flight outreach state is preserved
* When `ai_llm_provider` is unavailable, AI generation is deferred with exponential backoff; snapshot finalization is not blocked; stale AI serving applies
* Provider unavailability does not corrupt platform state; all read operations continue regardless of provider availability

---

#### 12.6.2 Retry Degradation Behavior

* When a provider failure is detected, the cooldown extension (`provider_failure_cooldown_extension_hours`) is added to the standard outreach cooldown
* When provider retry attempts reach `provider_failure_retry_limit`, the outreach is escalated to human review rather than silently dropped
* Both variables default to `NULL` (no extension, follows default retry policy); activation requires an explicit governance decision with documented values

---

#### 12.6.3 Cooldown Semantics

* Provider failure cooldown operates independently of the outreach retry window
* Cooldown extension is additive: `effective_cooldown = standard_cooldown + provider_failure_cooldown_extension_hours`
* The extended cooldown is logged in the outreach history record with `provider_failure_induced: true` annotation

---

#### 12.6.4 Exhaustion Handling

* When all retries are exhausted and the provider is still unavailable:
  * Outreach: transition to `INTERVENTION_REQUIRED` via the manual escalation path; do not auto-close
  * AI generation: serve last `AI_REVIEWED` insight with `stale: true`; log `AI_GENERATION_FAILED`
* Exhaustion events always produce an audit log entry regardless of execution mode

---

#### 12.6.5 Replay-Safe Provider Attribution

* Provider attribution in historical records reflects the provider that was active at original execution time
* Changing `ai_llm_provider` or `outreach_provider` does not retroactively modify attribution in prior `ai_insights` records, snapshot rows, or outreach history records
* The `model_used` field on `ai_insights` records is immutable after `AI_GENERATED` state (see `spec/03_state_transition_rules.md` §27.5)

---

### 12.7 Escalation Governance Foundations

Escalation threshold governance defines the config-bound rules that determine when automated advisory escalation signals are produced. These requirements are served by Group E variables.

---

#### 12.7.1 Escalation Threshold Governance

* `prior_escalation_repeat_threshold` and `consecutive_no_response_escalation_threshold` are classified `ESCALATION_THRESHOLD`
* Both default to `NULL` in V1 and V2 initial seed; activation requires an explicit governance decision with reviewed default values
* These variables feed the escalation advisory logic in `directives/core_decision_engine.md` Rule 3 and `directives/outreach_retry_policy.md` Rule 3

---

#### 12.7.2 Escalation Replay Behavior

* Escalation advisory flags produced during replay are logged but are **not actionable** in `SHADOW` mode (per UG-8)
* This means: replay produces the escalation signal so it can be audited, but no escalation workflow is triggered, no operator notification is sent, and no state transition is made
* In LIVE mode, escalation advisory signals are fully actionable per the escalation directive

---

#### 12.7.3 AI-Assist Boundaries in Escalation

* AI insights MAY inform but do not override deterministic escalation threshold evaluation
* A student meets the escalation threshold based on `consecutive_no_response_escalation_threshold` and `prior_escalation_repeat_threshold` values from the config; AI risk summary is advisory context, not the decision trigger
* AI inputs to escalation are classified `AI_ADVISORY_THRESHOLD`; they require the AI governance review for changes

---

#### 12.7.4 Cooldown and Lineage Expectations

* Escalation cooldown behavior (if configured) follows the same cooldown semantics as outreach retry cooldown
* Every escalation advisory event produced by the orchestration engine is recorded in the audit log with: config version ID, threshold values used, reason codes, student ID (opaque), correlation ID
* The lineage chain from config version → threshold value → escalation signal must be reconstructable from the audit log alone

---

### 12.8 Config Evolution Strategy

This section defines the complete process for introducing new configuration versions, from initial governance proposal through activation and historical lineage preservation.

---

#### 12.8.1 Supersession Activation Workflow

1. **Propose:** Operator creates a new `PROPOSED` version record in `config_version_registry`; `rule_set_snapshot` must contain all 41 canonical V2 variables (including unchanged ones); `change_rationale` is required
2. **Review:** Designated governance authority reviews the proposed change; reviews include: variable classification compliance, replay impact assessment for `RST`-classified variables, AI governance review for `AAT`-classified variables
3. **Approve:** Governance authority transitions the record to `APPROVED`; `approved_by` identity and `governance_approval_ref` are recorded
4. **Activate:** Authorized operator executes the activation; the atomic swap transitions `APPROVED → ACTIVE` (new) and `ACTIVE → SUPERSEDED` (prior); `effective_from` is set to the activation timestamp
5. **Verify:** Post-activation singleton check confirms exactly one `ACTIVE` version; activation log entry is emitted to the governance operations dashboard
6. **Audit:** Both the superseded and new active version records are permanently retained and fully queryable

---

#### 12.8.2 Governance Approval Chain

| Variable Class | Approval Chain | Minimum Review Time |
|---|---|---|
| `ARCHITECTURAL_CONSTANT` | Architecture board → CTO/Product sign-off | 5 business days |
| `GOVERNANCE_CONFIGURABLE` | Governance authority + academic team | 2 business days |
| `REPLAY_SENSITIVE_THRESHOLD` | Governance authority + replay impact assessment | 3 business days |
| `AI_ADVISORY_THRESHOLD` | AI governance review + governance authority | 2 business days |
| `ESCALATION_THRESHOLD` | Operations lead + academic team | 1 business day |
| `OPERATIONAL_TUNING` | Operations lead | Same-day |
| `PROVIDER_FAILURE_THRESHOLD` | Engineering + operations | Same-day |

---

#### 12.8.3 Activation Audit Requirements

Every activation event must produce both a database audit record and a structured governance log entry containing:
* Prior version ID and version number
* New version ID and version number
* `activated_by` identity
* `effective_from` timestamp
* One-line `change_rationale`
* List of changed variable keys (diff between prior and new `rule_set_snapshot`)
* `governance_approval_ref` linking to the approval artifact

---

#### 12.8.4 Historical Lineage Guarantees

* Every version record carries `prior_version_id`; the chain is complete and unbroken back to V1
* No version record is ever deleted by any application code or scheduled job
* Any historical snapshot fingerprint that references a version ID must be resolvable to the full `rule_set_snapshot` for that version, even if the version is `ARCHIVED`
* If a version is unavailable at fingerprint lookup time (corrupted, manually deleted — a compliance defect), the fingerprint notes it as `ARCHIVED`; regeneration proceeds with a `SEVERITY: HIGH` alert

---

#### 12.8.5 Future Extensibility

* New variables added in a future V3+ catalog update must follow the same classification process
* New variables are added to the `rule_set_snapshot` schema; prior version records carry `NULL` for new keys (interpreted as `UNKNOWN_V0` during replay resolution)
* Removing variables from the catalog requires a governance decision; removed variables remain in historical `rule_set_snapshot` JSONB for replay purposes but are no longer active in new evaluations

---

### 12.9 Acceptance Criteria (Governance-Focused)

---

**AC-GOV-1 — Exactly-One-ACTIVE Invariant**

**Given** a new configuration version is activated
**When** the activation transaction commits
**Then** exactly one record in `config_version_registry` has `status = 'ACTIVE'`; the prior ACTIVE record is now `SUPERSEDED`; this invariant holds at all times including mid-batch snapshot runs

---

**AC-GOV-2 — Prospective-Only Semantics**

**Given** a new configuration version is activated during a monthly snapshot batch run
**When** the batch completes
**Then** snapshots that locked content before the activation carry the prior version in their `configuration_registry_version` fingerprint component; snapshots that locked content after the activation carry the new version; no snapshot carries both or neither

---

**AC-GOV-3 — Historical Lineage Queryability**

**Given** a historical snapshot with fingerprint `configuration_registry_version = V1`
**When** the V1 version record is queried (regardless of its current status)
**Then** the complete `rule_set_snapshot` for V1 is returned; all 24 V1 threshold values are accessible; the query succeeds even if V1 is `SUPERSEDED` or `ARCHIVED`

---

**AC-GOV-4 — CONFIG_THRESHOLD_MISSING Behavior**

**Given** a replay execution resolves config from a V1 snapshot fingerprint
**And** the replay directive references `consecutive_no_response_escalation_threshold` (a V2-only key absent from V1)
**When** the threshold is resolved
**Then** the value `UNKNOWN_V0` is substituted; a `WARN` log entry is emitted; `CONFIG_THRESHOLD_MISSING_CONSECUTIVE_NO_RESPONSE_ESCALATION_THRESHOLD` is added to `reason_codes`; `degraded_evaluation: true` is set; dependent rules are excluded; the evaluation continues with independent rules

---

**AC-GOV-5 — Rollback Prohibition**

**Given** a configuration version is `SUPERSEDED`
**When** any code path attempts to transition it to `ACTIVE`
**Then** the transition is rejected by the database-level state machine; a `GovernanceViolation` error is raised and logged; the prior ACTIVE version remains unchanged

---

**AC-GOV-6 — Replay Isolation**

**Given** a replay execution is triggered for a historical month
**When** the replay runs
**Then** `execution_mode = SHADOW` is enforced; the resolved config is from the historical version, not the current ACTIVE version; no new idempotency keys are created; all output is annotated with `replay: true`

---

**AC-GOV-7 — Degraded Replay Annotation**

**Given** a replay resolves one or more `CONFIG_THRESHOLD_MISSING` conditions
**When** the replay evaluation completes
**Then** the evaluation record carries `degraded_evaluation: true`; the `reason_codes` array lists all `CONFIG_THRESHOLD_MISSING_{KEY}` entries; the result is classified `REPLAY_PARTIAL`; escalation advisory flags are logged but not actioned

---

**AC-GOV-8 — V2 Variable Count and Naming Integrity**

**Given** migration `0007` has executed and seeded the V2 config version record
**When** the `rule_set_snapshot` JSONB is inspected
**Then** all 41 canonical V2 variable keys (Groups A through K) are present; no V1 deprecated names are present; all `NULL`-default variables have `NULL` values; all numeric defaults match the Group tables in §12.3

---

**AC-GOV-9 — AI Snapshot Isolation in Config Context**

**Given** a new configuration version changes `ai_insight_ttl_hours`
**When** the new version is activated
**Then** finalized snapshots produced before the activation retain their physically copied AI text unchanged; no AI re-generation or snapshot row mutation occurs; the change is prospective only

---

**AC-GOV-10 — Provider Attribution Immutability**

**Given** `ai_llm_provider` is changed from `'anthropic'` to a new provider in a new config version
**When** the new version is activated
**Then** existing `ai_insights` records retain `model_used` values from the original provider; `warehouse.snapshot_ai_narratives` records retain AI text from the original model; the new provider is used only for AI generations that begin after the activation timestamp

---

### 12.10 Open Governance Decisions (Resolved)

These governance decisions were unresolved in V1. All are now resolved as binding governance policy. Each resolution is annotated with its rationale and constraint class.

---

**UG-1 — retry_window_behavior: ROLLING vs FIXED**

**Resolution:** `retry_window_behavior = ROLLING` is the authoritative platform default.
**Rationale:** ROLLING semantics (window resets from last attempt) more accurately models the operational intent of "student has had N days to respond since we last tried." FIXED semantics can cause premature case closure if attempts cluster at the start of the window.
**Constraint:** Classified `ARCHITECTURAL_CONSTANT`. Changing to FIXED requires architecture board sign-off. The resolved default is seeded in V2 migration `0007`.

---

**UG-2 — outreach retry window canonical unit**

**Resolution:** Canonical unit is **HOURS**. The canonical variable name is `outreach_retry_window_hours`. The V2 default is `72` hours (equivalent to the V1 "3 days" expressed as hours).
**Rationale:** Hour-based units eliminate ambiguity around "day" definition (calendar day vs. 24-hour period), support sub-day precision, and align with all other timing variables in the catalog.
**Constraint:** All directive Rule 3 tables must use `outreach_retry_window_hours` and specify values in hours.

---

**UG-3 — Payment threshold semantic normalization**

**Resolution:** The single V1 `payment_balance_risk_threshold` is replaced by two canonical names: `payment_at_risk_balance_threshold` (`0.01` default) and `payment_high_risk_balance_threshold` (`1000.00` default). The two-tier model is authoritative.
**Rationale:** A single variable conflated two distinct risk tiers. Separate variables make the risk classification logic unambiguous and auditable independently per tier.
**Constraint:** V1 alias `payment_balance_risk_threshold` is deprecated. All directives must use the canonical two-tier names.

---

**UG-4 — HW risk threshold naming normalization**

**Resolution:** Canonical names are `hws_behind_at_risk_threshold` and `hws_behind_high_risk_threshold` (Group B). V1 aliases (`hw_at_risk_min_behind`, `hws_behind_minimum_threshold`) are deprecated.
**Rationale:** V1 had inconsistent naming across directives. The canonical names use the `_at_risk_` and `_high_risk_` suffix pattern uniformly across all risk threshold variables.
**Constraint:** All directives must update Rule 3 tables to the V2 canonical names.

---

**UG-5 — outreach_max_attempts default and classification**

**Resolution:** `outreach_max_attempts = 3` is the recommended default. Classification is `GOVERNANCE_CONFIGURABLE`.
**Rationale:** Max attempts directly affects student outreach policy — more attempts increases contact rate but risks student fatigue. This is a student-facing policy decision that requires governance authority approval to change.
**Constraint:** Seeded at `3` in V2. Changes require governance authority documentation.

---

**UG-6 — AI sensitivity governance tier**

**Resolution:**
* `ai_insight_ttl_hours`: classified `OPERATIONAL_TUNING`. TTL is a system mechanics variable; changing it does not alter student-facing policy.
* Variables that feed AI prompt context (engagement score thresholds, risk thresholds, activity thresholds): classified `AI_ADVISORY_THRESHOLD`. Changing them requires AI governance review because they affect AI output quality and context.
**Rationale:** Not all AI-adjacent variables have the same governance weight. Operational TTL is a system knob; threshold values that change what AI "sees" in its context are policy decisions.

---

**UG-7 — Channel advisory governance split**

**Resolution:**
* Student-facing channel policy variables (`channel_opt_out_respect_period_hours`, `outreach_initial_channel_preference`, `channel_delivery_failure_suspension_threshold`): classified `GOVERNANCE_CONFIGURABLE`
* System mechanics variables (`channel_specific_cooldown_hours`, `provider_failure_cooldown_extension_hours`): classified `OPERATIONAL_TUNING`
**Rationale:** Channel opt-out periods and suspension thresholds are student-facing policy; changes require governance review. Cooldown mechanics are system-level tuning.

---

**UG-8 — Escalation flags in replay**

**Resolution:** Escalation advisory flags produced during replay executions are **logged but not actioned** in `SHADOW` mode.
**Rationale:** Replay is a diagnostic and audit tool, not a live orchestration path. Producing escalation signals during replay without actioning them allows operators to assess "what would have happened" without creating false escalation workflows.
**Constraint:** The runtime must enforce: `if execution_mode == SHADOW and is_replay == true, then escalation_flags.log_only = true`.

---

**UG-9 — Config version record retention**

**Resolution:** Config version records are **permanently retained** — no version record is ever deleted by any application code, scheduled job, or administrative action.
**Rationale:** Any FINALIZED snapshot fingerprint that references a version ID must be resolvable forever. Deleting version records breaks historical fingerprint lookups and destroys reproducibility guarantees.
**Constraint:** No delete path exists for `config_version_registry` records. Manual deletion is a compliance defect.

---

**UG-10 — sql_server_max_sync_age_hours classification and default**

**Resolution:** `sql_server_max_sync_age_hours = 4` hours is the recommended default. Classification is `ARCHITECTURAL_CONSTANT`.
**Rationale:** The maximum acceptable age of the SQL Server sync before snapshot content lock should block is a fundamental platform data freshness guarantee. It is not operational tuning — it is an architectural constraint on data integrity. Changing it requires architecture board sign-off.
**Constraint:** Seeded at `4` in V2. Changes require architecture-level review. The value must be enforced as a hard gate at snapshot content lock time (`DRAFT → VALIDATING` transition).

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
