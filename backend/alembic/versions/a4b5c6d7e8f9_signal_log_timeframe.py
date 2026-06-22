"""add timeframe to signal_logs

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-06-23 00:10:00.000000

C-5.13 신호 결과 정합성: signal_logs.timeframe(예: '1m','5m'), 기본 '1m'.
신호 결과(forward return) 조회 시 신호가 사용한 timeframe의 market_data를 조회하도록 한다
(이전엔 '1m' 고정이라 5m 전략/미장 신호의 결과가 조회되지 않았다).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, Sequence[str], None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "signal_logs",
        sa.Column("timeframe", sa.String(length=8), nullable=False, server_default="1m"),
    )


def downgrade() -> None:
    op.drop_column("signal_logs", "timeframe")
