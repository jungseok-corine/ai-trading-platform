"""add experiment_id and materialized_at to intelligence_strategy_proposals (C-2.27)

Revision ID: h1i2j3k4l5m6
Revises: g1h2i3j4k5l6
Create Date: 2026-06-24
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h1i2j3k4l5m6"
down_revision: Union[str, Sequence[str], None] = "g1h2i3j4k5l6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "intelligence_strategy_proposals",
        sa.Column("experiment_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "intelligence_strategy_proposals",
        sa.Column("materialized_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_intelligence_strategy_proposals_experiment",
        "intelligence_strategy_proposals",
        "experiments",
        ["experiment_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_intelligence_strategy_proposals_experiment",
        "intelligence_strategy_proposals",
        ["experiment_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_intelligence_strategy_proposals_experiment",
        table_name="intelligence_strategy_proposals",
    )
    op.drop_constraint(
        "fk_intelligence_strategy_proposals_experiment",
        "intelligence_strategy_proposals",
        type_="foreignkey",
    )
    op.drop_column("intelligence_strategy_proposals", "materialized_at")
    op.drop_column("intelligence_strategy_proposals", "experiment_id")
