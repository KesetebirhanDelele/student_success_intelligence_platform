"""public.config_version_registry — Configuration Version Registry initialization.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-25

Overview
--------
Creates public.config_version_registry — the platform's governance-controlled,
append-only record of every change to configurable operational rules (spec/01 §12.8).

This table is the historical anchor for the Snapshot Reproducibility Fingerprint
(spec/01 §4.8, FAD-6): every finalized snapshot stores the active config version
number in fingerprint_config_registry_version. A future auditor can look up that
version and retrieve the exact rule set that governed the snapshot's classification.

Governance principles enforced by this migration
-------------------------------------------------
1. EXACTLY-ONE-ACTIVE invariant — physically enforced at the database layer via a
   partial unique index on the constant expression (1) WHERE status = 'ACTIVE'.
   Attempting to INSERT a second ACTIVE row raises a unique violation before any
   application-layer logic can be bypassed. This invariant is DB-enforced, not
   application-enforced (DATA-INVARIANT-4, spec/10 §8.5).

2. Append-only configuration lineage — rule values in a version record are never
   modified after creation. Only governance metadata columns (status,
   superseded_by_version_id, deactivated_at) carry column-level UPDATE privileges
   for the config_admin_user role. No UPDATE privilege on rule columns exists for
   any role. Rollback to a prior version is accomplished by creating a new version
   record that copies the prior values — not by restoring the superseded record.

3. Prospective-only activation — a version change affects future classification runs
   only. Historical snapshots retain their original fingerprint_config_registry_version
   attribution regardless of how many subsequent versions are created (FAD-3).

4. Transactional seed integrity — the V1 INSERT is in the same Alembic upgrade()
   as CREATE TABLE. Alembic wraps the migration in a single transaction: if the
   INSERT fails, the entire migration rolls back, leaving no orphaned table without
   an ACTIVE row (spec/10 §8.5). A system without an ACTIVE config row is
   non-functional; the seed is not optional.

Exactly-one-ACTIVE enforcement
-------------------------------
    CREATE UNIQUE INDEX uq_cvr_active_singleton
    ON config_version_registry ((1))
    WHERE status = 'ACTIVE'

PostgreSQL evaluates the constant expression (1) to integer 1 for every row where
status = 'ACTIVE'. One ACTIVE row → one index entry. Two ACTIVE rows → two entries
with value 1 → unique constraint violated. The activation transaction must mark the
current ACTIVE row as SUPERSEDED before inserting the new ACTIVE row.

Version activation transaction pattern (application responsibility)
-------------------------------------------------------------------
    BEGIN;
        UPDATE config_version_registry
           SET status = 'SUPERSEDED',
               superseded_by_version_id = <new_id>,
               deactivated_at = now()
         WHERE status = 'ACTIVE';        -- exactly one row

        INSERT INTO config_version_registry (..., status, ...)
        VALUES (..., 'ACTIVE', ...);     -- new ACTIVE row; index allows it now
    COMMIT;

Architecture references
-----------------------
  spec/01 §12.1–12.7  — configurable rule definitions and V1 defaults
  spec/01 §12.8       — Configuration Version Registry governance principles
  spec/01 §4.8 (FAD-6)— Snapshot Reproducibility Fingerprint
  spec/08 §2          — config_version_registry data class
  spec/09 §11.5       — 0003 migration authoring sequence
  spec/10 §8.5        — transactional seed coupling requirement
  spec/03             — state transition rules for configuration lifecycle
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ──────────────────────────────────────────────────────────────────────────
    # 1. public.config_version_registry
    # ──────────────────────────────────────────────────────────────────────────
    op.create_table(
        "config_version_registry",

        # ── Identity and versioning ───────────────────────────────────────────
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        # Monotonically increasing human-readable identifier.
        # Used as TEXT in snapshot fingerprints: fingerprint_config_registry_version.
        sa.Column("version_number", sa.Integer(), nullable=False),
        # PROPOSED | UNDER_REVIEW | APPROVED | ACTIVE | ARCHIVED | SUPERSEDED
        sa.Column("status", sa.String(50), nullable=False),

        # ── Lineage pointers (self-referential) ───────────────────────────────
        # NULL for V1. Reference to the immediately preceding version.
        sa.Column("prior_version_id",         sa.Integer(), nullable=True),
        # Set when this version is superseded. Stored on the superseded row so
        # the lineage pointer is readable without joining to the newer version.
        sa.Column("superseded_by_version_id", sa.Integer(), nullable=True),

        # ── Activation lifecycle ──────────────────────────────────────────────
        sa.Column("effective_from",  sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at",    sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_by",    sa.String(200),             nullable=True),
        sa.Column("deactivated_at",  sa.DateTime(timezone=True), nullable=True),

        # ── Governance chain ──────────────────────────────────────────────────
        sa.Column("proposed_by",          sa.String(200), nullable=True),
        sa.Column("approved_by",          sa.String(200), nullable=True),
        sa.Column("approval_timestamp",   sa.DateTime(timezone=True), nullable=True),
        # Required for any version reaching ACTIVE; enforced at application layer.
        sa.Column("change_rationale", sa.Text(), nullable=True),
        sa.Column("governance_notes", sa.Text(), nullable=True),

        # ── Section 12.1 — Cohort identification thresholds ──────────────────
        # V1 defaults: 0.30, 0.59 from SQL operational heuristics (spec/01 §2.4)
        sa.Column("cap_hopeful_min_percomp",    sa.Float(), nullable=False),
        sa.Column("launch_hopeful_min_percomp", sa.Float(), nullable=False),
        # JSONB array of ILIKE patterns matched against CurrentSection.
        # V1: ["%launch%", "%CAP%"]
        sa.Column("cap_section_exclusion_patterns_json",
                  postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("launch_section_inclusion_pattern",    sa.Text(), nullable=False),
        sa.Column("placement_section_inclusion_pattern", sa.Text(), nullable=False),

        # ── Section 12.2 — Homework risk thresholds ──────────────────────────
        sa.Column("hw_at_risk_min_behind",      sa.Integer(), nullable=False),
        sa.Column("hw_at_risk_max_eff_rating",  sa.Float(),   nullable=False),
        sa.Column("hw_critical_min_behind",     sa.Integer(), nullable=False),
        sa.Column("hw_critical_max_eff_rating", sa.Float(),   nullable=False),

        # ── Section 12.3 — Payment risk thresholds ───────────────────────────
        # payment_deviation_alert_threshold: "default TBD" per spec; nullable.
        sa.Column("payment_medium_threshold",          sa.Float(), nullable=False),
        sa.Column("payment_high_threshold",            sa.Float(), nullable=False),
        sa.Column("payment_deviation_alert_threshold", sa.Float(), nullable=True),

        # ── Section 12.4 — Priority scoring formula ──────────────────────────
        # Additive score (0–135): HWsBehind × weight (cap) + EffRating × weight (cap)
        #                         + InactivityDays × weight (cap)
        sa.Column("priority_hw_weight",         sa.Float(), nullable=False),
        sa.Column("priority_hw_cap",            sa.Float(), nullable=False),
        sa.Column("priority_eff_weight",        sa.Float(), nullable=False),
        sa.Column("priority_eff_cap",           sa.Float(), nullable=False),
        sa.Column("priority_inactivity_weight", sa.Float(), nullable=False),
        sa.Column("priority_inactivity_cap",    sa.Float(), nullable=False),

        # ── Section 12.5 — Operational scheduling and timing ─────────────────
        sa.Column("ai_insight_ttl_hours",            sa.Integer(), nullable=False),
        sa.Column("outreach_retry_window_days",      sa.Integer(), nullable=False),
        sa.Column("placement_inactivity_alert_days", sa.Integer(), nullable=False),
        sa.Column("access_revocation_alert_hours",   sa.Integer(), nullable=False),

        # ── Section 12.6 — Provider selection ───────────────────────────────
        sa.Column("ai_llm_provider",   sa.Text(), nullable=False),
        sa.Column("outreach_provider", sa.Text(), nullable=False),

        # ── Reproducibility snapshot ──────────────────────────────────────────
        # Complete JSONB snapshot of all 24 rule values at this version version.
        # Enables one-shot reproducibility audit without reconstructing individual
        # columns. Immutable once written (no UPDATE privilege on this column).
        sa.Column("rule_set_snapshot_json",
                  postgresql.JSONB(astext_type=sa.Text()), nullable=True),

        # ── Metadata ─────────────────────────────────────────────────────────
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),

        # ── Constraints ───────────────────────────────────────────────────────
        sa.CheckConstraint(
            "status IN ('PROPOSED','UNDER_REVIEW','APPROVED','ACTIVE','ARCHIVED','SUPERSEDED')",
            name="chk_cvr_status",
        ),
        sa.CheckConstraint("version_number > 0", name="chk_cvr_version_positive"),
        sa.ForeignKeyConstraint(
            ["prior_version_id"],
            ["config_version_registry.id"],
            name="fk_cvr_prior_version",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_version_id"],
            ["config_version_registry.id"],
            name="fk_cvr_superseded_by",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── Standard indexes ──────────────────────────────────────────────────────

    # The fingerprint lookup: given fingerprint_config_registry_version = '2',
    # this index resolves the version record instantly.
    op.create_index("uq_cvr_version_number",
                    "config_version_registry", ["version_number"], unique=True)

    # Lineage traversal: "what was the version before V5?"
    op.create_index("ix_cvr_prior_version_id",
                    "config_version_registry", ["prior_version_id"])

    # Activation history: all versions ordered by activation time.
    op.create_index("ix_cvr_activated_at",
                    "config_version_registry", ["activated_at"])

    # Admin workflow: find PROPOSED / UNDER_REVIEW / APPROVED pending versions.
    op.create_index("ix_cvr_status",
                    "config_version_registry", ["status"])

    # ── Exactly-one-ACTIVE partial unique index (DATA-INVARIANT-4) ────────────
    # op.create_index cannot express a constant-expression index column.
    # Raw DDL is the correct approach here.
    op.execute(sa.text(
        "CREATE UNIQUE INDEX uq_cvr_active_singleton "
        "ON config_version_registry ((1)) "
        "WHERE status = 'ACTIVE'"
    ))

    # ── Permission grants (pg_roles existence guards) ─────────────────────────
    op.execute(sa.text("""
        DO $$
        BEGIN
            -- app_service_user: SELECT only.
            -- Reads the active config version for every classification run,
            -- snapshot generation, and AI insight TTL check.
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_service_user') THEN
                GRANT SELECT ON config_version_registry TO app_service_user;
            END IF;

            -- finalization_service_user: SELECT only.
            -- Reads the active version number to record in the snapshot fingerprint.
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finalization_service_user') THEN
                GRANT SELECT ON config_version_registry TO finalization_service_user;
            END IF;

            -- config_admin_user: SELECT + INSERT + column-level UPDATE.
            -- The only role permitted to create new versions and execute the
            -- atomic activation transaction (SUPERSEDE old → INSERT new).
            -- No UPDATE on rule columns; governance metadata only.
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'config_admin_user') THEN
                GRANT SELECT, INSERT ON config_version_registry TO config_admin_user;
                GRANT UPDATE (status, superseded_by_version_id, deactivated_at)
                    ON config_version_registry TO config_admin_user;
                GRANT USAGE, SELECT ON SEQUENCE config_version_registry_id_seq
                    TO config_admin_user;
            END IF;
        END;
        $$;
    """))

    # ── V1 seed record ────────────────────────────────────────────────────────
    # Transactional coupling with CREATE TABLE (spec/10 §8.5):
    #   The Alembic upgrade transaction is atomic. If this INSERT fails, the
    #   entire migration rolls back — no orphaned table without an ACTIVE row.
    #   A system with no ACTIVE config version violates DATA-INVARIANT-4 and
    #   makes snapshot generation non-functional from the first run.
    #
    # All 24 rule values sourced from spec/01 Sections 12.1–12.7.
    # rule_set_snapshot_json is a complete inline JSONB object duplicating all
    # rule columns — enables one-shot reproducibility audit without column joins.
    op.execute(sa.text("""
        INSERT INTO config_version_registry (
            version_number,
            status,
            prior_version_id,
            superseded_by_version_id,
            effective_from,
            activated_at,
            activated_by,
            deactivated_at,
            proposed_by,
            approved_by,
            approval_timestamp,
            change_rationale,
            governance_notes,
            cap_hopeful_min_percomp,
            launch_hopeful_min_percomp,
            cap_section_exclusion_patterns_json,
            launch_section_inclusion_pattern,
            placement_section_inclusion_pattern,
            hw_at_risk_min_behind,
            hw_at_risk_max_eff_rating,
            hw_critical_min_behind,
            hw_critical_max_eff_rating,
            payment_medium_threshold,
            payment_high_threshold,
            payment_deviation_alert_threshold,
            priority_hw_weight,
            priority_hw_cap,
            priority_eff_weight,
            priority_eff_cap,
            priority_inactivity_weight,
            priority_inactivity_cap,
            ai_insight_ttl_hours,
            outreach_retry_window_days,
            placement_inactivity_alert_days,
            access_revocation_alert_hours,
            ai_llm_provider,
            outreach_provider,
            rule_set_snapshot_json
        ) VALUES (
            1,
            'ACTIVE',
            NULL,
            NULL,
            now(),
            now(),
            'system_migration_0003',
            NULL,
            'system_migration_0003',
            'system_migration_0003',
            now(),
            'V1 baseline configuration — initial platform defaults per spec/01 Sections 12.1 through 12.7. All threshold values derived from SQL operational heuristics. This is the only version that does not require a prior human authorization workflow: it captures pre-existing operational defaults at platform launch.',
            'Seeded automatically by Alembic migration 0003. No prior version exists.',
            0.30,
            0.59,
            '["%launch%", "%CAP%"]',
            '%CAP%',
            '%launch%',
            1,
            3.0,
            3,
            2.0,
            0.01,
            1000.00,
            NULL,
            10.0,
            50.0,
            7.0,
            35.0,
            2.0,
            50.0,
            24,
            3,
            7,
            48,
            'anthropic',
            'ghl',
            '{
                "cap_hopeful_min_percomp": 0.30,
                "launch_hopeful_min_percomp": 0.59,
                "cap_section_exclusion_patterns": ["%launch%", "%CAP%"],
                "launch_section_inclusion_pattern": "%CAP%",
                "placement_section_inclusion_pattern": "%launch%",
                "hw_at_risk_min_behind": 1,
                "hw_at_risk_max_eff_rating": 3.0,
                "hw_critical_min_behind": 3,
                "hw_critical_max_eff_rating": 2.0,
                "payment_medium_threshold": 0.01,
                "payment_high_threshold": 1000.00,
                "payment_deviation_alert_threshold": null,
                "priority_hw_weight": 10.0,
                "priority_hw_cap": 50.0,
                "priority_eff_weight": 7.0,
                "priority_eff_cap": 35.0,
                "priority_inactivity_weight": 2.0,
                "priority_inactivity_cap": 50.0,
                "ai_insight_ttl_hours": 24,
                "outreach_retry_window_days": 3,
                "placement_inactivity_alert_days": 7,
                "access_revocation_alert_hours": 48,
                "ai_llm_provider": "anthropic",
                "outreach_provider": "ghl"
            }'::jsonb
        )
    """))


def downgrade() -> None:
    # Revoke grants before dropping the table.
    op.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'config_admin_user') THEN
                REVOKE ALL ON config_version_registry FROM config_admin_user;
                REVOKE ALL ON SEQUENCE config_version_registry_id_seq FROM config_admin_user;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finalization_service_user') THEN
                REVOKE ALL ON config_version_registry FROM finalization_service_user;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_service_user') THEN
                REVOKE ALL ON config_version_registry FROM app_service_user;
            END IF;
        END;
        $$;
    """))

    # DROP TABLE cascades to all indexes, constraints, and sequences.
    op.drop_table("config_version_registry")
