"""add market/exchange to watchlist_symbols

Revision ID: d1e2f3a4b5c6
Revises: c1d2e3f4a5b6
Create Date: 2026-06-22 16:50:00.000000

C-5.3 멀티마켓 watchlist:
- watchlist_symbols.market: 시장 구분(KR/US), 기본 'KR'. enum 없이 String(2).
- watchlist_symbols.exchange: 미국 거래소 코드(NAS/NYS/AMS), nullable.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "watchlist_symbols",
        sa.Column("market", sa.String(length=2), nullable=False, server_default="KR"),
    )
    op.add_column(
        "watchlist_symbols",
        sa.Column("exchange", sa.String(length=8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("watchlist_symbols", "exchange")
    op.drop_column("watchlist_symbols", "market")
