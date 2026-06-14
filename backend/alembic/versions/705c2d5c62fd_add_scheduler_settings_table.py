"""add scheduler_settings table

Revision ID: 705c2d5c62fd
Revises: e91c53ebe8e4
Create Date: 2026-06-12 16:39:20.008236

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '705c2d5c62fd'
down_revision: Union[str, Sequence[str], None] = 'e91c53ebe8e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "scheduler_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("strategy_scheduler_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("order_sync_scheduler_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("scheduler_settings")
