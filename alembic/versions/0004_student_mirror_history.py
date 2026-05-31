"""Add student_mirror_history table for month-end SQL Server state capture.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-31

Purpose
-------
Enables historically accurate monthly snapshots by storing the SQL Server
mirror state captured at (or near) the end of each month.

Without this table, assemble_snapshot reads from ai_chatbot_triggerdata which
always reflects the *current* sync state. Relative fields like LastActivityDays
are computed as "days from today", so a March snapshot assembled in May shows
May-relative values, making all three months identical.

With this table:
  - POST /sync/capture-month-state stores the current ai_chatbot_triggerdata
    state into student_mirror_history for a given snapshot_month.
  - assemble_snapshot checks student_mirror_history first and adjusts relative
    fields (LastActivityDays, LastLoginDays) by the offset between captured_at
    and the last day of snapshot_month.
  - Running capture at month-end (offset=0) gives exact values.
  - Running capture after month-end gives an approximation; fields that would
    have been zero or negative (activity happened after month-end) are floored
    to zero.

Idempotency: (snapshot_month, UserID) is unique. Re-capturing overwrites the
existing row so the latest capture wins (DO UPDATE SET ...).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "student_mirror_history",

        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        # First day of the month this history entry covers.
        sa.Column("snapshot_month", sa.Date(), nullable=False),
        # Wall-clock time this row was written — used to adjust relative fields.
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        # Mirror columns — identical types to ai_chatbot_triggerdata (0001).
        sa.Column("UserID",               sa.Integer(),              nullable=False),
        sa.Column("FirstName",            sa.String(100),            nullable=True),
        sa.Column("LastName",             sa.String(100),            nullable=True),
        sa.Column("Email",                sa.String(255),            nullable=True),
        sa.Column("PhoneNumber",          sa.String(50),             nullable=True),
        sa.Column("PathName",             sa.String(100),            nullable=True),
        sa.Column("HWsBehind",            sa.Integer(),              nullable=False, server_default="0"),
        sa.Column("AvgEffRating",         sa.Float(),                nullable=False, server_default="0.0"),
        sa.Column("LastActivityDays",     sa.Integer(),              nullable=False, server_default="0"),
        sa.Column("AttendancePercentage", sa.Float(),                nullable=True),
        sa.Column("CurrentSection",       sa.String(200),            nullable=True),
        sa.Column("IPBCStartDate",        sa.DateTime(timezone=False), nullable=True),
        sa.Column("Past10DaysLogon",      sa.Integer(),              nullable=True),
        sa.Column("Total_Payments",       sa.Float(),                nullable=True),
        sa.Column("Total_Credits",        sa.Float(),                nullable=True),
        sa.Column("PaymentBalance",       sa.Float(),                nullable=True),
        sa.Column("ClassValue",           sa.Float(),                nullable=True),
        sa.Column("FeePaid",              sa.Boolean(),              nullable=True),
        sa.Column("ClassFeesPaid",        sa.Float(),                nullable=True),
        sa.Column("ClassName",            sa.String(200),            nullable=True),
        sa.Column("ClassSignupsID",       sa.String(100),            nullable=True),
        sa.Column("ActiveStatus",         sa.String(50),             nullable=True),
        sa.Column("StatusI",              sa.String(100),            nullable=True),
        sa.Column("StatusII",             sa.String(100),            nullable=True),
        sa.Column("StudentStartDate",     sa.DateTime(timezone=False), nullable=True),
        sa.Column("ClassStartDate",       sa.DateTime(timezone=False), nullable=True),
        sa.Column("LastActivitySection",  sa.String(300),            nullable=True),
        sa.Column("LastLoginDays",        sa.Integer(),              nullable=True),
        sa.Column("LastSubmitted",        sa.String(200),            nullable=True),

        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_month", "UserID", name="uq_smh_month_user"),
    )

    op.create_index("ix_smh_snapshot_month", "student_mirror_history", ["snapshot_month"])
    op.create_index("ix_smh_user_id",        "student_mirror_history", ["UserID"])


def downgrade() -> None:
    op.drop_index("ix_smh_user_id",        table_name="student_mirror_history")
    op.drop_index("ix_smh_snapshot_month", table_name="student_mirror_history")
    op.drop_table("student_mirror_history")
