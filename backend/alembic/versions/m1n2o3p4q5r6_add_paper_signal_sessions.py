"""add paper_signal_sessions

Revision ID: m1n2o3p4q5r6
Revises: l1m2n3o4p5q6
Create Date: 2026-06-26 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "m1n2o3p4q5r6"
down_revision: str | None = "l1m2n3o4p5q6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paper_signal_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_strategy_proposal_id", sa.Integer(), nullable=False),
        sa.Column("experiment_id", sa.Integer(), nullable=True),
        sa.Column("strategy_version_id", sa.Integer(), nullable=True),
        sa.Column("candidate_event_id", sa.Integer(), nullable=True),
        sa.Column("symbol_code", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("started_by", sa.String(100), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_by", sa.String(100), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("signal_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["candidate_strategy_proposal_id"],
            ["candidate_strategy_proposals.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["strategy_version_id"], ["strategy_versions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["candidate_event_id"], ["candidate_events.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_paper_signal_sessions_proposal_status",
        "paper_signal_sessions",
        ["candidate_strategy_proposal_id", "status"],
    )
    op.create_index(
        "ix_paper_signal_sessions_status", "paper_signal_sessions", ["status"]
    )


def downgrade() -> None:
    op.drop_index("ix_paper_signal_sessions_status", table_name="paper_signal_sessions")
    op.drop_index(
        "ix_paper_signal_sessions_proposal_status", table_name="paper_signal_sessions"
    )
    op.drop_table("paper_signal_sessions")
