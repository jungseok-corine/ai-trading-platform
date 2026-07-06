"""add symbol_trendiness to strategy_assignment_logs (C-6.22)

배정 시점의 종목 추세성 분류(trend/range/unknown)를 기록해 "왜 이 전략을 붙였는가"에
추세성 근거를 더한다. additive-only (nullable 컬럼 1개).

Revision ID: u1v2w3x4y5z6
Revises: t1u2v3w4x5y6
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "u1v2w3x4y5z6"
down_revision: str | None = "t1u2v3w4x5y6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "strategy_assignment_logs",
        sa.Column("symbol_trendiness", sa.String(length=8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("strategy_assignment_logs", "symbol_trendiness")
