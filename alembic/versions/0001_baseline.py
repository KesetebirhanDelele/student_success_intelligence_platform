"""Baseline migration — full SSIP schema as-at Phase 5 (with warehouse-prep indexes).

Revision ID: 0001
Revises: (none — initial migration)
Create Date: 2026-05-24

IMPORTANT — choosing the right upgrade path
--------------------------------------------
New installation (empty database):
    alembic upgrade head          # creates all tables and indexes from scratch

Existing installation (tables already exist from init_db startup):
    alembic stamp head            # registers this revision as applied WITHOUT
                                  # running any DDL — safe, idempotent

All future schema changes MUST be tracked as new Alembic revisions.
Do NOT add new columns to the _NEW_TRIGGER_COLS list in database.py for any
change made after this migration was introduced.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── ai_chatbot_triggerdata (source mirror from SQL Server) ─────────────────
    op.create_table(
        "ai_chatbot_triggerdata",
        sa.Column("UserID", sa.Integer(), nullable=False),
        sa.Column("FirstName", sa.String(100), nullable=True),
        sa.Column("LastName", sa.String(100), nullable=True),
        sa.Column("Email", sa.String(255), nullable=True),
        sa.Column("PhoneNumber", sa.String(50), nullable=True),
        sa.Column("PathName", sa.String(100), nullable=True),
        sa.Column("HWsBehind", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("AvgEffRating", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("LastActivityDays", sa.Integer(), nullable=False, server_default="0"),
        # Phase 4
        sa.Column("AttendancePercentage", sa.Float(), nullable=True),
        sa.Column("CurrentSection", sa.String(200), nullable=True),
        sa.Column("IPBCStartDate", sa.DateTime(timezone=False), nullable=True),
        sa.Column("Past10DaysLogon", sa.Integer(), nullable=True),
        sa.Column("Total_Payments", sa.Float(), nullable=True),
        sa.Column("Total_Credits", sa.Float(), nullable=True),
        sa.Column("PaymentBalance", sa.Float(), nullable=True),
        sa.Column("ClassValue", sa.Float(), nullable=True),
        sa.Column("FeePaid", sa.Boolean(), nullable=True),
        sa.Column("ClassFeesPaid", sa.Float(), nullable=True),
        # Phase 5
        sa.Column("ClassName", sa.String(200), nullable=True),
        sa.Column("ClassSignupsID", sa.String(100), nullable=True),
        sa.Column("ActiveStatus", sa.String(50), nullable=True),
        sa.Column("StatusI", sa.String(100), nullable=True),
        sa.Column("StatusII", sa.String(100), nullable=True),
        sa.Column("StudentStartDate", sa.DateTime(timezone=False), nullable=True),
        sa.Column("ClassStartDate", sa.DateTime(timezone=False), nullable=True),
        sa.Column("LastActivitySection", sa.String(300), nullable=True),
        sa.Column("LastLoginDays", sa.Integer(), nullable=True),
        sa.Column("LastSubmitted", sa.String(200), nullable=True),
        sa.PrimaryKeyConstraint("UserID"),
    )

    # ── student_interview_prep ─────────────────────────────────────────────────
    op.create_table(
        "student_interview_prep",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id"),
    )

    # ── student_outreach_tracking ──────────────────────────────────────────────
    op.create_table(
        "student_outreach_tracking",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("checkpoint_type", sa.String(50), nullable=False),
        sa.Column("state", sa.String(50), nullable=False, server_default="ELIGIBLE"),
        sa.Column("current_attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_contact_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "checkpoint_type", name="uq_student_checkpoint"),
    )
    op.create_index("ix_sot_state",      "student_outreach_tracking", ["state"])
    op.create_index("ix_sot_user_id",    "student_outreach_tracking", ["user_id"])
    op.create_index("ix_sot_updated_at", "student_outreach_tracking", ["updated_at"])

    # ── outreach_history ───────────────────────────────────────────────────────
    op.create_table(
        "outreach_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tracking_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("checkpoint_type", sa.String(50), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(20), nullable=True),
        sa.Column("action", sa.String(50), nullable=True),
        sa.Column("execution_mode", sa.String(10), nullable=False, server_default="SHADOW"),
        sa.Column("simulated_status", sa.String(20), nullable=False, server_default="NOT_SENT"),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("response_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("llm_analysis", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("decision", sa.String(50), nullable=True),
        sa.Column("state_before", sa.String(50), nullable=True),
        sa.Column("state_after", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tracking_id"],
            ["student_outreach_tracking.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_oh_user_id",    "outreach_history", ["user_id"])
    op.create_index("ix_oh_tracking_id","outreach_history", ["tracking_id"])
    op.create_index("ix_oh_created_at", "outreach_history", ["created_at"])
    op.create_index("ix_oh_checkpoint", "outreach_history", ["checkpoint_type"])

    # ── state_transition_log ───────────────────────────────────────────────────
    op.create_table(
        "state_transition_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tracking_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("from_state", sa.String(50), nullable=False),
        sa.Column("to_state", sa.String(50), nullable=False),
        sa.Column("trigger", sa.String(100), nullable=True),
        sa.Column("actor", sa.String(50), nullable=False, server_default="system"),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tracking_id"],
            ["student_outreach_tracking.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stl_tracking_id", "state_transition_log", ["tracking_id"])
    op.create_index("ix_stl_user_id",     "state_transition_log", ["user_id"])
    op.create_index("ix_stl_created_at",  "state_transition_log", ["created_at"])

    # ── processed_events (webhook idempotency store) ───────────────────────────
    op.create_table(
        "processed_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_hash", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_hash"),
    )

    # ── student_notes ──────────────────────────────────────────────────────────
    op.create_table(
        "student_notes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("author", sa.String(100), nullable=False, server_default="system"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_ai_generated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("note_type", sa.String(50), nullable=True),
        sa.Column("visibility", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_snotes_user_id", "student_notes", ["user_id"])

    # ── ai_insights ────────────────────────────────────────────────────────────
    op.create_table(
        "ai_insights",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("insight_type", sa.String(50), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("content_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_user_id", "ai_insights", ["user_id"])
    op.create_index("ix_ai_type",    "ai_insights", ["insight_type"])

    # ── ghl_messages ───────────────────────────────────────────────────────────
    op.create_table(
        "ghl_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ghl_message_id", sa.String(100), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("direction", sa.String(20), nullable=False, server_default="INBOUND"),
        sa.Column("channel", sa.String(30), nullable=False, server_default="UNKNOWN"),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("ghl_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ghl_message_id"),
    )
    op.create_index("ix_ghl_user_id",  "ghl_messages", ["user_id"])
    op.create_index("ix_ghl_synced_at","ghl_messages", ["synced_at"])

    # ── student_campaign_activity ──────────────────────────────────────────────
    op.create_table(
        "student_campaign_activity",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("student_user_id", sa.Integer(), nullable=False),
        sa.Column("activity_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activity_type", sa.String(100), nullable=True),
        sa.Column("activity_label", sa.String(200), nullable=True),
        sa.Column("channel", sa.String(50), nullable=True),
        sa.Column("subject", sa.String(300), nullable=True),
        sa.Column("message_body", sa.Text(), nullable=True),
        sa.Column("source", sa.String(100), nullable=False, server_default="operator"),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("execution_mode", sa.String(20), nullable=False, server_default="SHADOW"),
        sa.Column("shadow_only", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sca_student_user_id", "student_campaign_activity", ["student_user_id"])
    op.create_index("ix_sca_created_at",      "student_campaign_activity", ["created_at"])

    # ── student_quick_action_log ───────────────────────────────────────────────
    op.create_table(
        "student_quick_action_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("student_user_id", sa.Integer(), nullable=False),
        sa.Column("action_key", sa.String(100), nullable=False),
        sa.Column("action_label", sa.String(200), nullable=True),
        sa.Column("tab_name", sa.String(50), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="LOGGED"),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("execution_mode", sa.String(20), nullable=False, server_default="SHADOW"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sqal_student_user_id", "student_quick_action_log", ["student_user_id"])


def downgrade() -> None:
    # Drop in reverse dependency order (FK-dependents first)
    op.drop_table("student_quick_action_log")
    op.drop_table("student_campaign_activity")
    op.drop_table("ghl_messages")
    op.drop_table("ai_insights")
    op.drop_table("student_notes")
    op.drop_table("processed_events")
    op.drop_table("state_transition_log")
    op.drop_table("outreach_history")
    op.drop_table("student_outreach_tracking")
    op.drop_table("student_interview_prep")
    op.drop_table("ai_chatbot_triggerdata")
