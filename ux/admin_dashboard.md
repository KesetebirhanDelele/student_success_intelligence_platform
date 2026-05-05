# ux/admin_dashboard.md

---

## LAYER 12 — USER EXPERIENCE (ADMIN DASHBOARD)

---

## 1. PURPOSE

This file defines:

* Admin dashboard structure
* Key views and components
* Data visualization requirements
* Operator controls and workflows

The goal is to provide:

* Full system visibility
* Actionable insights
* Efficient monitoring and intervention

---

## 2. DASHBOARD OBJECTIVES

---

The dashboard MUST enable users to:

* Monitor system performance in real time
* Track student outreach lifecycle
* Identify at-risk students
* Investigate failures
* Trigger manual interventions

---

## 3. DASHBOARD STRUCTURE

---

### 3.1 Main Sections

```plaintext id="g8tx7m"
Overview  
Students  
Outreach Activity  
Failures  
Analytics  
Settings  
```

---

## 4. OVERVIEW DASHBOARD

---

### Displays

* Total students processed (daily)
* Outreach attempts (today)
* Contact success rate
* Meetings booked
* Sentiment distribution

---

### Visual Components

* KPI cards
* Trend charts
* Status summaries

---

### Scope Behavior

* MVP: Basic counters
* STANDARD: KPI + simple charts
* PRODUCTION: Full analytics + trends

---

---

## 5. STUDENT MANAGEMENT VIEW

---

### Features

* Search by:

  * UserID
  * Name
  * Email
* Filter by:

  * State
  * Checkpoint
  * Risk level

---

### Displays

* Student profile
* Current state
* Outreach history
* Decision outputs
* Transcript summary

---

---

## 6. OUTREACH ACTIVITY VIEW

---

### Displays

* All outreach attempts
* Attempt number
* Channel used (Call/SMS/Email)
* Result (Connected / No Response)
* Timestamp

---

### Features

* Sort by date
* Filter by checkpoint
* Filter by outcome

---

---

## 7. FAILURE DASHBOARD

---

### Displays

* Failed GHL triggers
* LLM failures
* Scheduler issues
* State violations

---

### Features

* Filter by failure type
* View recovery status
* Drill-down into logs

---

---

## 8. ANALYTICS DASHBOARD

---

### Metrics

* Outreach success rate
* Retry success rate
* Meeting conversion rate
* Sentiment trends
* IPBC conversion tracking

---

### Visualizations

* Line charts
* Bar charts
* Distribution graphs

---

---

## 9. MANUAL ACTIONS

---

### Allowed Actions

* Trigger outreach manually
* Retry outreach
* Mark case as resolved
* Force meeting booking (admin override)

---

### Constraints

* All actions must go through API
* Must validate state before execution
* Must log all actions

---

---

## 10. SETTINGS PANEL

---

### Configuration Options

* Feature flags (toggle)
* Scheduler time (view-only or configurable)
* Threshold values (future)

---

---

## 11. ROLE-BASED ACCESS

---

### MVP

* Single role (admin)

---

### STANDARD

* Basic roles:

  * Viewer
  * Operator

---

### PRODUCTION

* Full RBAC:

  * Viewer
  * Operator
  * Admin
  * Super Admin

---

---

## 12. PERFORMANCE REQUIREMENTS

---

* Dashboard load time ≤ 2 seconds
* API response ≤ 500 ms
* Pagination for large datasets

---

---

## 13. UX CONSTRAINTS

---

* No business logic in UI
* All decisions come from backend
* UI reflects real system state
* No hidden or derived UI-only data

---

---

## 14. ERROR HANDLING

---

### Rules

* Display user-friendly messages
* Hide technical details
* Provide retry options where safe

---

---

### Example

```plaintext id="qpvkn1"
"Unable to load data. Please try again."
```

---

---

## 15. SCOPE-SPECIFIC BEHAVIOR

---

### MVP

* Basic dashboard
* Minimal views
* Limited filtering

---

---

### STANDARD

* Full dashboards
* Core analytics
* Basic filtering

---

---

### PRODUCTION

* Full analytics suite
* Advanced filtering
* Failure monitoring
* Real-time updates (if supported)

---

---

## 16. ACCEPTANCE CRITERIA

---

### Case 1 — Overview Metrics

**Given** dashboard loaded
**When** data fetched
**Then** KPIs displayed correctly

---

---

### Case 2 — Student Detail

**Given** student selected
**When** view opened
**Then** full history shown

---

---

### Case 3 — Failure Visibility

**Given** system failures exist
**When** dashboard opened
**Then** failures displayed

---

---

### Case 4 — Manual Action

**Given** admin triggers action
**When** API call made
**Then** system executes and logs action

---

---

## 17. REFERENCES

---

Depends on:

* ux/user_experience.md
* spec/07_api_contracts.md
* runtime/system_loop.md
* state/system_state_model.md
* directives/core_decision_engine.md
* meta/project_classification.md

---

## END OF FILE
