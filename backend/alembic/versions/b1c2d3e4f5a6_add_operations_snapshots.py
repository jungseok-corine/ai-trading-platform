"""add operations_snapshots table

Revision ID: b1c2d3e4f5a6
Revises: e1f2a3b4c5d6
Create Date: 2026-06-20 20:00:00.000000

C-3.17 Operations Snapshots:
- operations_snapshots: 일자별 운영 종합 헤드라인 적재(추세용). enum 없음.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "operations_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("invariants_ok", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("pending_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("promotion_ready", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("est_cost_usd", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_pnl", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("win_rate", sa.Float(), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_date", name="uq_operations_snapshots_date"),
    )


def downgrade() -> None:
    op.drop_table("operations_snapshots")
