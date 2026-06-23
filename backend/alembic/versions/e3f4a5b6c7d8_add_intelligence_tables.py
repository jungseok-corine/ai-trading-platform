"""add intelligence_sources and intelligence_events tables (C-2.21.1b)

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-06-24
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# PostgreSQL ENUM 타입 이름
_SOURCE_TYPE_ENUM = "intelligence_source_type"
_PROVIDER_ENUM = "intelligence_provider"
_MARKET_SCOPE_ENUM = "intelligence_market_scope"
_EVENT_STATUS_ENUM = "intelligence_event_status"


def upgrade() -> None:
    # ENUM 타입 생성
    op.execute(
        f"CREATE TYPE {_SOURCE_TYPE_ENUM} AS ENUM "
        "('news', 'disclosure', 'financials', 'market_data', 'macro', "
        "'policy', 'tech_trend', 'theme', 'manual')"
    )
    op.execute(
        f"CREATE TYPE {_PROVIDER_ENUM} AS ENUM "
        "('dart', 'edgar', 'dartlab', 'kis', 'rss', 'manual', 'internal', 'other')"
    )
    op.execute(
        f"CREATE TYPE {_MARKET_SCOPE_ENUM} AS ENUM ('KR', 'US', 'GLOBAL', 'MIXED')"
    )
    op.execute(
        f"CREATE TYPE {_EVENT_STATUS_ENUM} AS ENUM "
        "('raw', 'normalized', 'assessed', 'ignored')"
    )

    # intelligence_sources
    op.create_table(
        "intelligence_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_key", sa.String(length=100), nullable=False),
        sa.Column(
            "source_type",
            postgresql.ENUM(name=_SOURCE_TYPE_ENUM, create_type=False),
            nullable=False,
        ),
        sa.Column(
            "provider",
            postgresql.ENUM(name=_PROVIDER_ENUM, create_type=False),
            nullable=False,
        ),
        sa.Column(
            "market_scope",
            postgresql.ENUM(name=_MARKET_SCOPE_ENUM, create_type=False),
            nullable=False,
            server_default="KR",
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("reliability_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_key", name="uq_intelligence_source_key"),
    )

    # intelligence_events
    op.create_table(
        "intelligence_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column(
            "market",
            postgresql.ENUM(name="market_code", create_type=False),
            nullable=True,
        ),
        sa.Column("symbol_code", sa.String(length=20), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.String(length=2000), nullable=True),
        sa.Column("source_ref", sa.String(length=1000), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(name=_EVENT_STATUS_ENUM, create_type=False),
            nullable=False,
            server_default="raw",
        ),
        sa.Column("importance_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("confidence_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("dedup_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["intelligence_sources.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedup_hash", name="uq_intelligence_event_dedup"),
    )
    op.create_index(
        "ix_intelligence_events_source_collected",
        "intelligence_events",
        ["source_id", "collected_at"],
    )
    op.create_index(
        "ix_intelligence_events_market_occurred",
        "intelligence_events",
        ["market", "occurred_at"],
    )
    op.create_index(
        "ix_intelligence_events_symbol",
        "intelligence_events",
        ["symbol_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_intelligence_events_symbol", table_name="intelligence_events")
    op.drop_index("ix_intelligence_events_market_occurred", table_name="intelligence_events")
    op.drop_index("ix_intelligence_events_source_collected", table_name="intelligence_events")
    op.drop_table("intelligence_events")
    op.drop_table("intelligence_sources")
    op.execute(f"DROP TYPE IF EXISTS {_EVENT_STATUS_ENUM}")
    op.execute(f"DROP TYPE IF EXISTS {_MARKET_SCOPE_ENUM}")
    op.execute(f"DROP TYPE IF EXISTS {_PROVIDER_ENUM}")
    op.execute(f"DROP TYPE IF EXISTS {_SOURCE_TYPE_ENUM}")
