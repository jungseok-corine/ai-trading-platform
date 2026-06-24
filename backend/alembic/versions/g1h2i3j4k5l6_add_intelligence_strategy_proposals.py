"""add intelligence_strategy_proposals table (C-2.26)

Revision ID: g1h2i3j4k5l6
Revises: f1a2b3c4d5e6
Create Date: 2026-06-24
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PROPOSAL_STATUS_ENUM = "intelligence_strategy_proposal_status"


def upgrade() -> None:
    op.execute(
        f"CREATE TYPE {_PROPOSAL_STATUS_ENUM} AS ENUM ('pending', 'approved', 'rejected')"
    )

    market_code = PgEnum("KR", "US", name="market_code", create_type=False)
    status_enum = PgEnum(
        "pending", "approved", "rejected",
        name=_PROPOSAL_STATUS_ENUM,
        create_type=False,
    )

    op.create_table(
        "intelligence_strategy_proposals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("intelligence_candidate_id", sa.Integer(), nullable=False),
        sa.Column("symbol_code", sa.String(20), nullable=False),
        sa.Column("market", market_code, nullable=False),
        sa.Column("suggested_strategy_type", sa.String(50), nullable=False),
        sa.Column(
            "suggested_parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column(
            "score_components",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("source", sa.String(50), nullable=False, server_default="heuristic"),
        sa.Column("status", status_enum, nullable=False, server_default="pending"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
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
            ["intelligence_candidate_id"],
            ["intelligence_candidates.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedup_hash", name="uq_intelligence_strategy_proposal_dedup"),
    )
    op.create_index(
        "ix_intelligence_strategy_proposals_candidate_status",
        "intelligence_strategy_proposals",
        ["intelligence_candidate_id", "status"],
    )
    op.create_index(
        "ix_intelligence_strategy_proposals_symbol",
        "intelligence_strategy_proposals",
        ["symbol_code"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_intelligence_strategy_proposals_symbol",
        table_name="intelligence_strategy_proposals",
    )
    op.drop_index(
        "ix_intelligence_strategy_proposals_candidate_status",
        table_name="intelligence_strategy_proposals",
    )
    op.drop_table("intelligence_strategy_proposals")
    op.execute(f"DROP TYPE IF EXISTS {_PROPOSAL_STATUS_ENUM}")
