"""add strategy_proposals table

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-19 06:00:00.000000

C-2.27 AI Proposal System:
- proposal_status enum (pending/approved/rejected)
- strategy_proposals: AI/수동 전략 개선 제안 (승인 시 새 DRAFT 버전 생성)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    sa.Enum("pending", "approved", "rejected", name="proposal_status").create(
        op.get_bind(), checkfirst=True
    )
    proposal_status = PgEnum(
        "pending", "approved", "rejected", name="proposal_status", create_type=False
    )

    op.create_table(
        "strategy_proposals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("strategy_id", sa.Integer(), nullable=False),
        sa.Column("base_version_id", sa.Integer(), nullable=True),
        sa.Column("ai_analysis_run_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("expected_effect", sa.Text(), nullable=True),
        sa.Column("risk_notes", sa.Text(), nullable=True),
        sa.Column("suggested_parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False, server_default=sa.text("'ai'")),
        sa.Column("status", proposal_status, nullable=False),
        sa.Column("created_version_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=100), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["base_version_id"], ["strategy_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_version_id"], ["strategy_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["ai_analysis_run_id"], ["ai_analysis_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_strategy_proposals_strategy_status",
        "strategy_proposals",
        ["strategy_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_strategy_proposals_strategy_status", table_name="strategy_proposals")
    op.drop_table("strategy_proposals")
    sa.Enum(name="proposal_status").drop(op.get_bind(), checkfirst=True)
