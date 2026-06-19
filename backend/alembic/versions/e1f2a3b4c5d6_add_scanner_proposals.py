"""add scanner_rule_proposals table

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-06-19 09:00:00.000000

C-2.39 Scanner Rule Proposals:
- scanner_rule_proposals: 후보 성과 분석 기반 스캐너 조건 강화 제안
  (승인 시 새 scanner_rule_version(DRAFT) 생성)
- proposal_status enum은 C-2.27에서 이미 생성되어 재사용한다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # proposal_status enum은 strategy_proposals(C-2.27)에서 이미 생성됨 → 재사용.
    proposal_status = PgEnum(
        "pending", "approved", "rejected", name="proposal_status", create_type=False
    )

    op.create_table(
        "scanner_rule_proposals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scanner_rule_id", sa.Integer(), nullable=False),
        sa.Column("base_version_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("expected_effect", sa.Text(), nullable=True),
        sa.Column("risk_notes", sa.Text(), nullable=True),
        sa.Column("suggested_conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False, server_default=sa.text("'ai'")),
        sa.Column("status", proposal_status, nullable=False),
        sa.Column("created_version_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=100), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["scanner_rule_id"], ["scanner_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["base_version_id"], ["scanner_rule_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_version_id"], ["scanner_rule_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scanner_rule_proposals_rule_status",
        "scanner_rule_proposals",
        ["scanner_rule_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scanner_rule_proposals_rule_status", table_name="scanner_rule_proposals"
    )
    op.drop_table("scanner_rule_proposals")
    # proposal_status enum은 strategy_proposals가 계속 사용하므로 drop하지 않는다.
