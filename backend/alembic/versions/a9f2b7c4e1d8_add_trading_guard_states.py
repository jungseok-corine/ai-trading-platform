"""add_trading_guard_states

Revision ID: a9f2b7c4e1d8
Revises: d51e1c348111
Create Date: 2026-06-18 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a9f2b7c4e1d8'
down_revision: Union[str, Sequence[str], None] = 'd51e1c348111'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'trading_guard_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('is_paused', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('pause_reason', sa.Text(), nullable=True),
        sa.Column('pause_source', sa.Enum(
            'reconciliation', 'order_sync', 'manual', 'risk_limit',
            name='pause_source',
        ), nullable=True),
        sa.Column('paused_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('paused_by', sa.String(length=20), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by', sa.String(length=100), nullable=True),
        sa.Column('resolution_note', sa.Text(), nullable=True),
        sa.Column('related_risk_event_id', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['related_risk_event_id'], ['risk_events.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id'),
    )


def downgrade() -> None:
    op.drop_table('trading_guard_states')
    op.execute("DROP TYPE IF EXISTS pause_source")
