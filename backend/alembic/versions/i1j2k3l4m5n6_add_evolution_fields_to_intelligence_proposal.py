"""add evolution fields to intelligence_strategy_proposals (C-2.28)

Revision ID: i1j2k3l4m5n6
Revises: h1i2j3k4l5m6
Create Date: 2026-06-24
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i1j2k3l4m5n6"
down_revision: Union[str, Sequence[str], None] = "h1i2j3k4l5m6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "intelligence_strategy_proposals",
        sa.Column("evolution_analyzed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "intelligence_strategy_proposals",
        sa.Column("evolution_strategy_proposal_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "intelligence_strategy_proposals",
        sa.Column("evolution_status", sa.String(50), nullable=True),
    )
    op.add_column(
        "intelligence_strategy_proposals",
        sa.Column("evolution_reason", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_intelligence_strategy_proposals_evolution_sp",
        "intelligence_strategy_proposals",
        "strategy_proposals",
        ["evolution_strategy_proposal_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_intelligence_strategy_proposals_evolution_sp",
        "intelligence_strategy_proposals",
        type_="foreignkey",
    )
    op.drop_column("intelligence_strategy_proposals", "evolution_reason")
    op.drop_column("intelligence_strategy_proposals", "evolution_status")
    op.drop_column("intelligence_strategy_proposals", "evolution_strategy_proposal_id")
    op.drop_column("intelligence_strategy_proposals", "evolution_analyzed_at")
