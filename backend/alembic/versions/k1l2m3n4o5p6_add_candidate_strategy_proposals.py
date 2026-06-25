"""add candidate_strategy_proposals

Revision ID: k1l2m3n4o5p6
Revises: j1k2l3m4n5o6
Create Date: 2026-06-25 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k1l2m3n4o5p6"
down_revision: str | None = "j1k2l3m4n5o6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "candidate_strategy_proposals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_event_id", sa.Integer(), nullable=False),
        sa.Column("symbol_code", sa.String(20), nullable=False),
        sa.Column("suggested_strategy_type", sa.String(50), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("suggested_parameters", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("source", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(100), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["candidate_event_id"],
            ["candidate_events.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_candidate_strategy_proposals_candidate_status",
        "candidate_strategy_proposals",
        ["candidate_event_id", "status"],
    )
    op.create_index(
        "ix_candidate_strategy_proposals_symbol",
        "candidate_strategy_proposals",
        ["symbol_code"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_candidate_strategy_proposals_symbol",
        table_name="candidate_strategy_proposals",
    )
    op.drop_index(
        "ix_candidate_strategy_proposals_candidate_status",
        table_name="candidate_strategy_proposals",
    )
    op.drop_table("candidate_strategy_proposals")
