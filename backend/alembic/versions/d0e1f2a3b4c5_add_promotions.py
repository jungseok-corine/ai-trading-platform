"""add promotion_criteria and promotion_evaluations

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-06-19 09:00:00.000000

C-2.30 Paper-to-Live Promotion Gate:
- promotion_criteria: 실전 승격 최소 기준
- promotion_evaluations: 전략 버전 승격 평가 결과
market_code enum은 기존 것을 재사용한다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    market_code = PgEnum("KR", "US", name="market_code", create_type=False)

    op.create_table(
        "promotion_criteria",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market", market_code, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("min_trade_count", sa.Integer(), nullable=False, server_default=sa.text("50")),
        sa.Column("min_days", sa.Integer(), nullable=False, server_default=sa.text("30")),
        sa.Column("min_expectancy", sa.Numeric(precision=18, scale=4), nullable=False, server_default=sa.text("0")),
        sa.Column("max_drawdown", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "promotion_evaluations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("strategy_version_id", sa.Integer(), nullable=False),
        sa.Column("criteria_id", sa.Integer(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("trades_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("days", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("expectancy", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("max_drawdown", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("checks", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["strategy_version_id"], ["strategy_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["criteria_id"], ["promotion_criteria.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_promotion_evaluations_version", "promotion_evaluations", ["strategy_version_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_promotion_evaluations_version", table_name="promotion_evaluations")
    op.drop_table("promotion_evaluations")
    op.drop_table("promotion_criteria")
