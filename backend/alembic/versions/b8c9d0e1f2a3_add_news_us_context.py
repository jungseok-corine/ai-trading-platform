"""add news_events and us_market_snapshots

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-19 07:00:00.000000

C-2.28 News/US Market Context Pipeline:
- news_events: 뉴스/공시 이벤트 (종목/시장 단위, 테마/감성 태깅)
- us_market_snapshots: 미국장 일별 요약 (나스닥/S&P500/SOX/금리/VIX)
market_code enum은 기존 것을 재사용한다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    market_code = PgEnum("KR", "US", name="market_code", create_type=False)

    op.create_table(
        "news_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market", market_code, nullable=False),
        sa.Column("symbol_code", sa.String(length=20), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False, server_default=sa.text("'manual'")),
        sa.Column("headline", sa.String(length=500), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("sentiment", sa.String(length=10), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("themes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_news_events_symbol_published", "news_events", ["symbol_code", "published_at"])
    op.create_index("ix_news_events_market_published", "news_events", ["market", "published_at"])

    op.create_table(
        "us_market_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("nasdaq_change_pct", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("sp500_change_pct", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("sox_change_pct", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("treasury_10y", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("vix", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("major_news", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_date", name="uq_us_market_snapshots_date"),
    )


def downgrade() -> None:
    op.drop_table("us_market_snapshots")
    op.drop_index("ix_news_events_market_published", table_name="news_events")
    op.drop_index("ix_news_events_symbol_published", table_name="news_events")
    op.drop_table("news_events")
