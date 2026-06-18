"""add signal_price to signal_logs

Revision ID: c3f8a1d9e2b4
Revises: a9f2b7c4e1d8
Create Date: 2026-06-18 00:00:00.000000

signal_price: 시그널 발생 당시의 시장 현재가 (close price of the candle used for signal generation).
기존 price 컬럼과 구분: price = 전략이 권장하는 주문 호가, signal_price = 시그널 생성 시점 시장가.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3f8a1d9e2b4"
down_revision: Union[str, Sequence[str], None] = "a9f2b7c4e1d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "signal_logs",
        sa.Column("signal_price", sa.Numeric(18, 4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("signal_logs", "signal_price")
