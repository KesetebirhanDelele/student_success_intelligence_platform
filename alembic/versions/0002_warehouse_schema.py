"""Warehouse and compliance_audit schema initialization (FAD-4 co-located schemas).

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-25

Overview
--------
Creates two physically isolated PostgreSQL schemas in the same migration per
FAD-4 (spec/01 §13, implementation implication 1):

  "compliance_audit schema must be created in the same Alembic migration
   as the warehouse schema."

warehouse schema — immutable historical archive
  INSERT-only for finalization service account.
  SELECT-only for standard application account.
  No UPDATE or DELETE from any application account (sole exception below).

compliance_audit schema — governance-isolated audit trail
  INSERT-only for compliance pathway service account.
  SELECT-only for standard application account.
  No UPDATE or DELETE ever, from any account.

Architecture references
-----------------------
  spec/09_warehouse_physical_architecture.md  — physical column design
  spec/10_pre_migration_storage_validation.md — formal pre-migration validation
  spec/01_requirements.md FAD-1 through FAD-6
  spec/08_data_model.md DATA-INVARIANT-1 through DATA-INVARIANT-8

Critical corrections applied (spec/10 §10.9, both marked CRITICAL)
-------------------------------------------------------------------
  1. compliance_audit.scope_manifests — is_current column OMITTED.
     Root cause: INSERT-only schema prohibits the UPDATE required to flip
     is_current=false on older rows when a manifest is refreshed. Attempting
     it would fail with a PostgreSQL insufficient_privilege error on first
     manifest refresh. Replacement: current manifest is always
       SELECT * FROM compliance_audit.scope_manifests
       WHERE workflow_id = $1 ORDER BY manifest_version DESC LIMIT 1
     No UPDATE operation is required. Append-only semantics fully preserved.

  2. GRANT UPDATE (status) ON warehouse.student_snapshots TO compliance_pathway_user
     This column-level UPDATE privilege is the sole exception to the warehouse
     INSERT-only model. Required because compliance deletion must transition
     warehouse.student_snapshots rows to status = 'COMPLIANCE_DELETED'. No
     other account held this privilege prior to this correction, making
     compliance deletion impossible after deployment (spec/10 §3.5, §6.6).

Two-table snapshot strategy (spec/09 §3.2, spec/10 §1)
-------------------------------------------------------
  warehouse.student_snapshots      — compact metrics row (~400 bytes)
  warehouse.snapshot_ai_narratives — 1:1 AI text companion (TOAST-eligible)

  Rationale: Five AI narrative fields per snapshot (100–1000+ words each)
  would inflate every analytical scan even with TOAST deferral. Five TOAST
  pointers alone = 100 bytes inline per row × 72,000 rows = ~7MB page savings.
  Two-table design delivers compact metrics scans at all AI text sizes.
  FAD-1 compliance: snapshot_ai_narratives FKs to student_snapshots, NOT to
  ai_insights. The text is a physical point-in-time copy at finalization — no
  FK to ai_insights would be safe (compliance deletion or cleanup of ai_insights
  would either violate the FK or cascade-delete the frozen copy).

Service account names (configure per deployment environment)
------------------------------------------------------------
  app_service_user           — standard application account
  finalization_service_user  — finalization service account
  compliance_pathway_user    — compliance pathway service account

  GRANTs are wrapped in pg_roles existence checks so the migration executes
  safely in environments where roles have not been provisioned (dev, CI).
  In production all three roles MUST exist before this migration runs
  (spec/09 §11.3 remaining blockers: finalization and compliance pathway
  service account credentials are high-severity pre-production blockers).

  Future tables added to warehouse or compliance_audit schemas in later
  migrations must include explicit GRANT statements — this migration only
  covers the tables it creates.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ──────────────────────────────────────────────────────────────────────────
    # 1. Schema creation and public-role lockdown
    # ──────────────────────────────────────────────────────────────────────────
    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS warehouse"))
    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS compliance_audit"))

    # Strip PUBLIC access before creating any objects. PostgreSQL ≤ 14 grants
    # PUBLIC USAGE on all schemas by default; ≥ 15 does not, but the REVOKE is
    # harmless on newer versions.
    op.execute(sa.text("REVOKE ALL ON SCHEMA warehouse FROM PUBLIC"))
    op.execute(sa.text("REVOKE ALL ON SCHEMA compliance_audit FROM PUBLIC"))

    # ──────────────────────────────────────────────────────────────────────────
    # 2. warehouse.student_snapshots
    #
    # Compact metrics row — one finalized row per (student_id, snapshot_month).
    # AI narrative text lives in the companion table snapshot_ai_narratives.
    # All columns are immutable after status transitions to FINALIZED via the
    # INSERT-only permission model (no UPDATE path on this table except the
    # column-level status UPDATE for compliance_pathway_user, granted below).
    #
    # SQL Server mirror columns carry the ss_ prefix to distinguish physical
    # copies from live mirror columns during joins (spec/09 §3.3).
    # ──────────────────────────────────────────────────────────────────────────
    op.create_table(
        "student_snapshots",

        # ── Identity and lifecycle ──────────────────────────────────────────
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        # Physical copy of SQL Server UserID at snapshot time. No FK to
        # ai_chatbot_triggerdata — the snapshot must survive the mirror row.
        sa.Column("student_id", sa.Integer(), nullable=False),
        # DATE, first day of the month this snapshot covers.
        sa.Column("snapshot_month", sa.Date(), nullable=False),
        # FINALIZED | REGENERATION_REQUESTED | COMPLIANCE_HOLD | COMPLIANCE_DELETED
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("lineage_version", sa.Integer(), nullable=False, server_default="1"),
        # NULL for original (lineage_version=1); references prior lineage member.
        sa.Column("parent_snapshot_id", sa.Integer(), nullable=True),
        # True when regeneration source fingerprint differs from original —
        # indicates derived metrics may differ under current config rules.
        sa.Column("potentially_divergent", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),

        # ── SQL Server mirror columns (physical copy at snapshot_month cutoff) ──
        # Names mirror ai_chatbot_triggerdata (0001 baseline) with ss_ prefix.
        # All nullable — columns added to SQL Server after snapshot month do
        # not back-populate historical rows.
        sa.Column("ss_first_name",            sa.String(100),  nullable=True),
        sa.Column("ss_last_name",             sa.String(100),  nullable=True),
        sa.Column("ss_email",                 sa.String(255),  nullable=True),
        sa.Column("ss_phone_number",          sa.String(50),   nullable=True),
        sa.Column("ss_path_name",             sa.String(100),  nullable=True),
        sa.Column("ss_hws_behind",            sa.Integer(),    nullable=True),
        sa.Column("ss_avg_eff_rating",        sa.Float(),      nullable=True),
        sa.Column("ss_last_activity_days",    sa.Integer(),    nullable=True),
        sa.Column("ss_attendance_percentage", sa.Float(),      nullable=True),
        sa.Column("ss_current_section",       sa.String(200),  nullable=True),
        # timezone=False matches SQL Server DATETIME (no tz offset)
        sa.Column("ss_ipbc_start_date",       sa.DateTime(timezone=False), nullable=True),
        sa.Column("ss_past_10_days_logon",    sa.Integer(),    nullable=True),
        sa.Column("ss_total_payments",        sa.Float(),      nullable=True),
        sa.Column("ss_total_credits",         sa.Float(),      nullable=True),
        sa.Column("ss_payment_balance",       sa.Float(),      nullable=True),
        sa.Column("ss_class_value",           sa.Float(),      nullable=True),
        sa.Column("ss_fee_paid",              sa.Boolean(),    nullable=True),
        sa.Column("ss_class_fees_paid",       sa.Float(),      nullable=True),
        sa.Column("ss_class_name",            sa.String(200),  nullable=True),
        sa.Column("ss_class_signups_id",      sa.String(100),  nullable=True),
        sa.Column("ss_active_status",         sa.String(50),   nullable=True),
        sa.Column("ss_status_i",              sa.String(100),  nullable=True),
        sa.Column("ss_status_ii",             sa.String(100),  nullable=True),
        sa.Column("ss_student_start_date",    sa.DateTime(timezone=False), nullable=True),
        sa.Column("ss_class_start_date",      sa.DateTime(timezone=False), nullable=True),
        sa.Column("ss_last_activity_section", sa.String(300),  nullable=True),
        sa.Column("ss_last_login_days",       sa.Integer(),    nullable=True),
        sa.Column("ss_last_submitted",        sa.String(200),  nullable=True),

        # ── Derived metrics (computed at finalization under active config version) ──
        # NEWCOMERS | CAP_HOPEFULS | LAUNCH_HOPEFULS | PLACEMENT_HOPEFULS | HYPER_ACTIVE
        sa.Column("segment_classification",      sa.String(30),  nullable=True),
        # CLEAR | MEDIUM | HIGH
        sa.Column("payment_risk_label",          sa.String(20),  nullable=True),
        # ON_TRACK | AT_RISK | CRITICAL
        sa.Column("hw_risk_score",               sa.String(20),  nullable=True),
        # Bundle-corrected balance computed at finalization
        sa.Column("actual_balance",              sa.Float(),     nullable=True),
        sa.Column("is_bundle_deal",              sa.Boolean(),   nullable=True),
        sa.Column("weeks_in_program",            sa.Integer(),   nullable=True),
        sa.Column("days_since_last_submission",  sa.Integer(),   nullable=True),

        # ── Communication summary (computed at finalization from append-only tables) ──
        sa.Column("total_outreach_attempts",  sa.Integer(), nullable=True),
        sa.Column("total_responses",          sa.Integer(), nullable=True),
        sa.Column("last_contact_date",        sa.Date(),    nullable=True),
        sa.Column("days_since_last_contact",  sa.Integer(), nullable=True),
        # {CALL: N, SMS: N, EMAIL: N} — small inline JSONB
        sa.Column("channel_breakdown_json",
                  postgresql.JSONB(astext_type=sa.Text()), nullable=True),

        # ── Reproducibility fingerprint (all 5 components; locked at FINALIZED) ──
        # Three scalar TEXT columns for direct equality filtering (spec/10 §3.1).
        # Alembic revision ID active when this snapshot was finalized.
        sa.Column("fingerprint_schema_version",          sa.Text(), nullable=True),
        # config_version_registry.version_number (as TEXT) active at DRAFT→VALIDATING.
        sa.Column("fingerprint_config_registry_version", sa.Text(), nullable=True),
        # Report template version active at snapshot time.
        sa.Column("fingerprint_report_template_version", sa.Text(), nullable=True),
        # Per-type AI version map: {"risk_summary": {"prompt": "v1.2", "model": "..."}, ...}
        # JSONB because insight type cardinality is variable (spec/10 §3.1).
        sa.Column("fingerprint_ai_versions_json",
                  postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fingerprint_computed_at", sa.DateTime(timezone=True), nullable=True),

        # ── Metadata ─────────────────────────────────────────────────────────
        sa.Column("created_at",     sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        # SHADOW | LIVE
        sa.Column("execution_mode", sa.String(10), nullable=False, server_default="SHADOW"),
        sa.Column("generated_by",   sa.String(100), nullable=True),

        # ── Constraints ───────────────────────────────────────────────────────
        # Self-referential FK for regeneration lineage linked list.
        sa.ForeignKeyConstraint(
            ["parent_snapshot_id"],
            ["warehouse.student_snapshots.id"],
            name="fk_wss_parent_snapshot",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="warehouse",
    )

    # Partial unique: exactly one FINALIZED row per (student, month).
    # Partial scope allows multiple draft/validating rows during two-phase
    # finalization without spurious constraint violations (spec/09 §8.2).
    op.create_index(
        "uq_wss_finalized_student_month",
        "student_snapshots",
        ["student_id", "snapshot_month"],
        unique=True,
        postgresql_where=sa.text("status = 'FINALIZED'"),
        schema="warehouse",
    )
    # Primary analytical access: per-student history, cohort report generation.
    op.create_index("ix_wss_student_month",
                    "student_snapshots", ["student_id", "snapshot_month"], schema="warehouse")
    # Cohort aggregations: all students in a given month for report generation.
    op.create_index("ix_wss_month_segment",
                    "student_snapshots", ["snapshot_month", "segment_classification"], schema="warehouse")
    # Multi-month trend per student (ORDER BY snapshot_month on student_id scan).
    op.create_index("ix_wss_student_id",
                    "student_snapshots", ["student_id"], schema="warehouse")
    # Fingerprint audit queries: "how many snapshots used config version V2?"
    op.create_index("ix_wss_fp_config",
                    "student_snapshots", ["fingerprint_config_registry_version"], schema="warehouse")
    op.create_index("ix_wss_fp_schema",
                    "student_snapshots", ["fingerprint_schema_version"], schema="warehouse")

    # ──────────────────────────────────────────────────────────────────────────
    # 3. warehouse.snapshot_ai_narratives
    #
    # 1:1 AI text companion to student_snapshots. Physical copy semantics (FAD-1):
    # text is copied from ai_insights at finalization and is thereafter frozen.
    # Post-finalization operations on ai_insights (force-refresh, model upgrade,
    # compliance deletion of insights) have zero effect on these rows.
    #
    # Critical: snapshot_id FKs to warehouse.student_snapshots, NOT to ai_insights.
    # A real FK to ai_insights would either block compliance deletion of insight
    # records (violating GDPR/FERPA) or cascade-delete the frozen text (violating
    # DATA-INVARIANT-3 and FAD-1). Neither is acceptable (spec/10 §1.7).
    # ──────────────────────────────────────────────────────────────────────────
    op.create_table(
        "snapshot_ai_narratives",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),

        # Physical copies of AI_REVIEWED text at finalization time.
        # NULL means the insight type was absent or not yet reviewed at finalization.
        # All five fields stored as TEXT; PostgreSQL TOAST handles values > ~2KB.
        sa.Column("risk_summary_text",               sa.Text(), nullable=True),
        sa.Column("progress_summary_text",           sa.Text(), nullable=True),
        sa.Column("monthly_narrative_text",          sa.Text(), nullable=True),
        sa.Column("intervention_recommendation_text",sa.Text(), nullable=True),
        sa.Column("trend_interpretation_text",       sa.Text(), nullable=True),
        sa.Column("copied_at", sa.DateTime(timezone=True), nullable=False),

        # Advisory hint — NOT a FK constraint. Answers "which ai_insights row
        # was the source?" for audit purposes only. Becomes stale if the source
        # ai_insights record is deleted; that is acceptable (text is a physical
        # copy). Adding a real FK here would recreate the dependency FAD-1 forbids.
        sa.Column("ai_source_insight_id_hint", sa.Integer(), nullable=True),

        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["warehouse.student_snapshots.id"],
            name="fk_wsan_snapshot",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="warehouse",
    )

    # Unique on snapshot_id enforces the 1:1 relationship at DB layer.
    op.create_index("uq_wsan_snapshot_id",
                    "snapshot_ai_narratives", ["snapshot_id"], unique=True, schema="warehouse")

    # ──────────────────────────────────────────────────────────────────────────
    # 4. warehouse.monthly_reports
    #
    # Lineage-versioned published report per (cohort_id, report_month).
    # Regeneration appends new rows (lineage_version N+1); the original
    # REPORT_PUBLISHED row is never modified (warehouse INSERT-only model).
    # Current publication = highest lineage_version in REPORT_PUBLISHED status
    # for a given (cohort_id, report_month) (spec/09 §1.6, §4.3).
    # ──────────────────────────────────────────────────────────────────────────
    op.create_table(
        "monthly_reports",

        # ── Identity and lineage ──────────────────────────────────────────────
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        # ClassName or cohort identifier mapping to a group of student_snapshots.
        sa.Column("cohort_id",        sa.String(200), nullable=False),
        sa.Column("report_month",     sa.Date(),      nullable=False),
        sa.Column("template_version", sa.String(100), nullable=False),
        sa.Column("lineage_version",  sa.Integer(),   nullable=False, server_default="1"),
        # NULL for lineage_version=1; references prior publication on regeneration.
        sa.Column("parent_report_id", sa.Integer(),   nullable=True),
        # REPORT_PENDING | REPORT_GENERATING | REPORT_GENERATED |
        # REPORT_REVIEW_PENDING | REPORT_APPROVED | REPORT_PUBLISHED |
        # REPORT_GENERATION_FAILED | REPORT_REJECTED
        sa.Column("status", sa.String(50), nullable=False),
        # True when regeneration source snapshot fingerprint differs from
        # the fingerprint at original publication time (FAD-6).
        sa.Column("potentially_divergent", sa.Boolean(), nullable=False, server_default="false"),

        # ── Source attribution (FAD-2: historical analytics use snapshot data only) ──
        # Collective fingerprint of all source snapshots at job creation time.
        sa.Column("source_snapshot_fingerprint_json",
                  postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Deterministic key: hash(cohort_id, report_month, template_version, lineage_version).
        # UNIQUE — prevents duplicate generation jobs for the same logical report.
        sa.Column("report_idempotency_key", sa.Text(), nullable=False),

        # ── Rendered content ─────────────────────────────────────────────────
        # JSONB inline for initial implementation (spec/09 §4.1).
        # Per spec/10 §9.6: reference snapshot_ids rather than embedding full
        # narrative text to bound payload size for large cohorts.
        sa.Column("report_content_json",    postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("aggregate_stats_json",   postgresql.JSONB(astext_type=sa.Text()), nullable=True),

        # ── Metadata ─────────────────────────────────────────────────────────
        sa.Column("generated_at",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("generated_by",   sa.String(100),             nullable=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
        # SHADOW | LIVE
        sa.Column("execution_mode", sa.String(10), nullable=False, server_default="SHADOW"),

        # Self-referential FK for lineage linked list (spec/09 §1.6).
        sa.ForeignKeyConstraint(
            ["parent_report_id"],
            ["warehouse.monthly_reports.id"],
            name="fk_wmr_parent_report",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="warehouse",
    )

    # Idempotency key uniqueness — one generation job per logical report version.
    op.create_index("uq_wmr_idempotency_key",
                    "monthly_reports", ["report_idempotency_key"], unique=True, schema="warehouse")
    # Partial unique: one published row per (cohort, month, lineage_version).
    # Partial scope allows PENDING/GENERATING rows without constraint violations.
    op.create_index(
        "uq_wmr_published_lineage",
        "monthly_reports",
        ["cohort_id", "report_month", "lineage_version"],
        unique=True,
        postgresql_where=sa.text("status = 'REPORT_PUBLISHED'"),
        schema="warehouse",
    )
    # Current publication lookup: (cohort_id, report_month) filtered by status.
    op.create_index("ix_wmr_cohort_month_status",
                    "monthly_reports", ["cohort_id", "report_month", "status"], schema="warehouse")

    # ──────────────────────────────────────────────────────────────────────────
    # 5. warehouse.report_audit_log
    #
    # Append-only lifecycle event log for every monthly_reports row.
    # Covers: GenerationJobCreated, GenerationCompleted, PublicationCommitted,
    # RegenerationRequested, PotentiallyDivergentFlagged, GenerationFailed.
    # ──────────────────────────────────────────────────────────────────────────
    op.create_table(
        "report_audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("report_id",   sa.Integer(),  nullable=False),
        sa.Column("event_type",  sa.String(100), nullable=False),
        # Denormalized copy from monthly_reports row: enables audit queries
        # without joining back to the parent when the report row is slow to fetch.
        sa.Column("report_idempotency_key",           sa.Text(), nullable=True),
        sa.Column("source_snapshot_fingerprint_json",
                  postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("event_details_json",
                  postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor",          sa.String(100), nullable=True),
        sa.Column("created_at",     sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),

        sa.ForeignKeyConstraint(
            ["report_id"],
            ["warehouse.monthly_reports.id"],
            name="fk_wral_report",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="warehouse",
    )

    op.create_index("ix_wral_report_id",   "report_audit_log", ["report_id"],      schema="warehouse")
    op.create_index("ix_wral_correlation", "report_audit_log", ["correlation_id"], schema="warehouse")
    op.create_index("ix_wral_created_at",  "report_audit_log", ["created_at"],     schema="warehouse")
    op.create_index("ix_wral_event_type",  "report_audit_log", ["event_type"],     schema="warehouse")

    # ──────────────────────────────────────────────────────────────────────────
    # 6. compliance_audit.deletion_log
    #
    # Permanent, governance-isolated audit trail for all compliance deletion
    # and anonymization workflows. Zero FK dependencies on public or warehouse
    # schemas — the audit row must survive the deletion it audits.
    #
    # Stores PRE_ACTION, POST_ACTION, and PARTIAL_COMPLETION_CHECKPOINT entries
    # keyed by workflow_id + sequence_number (spec/09 §7.2).
    # ──────────────────────────────────────────────────────────────────────────
    op.create_table(
        "deletion_log",

        # ── Identity ─────────────────────────────────────────────────────────
        sa.Column("id",              sa.Integer(),                   autoincrement=True, nullable=False),
        sa.Column("workflow_id",     postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.Integer(),                   nullable=False),
        # PRE_ACTION | POST_ACTION | PARTIAL_COMPLETION_CHECKPOINT
        sa.Column("entry_type", sa.String(40), nullable=False),

        # ── Student scope — plain INTEGER, no FK (survivability guarantee) ───
        sa.Column("student_id",  sa.Integer(),  nullable=False),
        # GDPR_DELETION | FERPA_REMOVAL | ANONYMIZATION_REQUEST | INTERNAL_COMPLIANCE
        sa.Column("action_type", sa.String(50), nullable=False),

        # ── Authorization chain ───────────────────────────────────────────────
        sa.Column("authorization_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("authorized_by",           sa.String(200), nullable=True),
        sa.Column("executed_by",             sa.String(200), nullable=True),
        # Required by governance: legal or compliance basis for the action.
        sa.Column("audit_rationale", sa.Text(), nullable=False),

        # ── Scope manifest reference ──────────────────────────────────────────
        # UUID pointing to compliance_audit.scope_manifests.manifest_id.
        # Stored as UUID column (not FK) to preserve append-only semantics within
        # the schema — no FK is needed because both tables are INSERT-only and
        # the manifest always exists before the deletion log entry references it.
        sa.Column("scope_manifest_id",     postgresql.UUID(as_uuid=True),         nullable=True),
        sa.Column("affected_tables_json",  postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("affected_record_count", sa.Integer(),                            nullable=True),

        # ── Execution details ─────────────────────────────────────────────────
        sa.Column("execution_details_json",
                  postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # COMPLETED_DELETED | COMPLETED_ANONYMIZED | PARTIALLY_COMPLETED | IN_PROGRESS
        sa.Column("outcome", sa.String(50), nullable=True),

        # ── Metadata ─────────────────────────────────────────────────────────
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at",     sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),

        sa.PrimaryKeyConstraint("id"),
        schema="compliance_audit",
    )

    op.create_index("ix_cadl_workflow_id",
                    "deletion_log", ["workflow_id"], schema="compliance_audit")
    op.create_index("ix_cadl_student_id",
                    "deletion_log", ["student_id"], schema="compliance_audit")
    op.create_index("ix_cadl_created_at",
                    "deletion_log", ["created_at"], schema="compliance_audit")
    # Covering index for per-student audit export (spec/09 §9.3, future use).
    op.create_index("ix_cadl_student_created",
                    "deletion_log", ["student_id", "created_at"], schema="compliance_audit")

    # ──────────────────────────────────────────────────────────────────────────
    # 7. compliance_audit.scope_manifests
    #
    # Captures the complete set of records in scope at APPROVED_FOR_ACTION time.
    # Append-only version lineage: each refresh INSERTs a new row with
    # manifest_version = old_version + 1. No is_current column (see correction 1
    # in module docstring — UPDATE would violate INSERT-only invariant).
    #
    # Current manifest query pattern (no UPDATE required):
    #   SELECT * FROM compliance_audit.scope_manifests
    #   WHERE workflow_id = $1 ORDER BY manifest_version DESC LIMIT 1
    # ──────────────────────────────────────────────────────────────────────────
    op.create_table(
        "scope_manifests",
        sa.Column("id",               sa.Integer(),                   autoincrement=True, nullable=False),
        # Referenced by deletion_log.scope_manifest_id (UUID pointer, not FK).
        sa.Column("manifest_id",      postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_id",      postgresql.UUID(as_uuid=True), nullable=False),
        # No FK to student_trigger_data — survives student record deletion.
        sa.Column("student_id",       sa.Integer(),                   nullable=False),
        sa.Column("captured_at",      sa.DateTime(timezone=True),     nullable=False),
        # Incremented on each refresh before execution. Used to determine current
        # manifest without UPDATE: ORDER BY manifest_version DESC LIMIT 1.
        sa.Column("manifest_version", sa.Integer(),                   nullable=False, server_default="1"),
        # Full table-by-table enumeration with record IDs or query predicates.
        sa.Column("tables_in_scope_json",
                  postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),

        sa.PrimaryKeyConstraint("id"),
        schema="compliance_audit",
    )

    # manifest_id is the external reference key used in deletion_log.
    op.create_index("uq_casm_manifest_id",
                    "scope_manifests", ["manifest_id"], unique=True, schema="compliance_audit")
    # Primary access pattern: current manifest for a workflow.
    op.create_index("ix_casm_workflow_version",
                    "scope_manifests", ["workflow_id", "manifest_version"], schema="compliance_audit")
    op.create_index("ix_casm_student_id",
                    "scope_manifests", ["student_id"], schema="compliance_audit")

    # ──────────────────────────────────────────────────────────────────────────
    # 8. Permission grants
    #
    # These GRANTs are part of the schema definition, not separate operational
    # steps (spec/09 §11.4). They MUST be in this migration file so that every
    # environment (dev, CI, staging, production) gets the correct access control
    # profile when running `alembic upgrade head`.
    #
    # Role-existence guards: the migration executes without error in environments
    # where roles have not been provisioned. In production all three roles MUST
    # exist and MUST be provisioned before this migration runs.
    #
    # Sequence grants: finalization_service_user and compliance_pathway_user
    # need USAGE on sequences to call nextval() for autoincrement PKs on INSERT.
    # ──────────────────────────────────────────────────────────────────────────
    op.execute(sa.text("""
        DO $$
        BEGIN

            -- ── app_service_user ─────────────────────────────────────────────
            -- Standard application account: SELECT-only on both schemas.
            -- No INSERT, UPDATE, or DELETE on any warehouse or compliance_audit table.
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_service_user') THEN
                GRANT USAGE ON SCHEMA warehouse TO app_service_user;
                GRANT SELECT ON ALL TABLES IN SCHEMA warehouse TO app_service_user;
                GRANT USAGE ON SCHEMA compliance_audit TO app_service_user;
                GRANT SELECT ON ALL TABLES IN SCHEMA compliance_audit TO app_service_user;
            END IF;

            -- ── finalization_service_user ─────────────────────────────────────
            -- Finalization account: INSERT-only on warehouse tables.
            -- Covers all four warehouse tables (spec/09 §1.4).
            -- No UPDATE or DELETE grants on any warehouse table.
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finalization_service_user') THEN
                GRANT USAGE ON SCHEMA warehouse TO finalization_service_user;
                GRANT INSERT ON warehouse.student_snapshots        TO finalization_service_user;
                GRANT INSERT ON warehouse.snapshot_ai_narratives   TO finalization_service_user;
                GRANT INSERT ON warehouse.monthly_reports          TO finalization_service_user;
                GRANT INSERT ON warehouse.report_audit_log         TO finalization_service_user;
                -- Sequence access required for autoincrement PKs on INSERT.
                GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA warehouse TO finalization_service_user;
            END IF;

            -- ── compliance_pathway_user ───────────────────────────────────────
            -- Compliance pathway account: INSERT-only on compliance_audit tables.
            -- Column-level UPDATE on warehouse.student_snapshots.status only —
            -- the sole exception to the warehouse INSERT-only model.
            -- Required for COMPLIANCE_DELETED status transitions (spec/10 §3.5, §6.6).
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'compliance_pathway_user') THEN
                GRANT USAGE ON SCHEMA compliance_audit TO compliance_pathway_user;
                GRANT INSERT ON compliance_audit.deletion_log   TO compliance_pathway_user;
                GRANT INSERT ON compliance_audit.scope_manifests TO compliance_pathway_user;
                GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA compliance_audit TO compliance_pathway_user;
                -- Warehouse schema access for the column-level UPDATE only.
                GRANT USAGE ON SCHEMA warehouse TO compliance_pathway_user;
                -- This is the ONLY UPDATE privilege on any warehouse table.
                -- compliance_pathway_user may UPDATE the status column and no other column.
                GRANT UPDATE (status) ON warehouse.student_snapshots TO compliance_pathway_user;
            END IF;

        END;
        $$;
    """))


def downgrade() -> None:
    # ── Revoke grants before dropping objects ─────────────────────────────────
    # Prevents stale privilege entries if roles still exist after the downgrade.
    op.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'compliance_pathway_user') THEN
                REVOKE UPDATE (status) ON warehouse.student_snapshots FROM compliance_pathway_user;
                REVOKE ALL ON compliance_audit.deletion_log    FROM compliance_pathway_user;
                REVOKE ALL ON compliance_audit.scope_manifests FROM compliance_pathway_user;
                REVOKE ALL ON ALL SEQUENCES IN SCHEMA compliance_audit FROM compliance_pathway_user;
                REVOKE USAGE ON SCHEMA compliance_audit FROM compliance_pathway_user;
                REVOKE USAGE ON SCHEMA warehouse FROM compliance_pathway_user;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finalization_service_user') THEN
                REVOKE ALL ON warehouse.student_snapshots        FROM finalization_service_user;
                REVOKE ALL ON warehouse.snapshot_ai_narratives   FROM finalization_service_user;
                REVOKE ALL ON warehouse.monthly_reports          FROM finalization_service_user;
                REVOKE ALL ON warehouse.report_audit_log         FROM finalization_service_user;
                REVOKE ALL ON ALL SEQUENCES IN SCHEMA warehouse  FROM finalization_service_user;
                REVOKE USAGE ON SCHEMA warehouse FROM finalization_service_user;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_service_user') THEN
                REVOKE ALL ON ALL TABLES IN SCHEMA warehouse       FROM app_service_user;
                REVOKE ALL ON ALL TABLES IN SCHEMA compliance_audit FROM app_service_user;
                REVOKE USAGE ON SCHEMA warehouse FROM app_service_user;
                REVOKE USAGE ON SCHEMA compliance_audit FROM app_service_user;
            END IF;
        END;
        $$;
    """))

    # ── Drop tables in FK dependency order ────────────────────────────────────
    # compliance_audit tables have no cross-schema FKs — drop either order.
    op.drop_table("scope_manifests", schema="compliance_audit")
    op.drop_table("deletion_log",    schema="compliance_audit")

    # warehouse tables: FK-dependent children first, then parents.
    # report_audit_log FK -> monthly_reports
    op.drop_table("report_audit_log", schema="warehouse")
    # snapshot_ai_narratives FK -> student_snapshots
    op.drop_table("snapshot_ai_narratives", schema="warehouse")
    # monthly_reports: self-referential FK (safe to drop standalone)
    op.drop_table("monthly_reports", schema="warehouse")
    # student_snapshots: self-referential FK (safe to drop standalone)
    op.drop_table("student_snapshots", schema="warehouse")

    # ── Drop schemas ──────────────────────────────────────────────────────────
    op.execute(sa.text("DROP SCHEMA IF EXISTS compliance_audit CASCADE"))
    op.execute(sa.text("DROP SCHEMA IF EXISTS warehouse CASCADE"))
