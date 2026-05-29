# Open Risks Register

**Document ID:** ORR-001  
**Status:** ACTIVE  
**Classification:** Operational Risk Register  
**Governs:** Known open risks for PRODUCTION-SHADOW operation  
**Reference:** PRR-001 (Production Readiness Review)  
**Last Updated:** 2026-05-29  

---

> This register tracks all open risks identified during the Phase 58 Production Readiness Review.  
> Risks are not sorted by severity — they are organized by domain.  
> Each risk entry includes: ID, severity, description, observable signal, current mitigation, recommended remediation, owner, and resolution criteria.  
> This document is append-only. Resolved risks are marked RESOLVED with a date, not removed.

---

## Risk Severity Scale

| Severity | Definition |
|---|---|
| CRITICAL | Blocks SHADOW operation. Must resolve before any production traffic. |
| HIGH | Does not block SHADOW start but must resolve within first week of SHADOW operation. Unresolved, it becomes a CRITICAL risk before LIVE authorization. |
| MEDIUM | Should resolve during SHADOW operation. Does not block SHADOW or LIVE authorization individually, but accumulates with other MEDIUM risks. |
| LOW | Informational. Track and address at next planned maintenance window. |

---

## Domain: Runtime Configuration

---

### RISK-001 — Config V2 Startup Query Gap

| Field | Value |
|---|---|
| **ID** | RISK-001 |
| **Severity** | CRITICAL |
| **Status** | OPEN |
| **Opened** | 2026-05-29 |
| **Domain** | Runtime Configuration |
| **Reference** | UC-001, PRR-001 Section 4.2 |

**Description:**  
`app/main.py` passes `active_configs=[]` to `initialize_runtime_context()` at every startup. The `config_version_registry` table was created and seeded with a V1 ACTIVE record by migration 0003, but the startup sequence never queries it. Every startup therefore produces `config_version_id=UNKNOWN_V0` and `degradation_state=True`. Orchestration thresholds fall back to environment variables (`MAX_ATTEMPTS`, `RETRY_INTERVAL_HOURS`) instead of Config V2 governed values.

**Observable Signal:**  
Startup JSON log shows `"config_version_id": "UNKNOWN_V0"` and `"degradation_state": true` on every cold start.

**Current Mitigation:**  
None. The platform degrades gracefully (SHADOW_ONLY scope, no live effects), so it does not crash. But Config V2 governance is not operative.

**Recommended Remediation:**  
1. In `main.py` `on_startup()`, before calling `initialize_runtime_context()`, query `config_version_registry` for the single row with `status='ACTIVE'`  
2. Build the `active_configs` list from that row  
3. Pass it to `initialize_runtime_context()`  
4. Verify startup log shows a real `config_version_id` (e.g., `cv_v1_...` or the DB row ID)

**Owner:** Engineering Lead  
**Resolution Criteria:** Startup log shows `"config_version_id"` != `"UNKNOWN_V0"` and `"degradation_state": false` for a clean startup with PostgreSQL running.

---

### RISK-002 — AI Provider Identity Mismatch

| Field | Value |
|---|---|
| **ID** | RISK-002 |
| **Severity** | HIGH |
| **Status** | OPEN |
| **Opened** | 2026-05-29 |
| **Domain** | Runtime Configuration |
| **Reference** | UC-002, PRR-001 Section 3.3 |

**Description:**  
The `.env` file configures `LLM_API_KEY` (an OpenAI `sk-proj-*` key) and `LLM_MODEL=gpt-4o`. Governance documentation, the `.env.example`, and the `ANTHROPIC_MODEL=claude-sonnet-4-6` value in `.env.example` reference Anthropic as the canonical AI provider. FAD-3 (deterministic execution records) and lineage reproducibility require knowing exactly which model produced which AI advisory output. If OpenAI is the runtime provider but Anthropic is the documented provider, audit trails are incorrect.

**Observable Signal:**  
`config.py` `LLM_API_KEY` is set to an `sk-proj-*` (OpenAI) key. `ANTHROPIC_API_KEY` in `.env` is absent.

**Current Mitigation:**  
In SHADOW mode, AI advisory outputs are advisory-only and do not produce live effects. Mismatch has no production impact in SHADOW.

**Recommended Remediation:**  
1. Decide on the canonical AI provider (Anthropic or OpenAI)  
2. Update `.env.example` and `config.py` to use consistent variable names  
3. Update governance docs if the model attribution record references a different provider  
4. If Anthropic: obtain `ANTHROPIC_API_KEY`, update `.env`, rotate the OpenAI key if it is no longer needed  
5. If OpenAI: update `.env.example`, governance docs, and attribution model to reference `gpt-4o`

**Owner:** Platform Owner  
**Resolution Criteria:** `.env`, `.env.example`, `config.py`, and governance attribution docs all reference the same AI provider and model. No ambiguity in audit trail.

---

## Domain: Infrastructure

---

### RISK-003 — PostgreSQL Running State Unconfirmed

| Field | Value |
|---|---|
| **ID** | RISK-003 |
| **Severity** | CRITICAL |
| **Status** | OPEN |
| **Opened** | 2026-05-29 |
| **Domain** | Infrastructure |
| **Reference** | UC-007, PRR-001 Section 3.1 |

**Description:**  
Docker Compose and Alembic migrations are correctly defined, but no evidence exists that a PostgreSQL instance is currently running with migrations applied in the target PRODUCTION-SHADOW environment. The platform fails to start if PostgreSQL is unreachable (`init_db()` is the first startup call).

**Observable Signal:**  
Application startup failure with a connection error from `asyncpg` if PostgreSQL is not running.

**Current Mitigation:**  
Docker Compose definition is correct and will start PostgreSQL if executed. Three migrations are ready to apply.

**Recommended Remediation:**  
1. In the target environment: `docker compose up -d db`  
2. Wait for healthcheck: `docker compose ps` shows `(healthy)` for `db`  
3. Run `alembic upgrade head`  
4. Verify: `psql -U ssip ssip -c "SELECT version_number, status FROM config_version_registry WHERE status='ACTIVE';"` returns 1 row  
5. Start the API: `docker compose up -d api`  
6. Confirm startup log shows `"event": "application_started"` with `"degradation_state": false` (after RISK-001 is fixed)

**Owner:** Operations Lead  
**Resolution Criteria:** PostgreSQL healthcheck passes, all 3 migrations applied, V1 ACTIVE config row present, API starts successfully.

---

### RISK-004 — SQL Server Connectivity Unconfirmed

| Field | Value |
|---|---|
| **ID** | RISK-004 |
| **Severity** | HIGH |
| **Status** | OPEN |
| **Opened** | 2026-05-29 |
| **Domain** | Infrastructure |
| **Reference** | UC-008, PRR-001 Section 3.2 |

**Description:**  
SQL Server credentials are configured (`mssql_configured=True`), but no runtime connectivity smoke test has been executed. Sync operations depend on reading from `hypv8669.hostedbyappliedi.net:1433`. If the host is unreachable, sync will fail. The governance layer degrades gracefully (attribution preserved, no live effects), but student data will not be ingested.

**Observable Signal:**  
Sync endpoint returns degradation response. Structured log shows `"event": "sync_failed"` with `"error_class": "UpstreamUnavailable"` or similar.

**Current Mitigation:**  
`settings.mssql_configured` property confirms credentials are present. Graceful degradation is implemented and certified (OBSERVABILITY_DEGRADATION path).

**Recommended Remediation:**  
Execute connectivity test:
```python
import pyodbc
conn = pyodbc.connect(settings.mssql_dsn, timeout=10)
cursor = conn.execute("SELECT 1 AS alive")
print(cursor.fetchone())
conn.close()
```
Document result. If unreachable, investigate firewall / VPN requirements.

**Owner:** Engineering Lead  
**Resolution Criteria:** `SELECT 1` succeeds within 10 seconds against the production SQL Server host. Result documented with timestamp.

---

### RISK-005 — No Monitoring Infrastructure

| Field | Value |
|---|---|
| **ID** | RISK-005 |
| **Severity** | MEDIUM (HIGH before LIVE) |
| **Status** | OPEN |
| **Opened** | 2026-05-29 |
| **Domain** | Infrastructure |
| **Reference** | UC-003, PRR-001 Section 3.7 |

**Description:**  
No external metric collection (Prometheus, CloudWatch, Datadog, etc.), no alerting (PagerDuty, Opsgenie, alertmanager), and no structured log aggregation (Loki, Splunk, ELK) are provisioned. LIVE-MON-001 Section 7 requires these components be operational before LIVE. For SHADOW, log-based monitoring via stdout is acceptable but limits visibility.

**Observable Signal:**  
No monitoring dashboard accessible. No alert channel configured. Logs only visible via `docker compose logs`.

**Current Mitigation:**  
Application emits structured JSON logs to stdout. `app/routers/metrics.py` exposes a metrics endpoint. OpenTelemetry is installed. All observability primitives are in the application layer.

**Recommended Remediation:**  
For SHADOW minimum:
1. Configure log forwarding from stdout to a queryable store (minimum: `docker compose logs -f` + a log file with rotation)  
2. Document the manual monitoring procedure  

For pre-LIVE (required, not optional):
1. Prometheus scrape against `/metrics` endpoint  
2. Alertmanager rule for INV-3 / INV-4 violations  
3. Grafana dashboard for `authorized_scope_count`, `live_effects_produced`, `certification_outcome`  
4. On-call page channel configured

**Owner:** Operations Lead  
**Resolution Criteria (SHADOW):** Logs are queryable for the prior 24 hours. Manual monitoring procedure is documented.  
**Resolution Criteria (pre-LIVE):** Metric pipeline operational, alerting tested (item B-3 in LIVE-CHK-001).

---

### RISK-006 — No Database Backup Strategy

| Field | Value |
|---|---|
| **ID** | RISK-006 |
| **Severity** | MEDIUM |
| **Status** | OPEN |
| **Opened** | 2026-05-29 |
| **Domain** | Infrastructure |
| **Reference** | PRR-001 Section 3.8 |

**Description:**  
No PostgreSQL backup or WAL archiving strategy is defined. Any real student data ingested from SQL Server during SHADOW operation would be unrecoverable if the Docker volume is lost. Governance artifacts (activation records, operator reports, audit logs) must be retained for 2 years per LIVE-MON-001 Section 5.3 — currently these are only in the unbackedup PostgreSQL volume.

**Observable Signal:**  
`docker volume inspect ssip_pg_data` shows data on a local volume with no replication or backup policy.

**Current Mitigation:**  
Data is currently in SHADOW; no live student data has been sent. Risk increases as real student data is ingested.

**Recommended Remediation:**  
Minimum: daily `pg_dump` to a separate storage volume, retained for 30 days.  
Target: point-in-time recovery with WAL archiving + S3-compatible object store.

**Owner:** Operations Lead  
**Resolution Criteria:** Automated backup running, restore tested, backup retention documented.

---

## Domain: Test Infrastructure

---

### RISK-007 — pytest-asyncio Python 3.14 Incompatibility

| Field | Value |
|---|---|
| **ID** | RISK-007 |
| **Severity** | MEDIUM |
| **Status** | OPEN |
| **Opened** | 2026-05-29 |
| **Domain** | Test Infrastructure |
| **Reference** | UC-006, PRR-001 Section 1 |

**Description:**  
17 tests in `test_scheduler_governance.py` fail because pytest-asyncio 1.3.0 does not correctly activate asyncio mode under Python 3.14.4. The `pytest.ini` `asyncio_mode = auto` setting is not effective. All 17 failures produce "async def functions are not natively supported." The governance contracts covered by these tests are verified by synchronous equivalents in Phases 53–56. No production logic is broken.

**Observable Signal:**  
`pytest tests/test_scheduler_governance.py` shows 17 FAILED with "async def functions are not natively supported."

**Current Mitigation:**  
All governance contracts covered by these tests are also certified in `test_shadow_certification.py`, `test_replay_certification.py`, `test_end_to_end_governance.py`, and `test_orchestration_pipeline.py` using synchronous equivalents.

**Recommended Remediation:**  
1. Pin pytest-asyncio to a Python 3.14-compatible version (e.g., `pytest-asyncio>=0.23,<1.0`)  
2. Or upgrade to `pytest-asyncio>=1.3.1` if a Python 3.14 fix is released  
3. Verify all 17 tests pass after the version change  
4. Add to `requirements.txt` or `pyproject.toml` with the version pin

**Owner:** Engineering Lead  
**Resolution Criteria:** `pytest tests/test_scheduler_governance.py` shows 46 passed, 0 failed.

---

## Domain: Credentials and Security

---

### RISK-008 — Credentials Present in `.env` File

| Field | Value |
|---|---|
| **ID** | RISK-008 |
| **Severity** | HIGH |
| **Status** | OPEN |
| **Opened** | 2026-05-29 |
| **Domain** | Credentials / Security |
| **Reference** | UC-004, PRR-001 Section 2.2 |

**Description:**  
The `.env` file contains plaintext SQL Server credentials (`AgentCory` / `Iam2AgentCory!`), a Mandrill API key (`md-HkBav1fdtJSoh8GbIw60Xg`), and an OpenAI API key (`sk-proj-*`). CLAUDE.md Section Security states secrets must not be in source code or commit history. If `.env` is not in `.gitignore`, all these credentials are in version control history.

**Observable Signal:**  
`git log --all -- .env` — if this returns commits, the file was committed at some point. `cat .gitignore | grep .env` — if `.env` does not appear, it is not excluded.

**Current Mitigation:**  
Unknown — `.gitignore` contents were not reviewed during this audit.

**Recommended Remediation:**  
1. Immediately check: `git check-ignore -v .env`  
2. If tracked: rotate ALL credentials now (SQL Server, Mandrill, OpenAI), clean history (`git filter-branch` or `git filter-repo`), add `.env` to `.gitignore`  
3. If untracked: no immediate action needed, but confirm this is the case  
4. Move credentials to a secrets manager or environment variable injection (Docker secrets, Vault, etc.) before production use

**Owner:** Engineering Lead  
**Resolution Criteria:** `.env` is confirmed untracked. All credentials in `.env` rotated if the file was ever committed. Verification documented with git commands and timestamp.

---

### RISK-009 — Mandrill Integration Not in Governance Transport Layer

| Field | Value |
|---|---|
| **ID** | RISK-009 |
| **Severity** | HIGH |
| **Status** | OPEN |
| **Opened** | 2026-05-29 |
| **Domain** | Credentials / Governance |
| **Reference** | UC-010, PRR-001 Section 2.2 |

**Description:**  
`MANDRILL_API_KEY` and `MANDRILL_SENDER_EMAIL` are present in `.env` but Mandrill is not referenced in the Phase-51 governance transport layer (`app/services/integrations/email.py`). `email.py` likely uses its own credential path. If Mandrill is used to send student-facing communications, it must be gated by `ProviderOrchestrationAssessment` scope checking. If it bypasses the governance transport, it can send emails without authorization — an INV-4 violation.

**Observable Signal:**  
Any code path that calls Mandrill without first checking `governance_scope == AUTHORIZED` (or equivalent) is a potential bypass.

**Current Mitigation:**  
In SHADOW mode, all execution records are SHADOW_ONLY or REPLAY_ONLY. If Mandrill calls are gated on `is_shadow` or equivalent, they are suppressed. But this is the exact pattern Phase 51 replaced with explicit governance scope checking.

**Recommended Remediation:**  
1. Audit all code that references `MANDRILL_API_KEY`: `grep -r "MANDRILL" app/`  
2. Verify each call site is gated by the Phase-51 governance dispatch pattern (checks `governance_scope` before dispatch)  
3. If any call site uses direct `is_shadow` boolean check, replace with explicit scope check  
4. If Mandrill is used only for internal ops notifications (Cory briefings, Ali alerts), document this explicitly and confirm it is not student-facing

**Owner:** Platform Owner  
**Resolution Criteria:** Every Mandrill call site audited and documented. Student-facing Mandrill calls gated by governance transport layer. Internal-only Mandrill calls explicitly documented as ops notifications.

---

## Domain: Operations

---

### RISK-010 — On-Call Rotation Undefined

| Field | Value |
|---|---|
| **ID** | RISK-010 |
| **Severity** | MEDIUM |
| **Status** | OPEN |
| **Opened** | 2026-05-29 |
| **Domain** | Operations |
| **Reference** | UC-009, PRR-001 Section 5.4 |

**Description:**  
`operations/post_launch_monitoring.md` Section 4.4 lists escalation contacts as `[defined in on-call rotation]` and `[defined in team directory]` for all roles except Platform Owner. No on-call rotation exists. LIVE-DIS-001 Section 2.1 requires at least one person with emergency disable authority available at all times. During SHADOW operation, this is a lower-risk gap; during LIVE it is a hard requirement.

**Observable Signal:**  
LIVE-MON-001 Section 4.4 shows placeholder values for On-call operator, Operations Lead, and Technical Lead.

**Current Mitigation:**  
Platform Owner (ali@colaberry.com) has emergency disable authority and a defined 1-hour SLA. For SHADOW operation, this single point of contact is minimally acceptable.

**Recommended Remediation:**  
1. Name at least one on-call operator with emergency disable authority  
2. Update LIVE-MON-001 Section 4.4 with real names and contact info  
3. Brief the named operator on LIVE-DIS-001 — run the dry-run together  
4. Before LIVE: establish a formal on-call rotation with coverage SLA

**Owner:** Platform Owner  
**Resolution Criteria:** Minimum one named on-call operator in LIVE-MON-001 Section 4.4. That operator has been briefed on LIVE-DIS-001 and has practiced the dry-run.

---

## Risk Summary Table

| ID | Severity | Domain | Summary | Status |
|---|---|---|---|---|
| RISK-001 | CRITICAL | Runtime Config | Config V2 startup never queries DB → UNKNOWN_V0 always | OPEN |
| RISK-002 | HIGH | Runtime Config | AI provider mismatch (OpenAI in .env, Anthropic in docs) | OPEN |
| RISK-003 | CRITICAL | Infrastructure | PostgreSQL running state unconfirmed | OPEN |
| RISK-004 | HIGH | Infrastructure | SQL Server connectivity unconfirmed | OPEN |
| RISK-005 | MEDIUM | Infrastructure | No external monitoring infrastructure | OPEN |
| RISK-006 | MEDIUM | Infrastructure | No database backup strategy | OPEN |
| RISK-007 | MEDIUM | Test Infrastructure | pytest-asyncio Python 3.14 incompatibility (17 failing tests) | OPEN |
| RISK-008 | HIGH | Credentials / Security | Credentials in `.env`; git tracking status unknown | OPEN |
| RISK-009 | HIGH | Credentials / Governance | Mandrill not in governance transport layer | OPEN |
| RISK-010 | MEDIUM | Operations | On-call rotation undefined | OPEN |

---

## Blocked Items (risks that block SHADOW start)

| ID | Severity | Summary |
|---|---|---|
| RISK-001 | CRITICAL | Config V2 startup query gap — every startup produces UNKNOWN_V0 |
| RISK-003 | CRITICAL | PostgreSQL must be confirmed running with migrations applied |

All other risks are tracked for resolution during or before SHADOW operation but do not prevent starting PRODUCTION-SHADOW.

---

*This register is a governance artifact. Entries are added when new risks are identified. Entries are marked RESOLVED when resolution criteria are confirmed, never deleted. Updates include date and summary of resolution evidence.*
