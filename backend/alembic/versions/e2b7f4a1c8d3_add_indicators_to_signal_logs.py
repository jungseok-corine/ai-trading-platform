"""add indicators to signal_logs

Revision ID: e2b7f4a1c8d3
Revises: c3f8a1d9e2b4
Create Date: 2026-06-18 00:00:00.000000

indicators: 전략이 생성한 기술적 지표 스냅샷 (JSONB, nullable).
기존 short_ma/long_ma 전용 컬럼은 유지하며, 전략별 추가 지표(volume 등)를 범용으로 저장한다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e2b7f4a1c8d3"
down_revision: Union[str, Sequence[str], None] = "c3f8a1d9e2b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "signal_logs",
        sa.Column("indicators", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("signal_logs", "indicators")
