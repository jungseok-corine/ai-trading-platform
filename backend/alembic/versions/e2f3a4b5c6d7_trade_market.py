"""add market to trades

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-06-22 18:10:00.000000

Phase 2 멀티마켓 체결: trades.market(KR/US), 기본 'KR'. enum 없이 String(2).
어떤 시장(국장/미장)의 주문인지 기록해 브로커 라우팅/회고에 사용한다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "trades",
        sa.Column("market", sa.String(length=2), nullable=False, server_default="KR"),
    )


def downgrade() -> None:
    op.drop_column("trades", "market")
