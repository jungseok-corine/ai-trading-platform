"""add_org_no_to_trades

Revision ID: d51e1c348111
Revises: b3d7e2c9a1f5
Create Date: 2026-06-17 17:42:34.395963

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd51e1c348111'
down_revision: Union[str, Sequence[str], None] = 'b3d7e2c9a1f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('trades', sa.Column('org_no', sa.String(length=10), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('trades', 'org_no')
