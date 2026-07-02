"""add backtest_runs table (C-6.1 — historical replay result record only)

Revision ID: s1t2u3v4w5x6
Revises: r1s2t3u4v5w6
Create Date: 2026-07-03 00:00:00.000000

Additive only. 신규 테이블 `backtest_runs`:
- 저장된 market_data 위에서 전략 신호를 히스토리컬 리플레이한 **시뮬레이션 결과 기록**.
- **FK 없음**: Trade/Position/SignalLog/broker/KIS/StrategyVersion/Account 미연결.
- 주문/브로커 호출 없음 — read-only 계산 결과 저장만.
- status는 String + CheckConstraint (enum 마이그레이션 불필요).

Downgrade: 테이블/인덱스 통째 drop.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "s1t2u3v4w5x6"
down_revision: str | None = "r1s2t3u4v5w6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("strategy_type", sa.String(length=50), nullable=False),
        sa.Column("parameters", JSONB(), nullable=False),
        sa.Column("symbol_code", sa.String(length=20), nullable=False),
        sa.Column("timeframe", sa.String(length=10), nullable=False),
        sa.Column("market", sa.String(length=5), nullable=False),
        sa.Column("start_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("metrics", JSONB(), nullable=True),
        sa.Column("simulated_trades", JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed')",
            name="ck_backtest_runs_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backtest_runs_created_at", "backtest_runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_backtest_runs_created_at", table_name="backtest_runs")
    op.drop_table("backtest_runs")
