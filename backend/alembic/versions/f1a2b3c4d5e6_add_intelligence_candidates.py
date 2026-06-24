"""add intelligence_candidates table (C-2.24)

Revision ID: f1a2b3c4d5e6
Revises: e3f4a5b6c7d8
Create Date: 2026-06-24
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUS_ENUM = "intelligence_candidate_status"


def upgrade() -> None:
    op.execute(
        f"CREATE TYPE {_STATUS_ENUM} AS ENUM ('pending', 'reviewed', 'promoted', 'ignored')"
    )

    market_code = PgEnum("KR", "US", name="market_code", create_type=False)
    status_enum = PgEnum(
        "pending", "reviewed", "promoted", "ignored",
        name=_STATUS_ENUM,
        create_type=False,
    )

    op.create_table(
        "intelligence_candidates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("intelligence_event_id", sa.Integer(), nullable=True),
        sa.Column("symbol_code", sa.String(20), nullable=False),
        sa.Column("market", market_code, nullable=False),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("why_text", sa.String(2000), nullable=True),
        sa.Column("status", status_enum, nullable=False, server_default="pending"),
        sa.Column("source_type", sa.String(50), nullable=True),
        sa.Column("matched_themes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("score_components", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("dedup_hash", sa.String(64), nullable=False),
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
            ["intelligence_event_id"],
            ["intelligence_events.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedup_hash", name="uq_intelligence_candidate_dedup"),
    )
    op.create_index(
        "ix_intelligence_candidates_symbol_created",
        "intelligence_candidates",
        ["symbol_code", "created_at"],
    )
    op.create_index(
        "ix_intelligence_candidates_market_status",
        "intelligence_candidates",
        ["market", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_intelligence_candidates_market_status", table_name="intelligence_candidates")
    op.drop_index("ix_intelligence_candidates_symbol_created", table_name="intelligence_candidates")
    op.drop_table("intelligence_candidates")
    op.execute(f"DROP TYPE IF EXISTS {_STATUS_ENUM}")
