"""add market to signal_logs

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-06-22 23:30:00.000000

C-5.11 시장별 분석: signal_logs.market(KR/US), 기본 'KR'. enum 없이 String(2).
시장별 신호 집계/일일리포트/필터에 사용한다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "signal_logs",
        sa.Column("market", sa.String(length=2), nullable=False, server_default="KR"),
    )
    op.create_index("ix_signal_logs_market_generated_at", "signal_logs", ["market", "generated_at"])


def downgrade() -> None:
    op.drop_index("ix_signal_logs_market_generated_at", table_name="signal_logs")
    op.drop_column("signal_logs", "market")
