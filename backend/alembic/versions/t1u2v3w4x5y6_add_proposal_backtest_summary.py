"""add backtest_summary to strategy_proposals (C-6.1b)

Revision ID: t1u2v3w4x5y6
Revises: s1t2u3v4w5x6
Create Date: 2026-07-03 00:00:00.000000

Additive only. strategy_proposals에 nullable JSONB 컬럼 `backtest_summary` 추가 —
제안 생성 시 base vs proposed 파라미터 백테스트 비교 결과를 저장한다(검토 참고용).
기존 행은 NULL 유지. Downgrade: 컬럼 drop.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "t1u2v3w4x5y6"
down_revision: str | None = "s1t2u3v4w5x6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("strategy_proposals", sa.Column("backtest_summary", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("strategy_proposals", "backtest_summary")
