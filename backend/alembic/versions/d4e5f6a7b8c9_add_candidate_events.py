"""add candidate_events table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-19 03:00:00.000000

C-2.24 Candidate Event System:
- candidate_events: 스캐너 룰에 걸린 종목 기록 (matched_conditions, facts, score)
market_code enum은 기존 것을 재사용한다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    market_code = PgEnum("KR", "US", name="market_code", create_type=False)

    op.create_table(
        "candidate_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scanner_rule_version_id", sa.Integer(), nullable=False),
        sa.Column("market", market_code, nullable=False),
        sa.Column("symbol_code", sa.String(length=20), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("matched_conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("facts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("context_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["scanner_rule_version_id"], ["scanner_rule_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["context_snapshot_id"], ["market_context_snapshots.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_candidate_events_version_triggered",
        "candidate_events",
        ["scanner_rule_version_id", "triggered_at"],
    )
    op.create_index(
        "ix_candidate_events_symbol_triggered",
        "candidate_events",
        ["symbol_code", "triggered_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_candidate_events_symbol_triggered", table_name="candidate_events")
    op.drop_index("ix_candidate_events_version_triggered", table_name="candidate_events")
    op.drop_table("candidate_events")
