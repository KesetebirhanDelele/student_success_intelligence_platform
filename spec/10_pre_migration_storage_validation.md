# spec/10_pre_migration_storage_validation.md

---

## LAYER 2 — SPECIFICATIONS (PRE-MIGRATION STORAGE VALIDATION)

---

## PURPOSE

This document performs a formal pre-migration storage validation for the SSIP warehouse physical architecture defined in `spec/09_warehouse_physical_architecture.md`. It validates AI narrative payload sizing, snapshot physicalization design, event storage appropriateness, config version enforcement, compliance storage correctness, and migration sequencing before any migration code is written.

**Scope of this document:** Architecture and planning validation only. No SQL DDL, Alembic migrations, ORM models, or implementation code appears in this document.

**Canonical inputs:** `spec/01_requirements.md`, `spec/03_state_transition_rules.md`, `spec/04_idempotency_concurrency.md`, `spec/08_data_model.md`, `spec/09_warehouse_physical_architecture.md`

**Preservation constraints (mandatory throughout):**
- Append-only finalized reporting
- Immutable publication lineage
- Frozen AI narrative semantics (FAD-1)
- Reproducibility fingerprint guarantees (FAD-6)
- Compliance audit isolation (FAD-4)
- Snapshot-centric historical architecture (FAD-2)
- SQL Server authority boundaries (FAD-5)

---

## 1. AI NARRATIVE STORAGE VALIDATION

---

### 1.1 Two-Table Design: Physical Storage Implications

The proposed design separates snapshot storage into:

- `warehouse.student_snapshots` — compact metrics row
- `warehouse.snapshot_ai_narratives` — 1:1 AI text companion

**PostgreSQL TOAST behavior and its implications for this design:**

PostgreSQL triggers TOAST (The Oversized Attribute Storage Technique) when a stored value exceeds approximately 2,040 bytes (BLCKSZ/4 at the default 8KB page size). Values above this threshold are first compressed in-line (PGLZ); if still oversized, they are moved out-of-line to a separate TOAST relation with a 20-byte pointer in the main heap row.

This has two direct implications for the AI narrative decision:

**Implication A — When AI text is TOASTed (> ~2KB per field):**
In the single-table design, analytical queries on metric columns do NOT load TOAST values unless the query explicitly selects them. TOAST deferral means a `SELECT segment_classification, payment_risk_label FROM warehouse.student_snapshots` scan will NOT read the AI text TOAST pages. In this regime, the single-table approach has lower I/O overhead than intuition suggests.

**Implication B — When AI text is inline (< ~2KB per field):**
If any AI narrative field is below the TOAST threshold and stored inline, it consumes physical page space in the main heap even when not selected. Five fields of 1KB each adds ~5KB of inline text to every snapshot row. At 8KB page size, this leaves room for only one snapshot row per page, multiplying sequential scan I/O by 5–10× compared to a compact row.

**Critical observation:** The two-table design is architecturally superior in both regimes:
- When text is TOASTed: both designs share the TOAST deferral benefit, but the two-table design additionally keeps the snapshot row physically compact (no TOAST pointer overhead, cleaner buffer pool usage)
- When text is inline: the two-table design completely eliminates the row bloat problem because AI text never lives in the metrics table

**Storage geometry at target scale (2,000 students × 36 months):**

| Design | Snapshot metrics rows | Total AI text rows | Avg row width (metrics) | Pages for full scan |
|---|---|---|---|---|
| Single-table (text inline, ~1KB/field) | 72,000 combined | — | ~5,500 bytes | ~49,500 pages |
| Single-table (text TOASTed, ~5KB/field) | 72,000 combined | — | ~500 bytes + 5×20-byte TOAST ptrs | ~5,400 pages |
| Two-table (recommended) | 72,000 metric rows | 72,000 companion rows | ~400 bytes (metrics only) | ~3,600 pages |

The two-table design delivers the most compact metrics table regardless of AI text size, because TOAST pointers (even when text IS TOASTed) still consume 20 bytes each inline per field. Five TOAST pointers = 100 bytes saved per row × 72,000 rows = ~7MB of page savings — meaningful in shared_buffers.

### 1.2 Analytical Query Performance

**Trend analysis query pattern (most critical):**
Report generation reads metrics for all students in a cohort for a given `snapshot_month`. This is a cohort-wide scan on `warehouse.student_snapshots` filtering by `(snapshot_month, segment_classification)` or similar. In the two-table design, this scan operates on the metrics-only table with no AI text loaded whatsoever — the query planner never visits `snapshot_ai_narratives`.

In a single-table design, even with TOAST deferral, the heap page must be read to reach the metrics columns. If text is inline, each heap page contains fewer rows (more I/O). If text is TOASTed, each heap page contains compact rows, but the TOAST pointers still occupy inline bytes.

**Per-student history query pattern:**
`SELECT * FROM warehouse.student_snapshots WHERE student_id = X ORDER BY snapshot_month` is a low-cardinality indexed access (at most 36 rows). In either design this is fast. The two-table design adds one join to `snapshot_ai_narratives` for report rendering — this join is a single FK lookup per row, negligible overhead.

**Cohort aggregation pattern:**
`SELECT segment_classification, COUNT(*), AVG(payment_risk_score) FROM warehouse.student_snapshots WHERE snapshot_month = '2026-05-01' GROUP BY segment_classification` — pure metrics query. Two-table design is strictly faster here because the scan is over compact rows.

**Verdict:** The two-table design delivers measurably better performance for all analytical patterns that do not require AI text. The one pattern that is slightly more expensive in the two-table design (loading a full snapshot including AI narrative for a single report) requires one additional join, which is sub-millisecond on an indexed FK column.

### 1.3 Row Bloat Risk Assessment

**Single-table risk — inline text below TOAST threshold:**

If AI narratives are short (100–300 words, ~600–1,800 bytes per field), they fall below the TOAST threshold and are stored inline. Five fields × 1,500 bytes = 7,500 bytes of inline text. Added to ~500 bytes of metrics columns: the row now exceeds 8KB. PostgreSQL will store the row across multiple pages using a TOAST fallback, but this creates:

- Increased I/O for any full scan
- Index inefficiency: row pointers span multiple pages
- Dead tuple overhead after vacuum: wider rows leave more dead space

This is the worst-case scenario for the single-table design: text just below TOAST threshold, fully inline, severely bloating the metrics table.

**Two-table risk:**
No row bloat risk exists in the metrics table. `snapshot_ai_narratives` may have wide rows due to inline text, but this table is only accessed when AI text is explicitly needed. Bloat in the companion table does not affect metrics scan performance.

**TOAST page overflow concern:**
TOAST stores values in 2KB chunks in a separate TOAST relation. For a snapshot with five AI narrative fields totaling 30KB, TOAST storage is approximately 15 chunks. At 2,000 students × 36 months, the TOAST relation for `snapshot_ai_narratives` holds approximately 72,000 × 15 = 1,080,000 chunks. At 2KB each, this is approximately 2GB of TOAST storage — well within normal PostgreSQL operational range.

The concern is not TOAST table size but TOAST access patterns during report generation. Loading all five narrative fields for 100–200 students to generate a cohort report triggers sequential TOAST reads for each student. This is an expected and acceptable access pattern — report generation is a batch operation, not a real-time query.

### 1.4 Append-Only Growth Behavior

Both the metrics table and AI narrative companion table are append-only after FINALIZED. PostgreSQL's MVCC model handles append-only tables efficiently: no dead tuple accumulation (no UPDATEs generate dead tuples), vacuum has minimal work to do, and the fillfactor can be set to 100% (default) since no future updates will occur on finalized rows.

The only vacuum concern is in the `public` schema draft queue table, where rows transition from DRAFT → VALIDATING → FINALIZED and the finalized rows are subsequently "completed." This is a normal mutable table — standard vacuum behavior applies.

Growth rate for warehouse tables:
- `warehouse.student_snapshots`: `students × months` rows, each ~400 bytes = ~29MB at 2,000 students × 36 months
- `warehouse.snapshot_ai_narratives`: same cardinality, each ~1–30KB depending on AI text length = ~0.1–2GB at full scale

Both are well within PostgreSQL operational bounds without any special management at the target scale.

### 1.5 Historical Reporting Efficiency

A cohort monthly report reads:
1. All `warehouse.student_snapshots` rows for `(cohort_id, snapshot_month)` — metrics scan
2. All corresponding `warehouse.snapshot_ai_narratives` rows for the same students — one FK join

In the two-table design, step 1 is a compact metrics scan. Step 2 is an indexed FK lookup. Both are read-once operations for a single report generation job. The join overhead is negligible compared to report rendering time (LLM calls, PDF assembly).

In the single-table design, step 1 already loads all AI text (either inline or via TOAST deferral). If the query selects all columns, TOAST values are fetched for every row. If the query is selective, TOAST is still deferred.

The two-table design is never slower for this pattern and is structurally cleaner.

### 1.6 Regeneration-Read Performance

Historical regeneration reads from `warehouse.student_snapshots` and `warehouse.snapshot_ai_narratives` for a specific `(cohort_id, report_month)`. This is a small, indexed, point-in-time read — both tables are accessed together explicitly. Performance is determined by index efficiency, not table width.

The two-table design adds one join to the regeneration read path. Given the cardinality (100–200 students per cohort), this join executes in microseconds. No performance concern.

### 1.7 FAD-1 Compliance Under Both Designs

**Why `snapshot_ai_narratives` must NOT FK to `ai_insights`:**

The FK relationship `snapshot_ai_narratives.ai_source_insight_id_hint → ai_insights.id` in the current spec is explicitly defined as NON-FK advisory (spec/09 Section 3.4). This is architecturally correct.

If a real FK existed:
- Deletion of an `ai_insights` row (via compliance pathway or data cleanup) would either violate the FK (preventing deletion) or cascade-delete the frozen snapshot narrative (violating FAD-1)
- Neither outcome is acceptable: blocking compliance deletion violates GDPR/FERPA compliance, and cascade-deleting the frozen copy violates snapshot immutability
- A real FK would also imply reference semantics — the snapshot narrative would be "owned by" the insight record, which contradicts the physical copy intent

The advisory `ai_source_insight_id_hint` column (INTEGER, no FK constraint) preserves audit traceability without creating any dependency. If the source `ai_insights` record is later deleted, the hint becomes stale — this is acceptable because the frozen text is the authoritative copy. The hint answers "where did this text originate?" for audit purposes only, not for runtime access.

**Why frozen-copy isolation matters operationally:**

Post-finalization operations that would break reference semantics but are fully compatible with physical copy semantics:
1. AI force-refresh (new `ai_insights` version created for a student)
2. Model upgrade (new `model_used` value in future `ai_insights` records)
3. Prompt version change (new `prompt_version` in future `ai_insights` records)
4. AI insight deletion via compliance pathway (removing an insight record for GDPR compliance)
5. AI insight correction (a reviewed insight was factually wrong; a replacement is generated)

Under physical copy semantics, all five operations are transparent to the snapshot. The frozen text was what it was at finalization time. Historical regeneration produces the same output regardless of what happened to `ai_insights` afterward.

Under reference semantics, operations 1, 3, and 5 would silently change historical report output on the next regeneration — a direct violation of DATA-INVARIANT-2 and DATA-INVARIANT-3.

### 1.8 Single-Table vs Two-Table: Summary Comparison

| Criterion | Single-Table | Two-Table (Recommended) |
|---|---|---|
| Analytical query I/O (no AI text needed) | Higher if text is inline; same if text is TOASTed | Lower — no AI text columns in scan path |
| Report generation read (all columns needed) | One table scan | One table scan + one FK join (~negligible overhead) |
| Buffer pool efficiency | Lower if text is inline | Higher — compact rows |
| FAD-1 compliance | Yes (with advisory hint) | Yes (with advisory hint) |
| Embedding/RAG future path | Possible but requires full row load | Clean — `snapshot_ai_narratives` is the dedicated text source |
| Schema clarity | Lower — AI text mixed with metrics | Higher — clear separation of concern |
| Partitioning readiness | Harder with wide rows | Clean partition on compact snapshot_month |
| Benchmark dependency | High — single-table is only safe if text stays small | Low — two-table works at any text size |
| **Overall recommendation** | Viable only if P95 per-field < 512 bytes | **Safe default regardless of AI text length** |

---

## 2. AI PAYLOAD BENCHMARKING PLAN

---

### 2.1 Benchmarking Purpose

Before writing `0002_warehouse_schema.py`, measure representative AI narrative lengths from existing `ai_insights.content` data. This validates the two-table design choice and determines whether any column types require adjustment.

The benchmarking step is listed in spec/09 Section 12.3 Step 1 and in spec/01 Section 14.3 risk register as a mandatory pre-migration action.

### 2.2 Metrics to Measure

**Per insight type:**

| Metric | Why it matters |
|---|---|
| `MIN(length(content))` | Identifies vacuous outputs (empty / near-empty) |
| `MAX(length(content))` | Worst-case row size; determines TOAST behavior |
| `AVG(length(content))` | Expected storage per row |
| `P50` — median payload | Typical storage; drives storage estimate |
| `P95` — 95th percentile | Design threshold — 95% of rows must fit well |
| `P99` — 99th percentile | Outlier behavior; determines TOAST headroom |
| `COUNT(*)` | Sample size validity |

**Per-student total (all insight types combined):**

| Metric | Why it matters |
|---|---|
| `MAX(total_content_bytes)` | Worst-case single student AI narrative payload |
| `AVG(total_content_bytes)` | Expected storage per student snapshot |
| `P95(total_content_bytes)` | Design threshold for single-table viability |

**Structural characteristics:**

| Check | Purpose |
|---|---|
| Distribution of insight types present | Are all 5 types populated or only some? |
| Null / missing insight type coverage | How many students lack any AI insight? |
| Temporal trend (if multiple content versions per student exist) | Is AI text growing over time? |

### 2.3 Benchmark Queries

**Query 1 — Per-insight-type distribution:**
```
SELECT
  insight_type,
  COUNT(*)                                                            AS row_count,
  MIN(length(content))                                               AS min_bytes,
  MAX(length(content))                                               AS max_bytes,
  ROUND(AVG(length(content)))                                        AS avg_bytes,
  PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY length(content))     AS p50_bytes,
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY length(content))     AS p95_bytes,
  PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY length(content))     AS p99_bytes
FROM ai_insights
GROUP BY insight_type
ORDER BY avg_bytes DESC;
```

**Query 2 — Per-student total payload:**
```
SELECT
  MAX(total_content_bytes)                                           AS max_student_total,
  ROUND(AVG(total_content_bytes))                                    AS avg_student_total,
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_content_bytes) AS p95_student_total,
  PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY total_content_bytes) AS p99_student_total
FROM (
  SELECT user_id, SUM(length(content)) AS total_content_bytes
  FROM ai_insights
  GROUP BY user_id
) per_student;
```

**Query 3 — Insight type coverage per student:**
```
SELECT
  COUNT(DISTINCT user_id)                          AS total_students,
  COUNT(DISTINCT CASE WHEN insight_type = 'risk' THEN user_id END)
                                                   AS students_with_risk_narrative,
  COUNT(DISTINCT CASE WHEN insight_type = 'opportunity' THEN user_id END)
                                                   AS students_with_opportunity_narrative
FROM ai_insights;
```

(Adjust insight_type values to match actual production values.)

**Query 4 — Temporal growth check (if timestamp tracking is available):**
```
SELECT
  DATE_TRUNC('week', created_at)          AS week,
  insight_type,
  ROUND(AVG(length(content)))             AS avg_bytes_that_week
FROM ai_insights
GROUP BY week, insight_type
ORDER BY week, insight_type;
```

### 2.4 Decision Boundaries

**Threshold set A — Per-insight-type P95:**

| P95 per insight type | Implication |
|---|---|
| P95 < 512 bytes | All 5 fields inline and compact; single-table viable |
| 512–2,048 bytes | Text is inline but approaches TOAST threshold; two-table recommended |
| 2,048–8,192 bytes | Text will TOAST; two-table is the clean design |
| > 8,192 bytes | Text heavily TOASTed; two-table is mandatory |

**Threshold set B — Per-student total P95:**

| Per-student total P95 | Implication |
|---|---|
| < 8 KB | Single-table is viable; total narrative payload per row fits in ~1 page |
| 8–32 KB | Single-table creates row bloat risk; two-table is preferred |
| > 32 KB | Two-table is the correct physical choice regardless of other factors |

**Decision rule (both thresholds must be met for single-table to be considered):**

```
Single-table is viable IFF:
  (P95 per insight type < 512 bytes for ALL types)
  AND (P95 total per-student < 8 KB)

Two-table is correct for all other cases.
```

**The two-table approach (spec/09 Section 3.2) is the recommended default regardless of benchmarking outcome.** Benchmarking can only confirm that single-table is also viable; it cannot make two-table wrong.

### 2.5 Growth Projection Assumptions

When projecting forward from current benchmark data:

| Factor | Conservative assumption | Aggressive assumption |
|---|---|---|
| AI model output length growth | 10% per year | 40% per year |
| Prompt evolution (more detailed analysis) | +500 bytes per insight type per major version | +2,000 bytes per type |
| New insight types added | 0–1 per year | 2–3 per year |

At conservative growth and current scale, a system that benchmarks at 6KB per student today will reach ~9KB in 3 years (36-month retention window). This crosses the 8KB single-table viability threshold during the retention window, making two-table the only safe forward-looking choice.

At aggressive growth, a system benchmarking at 3KB today reaches 12KB in 3 years — already requiring two-table.

### 2.6 When Row Width Becomes Operationally Dangerous

**For single-table design:**

The danger zone begins when the main snapshot row (metrics + inline AI text) approaches or exceeds 8KB. PostgreSQL handles rows exceeding 8KB via TOAST of the largest columns, but this is a reactive process (the DB TOASTs what it needs to). Operationally dangerous because:

- Rows near 8KB saturate shared_buffers faster (fewer rows per buffer page)
- Autovacuum work increases proportionally with row width
- Covering indexes on wide tables fail to deliver their performance benefit (index pages become wider)
- Future schema additions (new metric columns) push rows past the tipping point silently

**For two-table design:**

No analogous danger zone exists for the metrics table. The companion table (`snapshot_ai_narratives`) can grow without impacting metrics query performance. The companion table's own page efficiency is irrelevant for analytics.

### 2.7 When Analytical Scans Become Inefficient

**Single-table inflection point:**

Analytical scans become observably inefficient when sequential scan I/O exceeds the indexed scan I/O for the same query. This occurs when:

- Rows per page < 2 (row width > 4KB inline) — each page serves only 1-2 rows
- Buffer pool hitrate drops below ~90% for the metrics table — too few rows fit in shared_buffers
- The analytics index requires heap fetches for non-covering columns that are wide (text fields)

For SSIP at 2,000 students × 36 months = 72,000 rows: if average row width exceeds 4KB (inline text scenario), a full-cohort scan for one month (~2,000 rows) requires reading ~4,000 pages instead of ~400. At 8KB per page, that is ~32MB vs ~3MB of I/O per cohort scan — a 10× difference observable in production.

**Two-table inflection point:**

The two-table design has no analytical scan inefficiency concern for the metrics table. The companion table has its own scan characteristics, but it is only scanned during report generation — not during analytical aggregations.

---

## 3. SNAPSHOT TABLE PHYSICALIZATION REVIEW

---

### 3.1 Fingerprint Scalar Columns — Validation

The spec/09 Section 3.3 defines three scalar TEXT fingerprint columns plus one JSONB:

- `fingerprint_schema_version` — TEXT
- `fingerprint_config_registry_version` — TEXT
- `fingerprint_report_template_version` — TEXT
- `fingerprint_ai_versions_json` — JSONB

**Validation — are three scalar columns the right choice?**

Three scalar columns are correct for the queryable fingerprint components. The primary use cases for fingerprint queries are:

1. "How many snapshots used config version V2?" → `WHERE fingerprint_config_registry_version = 'V2'`
2. "Which snapshots were finalized under schema revision abc123?" → `WHERE fingerprint_schema_version = 'abc123'`
3. "Which snapshots use an outdated template?" → `WHERE fingerprint_report_template_version != 'current_template'`

These are equality filters on stable identifiers. Scalar TEXT columns support direct equality indexing; JSONB path queries (`WHERE fingerprint_json->>'config_registry_version' = 'V2'`) are slower and require GIN or expression indexes.

**Is additional scalarization warranted?**

The per-type AI version map (`fingerprint_ai_versions_json`) is correctly kept as JSONB because:
- The number of insight types is variable (currently 2–5; may expand)
- Queries on AI versions are rare (audit queries, not operational queries)
- Each entry has two sub-fields (`prompt_version`, `model_version`) — a structured nested value that JSONB handles naturally
- Scalarizing 5 types × 2 fields = 10 additional columns would bloat the snapshot row with rarely-queried data

The JSONB column is the correct choice for the AI version map.

**Recommendation:** The mixed fingerprint column strategy in spec/09 is validated. No changes needed.

### 3.2 JSONB Usage Across Snapshot Table

Columns using JSONB in `warehouse.student_snapshots`:

| Column | JSONB justification |
|---|---|
| `channel_breakdown_json` | Small, structured object `{CALL: N, SMS: N, EMAIL: N}`; schema may expand channels |
| `fingerprint_ai_versions_json` | Per-type nested map; variable cardinality |

**Concern — JSONB in a warehouse schema:**

JSONB values are stored inline if small (< 2KB) and TOASTed if larger. For `channel_breakdown_json` (likely < 100 bytes) and `fingerprint_ai_versions_json` (likely < 500 bytes), both are inline. This is acceptable — they add minimal overhead and enable schema flexibility.

**GIN index consideration:** If future audit queries filter on `fingerprint_ai_versions_json` contents (e.g., "all snapshots using model version X"), a GIN index on that column can be added in a future migration without altering the table structure. This is a non-blocking future evolution.

### 3.3 Lineage References — Validation

The `parent_snapshot_id` self-referential FK creates a linked list within `warehouse.student_snapshots`. This is physically correct because:

- The linked list never exceeds a shallow depth at SSIP scale (snapshots are not regenerated frequently)
- The FK is within the same table and schema (no cross-schema dependency)
- Lineage traversal queries are rare (audit-only) and can use recursive CTEs without performance concern at the expected depth (typically 1–3 levels)

**Concern — what happens to the linked list under compliance deletion?**

When a student's snapshot rows are COMPLIANCE_DELETED:
- The rows are not physically deleted; their `status` is set to `COMPLIANCE_DELETED`
- The `parent_snapshot_id` FK still points to a valid row (it's just marked COMPLIANCE_DELETED)
- The lineage chain remains intact and traversable
- Compliance audit records in `compliance_audit.deletion_log` document which rows were COMPLIANCE_DELETED

This behavior is correct and does not require any special handling in the schema design.

### 3.4 Regeneration Lineage — Validation

Snapshot regeneration creates a new row with `lineage_version = prior + 1` and `parent_snapshot_id = prior row ID`. The original FINALIZED row is never modified.

**Concern — POTENTIALLY_DIVERGENT flag semantics in snapshot context:**

The spec/09 describes `POTENTIALLY_DIVERGENT` as "true when regeneration source fingerprint differs from original." For snapshots, this means: the data available at regeneration time differs from the data at original finalization time. Specifically:

- SQL Server mirror state has changed since original snapshot
- Derived metrics would be computed differently with current live data

**Important clarification:** Snapshot regeneration does NOT re-read live SQL Server data. It is a re-processing of the already-finalized snapshot row (e.g., if derived metrics computation logic is updated). The `POTENTIALLY_DIVERGENT` flag on snapshots applies to the case where the configuration version or schema version changed between original finalization and regeneration — the same metrics data is present, but it would be classified differently under current rules.

This distinction must be clearly documented in the implementation: snapshot regeneration reads from the original snapshot's raw SQL Server metric columns (which are physically stored in the row) and recomputes derived metrics. It does NOT re-sync from SQL Server. This preserves the snapshot's role as a point-in-time record of what SQL Server contained at `snapshot_month` cutoff.

### 3.5 Append-Only Assumption Validation

Both `warehouse.student_snapshots` and `warehouse.snapshot_ai_narratives` are INSERT-only via the finalization service account and SELECT-only via the standard service account. The only write path that touches existing rows in these tables is compliance deletion, which sets `status = 'COMPLIANCE_DELETED'` — and this requires the finalization account (since the compliance pathway needs a way to mark rows).

**Important gap identified:** The current spec defines:
- Standard service account: SELECT only on `warehouse`
- Finalization service account: INSERT only on `warehouse`
- Compliance pathway service account: INSERT only on `compliance_audit`

But compliance deletion must UPDATE `warehouse.student_snapshots.status = 'COMPLIANCE_DELETED'`. The finalization service account has INSERT-only, not UPDATE. Neither the standard account nor the compliance pathway account can perform this UPDATE.

**Resolution required before authoring 0002:** A dedicated update privilege for the compliance pathway is needed for status-column-only UPDATE on `warehouse.student_snapshots`. Options:

| Option | Description |
|---|---|
| A | Compliance pathway account is granted `UPDATE (status)` on `warehouse.student_snapshots` only (column-level privilege) |
| B | Finalization service account is extended with restricted UPDATE privilege (same effect, different account) |
| C | A dedicated compliance_execution service account is introduced for this purpose |

**Recommendation:** Option A. The compliance pathway service account is already the authorized actor for compliance operations. Extending it with column-level UPDATE on the `status` column of `warehouse.student_snapshots` is the minimal, targeted permission. The GRANT statement is: `GRANT UPDATE (status) ON warehouse.student_snapshots TO compliance_pathway_user`.

This must be included in the 0002 migration GRANT block.

### 3.6 Partitioning Readiness Validation

The `warehouse.student_snapshots` table is designed to be partition-ready. Validation:

**Partition key candidate:** `snapshot_month` (DATE, first day of month)
- All major access patterns include `snapshot_month` in the WHERE clause
- Range partitioning by year (12 partitions per year) or quarter (4 per year) is natural
- The unique constraint `(student_id, snapshot_month) WHERE status = 'FINALIZED'` must become a partition-local unique constraint when partitioning is introduced — this is standard PostgreSQL behavior for declarative partitioning

**Constraints on partition-ready design:**
- No global unique indexes allowed on partitioned tables in PostgreSQL (only partition-local)
- The planned partial unique index `(student_id, snapshot_month) WHERE status = 'FINALIZED'` will need to be `(student_id) WHERE status = 'FINALIZED'` within each partition (the partition key is `snapshot_month`, so all rows in a partition share it implicitly)
- The `parent_snapshot_id` self-referential FK within the table requires that the parent and child rows be in the same partition — which they will be, since lineage members share the same `snapshot_month`

**Partition-ready design confirmation:** No column or constraint in the current spec/09 design prevents future declarative partitioning on `snapshot_month`. The design is partition-ready.

### 3.7 Storage Density Expectations

At SSIP target scale:

| Table | Rows at 2K students × 36 months | Avg row width | Total table size (est.) |
|---|---|---|---|
| `warehouse.student_snapshots` | 72,000 | ~400 bytes | ~30 MB |
| `warehouse.snapshot_ai_narratives` | 72,000 | ~2–20 KB | ~150 MB – 1.5 GB |
| `warehouse.monthly_reports` | ~2,160 (60 cohorts × 36 months) | ~5–500 KB (JSONB report content) | ~10 MB – 1 GB |
| `warehouse.report_audit_log` | ~10,800 (5 events per report) | ~500 bytes | ~5 MB |

All tables are well within PostgreSQL management thresholds at this scale. No special infrastructure needed.

---

## 4. EVENT STORAGE VALIDATION

---

### 4.1 Hybrid Event Architecture — Structural Validation

The hybrid approach (spec/09 Section 5.1) places:
- Five operational event types → `public.student_timeline_events`
- Report lifecycle events → `warehouse.report_audit_log`
- Compliance lifecycle events → `compliance_audit.deletion_log`

**Validation of the three-location split:**

The split is architecturally correct because the three locations have different mutability, access, and survivability requirements:

| Location | Mutability | Access | Survivability requirement |
|---|---|---|---|
| `public.student_timeline_events` | Append-only | Standard service account | Operational retention window |
| `warehouse.report_audit_log` | Append-only | Finalization service (INSERT), Standard (SELECT) | Indefinite — tied to report lifecycle |
| `compliance_audit.deletion_log` | Append-only always | Compliance pathway (INSERT), Standard (SELECT) | Permanent — no retention policy |

A fully unified table cannot satisfy all three survivability requirements simultaneously (a row in `public` can be archived; a row in `compliance_audit` is permanent). The hybrid approach resolves this without duplication.

### 4.2 Event Volume Scalability

`public.student_timeline_events` is the highest-volume append-only table in the system. Estimating event volume:

| Event type | Estimated events/student/month | At 2,000 students × 36 months |
|---|---|---|
| CommunicationEvent | 10–30 | 720,000 – 2,160,000 |
| AccessHistoryEvent | 5–15 (SQL Server mirror) | 360,000 – 1,080,000 |
| AILifecycleEvent | 5–10 (per insight generation) | 360,000 – 720,000 |
| SnapshotLifecycleEvent | 3–5 (draft, validating, finalized) | 216,000 – 360,000 |
| ConfigLifecycleEvent | < 1/month on average | < 36,000 total |

**Total estimated: 1.7 – 4.4 million rows** at full scale and full retention window. This is below the practical partitioning threshold for PostgreSQL (~10 million rows for unpartitioned tables with good indexes). The table requires no partitioning at initial deployment but should be designed partition-ready (Section 8.3 of spec/09 confirms this).

### 4.3 Operational Timeline Query Efficiency

The primary access pattern for `student_timeline_events` is per-student ordered timeline:

```
SELECT * FROM public.student_timeline_events
WHERE student_id = X
ORDER BY attribution_timestamp DESC
LIMIT 50
```

This pattern is served by the index on `(student_id, attribution_timestamp DESC)` defined in spec/09 Section 8.2. At the expected cardinality (1,000–3,000 events per student over 36 months), this index scan returns the top 50 events in microseconds.

The secondary pattern (cohort-level timeline for reporting) is served by the same index with a range predicate on `attribution_timestamp`.

**No efficiency concerns at current or projected scale.**

### 4.4 SQL Server Mirrored-Event Differentiation — Validation

FAD-5 requires SQL Server-mirrored events to be distinguishable from platform-originated events. The three-column strategy:

- `origin_source = 'mirrored_sql_server'`
- `origin_authority = 'sql_server_authoritative'`
- `is_authoritative = true`

**Validation:** These three columns together provide unambiguous differentiation. Index on `is_authoritative` enables filtered queries for "only authoritative events." The redundancy (all three columns together identify SQL Server events) provides fault tolerance in case one column is unexpectedly NULL.

**Conflict handling validation:** The specified behavior (both rows retained, SQL Server row governs, conflict logged in `detail_json`) is correct for append-only semantics. No deletion or overwrite occurs. The `detail_json` conflict flag provides the audit trail without requiring a separate conflict log table.

### 4.5 Is Unified Timeline Appropriate?

The unified `public.student_timeline_events` table uses an `event_type` discriminator + `detail_json` JSONB pattern. This is appropriate because:

1. All five operational event types share identical attribution fields (see spec/09 Section 5.2)
2. The unified timeline view renders all event types together, sorted by `attribution_timestamp`
3. A UNION across five tables would require coordinated index design and result merging at query time
4. Adding a new event subtype requires no schema change — only a new `event_subtype` value

**Structural risk of the unified approach:** If event types diverge significantly in their `detail_json` schema, validation becomes harder. Mitigation: define a per-type JSONB schema document (as part of spec/07 API contracts or as an embedded JSON Schema in application validation logic). The physical table schema is stable; the `detail_json` schemas are the contract to document.

### 4.6 Event Partitioning Assessment

At current deployment scale (< 500 students), no partitioning is needed. The table is designed for future declarative partitioning on `attribution_timestamp` (spec/09 Section 9.5).

**Partition-ready design confirmation:** The `attribution_timestamp` column is present on every row and is a natural range partition key. The planned index `(student_id, attribution_timestamp DESC)` works identically on a partitioned table (the leading column `student_id` is not the partition key, so cross-partition scans occur, but at the expected query cardinality of 1 student per query, only 1–2 partitions are accessed).

---

## 5. CONFIG VERSION PHYSICAL GUARANTEE REVIEW

---

### 5.1 Partial Unique Index — Operational Correctness

The partial unique index `CREATE UNIQUE INDEX ON config_version_registry (status) WHERE status = 'ACTIVE'` enforces the exactly-one-ACTIVE invariant at the database layer.

**Why this index is correct:**

PostgreSQL partial unique indexes enforce uniqueness only among rows satisfying the WHERE clause. Since `status = 'ACTIVE'` is the filter, the index contains at most one entry — the single ACTIVE row. Attempting to INSERT or UPDATE a second row to `status = 'ACTIVE'` while one already exists raises a unique constraint violation, regardless of which transaction attempts it.

**Implicit guarantee:** Because the index entry is on the constant expression `(status)` WHERE `status = 'ACTIVE'`, the index acts as a sentinel: it either contains zero entries (no ACTIVE version — a transient state during the atomic swap) or exactly one entry (the ACTIVE version). This is structurally simpler and more reliable than application-level "check before insert" patterns.

### 5.2 Concurrency Behavior and Race Safety

**Atomic swap sequence under concurrency:**

Consider two transactions competing to activate different config versions simultaneously:

```
Transaction A:
  BEGIN
  UPDATE config_version_registry SET status='SUPERSEDED', superseded_at=now() WHERE status='ACTIVE'  -- acquires row lock on ACTIVE row
  UPDATE config_version_registry SET status='ACTIVE', activated_at=now() WHERE id=new_version_A_id AND status='APPROVED'

Transaction B (overlapping):
  BEGIN
  UPDATE config_version_registry SET status='SUPERSEDED', superseded_at=now() WHERE status='ACTIVE'  -- BLOCKS waiting for Transaction A's row lock
```

When Transaction A commits:
- The old ACTIVE row is now SUPERSEDED (Transaction A's change visible)
- A new row (version A) is now ACTIVE
- The partial unique index now has one entry for version A

Transaction B unblocks:
- The UPDATE to supersede the old ACTIVE row finds no rows matching `status='ACTIVE'` for the old row (it's already SUPERSEDED) — this is a no-op update
- Transaction B's UPDATE to set version B to ACTIVE: the partial unique index now has an entry for version A, so this UPDATE raises a unique constraint violation
- Transaction B ROLLBACKS with a constraint error

**Outcome:** Transaction A succeeds; Transaction B fails cleanly with a constraint violation. No double-ACTIVE state is possible. This is correct concurrent behavior.

**Required application handling:** The config activation service must handle the constraint violation from Transaction B as a retryable conflict (409 Conflict), not as an unexpected error. This is an application-layer concern but must be documented as a migration-adjacent constraint.

### 5.3 Activation Race Safety — Assessment

The combination of row-level locking (from the UPDATE on the current ACTIVE row) and the partial unique index (preventing double-ACTIVE) provides complete race safety for the config activation atomic swap.

**No advisory locking needed.** PostgreSQL row-level locking provides sufficient isolation for this pattern. Advisory locking would add unnecessary complexity without additional safety guarantees given the partial unique index.

### 5.4 Application-Level Enforcement — Necessity

Application-level enforcement (the atomic swap transaction) is still necessary alongside the database-level partial unique index because:

1. The partial unique index prevents double-ACTIVE states but does not enforce the sequencing (old → SUPERSEDED before new → ACTIVE)
2. Without the atomic swap, a correctly-gated application could set a new version to ACTIVE before superseding the old one — resulting in a constraint violation from the partial unique index, which is correct, but the old version would be in a "failed to be superseded" state
3. The atomic swap ensures that the SUPERSEDED timestamp on the old version and the ACTIVE timestamp on the new version are correlated (both occur in the same transaction, with the same `now()` call)

**Recommendation:** Both layers of enforcement are required and must be implemented. The DB-level index is the safety net; the application-level atomic swap is the correct mechanism.

### 5.5 Future Migration Implications

If `config_version_registry` ever needs to support multiple "domains" (e.g., separate config versions for different cohort types), the partial unique index strategy extends naturally:

- Partial unique index becomes `UNIQUE (domain) WHERE status = 'ACTIVE'` (one ACTIVE per domain)
- The atomic swap is parameterized by domain

No schema change to existing columns is required for this evolution. This is a non-breaking extension.

---

## 6. COMPLIANCE STORAGE REVIEW

---

### 6.1 Schema Isolation — Validation

The `compliance_audit` schema has no FK dependencies on `public` or `warehouse` schemas. All student references use plain INTEGER `student_id` columns. This ensures:

- `public` schema deletions do not cascade to `compliance_audit`
- `warehouse` schema archival does not cascade to `compliance_audit`
- `compliance_audit` can be independently exported, replicated, or migrated

**No FK coupling is validated as correct.** The audit trail must survive the deletion it audits.

### 6.2 Deletion-Log Survivability — Validation

The `deletion_log` survivability matrix from spec/09 Section 7.4 is validated:

| Scenario | Mechanism | Assessment |
|---|---|---|
| `student_trigger_data` rows deleted | `student_id` is INTEGER, no FK | ✓ Correct |
| `warehouse.student_snapshots` COMPLIANCE_DELETED | No FK from deletion_log to warehouse | ✓ Correct |
| `ai_insights` rows deleted | No FK from deletion_log to ai_insights | ✓ Correct |
| Entire `public` schema dropped | `compliance_audit` schema is physically separate | ✓ Correct |
| DBA drops `compliance_audit` accidentally | Only DBA emergency access; documented as prohibited | ✓ Governance control |

### 6.3 Critical Defect Identified — scope_manifests.is_current

**Problem:**

`compliance_audit.scope_manifests` includes an `is_current BOOLEAN` column (spec/09 Section 7.3). This column is designed to be `true` for the most recent manifest version and `false` for stale manifests.

However, the `compliance_audit` schema is INSERT-only for the compliance pathway account. Setting `is_current = false` on an existing scope manifest row requires an UPDATE operation. The compliance pathway account does not have UPDATE privilege. This creates an irreconcilable conflict:

- The compliance pathway account must write to `compliance_audit` only via INSERT (schema invariant)
- Marking an older manifest as `is_current = false` requires UPDATE (defect)

**Resolution:**

Remove `is_current` from `compliance_audit.scope_manifests`. Replace with a query pattern based on `manifest_version`:

```
SELECT * FROM compliance_audit.scope_manifests
WHERE workflow_id = $1
ORDER BY manifest_version DESC
LIMIT 1
```

This query returns the most recent manifest for a workflow without requiring any UPDATE operations. The append-only semantics of the compliance schema are preserved.

**The manifests table insert pattern on refresh:** When a manifest is refreshed before execution, a new row is INSERTed with `manifest_version = old_version + 1`. The old manifest row is retained (append-only). The "current" manifest is always the one with the highest `manifest_version` for that `workflow_id`.

**Corrected spec/09 Section 7.3 column list (remove `is_current`):**

Remove: `is_current BOOLEAN`

Add clarifying note: "Current manifest for a workflow is always `MAX(manifest_version)` for that `workflow_id`. No UPDATE operations are required."

This change must be reflected in `0002_warehouse_schema.py` when it is authored.

### 6.4 Governance Audit Persistence — Validation

The pre-action / post-action duality in `deletion_log` is validated as correct:

- `entry_type = 'PRE_ACTION'`: inserted before IN_EXECUTION begins; the existence of this row is the hard gate
- `entry_type = 'POST_ACTION'`: inserted after completion; failure to write is an incident
- `entry_type = 'PARTIAL_COMPLETION_CHECKPOINT'`: inserted per-table during IN_EXECUTION for recovery

The `sequence_number` within a `workflow_id` allows reconstruction of execution order. The `workflow_id` (UUID, shared across entries) allows all entries for a single compliance action to be queried together.

**No structural defects identified** beyond the `is_current` issue in `scope_manifests` (Section 6.3).

### 6.5 MVP/STANDARD Tier Sufficiency

The current `compliance_audit` schema design is sufficient for:

- **MVP tier:** Manual compliance requests; pre/post-action audit trail; basic GDPR/FERPA response workflow
- **STANDARD tier:** Scope manifest capture; per-table checkpoint logging; partial failure recovery

What would be needed for enterprise governance:
- Row-level security policies granting auditor access to individual student records without full schema access
- Structured export API (NDJSON or signed PDF) for regulatory submission
- Retention-proof backup to separate object storage (e.g., S3) for compliance records
- Audit log signing/hashing for tamper-evidence

None of these are needed at MVP or STANDARD tier. The schema design accommodates them as non-breaking future additions.

### 6.6 Compliance Pathway Account Permission Correction

As noted in Section 3.5 of this document, the compliance pathway must be able to:

1. INSERT into `compliance_audit.deletion_log` (already specified)
2. INSERT into `compliance_audit.scope_manifests` (already specified)
3. UPDATE `status` column only on `warehouse.student_snapshots` (gap identified in Section 3.5)

The 0002 migration GRANT block must include the column-level UPDATE grant on `warehouse.student_snapshots` for the compliance pathway service account.

---

## 7. MIGRATION 0002 READINESS ASSESSMENT

---

### 7.1 Formal Readiness Classification

For each area, the classification is:

- **READY:** All decisions resolved; migration authoring can begin immediately
- **READY WITH VALIDATION:** One bounded open item; two-table design is safe default; authoring can begin with noted pre-validation
- **NOT READY:** Conceptual ambiguity or required decision blocks authoring

| Area | Classification | Rationale |
|---|---|---|
| `warehouse.student_snapshots` (metrics table) | **READY WITH VALIDATION** | Two-table design is validated and correct; benchmark recommended before authoring but does not block; all column groups specified |
| `warehouse.snapshot_ai_narratives` (AI companion) | **READY** | Two-table design validated; FAD-1 compliance confirmed; all column groups specified; `is_current` issue does not affect this table |
| `warehouse.monthly_reports` | **READY** | All column groups specified; lineage model validated; POTENTIALLY_DIVERGENT semantics clear |
| `warehouse.report_audit_log` | **READY** | Append-only; all columns specified; no ambiguity |
| `compliance_audit.deletion_log` | **READY** | All columns specified; no FK coupling validated |
| `compliance_audit.scope_manifests` | **READY WITH MODIFICATION** | `is_current` column must be removed (Section 6.3); all other columns valid |
| Config version registry (`public.config_version_registry`) | **READY** — this is migration 0003, not 0002 | All 22 rule columns specified; V1 seed values defined |
| Event timeline (`public.student_timeline_events`) | **READY** — this is migration 0004, not 0002 | Column strategy validated; no ambiguity |
| Lineage model (snapshot + report linked lists) | **READY** | Linked list pattern validated in Section 3.3 |
| Permission grants | **READY WITH MODIFICATION** | Column-level UPDATE grant for compliance pathway on `warehouse.student_snapshots.status` must be added (Section 3.5, 6.6) |

### 7.2 Pre-Migration Benchmarking Assessment

Benchmarking (Section 2) is **recommended but does not block migration authoring** because:

1. The two-table design (spec/09 Section 3.2) is valid and correct regardless of AI text size
2. Benchmarking can only confirm that single-table is also viable — it cannot invalidate the two-table approach
3. If benchmarking shows text is extremely small (P95 < 512 bytes per field), an optimization trade-off discussion is warranted, but the two-table design remains operationally correct

**Decision:** Author 0002 using the two-table design. Run benchmarking concurrently. If benchmarking reveals extreme surprise (e.g., AI text is near-zero, indicating the system hasn't generated any substantive narratives yet), note this in the migration but do not change the schema — the two-table design is the forward-looking correct choice.

### 7.3 Physical Ambiguity Assessment

No unresolved physical ambiguity exists in the 0002 migration specification after addressing:
1. `is_current` removal from `compliance_audit.scope_manifests`
2. Column-level UPDATE grant for compliance pathway on `warehouse.student_snapshots.status`

All other aspects of the schema are fully specified with no competing design options remaining.

### 7.4 Storage Uncertainty Assessment

No storage uncertainty blocks migration authoring:
- JSONB column sizing is well-understood
- TOAST behavior is predictable
- Two-table split eliminates the primary storage uncertainty (AI text in metrics table)

### 7.5 Summary Readiness Table

| Migration | Status | Blocker |
|---|---|---|
| 0002 (warehouse + compliance_audit schemas) | **READY** with two modifications noted | Fix: remove `is_current`; add compliance UPDATE grant |
| 0003 (config_version_registry) | **READY** — no blockers | None |
| 0004 (snapshot_draft_queue + timeline_events) | **READY** pending 0002 deployment | Depends on 0002 |
| 0005 (ai_insights versioning columns) | **READY** pending 0002 deployment | Depends on 0002 |

---

## 8. MIGRATION SEQUENCING VALIDATION

---

### 8.1 compliance_audit Belongs in 0002 — Confirmed

FAD-4 (spec/01 Section 13): "compliance_audit schema must be created in the same Alembic migration as the warehouse schema (Step 1 of the dependency sequence)."

spec/08 Section 25 references `0004_compliance_schema.py` as a separate migration. This is an inconsistency in spec/08 — it predates FAD-4.

**Resolution (consistent with spec/09 Section 11.1):** Migration 0002 covers both `warehouse` and `compliance_audit` schemas per FAD-4. The "0004" reference in spec/08 Section 25 is retired for compliance schema purposes. Migration 0004 is repurposed as `0004_snapshot_lifecycle_public.py` (snapshot draft queue + timeline events).

### 8.2 Prior 0004 Inconsistency — Confirmed Resolved

spec/08 Section 8 (migration table) lists compliance schema as 0004. spec/01 FAD-4 mandates it in 0002. The resolution in spec/09 Section 11.1 is validated: 0002 includes both schemas. The spec/08 reference is a superseded pre-FAD plan.

**No action needed beyond noting this in migration comments.** The 0002 migration itself is the authoritative record.

### 8.3 Validated Sequencing

```
0001_baseline.py  (DEPLOYED — public schema, Phase 5 tables)
    │
    ├── 0002_warehouse_schema.py  (NOW — BEGIN)
    │       warehouse schema:
    │         warehouse.student_snapshots (two-table design, compact metrics)
    │         warehouse.snapshot_ai_narratives (AI text companion)
    │         warehouse.monthly_reports (lineage-versioned)
    │         warehouse.report_audit_log (append-only lifecycle log)
    │       compliance_audit schema (same migration per FAD-4):
    │         compliance_audit.deletion_log (PRE/POST/CHECKPOINT entries)
    │         compliance_audit.scope_manifests (is_current REMOVED)
    │       Permission grants:
    │         REVOKE public on warehouse, compliance_audit
    │         GRANT SELECT on warehouse TO app_service_user
    │         GRANT INSERT on warehouse tables TO finalization_service_user
    │         GRANT SELECT on compliance_audit TO app_service_user
    │         GRANT INSERT on compliance_audit tables TO compliance_pathway_user
    │         GRANT UPDATE (status) ON warehouse.student_snapshots TO compliance_pathway_user  ← NEW
    │       Partial unique indexes:
    │         warehouse.student_snapshots: (student_id, snapshot_month) WHERE status='FINALIZED'
    │         warehouse.monthly_reports: (cohort_id, report_month, lineage_version) WHERE status='REPORT_PUBLISHED'
    │         warehouse.monthly_reports: idempotency key UNIQUE
    │
    └── 0003_config_version_registry.py  (CONCURRENT with 0002 — independent)
            public.config_version_registry (all 22 rule columns)
            Partial unique index: UNIQUE (1) WHERE status='ACTIVE'
            V1 seed INSERT with all spec/01 Section 12 defaults at status='ACTIVE'

0004_snapshot_lifecycle_public.py  (AFTER 0002 DEPLOYED)
        public.snapshot_draft_queue (draft lifecycle tracking)
        public.student_timeline_events (unified event log, hybrid approach)
        Indexes: (student_id, attribution_timestamp DESC) on timeline events

0005_ai_insights_versioning.py  (AFTER 0002 DEPLOYED)
        ALTER TABLE public.ai_insights ADD COLUMN version_number INTEGER
        ALTER TABLE public.ai_insights ADD COLUMN prompt_version VARCHAR
        ALTER TABLE public.ai_insights ADD COLUMN model_version VARCHAR
        ALTER TABLE public.ai_insights ADD COLUMN ai_idempotency_key TEXT UNIQUE

0006_report_generation_support.py  (AFTER 0002+0003+0004 DEPLOYED)
        Any additional tables for report generation service
        Deferred until app/services/snapshot.py design is complete
```

### 8.4 Additional Migrations Implied

No additional migrations are currently implied beyond the validated sequence. All warehouse and compliance schema entities are covered by 0002. Config registry is in 0003. Operational event tables are in 0004. AI versioning is in 0005.

**Future non-blocking migrations that may be needed but do not block the current sequence:**

| Future migration | Trigger condition |
|---|---|
| `0007_snapshot_embeddings.py` | When RAG/vector search feature is designed |
| `0008_compliance_audit_extension.py` | When enterprise audit export (signed PDF, NDJSON) is implemented |
| `0009_warehouse_partitioning.py` | When `student_snapshots` or `student_timeline_events` exceeds partition threshold |

### 8.5 Dangerous Coupling Concerns

**Coupling concern 1 — 0002 GRANT statements must be in the migration file:**

If GRANT statements are executed as separate database operations (not in the Alembic migration), they become an undocumented manual step that may not run in CI/CD or in fresh environment setup. Every GRANT statement that establishes the three-account access model must be in the migration file. This is documented in spec/09 Section 11.4 and re-confirmed here.

**Coupling concern 2 — V1 seed in 0003 must be transactional:**

The V1 config version record must be inserted in the same transaction as the table creation. A partial migration that creates the table but fails before the seed INSERT leaves the system in a state that violates DATA-INVARIANT-4 (no ACTIVE config version). The seed INSERT is not optional.

**Coupling concern 3 — 0002 and 0003 are independent but the snapshot service depends on both:**

`app/services/snapshot.py` (migration step 3 in spec/09 Section 12.3) requires both 0002 (warehouse schema exists) and 0003 (ACTIVE config version exists for fingerprint computation). Deploying 0002 without 0003 and then trying to finalize a snapshot would fail at the fingerprint computation step (no ACTIVE config version). Deployment sequencing must ensure 0003 is applied before snapshot finalization goes live.

**Coupling concern 4 — compliance deletion before 0002 is deployed:**

If a compliance deletion request comes in before 0002 is deployed (no `compliance_audit` schema exists), the compliance pathway service has no audit table to write to. This is a pre-condition violation, not a migration coupling issue. The compliance pathway service must check for schema readiness at startup.

---

## 9. IMPLEMENTATION RISK REVIEW

---

### 9.1 Highest-Risk Implementation Areas

| Risk | Severity | Description |
|---|---|---|
| Missing UPDATE grant for compliance pathway | **HIGH** | Compliance deletion requires `UPDATE (status)` on `warehouse.student_snapshots`; omitting this grant makes compliance deletion impossible after deployment |
| GRANT statements not in migration file | **HIGH** | If GRANTs are omitted from 0002, new environments (dev, CI, new VPS) will have the wrong permission model; silent failure: inserts via standard account fail with permission error |
| V1 seed missing or incomplete in 0003 | **HIGH** | Any snapshot finalization before V1 seed is applied violates DATA-INVARIANT-4; fingerprint will record `UNKNOWN_V0` for config version |
| `is_current` not removed from scope_manifests | **HIGH** | Compliance pathway account cannot UPDATE existing rows; first manifest refresh will fail; compliance operations silently broken |
| Atomic swap not implemented as single transaction | **HIGH** | If config activation is not atomic, a crash between SUPERSEDED and ACTIVE updates leaves system with zero ACTIVE config versions |

### 9.2 Highest-Risk Storage Assumptions

| Assumption | Risk | Mitigation |
|---|---|---|
| AI narrative payloads stay within PostgreSQL TOAST limits | Medium | TOAST handles up to 1GB per value; no practical concern for text narratives; benchmark confirms current state |
| Per-student total AI payload does not exceed 1MB | Low-Medium | Two-table design handles any size; TOAST is the fallback; monitor actual sizes in first production run |
| `report_content_json` JSONB stays below 1MB per report | Medium | Initial reports for 100-student cohorts are expected to be 50-200KB; monitor at first generation; object storage migration is documented in spec/09 Section 4.1 |
| Lineage depth stays shallow (< 10 versions per snapshot) | Low | Snapshots are not frequently regenerated; depth > 5 would indicate a process issue, not a storage issue |
| Event timeline events have consistent `attribution_timestamp` values | Medium | Mirrored SQL Server events may have timestamps from any historical date; the index must handle sparse-but-wide timestamp ranges |

### 9.3 Likely Future Scaling Bottlenecks

| Bottleneck | Trigger condition | Mitigation path |
|---|---|---|
| `student_timeline_events` full-table scans | > 5M rows, OR queries without `student_id` | Add `attribution_timestamp` range partitioning; already designed partition-ready |
| `warehouse.student_snapshots` cohort scan latency | > 500K rows, OR > 10,000 students | Add `snapshot_month` range partitioning; already designed partition-ready |
| `warehouse.monthly_reports` JSONB content size | Single report payload > 500KB | Migrate `report_content_json` to object storage (S3); path documented in spec/09 Section 4.1 |
| `snapshot_ai_narratives` TOAST table size | > 5GB TOAST storage | TOAST is automatic; if SELECT performance degrades, add fillfactor hint or move to object storage |
| `compliance_audit.deletion_log` audit export time | > 10,000 audit entries per student | Low probability; add covering index on `(student_id, created_at)` if needed |

### 9.4 Likely Future Migration Pain Points

| Migration concern | Why it is painful | Prevention |
|---|---|---|
| Adding declarative partitioning to `warehouse.student_snapshots` | Requires table rebuild (partition tables cannot be created from existing unpartitioned tables without data migration) | Ensure the schema design now has no constructs that prevent future partitioning (validated in Section 3.6 — no blockers) |
| Adding report template version registry | `template_version` is currently a scalar TEXT; a registry would require a new table and optionally a FK | The TEXT column is stable; adding a registry is non-breaking (add table, add FK in future migration without altering snapshot column type) |
| Evolving `fingerprint_ai_versions_json` JSONB schema | As insight types are added, the JSONB map grows; no physical migration needed | Document the JSONB schema in spec; add a JSON Schema validator in the application; no migration needed for new keys |
| Evolving `compliance_audit` schema for enterprise requirements | Compliance audit tables are INSERT-only and have no FK deps; adding columns requires ALTER TABLE | Use nullable columns with NULL meaning "pre-feature"; existing rows need no backfill |
| Removing `is_current` from `scope_manifests` in 0002 | If 0002 is authored before this fix is applied, a subsequent migration is needed to DROP COLUMN | Fix it now in the 0002 spec; do not deploy with `is_current` |

### 9.5 Append-Only Growth Risk

The append-only design has one systematic risk: rows are never deleted from `warehouse` or `compliance_audit` schemas (except via compliance pathway). This means storage grows monotonically. At SSIP's current scale, this is not a concern. At 10,000+ students over 5 years, the warehouse tables grow to:

- `warehouse.student_snapshots`: 600,000 rows, ~240MB
- `warehouse.snapshot_ai_narratives`: 600,000 rows, ~1–12GB
- `student_timeline_events`: ~50M rows, ~20GB

The 50M rows for timeline events is the first scaling inflection point, reached at roughly 10,000 students × 60 months × 80 events/student/month. At that point, partitioning on `attribution_timestamp` becomes essential. The design accommodates this.

### 9.6 AI Payload Expansion Risk

AI narrative payloads tend to grow over time as prompt engineering matures and models improve at generating detailed analyses. A 200-word risk summary today may become a 1,000-word narrative in 3 years. The two-table design fully absorbs this growth:

- Narrative growth affects only `warehouse.snapshot_ai_narratives` (TOAST handles it)
- Analytical query performance on `warehouse.student_snapshots` is unaffected
- Report generation adds more TOAST reads per student, but this is proportional and expected

The one area where AI payload growth creates implementation risk: the `report_content_json` JSONB in `warehouse.monthly_reports`. If reports include full AI narrative text (copied from snapshot narratives), a 100-student cohort report could reach 100 students × 5 narratives × 5KB = 2.5MB. This approaches the practical JSONB usability threshold. **Recommendation:** Report generation should reference AI narrative content by `snapshot_id` (join at read time) rather than embedding full narrative text in `report_content_json`. This limits `report_content_json` to structured metrics and metadata only.

### 9.7 Regeneration Lineage Complexity Risk

Regeneration creates new rows in `warehouse.student_snapshots` (for snapshot regeneration) and `warehouse.monthly_reports` (for report regeneration). As lineage chains grow deeper:

- `parent_snapshot_id` linked list traversal requires recursive CTEs
- `parent_report_id` linked list traversal requires recursive CTEs

At expected regeneration frequency (< 5 times per snapshot/report over its lifetime), linked lists have depth ≤ 5. Recursive CTEs on depth-5 linked lists are trivially fast.

**Risk:** If regeneration is triggered frequently (e.g., every config activation triggers regeneration of recent reports), lineage chains could grow to depth 20+. Recursive CTEs on depth-20 chains are still fast, but the number of rows multiplies. At depth 20 × 72,000 snapshots = 1.44M rows in `warehouse.student_snapshots`. Still manageable but warrants monitoring.

**Mitigation:** Define a regeneration policy (maximum lineage depth per `(student_id, snapshot_month)`) as a configurable operational parameter. Add this to the config version registry or as a separate operational setting.

### 9.8 Fingerprint Evolution Risk

The fingerprint is designed to accommodate evolution (`UNKNOWN_V0` for untracked components). However, adding new fingerprint components in the future requires a migration to add new columns to `warehouse.student_snapshots`.

The current design (3 scalar TEXT columns + 1 JSONB) is extensible:
- New scalar fingerprint components: add new TEXT columns in a future migration (nullable; NULL for pre-addition rows means `UNKNOWN_V0` for historical snapshots)
- New per-type AI versioning entries: add new keys to the existing `fingerprint_ai_versions_json` JSONB (no schema change needed)

**Risk:** If the `fingerprint_ai_versions_json` structure needs to change materially (e.g., adding a third version component per insight type), existing JSONB data may become inconsistent with the new schema. **Mitigation:** Document the JSONB schema in a companion spec document and include a version field inside the JSONB (`"schema_version": "1"`). Schema version 2 adds new fields; applications can handle both.

---

## 10. OUTPUT — FINAL RECOMMENDATIONS

---

### 10.1 AI Storage Recommendation

**Recommendation: Two-table design confirmed.**

`warehouse.student_snapshots` (compact metrics) + `warehouse.snapshot_ai_narratives` (1:1 AI text companion)

This recommendation is:
- Independent of AI text size (the design performs well at any payload size)
- Validated against FAD-1 physical copy semantics
- Validated against TOAST behavior analysis
- Aligned with future RAG/embedding use cases
- The correct forward-looking design for 36+ months at 2,000+ students

**Single-table remains viable only if:** P95 per insight type < 512 bytes AND P95 per-student total < 8KB. Run benchmarking (Section 2) to assess. Even if benchmarking confirms small payloads, two-table is still the recommended design for the reasons stated in Section 1.8.

### 10.2 Benchmark Strategy

Run the four queries from Section 2.3 against the live PostgreSQL instance before or concurrently with authoring 0002. Document results in PROGRESS.md. If results fall within the "single-table viable" thresholds in Section 2.4, note this as a finding but proceed with two-table design.

Minimum required benchmark output before marking 0002 as complete:
- P95 per insight type (bytes)
- P95 per-student total (bytes)
- Row count (sample validity)
- Temporal trend if AI insights have been accumulating for > 2 months

### 10.3 Finalized Snapshot Storage Recommendation

| Decision | Recommendation | Rationale |
|---|---|---|
| Snapshot metrics table | `warehouse.student_snapshots` | Compact; directly queryable for analytics |
| Snapshot AI companion | `warehouse.snapshot_ai_narratives` (1:1 FK) | Separated AI text; FAD-1 compliant; no FK to ai_insights |
| Fingerprint column strategy | 3 scalar TEXT + 1 JSONB | Validated in Section 3.1 |
| `ai_source_insight_id_hint` | Advisory INTEGER, no FK constraint | Preserves audit hint without creating dependency |
| Compliance deletion | Status-only UPDATE via compliance pathway UPDATE grant | Section 3.5 and 6.6 |

### 10.4 Migration Readiness Matrix

| Migration | Readiness | Modification Required |
|---|---|---|
| 0002 — warehouse schema | **READY** | Remove `is_current` from scope_manifests; add compliance pathway UPDATE grant on warehouse.student_snapshots.status |
| 0003 — config registry | **READY** | None |
| 0004 — snapshot lifecycle public | **READY** (after 0002 deployed) | None |
| 0005 — ai_insights versioning | **READY** (after 0002 deployed) | None |
| 0006 — report generation support | **DEFERRED** | Design snapshot service first |

### 10.5 Implementation Risk Matrix

| Risk | Severity | Status | Action |
|---|---|---|---|
| Missing UPDATE grant (compliance pathway) | **HIGH** | Open | Add to 0002 GRANT block |
| `is_current` in scope_manifests | **HIGH** | Open | Remove from 0002 spec before authoring |
| GRANT statements not in migration | **HIGH** | Mitigated by documentation | Confirm placement during 0002 authoring |
| Atomic swap not transactional | **HIGH** | Deferred to service design | Document as service constraint in 0003 |
| V1 seed missing from 0003 | **HIGH** | Deferred to migration authoring | Include in 0003 |
| AI payload growth (report_content_json) | **Medium** | Design decision | Reference snapshot IDs in report JSON rather than embedding full narratives |
| Lineage chain depth unbounded | **Low** | Design gap | Add max regeneration depth as configurable parameter |
| Fingerprint JSONB schema evolution | **Low** | Future concern | Document JSONB schema; add schema_version key inside JSONB |

### 10.6 Migration Sequencing Recommendation

```
STEP 0 (NOW): Run benchmarking queries (Section 2.3) — no migration writing required
STEP 1 (NOW, parallel): Author 0002_warehouse_schema.py
                         Author 0003_config_version_registry.py (independent)
STEP 2: Deploy 0002 + 0003 to dev environment
         Verify permission model (Case 17 acceptance criteria from spec/08)
STEP 3: Author 0004_snapshot_lifecycle_public.py
         Author 0005_ai_insights_versioning.py
STEP 4: Deploy 0004 + 0005 to dev environment
STEP 5: Design app/services/config_registry.py
STEP 6: Design app/services/snapshot.py (requires U-4 and U-9 before production)
STEP 7: Design app/services/compliance.py (compliance pathway service)
```

### 10.7 Physical Scalability Assessment

| Concern | Current scale (2K students) | Future scale (10K students) | Action trigger |
|---|---|---|---|
| `warehouse.student_snapshots` | 72K rows, ~30MB | 360K rows, ~150MB | Partition at ~500K rows |
| `warehouse.snapshot_ai_narratives` | 72K rows, ~150MB–1.5GB | 360K rows, ~750MB–7.5GB | TOAST handles; monitor |
| `student_timeline_events` | ~1.7–4.4M rows | ~8–22M rows | Partition at ~10M rows |
| `warehouse.monthly_reports` | ~2.2K rows | ~11K rows | No concern; small table |
| `compliance_audit.deletion_log` | < 1K rows | < 5K rows | No scaling concern |
| `config_version_registry` | < 100 rows | < 100 rows | No scaling concern |

All tables are within safe bounds at current and projected medium-term scale. No immediate partitioning is needed.

### 10.8 Operational Scalability Assessment

| Operation | Current performance expectation | Risk at 10K students |
|---|---|---|
| Cohort report generation (reading snapshots) | < 500ms for 100-student cohort | < 2s for 500-student cohort — acceptable |
| Per-student timeline load | < 50ms (indexed) | < 50ms (indexed, same cardinality) |
| Config activation atomic swap | < 10ms | < 10ms (single-row update) |
| Compliance deletion (full scope) | < 5 seconds | < 30 seconds | — manageable with per-table checkpoints |
| SQL Server sync (full table) | Depends on SQL Server query time | Unchanged — SQL Server is the bottleneck |

No operational scalability concerns at current or projected medium-term scale.

### 10.9 Final Recommendation Before Writing 0002

**PROCEED with authoring `0002_warehouse_schema.py` immediately with two corrections:**

**Correction 1 (CRITICAL):** Remove `is_current` from `compliance_audit.scope_manifests`. Replace with `MAX(manifest_version)` query pattern. Do not include `is_current` in the migration.

**Correction 2 (CRITICAL):** Add the following GRANT to the 0002 permission block:
```
GRANT UPDATE (status) ON warehouse.student_snapshots TO compliance_pathway_user;
```

**Confirmation checklist before authoring begins:**

| Item | Status |
|---|---|
| Two-table snapshot design validated | ✓ Validated (this document) |
| FAD-1 physical copy semantics preserved | ✓ Confirmed (Section 1.7) |
| Fingerprint column strategy validated | ✓ Confirmed (Section 3.1) |
| `is_current` bug identified and correction documented | ✓ Section 6.3 |
| Compliance pathway UPDATE grant gap identified and documented | ✓ Section 3.5 / 6.6 |
| Partial unique index strategy validated | ✓ Section 5.1 |
| Migration sequencing validated | ✓ Section 8 |
| Permission grant placement requirement confirmed | ✓ Section 8.5 |
| V1 seed requirement for 0003 confirmed | ✓ Section 8.5 |
| Benchmarking strategy defined (optional, non-blocking) | ✓ Section 2 |

**Architecture is validated. All decisions are resolved. 0002 and 0003 can be authored concurrently.**

---

## 11. SPECIFICATION CORRECTIONS TO PROPAGATE

---

The following corrections to `spec/09_warehouse_physical_architecture.md` are implied by this validation analysis and should be applied before migration authoring begins:

| Section in spec/09 | Correction | Urgency |
|---|---|---|
| Section 7.3 (scope_manifests columns) | Remove `is_current BOOLEAN` column; add note: "Current manifest is determined by MAX(manifest_version) for workflow_id — no UPDATE required" | **Before 0002 authoring** |
| Section 11.4 (implementation-sensitive areas) | Add: "GRANT UPDATE (status) ON warehouse.student_snapshots TO compliance_pathway_user — required for COMPLIANCE_DELETED status transitions" | **Before 0002 authoring** |
| Section 12.3 (recommended implementation sequence) | Add to Step 1 note: "Benchmark concurrently — does not block authoring; two-table design is correct regardless of benchmark outcome" | Before authoring |
| Section 1.4 (immutable history enforcement) | Add: "Compliance pathway account is granted column-level UPDATE on status column of warehouse.student_snapshots for COMPLIANCE_DELETED transitions — this is the sole exception to the warehouse INSERT-only model" | Before authoring |

---

## REFERENCES

---

### Canonical Sources for This Document

* `spec/01_requirements.md` — FAD-1 through FAD-6 (Section 13), open assumptions (Section 11.2), risk register (Section 14.3), configurable rules (Section 12)
* `spec/03_state_transition_rules.md` — State enums for all 6 lifecycle domains
* `spec/04_idempotency_concurrency.md` — Idempotency key patterns and concurrency invariants
* `spec/08_data_model.md` — Conceptual entity definitions; DATA-INVARIANT-1 through DATA-INVARIANT-8; acceptance criteria cases 13–18
* `spec/09_warehouse_physical_architecture.md` — Physical architecture plan that this document validates

### Primary Outputs of This Document

* Correction: `spec/09_warehouse_physical_architecture.md` Section 7.3 — remove `is_current` from scope_manifests
* Correction: `spec/09_warehouse_physical_architecture.md` Section 11.4 — add compliance pathway UPDATE grant
* Benchmarking strategy: Section 2 (to be executed against live PostgreSQL before or during 0002 authoring)
* Migration readiness matrix: Section 10.4
* Implementation risk matrix: Section 10.5
* Pre-authoring checklist: Section 10.9

### Governed By

* `alembic/versions/0002_warehouse_schema.py` — Primary output (authoring now unblocked with two corrections)
* `alembic/versions/0003_config_version_registry.py` — Secondary output (authoring now unblocked)
* `app/services/config_registry.py` — Application-layer atomic swap (after 0003)
* `app/services/snapshot.py` — Finalization service (after 0002 + 0003 + 0004)
* `app/services/compliance.py` — Compliance pathway service (after 0002)

---

## END OF FILE
