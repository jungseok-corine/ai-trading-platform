"""add mode column to ai_analysis_runs

Revision ID: b3d7e2c9a1f5
Revises: a2c5f8b4e6d1
Create Date: 2026-06-17 16:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

# revision identifiers, used by Alembic.
revision: str = 'b3d7e2c9a1f5'
down_revision: Union[str, Sequence[str], None] = 'a2c5f8b4e6d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    sa.Enum('single', 'dual', name='analysis_run_mode').create(op.get_bind(), checkfirst=True)
    op.add_column(
        'ai_analysis_runs',
        sa.Column(
            'mode',
            PgEnum('single', 'dual', name='analysis_run_mode', create_type=False),
            nullable=False,
            server_default='single',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('ai_analysis_runs', 'mode')
    sa.Enum(name='analysis_run_mode').drop(op.get_bind(), checkfirst=True)
