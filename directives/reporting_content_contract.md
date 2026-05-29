# directives/reporting_content_contract.md

---

## REPORTING CONTENT CONTRACT

---

> **Status:** Source field mappings marked `[TBD — source tables pending]` throughout.
> When source database table definitions are provided, replace every `[TBD]` entry with
> the authoritative `table_name.column_name` reference. No implementation work should
> begin on data-fetching for these surfaces until TBD entries are resolved.

---

## 1. PURPOSE

This directive is the authoritative reference for what fields appear in every reporting
surface, what data category each field belongs to, and what source table and column
supplies the value. It governs:

- Implementation of report generation services
- API response shapes for all reporting endpoints
- Snapshot assembly logic in `warehouse.student_snapshots`
- Lifecycle tab endpoint query construction
- Student drawer profile and AI narrative display

Governed by:
- `ux/admin_dashboard.md` §15 (lifecycle tab column schemas)
- `ux/user_experience.md` §5 (immutable lineage constraints on report display)
- `spec/05_external_integrations.md` §7 (snapshot generation orchestration)
- `spec/08_data_model.md` §12 (StudentSnapshot content definition)

---

## 2. DATA SOURCE CATEGORIES

Every field in every report belongs to exactly one source category. Mixed provenance is
not permitted without explicit annotation.

| Category | Origin | Authority | Notes |
|---|---|---|---|
| `MSSQL_MIRROR` | SQL Server `AI_ChatBot_TriggerData` | **Authoritative** — wins on conflict | Sync'd into `student_trigger_data` via `POST /sync/mssql` |
| `MSSQL_INTERVIEW_PREP` | SQL Server `AI_ChatBot_TriggerData_InterviewPrep` | Authoritative | Sync'd into `student_interview_prep` |
| `PLATFORM` | PostgreSQL platform-owned records | Platform-owned | `outreach_history`, `state_transition_log`, `student_notes`, etc. |
| `AI_GENERATED` | LLM narrative text | Advisory only | Stored in `ai_insights` (live) or `warehouse.snapshot_ai_narratives` (finalized) |
| `GHL_SUPPLEMENTARY` | GHL API cache (`ghl_messages`) | Supplementary — `MSSQL_MIRROR` wins on conflict | Contact/communication metadata only |
| `DERIVED` | Computed by platform at sync or finalization time | Platform-owned | `risk_level`, `priority_score`, `segment_classification`, `payment_risk_label` |

---

## 3. MONTHLY STUDENT REPORT

---

### 3.1 Definition

The monthly student report is a per-student document generated from a FINALIZED
`warehouse.student_snapshots` row. One report per `(student_id, snapshot_month)`.

**Source:** `warehouse.student_snapshots` exclusively (FAD-2 — no live SQL Server
queries at report generation time, no AI provider calls at generation time).

**Lifecycle state gate:** Report generation is only triggered after all student snapshots
for the cohort reach `FINALIZED` state. A student with a non-FINALIZED snapshot is
excluded from the current cohort report run.

**Governance constraint:** Every field in the report is a physical copy from the snapshot
row — not a live query. Regenerating the same report from the same FINALIZED snapshot
must produce identical output (CONC-INVARIANT-2 / FAD-6).

---

### 3.2 Section 1 — Student Identity

| Display field | Source category | Source column |
|---|---|---|
| Full Name | `MSSQL_MIRROR` | [TBD — source tables pending] |
| User ID | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Email | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Phone | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Program Path | `MSSQL_MIRROR` | [TBD — source tables pending] |
| IPBC Start Date | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Weeks in Program | `DERIVED` | Computed from IPBC Start Date at snapshot assembly |

---

### 3.3 Section 2 — Risk and Priority Classification

Derived at snapshot assembly time from SQL Server metric values. Stored in the
snapshot row — not recomputed at report generation.

| Display field | Source category | Derivation |
|---|---|---|
| Risk Level | `DERIVED` | HIGH / MEDIUM / LOW — see `directives/core_decision_engine.md` |
| Priority Score | `DERIVED` | 0–100 numeric score |
| Recommended Action | `DERIVED` | ESCALATE / CONTACT_IMMEDIATELY / SCHEDULE_OUTREACH / MONITOR |
| Risk Reason Codes | `DERIVED` | List of codes: HWS_BEHIND_HIGH_RISK, INACTIVITY_HIGH_RISK, etc. |
| Segment Classification | `DERIVED` | Cohort segment label computed at finalization |
| Payment Risk Label | `DERIVED` | HIGH / MEDIUM / LOW — based on payment balance thresholds |

---

### 3.4 Section 3 — Academic Performance

| Display field | Source category | Source column |
|---|---|---|
| HWs Behind | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Avg Effort Rating | `MSSQL_MIRROR` | [TBD — source tables pending] |
| HW Submitted Days Ago | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Attendance % | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Active Status | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Status I | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Status II | `MSSQL_MIRROR` | [TBD — source tables pending] |
| HW Risk Score | `DERIVED` | Computed from HWs Behind + Avg Effort Rating at finalization |

---

### 3.5 Section 4 — Engagement

| Display field | Source category | Source column |
|---|---|---|
| Last Activity Days | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Last Login Days | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Current Class Name | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Last Activity Section | `MSSQL_MIRROR` | [TBD — source tables pending] |

---

### 3.6 Section 5 — Financial

| Display field | Source category | Source column |
|---|---|---|
| Payment Balance | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Total Payments | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Fee Paid | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Payment Risk Label | `DERIVED` | Computed from Payment Balance at finalization |

---

### 3.7 Section 6 — Outreach Summary (snapshot month)

Sourced from `outreach_history` and `state_transition_log` records within the snapshot
month window. Copied as aggregated counts into the snapshot row at finalization.

| Display field | Source category | Source |
|---|---|---|
| Total Outreach Attempts (this month) | `PLATFORM` | Count of `outreach_history` rows in snapshot month |
| Channels Used | `PLATFORM` | Distinct channel values from `outreach_history` in snapshot month |
| Last Contact Date | `PLATFORM` | Max `created_at` from `outreach_history` |
| Last Contact Correlation ID | `PLATFORM` | `correlation_id` of most recent `outreach_history` row |
| Current Lifecycle State | `PLATFORM` | `outreach_tracking.state` at snapshot cutoff |
| Response Received (yes/no) | `PLATFORM` | Derived: any `RESPONDED` state transition in snapshot month |
| Last Action Type | `PLATFORM` | `action` field of most recent `outreach_history` row |

---

### 3.8 Section 7 — AI Narratives

All AI narrative text in a FINALIZED snapshot is a physical copy (FAD-1). The
`ai_governance_tier` is recorded in the snapshot to describe the tier at copy time.

| Display field | Source category | AI insight type | Governance note |
|---|---|---|---|
| Risk Summary | `AI_GENERATED` | `risk_summary` | Advisory only. Label: "AI Risk Assessment". Not an authorization. |
| Progress Summary | `AI_GENERATED` | `progress_summary` | Advisory only. |
| Monthly Narrative | `AI_GENERATED` | `monthly_narrative` | Advisory only. |
| Intervention Recommendation | `AI_GENERATED` | `intervention_recommendation` | Advisory only. Structured text. |
| Sentiment Classification | `AI_GENERATED` | `sentiment_analysis` | Advisory only. |
| AI Governance Tier | `PLATFORM` | — | FINALIZED_COPY / AI_GENERATED / STALE / UNAVAILABLE |

**Null handling:** If no `AI_REVIEWED` record exists at finalization time, the narrative
field is NULL and `ai_content_available = false`. The report renders a "No AI narrative
available at time of finalization" placeholder — it does not block report generation.

---

### 3.9 Section 8 — State History (snapshot month)

List of state transitions that occurred during the snapshot month. Copied as a
structured array into `warehouse.snapshot_ai_narratives` at finalization.

| Field | Source |
|---|---|
| Transition Date | `state_transition_log.created_at` |
| From State | `state_transition_log.from_state` |
| To State | `state_transition_log.to_state` |
| Trigger | `state_transition_log.trigger` |
| Actor | `state_transition_log.actor` (`system` or operator identity) |
| Correlation ID | `state_transition_log.correlation_id` |
| Execution Mode | `state_transition_log.execution_mode` |

**Governance note:** All entries carry `execution_mode` label. SHADOW-mode transitions
are included but clearly labeled `execution_mode = SHADOW` — they are governance records.

---

### 3.10 Section 9 — Governance Metadata

| Display field | Source |
|---|---|
| Snapshot Month | `warehouse.student_snapshots.snapshot_month` |
| Lifecycle State | `warehouse.student_snapshots.lifecycle_state` |
| Config Version ID | `warehouse.student_snapshots.config_version_id` (locked at VALIDATING) |
| Schema Version | Fingerprint component: `schema_version` |
| AI Prompt Version | Fingerprint component: `ai_prompt_version` (per insight type) |
| AI Model Version | Fingerprint component: `ai_model_version` (per insight type) |
| Report Template Version | Fingerprint component: `report_template_version` |
| Execution Mode at Finalization | `warehouse.student_snapshots.execution_mode` |
| Report Generated Date | `warehouse.monthly_reports.generated_at` |
| Report Lineage Version | `warehouse.monthly_reports.lineage_version` (1 = original; increments on regeneration) |

---

## 4. LIFECYCLE TAB FIELD MAPPINGS

---

Column schemas are defined in `ux/admin_dashboard.md §15.4`. This section adds source
category and source column for each column. Column order matches the display schema.

All lifecycle tab data is read from `student_trigger_data` (the SQL Server mirror in
PostgreSQL) plus platform records (`outreach_tracking`, `student_campaign_activity`).

### Shared columns (present in multiple tabs)

| Display column | Source category | Source column |
|---|---|---|
| Student Name | `MSSQL_MIRROR` | [TBD — source tables pending] |
| UserID | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Email | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Phone | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Program Path | `MSSQL_MIRROR` | [TBD — source tables pending] |
| IPBC Start Date | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Weeks in Program | `DERIVED` | Computed from IPBC Start Date |
| Attendance % | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Active | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Status I | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Status II | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Last Campaign Activity Date | `PLATFORM` | `student_campaign_activity.created_at` |
| Last Campaign Activity Type | `PLATFORM` | `student_campaign_activity.action_type` |
| Last Campaign Activity | `PLATFORM` | `student_campaign_activity.action_label` |
| Campaign Notes | `PLATFORM` | `student_campaign_activity.notes` |
| Notes | `PLATFORM` | `student_notes` (latest note body) |

---

### 4.1 Newcomers Tab (17 columns)

Filter: `IPBCStartDate` within last 90 days.

Additional columns beyond shared set:

| Display column | Source category | Source column |
|---|---|---|
| HW Submitted (days ago) | `MSSQL_MIRROR` | [TBD — source tables pending] |

---

### 4.2 Engagement Tab (18 columns)

Filter: All students.

Additional columns beyond shared set:

| Display column | Source category | Source column |
|---|---|---|
| Class Name | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Last Activity Section | `MSSQL_MIRROR` | [TBD — source tables pending] |
| HW Submitted (days ago) | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Last Login Days | `MSSQL_MIRROR` | [TBD — source tables pending] |

---

### 4.3 HW Risk Tab (20 columns)

Filter: `IPBCStartDate` not null.

Additional columns beyond shared set:

| Display column | Source category | Source column |
|---|---|---|
| HWs Behind | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Avg Effort Rating | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Last Activity Days | `MSSQL_MIRROR` | [TBD — source tables pending] |
| HW Submitted (days ago) | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Last Login Days | `MSSQL_MIRROR` | [TBD — source tables pending] |

---

### 4.4 CAP Hopefuls Tab (20 columns)

Filter: `IPBCStartDate` not null AND `AttendancePercentage > 50`.

Additional columns beyond shared set:

| Display column | Source category | Source column |
|---|---|---|
| Class Name | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Last Activity Section | `MSSQL_MIRROR` | [TBD — source tables pending] |
| HW Submitted (days ago) | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Total Payments | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Payment Balance | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Fee Paid | `MSSQL_MIRROR` | [TBD — source tables pending] |

**Note:** Status I / Status II are present in this tab (shared columns).

---

### 4.5 Launch Hopefuls Tab (20 columns)

Filter: `AttendancePercentage > 70` AND section contains "CAP Project".

Same column schema as CAP Hopefuls tab. Source mappings are identical.

---

### 4.6 Placement Hopefuls Tab (28 columns)

Filter: `AttendancePercentage > 70` AND section contains "Launch".

All CAP Hopefuls columns plus the following interview data columns:

| Display column | Source category | Source column |
|---|---|---|
| Last Interview | `MSSQL_INTERVIEW_PREP` | [TBD — source tables pending] |
| Last Interview Days Ago | `DERIVED` | Computed from Last Interview date |
| Recruiter Interview Count | `MSSQL_INTERVIEW_PREP` | [TBD — source tables pending] |
| Technical Interview Count | `MSSQL_INTERVIEW_PREP` | [TBD — source tables pending] |
| Recruiter:Technical Ratio | `DERIVED` | Computed from above two counts |
| Avg Interview Prep Score | `MSSQL_INTERVIEW_PREP` | [TBD — source tables pending] |
| Avg Interview Score | `MSSQL_INTERVIEW_PREP` | [TBD — source tables pending] |
| ChatGPT Prompt | `MSSQL_INTERVIEW_PREP` | [TBD — source tables pending] |

**Note:** Interview prep fields are currently null until the placement data source is
integrated (referenced in `ux/admin_dashboard.md §15.4`).

---

## 5. STUDENT DRAWER — PROFILE TAB

---

Displayed via `GET /students/{id}/profile`. All fields are read from
`student_trigger_data` plus `outreach_tracking`.

| Display field | Source category | Source column |
|---|---|---|
| Full Name | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Email | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Phone | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Program Path | `MSSQL_MIRROR` | [TBD — source tables pending] |
| HWs Behind | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Avg Effort Rating | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Inactive Days | `MSSQL_MIRROR` | [TBD — source tables pending] |
| Risk Badge | `DERIVED` | HIGH / MEDIUM / LOW — computed via `risk_level_for_display()` |
| Current Lifecycle State | `PLATFORM` | `outreach_tracking.state` |
| Checkpoint | `PLATFORM` | `outreach_tracking.checkpoint` |
| Attempt Count | `PLATFORM` | `outreach_tracking.current_attempt` |
| Config Version ID (governs attempt count limit) | `PLATFORM` | `outreach_tracking.config_version_id` |
| Last Contact Date | `PLATFORM` | Max `outreach_history.created_at` |
| Last Contact Correlation ID | `PLATFORM` | `outreach_history.correlation_id` (most recent) |
| Next Retry Date | `PLATFORM` | `outreach_tracking.next_retry_at` |

---

## 6. DASHBOARD KPI SUMMARY CARD

---

Served by `GET /dashboard/summary`. All values are aggregated from `outreach_tracking`
and `outreach_history`.

| KPI metric | Source | Definition |
|---|---|---|
| Tracked | `PLATFORM` | Count of students with any `outreach_tracking` row |
| Ever Contacted | `PLATFORM` | Count with at least one `outreach_history` row |
| Responded | `PLATFORM` | Count currently in `RESPONDED` or later states |
| No Response | `PLATFORM` | Count in `NO_RESPONSE` state |
| Intervention Required | `PLATFORM` | Count in `INTERVENTION_REQUIRED` state |
| Resolved | `PLATFORM` | Count in `RESOLVED` state |
| Closed | `PLATFORM` | Count in `CLOSED` state |
| Shadow Executions | `PLATFORM` | Count of `outreach_history` rows with `execution_mode = SHADOW` |
| Contacted Rate (pill) | `DERIVED` | Ever Contacted / Tracked |
| Response Rate (pill) | `DERIVED` | Responded / Ever Contacted |
| Resolution Rate (pill) | `DERIVED` | Resolved / (Resolved + Closed + Intervention Required) |

**Governance note:** Counts include SHADOW and LIVE records unless filtered. The
`execution_mode` filter is exposed on the State Distribution card (sibling card) — not
a KPI override. Config V2 version is shown read-only alongside this card to identify
which version's thresholds governed the current metrics window.

---

## 7. FIELD RESOLUTION RULES

---

### 7.1 Conflict resolution

When a field value exists in both `MSSQL_MIRROR` and `GHL_SUPPLEMENTARY`, the
`MSSQL_MIRROR` value always wins. This is enforced at sync time:
`origin_authority = sql_server_authoritative` on the winning record.

### 7.2 Null handling

A field that has no value in the source must render as a defined null state, not a
blank or missing field:

| Field type | Null display |
|---|---|
| Numeric metric | `—` or `0` (specify per field when source tables are provided) |
| Date | `Not set` |
| AI narrative | `No narrative available at time of finalization` |
| Risk label | `UNKNOWN` |
| State | `ELIGIBLE` (default initial state) |

### 7.3 Stale data annotation

Fields sourced from `MSSQL_MIRROR` that have not been refreshed within the
`mssql_sync_staleness_threshold_hours` Config V2 value carry a `STALE_SQL_SERVER_DATA`
annotation in the UI. The data is still displayed — staleness is a visibility annotation,
not a blocking condition.

---

## 8. IMPLEMENTATION NOTES

---

1. **Do not implement data-fetching** for any field marked `[TBD — source tables pending]`
   until the source table definitions are provided and this directive is updated.
   The field list and section structure are confirmed; only column references are pending.

2. **Monthly report generation service** must read exclusively from
   `warehouse.student_snapshots` (FAD-2). It must not issue SQL Server queries or
   AI provider calls during generation.

3. **Lifecycle tab queries** read from `student_trigger_data` (the PostgreSQL mirror),
   not from SQL Server directly. Data freshness depends on the most recent sync run.

4. **Derived fields** (risk level, priority score, weeks in program, etc.) are computed
   once at snapshot assembly or sync time and stored. They are never recomputed at
   query/display time.

5. **AI narrative governance:** Every AI narrative field must carry `ai_governance_tier`
   in the API response. The UI must label the output as advisory. No AI field may
   be rendered without its governance tier.

---

## 9. OPEN ITEMS (TO RESOLVE WHEN SOURCE TABLES ARE PROVIDED)

---

| # | Item | Blocker |
|---|---|---|
| OI-1 | Map all `[TBD]` display fields to `AI_ChatBot_TriggerData` columns | Source table definition pending |
| OI-2 | Map all Placement Hopefuls interview fields to `AI_ChatBot_TriggerData_InterviewPrep` columns | Source table definition pending |
| OI-3 | Confirm null display format per numeric field (0 vs dash) | Source column type needed |
| OI-4 | Confirm `Weeks in Program` derivation formula (calendar weeks vs business days) | Business rule needed |
| OI-5 | Confirm Recruiter:Technical Ratio formula (integer division or float) | Business rule needed |
| OI-6 | Confirm `segment_classification` label set (values and derivation logic) | Config V2 definition needed |
| OI-7 | Confirm `payment_risk_label` threshold values (what balance triggers HIGH vs MEDIUM) | Config V2 definition needed |

---

## END OF FILE
