"""add strategy_assignment_rules and strategy_assignment_logs

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-19 04:00:00.000000

C-2.25 Strategy Assignment Rules:
- strategy_assignment_rules: 후보 종목에 어떤 전략을 붙일지 정의
- strategy_assignment_logs: 후보별 전략 배정 기록
market_code enum은 기존 것을 재사용한다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    market_code = PgEnum("KR", "US", name="market_code", create_type=False)

    op.create_table(
        "strategy_assignment_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market", market_code, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scanner_rule_id", sa.Integer(), nullable=True),
        sa.Column("strategy_type", sa.String(length=50), nullable=False),
        sa.Column("default_parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["scanner_rule_id"], ["scanner_rules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_strategy_assignment_rules_scanner",
        "strategy_assignment_rules",
        ["scanner_rule_id"],
    )

    op.create_table(
        "strategy_assignment_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_event_id", sa.Integer(), nullable=False),
        sa.Column("strategy_assignment_rule_id", sa.Integer(), nullable=True),
        sa.Column("market", market_code, nullable=False),
        sa.Column("symbol_code", sa.String(length=20), nullable=False),
        sa.Column("strategy_type", sa.String(length=50), nullable=False),
        sa.Column("assigned_parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["candidate_event_id"], ["candidate_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["strategy_assignment_rule_id"], ["strategy_assignment_rules.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_strategy_assignment_logs_candidate",
        "strategy_assignment_logs",
        ["candidate_event_id"],
    )
    op.create_index(
        "ix_strategy_assignment_logs_symbol",
        "strategy_assignment_logs",
        ["symbol_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_strategy_assignment_logs_symbol", table_name="strategy_assignment_logs")
    op.drop_index("ix_strategy_assignment_logs_candidate", table_name="strategy_assignment_logs")
    op.drop_table("strategy_assignment_logs")
    op.drop_index("ix_strategy_assignment_rules_scanner", table_name="strategy_assignment_rules")
    op.drop_table("strategy_assignment_rules")
