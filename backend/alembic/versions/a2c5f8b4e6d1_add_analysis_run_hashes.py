"""add input_hash and prompt_hash to ai_analysis_runs

Revision ID: a2c5f8b4e6d1
Revises: f7a3c1b0d2e8
Create Date: 2026-06-17 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a2c5f8b4e6d1'
down_revision: Union[str, Sequence[str], None] = 'f7a3c1b0d2e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # input_hash: SHA256(canonical_json(input_payload) + "|" + prompt_type + "|" + provider + "|" + model)
    # prompt_hash: SHA256(prompt_text)
    # 기존 run row는 NULL 허용 (backward compatible)
    op.add_column('ai_analysis_runs', sa.Column('input_hash', sa.String(length=64), nullable=True))
    op.add_column('ai_analysis_runs', sa.Column('prompt_hash', sa.String(length=64), nullable=True))
    op.create_index('ix_ai_analysis_runs_input_hash', 'ai_analysis_runs', ['input_hash'])
    op.create_index('ix_ai_analysis_runs_prompt_hash', 'ai_analysis_runs', ['prompt_hash'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_ai_analysis_runs_prompt_hash', table_name='ai_analysis_runs')
    op.drop_index('ix_ai_analysis_runs_input_hash', table_name='ai_analysis_runs')
    op.drop_column('ai_analysis_runs', 'prompt_hash')
    op.drop_column('ai_analysis_runs', 'input_hash')
