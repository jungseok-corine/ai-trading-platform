"""add market context, themes, and context_snapshot links

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-19 01:00:00.000000

C-2.22 Market/Theme Context Foundation:
- market_code enum (KR/US) — 멀티마켓 확장 대비
- market_context_snapshots: 시장/수급/시간대/뉴스 맥락 스냅샷
- themes, symbol_theme_memberships: 테마/섹터 정의 및 종목 매핑
- signal_logs.context_snapshot_id, trades.context_snapshot_id: 맥락 연결
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. market_code enum 생성 (checkfirst=True). 이후 컬럼은 create_type=False로 참조.
    sa.Enum("KR", "US", name="market_code").create(op.get_bind(), checkfirst=True)
    market_code = PgEnum("KR", "US", name="market_code", create_type=False)

    # 2. market_context_snapshots
    op.create_table(
        "market_context_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market", market_code, nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("time_bucket", sa.String(length=20), nullable=True),
        sa.Column("index_trend", sa.String(length=10), nullable=True),
        sa.Column("foreign_flow", sa.String(length=10), nullable=True),
        sa.Column("institution_flow", sa.String(length=10), nullable=True),
        sa.Column("individual_flow", sa.String(length=10), nullable=True),
        sa.Column("news_sentiment", sa.String(length=10), nullable=True),
        sa.Column("indices", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("us_previous_session", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fx", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_market_context_snapshots_market_captured",
        "market_context_snapshots",
        ["market", "captured_at"],
    )

    # 3. themes
    op.create_table(
        "themes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market", market_code, nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market", "code", name="uq_themes_market_code"),
    )

    # 4. symbol_theme_memberships
    op.create_table(
        "symbol_theme_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market", market_code, nullable=False),
        sa.Column("symbol_code", sa.String(length=20), nullable=False),
        sa.Column("theme_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["theme_id"], ["themes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol_code", "theme_id", name="uq_symbol_theme"),
    )
    op.create_index("ix_symbol_theme_symbol", "symbol_theme_memberships", ["symbol_code"])

    # 5. context_snapshot_id 링크 컬럼 (signal_logs, trades)
    op.add_column(
        "signal_logs",
        sa.Column("context_snapshot_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_signal_logs_context_snapshot",
        "signal_logs",
        "market_context_snapshots",
        ["context_snapshot_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "trades",
        sa.Column("context_snapshot_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_trades_context_snapshot",
        "trades",
        "market_context_snapshots",
        ["context_snapshot_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_trades_context_snapshot", "trades", type_="foreignkey")
    op.drop_column("trades", "context_snapshot_id")
    op.drop_constraint("fk_signal_logs_context_snapshot", "signal_logs", type_="foreignkey")
    op.drop_column("signal_logs", "context_snapshot_id")

    op.drop_index("ix_symbol_theme_symbol", table_name="symbol_theme_memberships")
    op.drop_table("symbol_theme_memberships")
    op.drop_table("themes")
    op.drop_index(
        "ix_market_context_snapshots_market_captured",
        table_name="market_context_snapshots",
    )
    op.drop_table("market_context_snapshots")

    sa.Enum(name="market_code").drop(op.get_bind(), checkfirst=True)
