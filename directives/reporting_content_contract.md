# directives/reporting_content_contract.md

---

## REPORTING CONTENT CONTRACT

---

> **Status:** Partially resolved. Source field mappings updated from CCPP SQL Server SPs
> provided 2026-05-29. Fields still marked `[TBD — pending confirmation]` need answers
> to OI-8 through OI-16 before data-fetching implementation begins.
>
> No implementation work should begin on data-fetching for any `[TBD]` field until
> that entry is resolved and this directive is updated.

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
| `MSSQL_MIRROR` | SQL Server CCPP database (see Section 10 for table inventory) | **Authoritative** — wins on conflict | Sync'd into `student_trigger_data` via `POST /sync/mssql` |
| `MSSQL_INTERVIEW_PREP` | SQL Server `AI_ChatBot_TriggerData_InterviewPrep` | Authoritative | Sync'd into `student_interview_prep`. Source table definition pending (OI-2). |
| `PLATFORM` | PostgreSQL platform-owned records | Platform-owned | `outreach_history`, `state_transition_log`, `student_notes`, etc. |
| `AI_GENERATED` | LLM narrative text | Advisory only | Stored in `ai_insights` (live) or `warehouse.snapshot_ai_narratives` (finalized) |
| `GHL_SUPPLEMENTARY` | GHL API cache (`ghl_messages`) | Supplementary — `MSSQL_MIRROR` wins on conflict | Contact/communication metadata only |
| `DERIVED` | Computed by platform at sync or finalization time | Platform-owned | `risk_level`, `priority_score`, `segment_classification`, `payment_risk_label` |

**NOTE (OI-8):** The prior spec referenced `AI_ChatBot_TriggerData` as the single MSSQL
source table. Actual CCPP SPs query multiple tables and views. Confirm whether
`AI_ChatBot_TriggerData` is a denormalized aggregate of the tables in Section 10, or
whether it is a separate table entirely (OI-8 tracks this).

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
| Full Name | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.MM_Student` (pre-joined `dnnuser.Users.FirstName + ' ' + LastName`) |
| User ID | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.MM_UserID` (= `dnnuser.Users.UserID`) |
| Email | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.StudentEmail` (= `dnnuser.Users.Email`) |
| Phone | `MSSQL_MIRROR` | `UDF_GET_USER_PHONENUMBER(MM_UserID)` — [TBD — UDF source table; see OI-9] |
| Program Path | `MSSQL_MIRROR` | `ISNULL(IPBC_SubscriptionPlan.DisplayName, CB_SUBSCRIPTION_PLANS.PlanName)` |
| IPBC Start Date | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.IPBC_StartDate` |
| Weeks in Program | `DERIVED` | `ADF_Mentorship_Activity.WksInProgram` (pre-computed in SQL Server view; stored as-is at sync) |

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
| Segment Classification | `DERIVED` | Cohort segment label computed at finalization (OI-6) |
| Payment Risk Label | `DERIVED` | HIGH / MEDIUM / LOW — based on payment balance thresholds (OI-7) |

---

### 3.4 Section 3 — Academic Performance

| Display field | Source category | Source column |
|---|---|---|
| HWs Behind | `MSSQL_MIRROR` | [TBD — confirm whether explicit column in `ADF_Mentorship_Activity` or derived from `COUNT(DISTINCT adf_homework.sectionID)` vs expected sections; see OI-10] |
| Avg Effort Rating | `MSSQL_MIRROR` | [TBD — not found in SPs provided; see OI-11] |
| HW Submitted Days Ago | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.LastHWSubmittedDays` |
| Attendance % | `MSSQL_MIRROR` | [TBD — confirm whether `ADF_Mentorship_Activity.PerOnPace * 100` or separate attendance column; see OI-14] |
| Active Status | `MSSQL_MIRROR` | `ADF_Mentorship_Program.IsActive` (1 = Active, 0 = Suspended; rendered as "Active" / "Suspended") |
| Current Section | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.CurrSection_Phase1` |
| Status I | `MSSQL_MIRROR` | [TBD — possibly `ADF_Mentorship_Activity.MM_Status`; see OI-13] |
| Status II | `MSSQL_MIRROR` | [TBD — see OI-13] |
| HW Risk Score | `DERIVED` | Computed from HWs Behind + Avg Effort Rating at finalization |
| % Completed (Active) | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.PerComp_Act` (float 0–1; multiply by 100 for display) |
| Days to Market | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.DaysToMarket` [TBD — confirm business definition; see OI-16] |

---

### 3.5 Section 4 — Engagement

| Display field | Source category | Source column |
|---|---|---|
| Last Activity Days | `MSSQL_MIRROR` | DERIVED at sync: `DATEDIFF(day, VW_RETOOL_CAMPAIGNACTIVITY_LASTACTIVITY.LastActivityDate, GETDATE())` |
| Last Activity Type | `MSSQL_MIRROR` | `VW_RETOOL_CAMPAIGNACTIVITY_LASTACTIVITY.LastActivityType` |
| Last Activity Notes | `MSSQL_MIRROR` | `VW_RETOOL_CAMPAIGNACTIVITY_LASTACTIVITY.Notes` |
| Last Login Days | `MSSQL_MIRROR` | [TBD — source not found in provided SPs; see OI-12] |
| Current Class Name | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.CurrSection_Phase1` |
| Last Activity Section | `MSSQL_MIRROR` | [TBD — confirm if same as CurrSection_Phase1 or separate column; see OI-12] |

---

### 3.6 Section 5 — Financial

| Display field | Source category | Source column |
|---|---|---|
| Total Contract Value | `MSSQL_MIRROR` | `IPBC_SubscriptionPlan.TotalCost` |
| Down Payment Amount | `MSSQL_MIRROR` | `IPBC_SubscriptionPlan.InitialDownPayment` |
| Total Payments Made | `MSSQL_MIRROR` | `vw_IPBC_Students_Payment_Summary.TotalAmountInPaySimple + vw_IPBC_Students_Payment_Summary.TotalAmountInPayPal` (DERIVED sum) |
| DA Fees Paid | `MSSQL_MIRROR` | `VW_PAYPAL_DISTINCT_TRANSACTIONS.Amount` where `TRANSTYPE='T' AND PaymentStatus != 'PENDING'` (sum per student) |
| Amount Paid (net) | `DERIVED` | `TotalAmountInPaySimple + TotalAmountInPayPal - DAFeesPaid` |
| Payment Balance | `DERIVED` | `IPBC_SubscriptionPlan.TotalCost - AmountPaid(net)` |
| Fee Paid | `MSSQL_MIRROR` | [TBD — confirm whether this is InitialDownPayment (down payment) or DAFeesPaid; see OI-15] |
| Payment Risk Label | `DERIVED` | Computed from Payment Balance at finalization (OI-7) |

---

### 3.7 Section 6 — Outreach Summary (snapshot month)

Sourced from `outreach_history` and `state_transition_log` records within the snapshot
month window. Copied as aggregated counts into the snapshot row at finalization.

**Legacy note:** The CCPP Retool dashboard stores campaign activity in
`VW_RETOOL_CAMPAIGNACTIVITY_LASTACTIVITY` (SQL Server). The platform records new
outreach in PostgreSQL `outreach_history`. At platform launch, existing Retool activity
is imported as initial state; from that point forward, the platform is authoritative.

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

### Shared columns (present in all tabs)

| Display column | Source category | Source column |
|---|---|---|
| Student Name | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.MM_Student` |
| UserID | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.MM_UserID` |
| Email | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.StudentEmail` |
| Phone | `MSSQL_MIRROR` | `UDF_GET_USER_PHONENUMBER(MM_UserID)` [TBD — UDF source; OI-9] |
| Program Path | `MSSQL_MIRROR` | `ISNULL(IPBC_SubscriptionPlan.DisplayName, CB_SUBSCRIPTION_PLANS.PlanName)` |
| IPBC Start Date | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.IPBC_StartDate` |
| Weeks in Program | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.WksInProgram` |
| Attendance % | `MSSQL_MIRROR` | [TBD — confirm PerOnPace*100 or separate column; OI-14] |
| Active | `MSSQL_MIRROR` | `ADF_Mentorship_Program.IsActive` (1=Active, 0=Suspended) |
| Status I | `MSSQL_MIRROR` | [TBD — OI-13] |
| Status II | `MSSQL_MIRROR` | [TBD — OI-13] |
| Last Campaign Activity Date | `MSSQL_MIRROR` | `VW_RETOOL_CAMPAIGNACTIVITY_LASTACTIVITY.LastActivityDate` |
| Last Campaign Activity Type | `MSSQL_MIRROR` | `VW_RETOOL_CAMPAIGNACTIVITY_LASTACTIVITY.LastActivityType` |
| Campaign Notes | `MSSQL_MIRROR` | `VW_RETOOL_CAMPAIGNACTIVITY_LASTACTIVITY.Notes` |
| Notes | `PLATFORM` | `student_notes` (latest note body) |

---

### 4.1 Newcomers Tab (17 columns)

**SP source:** IPBC NEW SIGNUPS query

**Filter logic:**
```sql
ADF_Mentorship_Program.CreateDate > DATEADD(M, -2, GETDATE())
AND U.UserID != 46095  -- excluded per business rule
```

Additional columns beyond shared set:

| Display column | Source category | Source column |
|---|---|---|
| IPBC Sign-Up Date | `MSSQL_MIRROR` | `ADF_Mentorship_Program.CreateDate` |
| Agreement Signed | `MSSQL_MIRROR` | `CB_HR_EDOCS.status = 1` where `HRDocumentId = 4` (1=signed, 0=not signed) |
| Plan Name | `MSSQL_MIRROR` | `ISNULL(IPBC_SubscriptionPlan.DisplayName, CB_SUBSCRIPTION_PLANS.PlanName)` |
| Down Payment Amount | `MSSQL_MIRROR` | `IPBC_SubscriptionPlan.InitialDownPayment` |
| Total Contract Value | `MSSQL_MIRROR` | `IPBC_SubscriptionPlan.TotalCost` |
| Amount Paid | `DERIVED` | `(TotalAmountInPaySimple + TotalAmountInPayPal) - DAFeesPaid` |

---

### 4.2 Engagement Tab (18 columns)

**SP source:** Not yet provided. (User to share.)

**Filter logic:** All active students [TBD — confirm filter from SP when provided]

Additional columns beyond shared set:

| Display column | Source category | Source column |
|---|---|---|
| Class Name | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.CurrSection_Phase1` |
| Last Activity Section | `MSSQL_MIRROR` | [TBD — confirm column; OI-12] |
| HW Submitted (days ago) | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.LastHWSubmittedDays` |
| Last Login Days | `MSSQL_MIRROR` | [TBD — source not found in provided SPs; OI-12] |

---

### 4.3 HW Risk Tab (20 columns)

**SP source:** IPBC - Homework not submitted for more than 3 days

**Filter logic:**
```sql
ADF_Mentorship_Activity.CurrSection_Phase1 LIKE '%IPBC%'
AND ADF_Mentorship_Activity.LastHWSubmittedDays > 3
AND ADF_Mentorship_Activity.PerOnPace < 1.00
```

Additional columns beyond shared set:

| Display column | Source category | Source column |
|---|---|---|
| Class Name (Current Section) | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.CurrSection_Phase1` |
| % On Pace | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.PerOnPace` (float 0–1; multiply by 100 for display) |
| HW Submitted (days ago) | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.LastHWSubmittedDays` |
| Weeks in Program | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.WksInProgram` |
| Days to Market | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.DaysToMarket` |
| Avg Effort Rating | `MSSQL_MIRROR` | [TBD — OI-11] |
| Last Login Days | `MSSQL_MIRROR` | [TBD — OI-12] |

---

### 4.4 CAP Hopefuls Tab (20 columns)

**SP source:** IPBC - Group 1 - CAP Hopefuls

**Filter logic:**
```sql
ADF_Mentorship_Activity.PerComp_Act > 0.30
AND ADF_Mentorship_Activity.MM_Status <> 'Dropouts'
AND ADF_Mentorship_Activity.CAP_StartDate IS NULL
AND ADF_Mentorship_Activity.LaunchStartDate IS NULL
AND ADF_Mentorship_Activity.CurrSection_Phase1 NOT LIKE '%launch%'
AND ADF_Mentorship_Activity.CurrSection_Phase1 NOT LIKE '%CAP%'
```

Additional columns beyond shared set:

| Display column | Source category | Source column |
|---|---|---|
| Class Name (Current Section) | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.CurrSection_Phase1` |
| % Completed (Active) | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.PerComp_Act` (float 0–1; multiply by 100 for display) |
| Last HW Submitted | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.LastHWSubmitted` (date) |
| HW Submitted (days ago) | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.LastHWSubmittedDays` |
| Days to Market | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.DaysToMarket` |
| Total Payments | `MSSQL_MIRROR` | `vw_IPBC_Students_Payment_Summary.TotalAmountInPaySimple + TotalAmountInPayPal` |
| Payment Balance | `DERIVED` | `IPBC_SubscriptionPlan.TotalCost - AmountPaid(net)` |
| Fee Paid | `MSSQL_MIRROR` | [TBD — OI-15] |

**Note:** Status I / Status II are present in this tab (shared columns, OI-13).
`CAP_StartDate` and `LaunchStartDate` are used in filter logic only; not displayed.

---

### 4.5 Launch Hopefuls Tab (20 columns)

**SP source:** IPBC - Group 2 - LAUNCH Hopefuls (to be provided by user).

**Filter logic:** [TBD — derived from Launch Hopefuls SP when provided]

Expected: same column schema as CAP Hopefuls with updated section filter (students who
HAVE a `CAP_StartDate` but no `LaunchStartDate`, near launch section).

---

### 4.6 Placement Hopefuls Tab (28 columns)

**SP source:** Not yet provided. (User to share.)

**Filter logic:** [TBD — derived from Placement Hopefuls SP when provided]

All CAP Hopefuls columns plus the following interview data columns (source:
`AI_ChatBot_TriggerData_InterviewPrep`):

| Display column | Source category | Source column |
|---|---|---|
| Last Interview | `MSSQL_INTERVIEW_PREP` | [TBD — OI-2] |
| Last Interview Days Ago | `DERIVED` | Computed from Last Interview date |
| Recruiter Interview Count | `MSSQL_INTERVIEW_PREP` | [TBD — OI-2] |
| Technical Interview Count | `MSSQL_INTERVIEW_PREP` | [TBD — OI-2] |
| Recruiter:Technical Ratio | `DERIVED` | Computed from above two counts (OI-5) |
| Avg Interview Prep Score | `MSSQL_INTERVIEW_PREP` | [TBD — OI-2] |
| Avg Interview Score | `MSSQL_INTERVIEW_PREP` | [TBD — OI-2] |
| ChatGPT Prompt | `MSSQL_INTERVIEW_PREP` | [TBD — OI-2] |

---

## 5. STUDENT DRAWER — PROFILE TAB

---

Displayed via `GET /students/{id}/profile`. All fields are read from
`student_trigger_data` plus `outreach_tracking`.

| Display field | Source category | Source column |
|---|---|---|
| Full Name | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.MM_Student` |
| Email | `MSSQL_MIRROR` | `ADF_Mentorship_Activity.StudentEmail` |
| Phone | `MSSQL_MIRROR` | `UDF_GET_USER_PHONENUMBER(MM_UserID)` [TBD — OI-9] |
| Program Path | `MSSQL_MIRROR` | `ISNULL(IPBC_SubscriptionPlan.DisplayName, CB_SUBSCRIPTION_PLANS.PlanName)` |
| HWs Behind | `MSSQL_MIRROR` | [TBD — OI-10] |
| Avg Effort Rating | `MSSQL_MIRROR` | [TBD — OI-11] |
| Inactive Days | `MSSQL_MIRROR` | DERIVED: `DATEDIFF(day, VW_RETOOL_CAMPAIGNACTIVITY_LASTACTIVITY.LastActivityDate, GETDATE())` |
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

1. **Do not implement data-fetching** for any field marked `[TBD]` until the open item
   is resolved and this directive is updated. The field list and section structure are
   confirmed; only the marked column references are still pending.

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

6. **Tab filter logic** is now documented per-tab from the actual SPs. Platform queries
   must reproduce these WHERE conditions exactly against `student_trigger_data`.
   Any deviation from the SP logic requires explicit sign-off.

7. **UserID exclusion:** SP for Newcomers excludes `UserID = 46095` per business
   instruction. This exclusion must be honoured in the platform sync/filter logic.

---

## 9. OPEN ITEMS (RESOLUTION REQUIRED BEFORE IMPLEMENTATION)

---

| # | Item | Status | Blocker |
|---|---|---|---|
| OI-1 | Map all `[TBD]` fields to source columns | **PARTIALLY RESOLVED** — most fields mapped from SPs 2026-05-29; remaining items tracked in OI-9 through OI-16 | Remaining TBDs need confirmation |
| OI-2 | Map Placement Hopefuls interview fields to `AI_ChatBot_TriggerData_InterviewPrep` columns | **OPEN** | Interview prep SP not yet provided |
| OI-3 | Confirm null display format per numeric field (0 vs dash) | **OPEN** | Source column type needed |
| OI-4 | Confirm `Weeks in Program` derivation formula | **RESOLVED** — `ADF_Mentorship_Activity.WksInProgram` (SQL Server view pre-computes it) | — |
| OI-5 | Confirm Recruiter:Technical Ratio formula | **OPEN** | Interview prep SP needed |
| OI-6 | Confirm `segment_classification` label set | **OPEN** | Config V2 definition needed |
| OI-7 | Confirm `payment_risk_label` threshold values | **OPEN** | Config V2 definition needed |
| OI-8 | Confirm whether `AI_ChatBot_TriggerData` is a denormalized view of the CCPP tables listed in Section 10, or a separate table | **OPEN** | CCPP schema clarification needed |
| OI-9 | Identify source table queried by `UDF_GET_USER_PHONENUMBER` | **OPEN** | UDF definition or source table needed |
| OI-10 | Confirm HWs Behind source: explicit column in `ADF_Mentorship_Activity` or derived from `adf_homework.sectionID` count vs expected count | **OPEN** | Business rule + source column needed |
| OI-11 | Confirm Avg Effort Rating source column and table | **OPEN** | Not found in any SP provided so far |
| OI-12 | Confirm Last Login Days and Last Activity Section source columns | **OPEN** | Not found in SPs; may require separate login-tracking table |
| OI-13 | Confirm Status I and Status II source columns (possibly `ADF_Mentorship_Activity.MM_Status`?) | **OPEN** | Column definition or SP showing their usage needed |
| OI-14 | Confirm Attendance %: is it `ADF_Mentorship_Activity.PerOnPace * 100` or a separate attendance column? | **OPEN** | Business rule confirmation needed (`PerOnPace` = "on pace", not attendance per se) |
| OI-15 | Confirm Fee Paid display field: `IPBC_SubscriptionPlan.InitialDownPayment` (down payment amount) or `DAFeesPaid` from `VW_PAYPAL_DISTINCT_TRANSACTIONS`? | **OPEN** | Business rule clarification needed |
| OI-16 | Confirm `DaysToMarket` business definition (days from current date to expected job placement? days remaining in program?) | **OPEN** | Business definition needed |

---

## 10. SQL SERVER SOURCE TABLES INVENTORY

---

Source tables and views identified from CCPP SPs provided 2026-05-29. These are the
SQL Server objects that must be mirrored into `student_trigger_data` (PostgreSQL).

| Table / View | Purpose | Key columns identified |
|---|---|---|
| `CCPP.dbo.ADF_Mentorship_Activity` | Primary denormalized engagement view. Most per-student metrics live here. | `MM_Student`, `StudentEmail`, `MM_UserID`, `MM_Mentor`, `MentorEmail`, `SuperMentor`, `SuperMentorEmail`, `IPBC_Instructor`, `IPBC_InstructorEmail`, `CurrSection_Phase1`, `PerOnPace`, `PerComp_Act`, `LastHWSubmitted`, `LastHWSubmittedDays`, `WksInProgram`, `DaysToMarket`, `IPBC_StudentsActive`, `IPBC_StartDate`, `CAP_StartDate`, `LaunchStartDate`, `MM_Status` |
| `CCPP.dbo.dnnuser.Users` | Student identity | `UserID`, `FirstName`, `LastName`, `Email` |
| `CCPP.dbo.ADF_Mentorship_Program` | Enrollment / subscription record | `StudentUserID`, `ClassSignupsID`, `CreateDate`, `IsActive` |
| `CCPP.dbo.ADF_ClassSignups` | Class-level enrollment | `ClassSignupsID`, `SubscriptionPlanID` |
| `CCPP.dbo.CB_SUBSCRIPTION_PLANS` | Plan names (fallback) | `PlanName` |
| `CCPP.dbo.IPBC_SubscriptionPlan` | Plan details (preferred) | `DisplayName`, `InitialDownPayment`, `TotalCost`, `PlanName` |
| `CCPP.dbo.vw_IPBC_Students_Payment_Summary` | Payment totals view | `ClassSignupsID`, `TotalAmountInPaySimple`, `TotalAmountInPayPal` |
| `CCPP.dbo.VW_PAYPAL_DISTINCT_TRANSACTIONS` | PayPal transaction detail | `ClassSignupsID`, `Amount`, `TRANSTYPE`, `PaymentStatus` (used to compute DAFeesPaid) |
| `CCPP.dbo.CB_HR_EDOCS` | Agreement/document records | `UserID`, `HRDocumentId`, `status` (`HRDocumentId=4` = IPBC agreement) |
| `CCPP.dbo.adf_homework` | HW submission records | `ClassSignupsID`, `sectionID` (COUNT DISTINCT = HWs submitted) |
| `CCPP.dbo.VW_RETOOL_CAMPAIGNACTIVITY_LASTACTIVITY` | Most recent campaign touchpoint per student | `UserID`, `LastActivityDate`, `LastActivityType`, `Notes` |
| `CCPP.dbo.vw_IPBC_Signups` | IPBC signup view | Wraps ADF_ClassSignups + related; includes `StudentUserId`, `ClassSignupsID`, `IPBC_StartDate`, `ClassStartDate`, `CertifiedDate` |
| `UDF_GET_USER_PHONENUMBER` | Scalar UDF returning phone number for a UserID | Source table TBD (OI-9) |

**IPBC curriculum constant:** Homework completion percentage uses `27.0` as the total
section count: `COUNT(DISTINCT adf_homework.sectionID) / 27.0 * 100`. Confirm whether
this constant is fixed or should come from a config value (OI-10).

---

## END OF FILE
