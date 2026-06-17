"""add ai_analysis_runs and ai_model_responses tables

Revision ID: f7a3c1b0d2e8
Revises: 6a4b4a0af7ea
Create Date: 2026-06-17 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

# revision identifiers, used by Alembic.
revision: str = 'f7a3c1b0d2e8'
down_revision: Union[str, Sequence[str], None] = '6a4b4a0af7ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Enum 타입을 먼저 명시적으로 생성 (checkfirst=True).
    #    create_table 내에서는 PgEnum(create_type=False)로 지정해 재생성을 방지한다.
    sa.Enum(
        'pending', 'running', 'succeeded', 'failed',
        name='analysis_run_status',
    ).create(op.get_bind(), checkfirst=True)

    sa.Enum(
        'strategy_performance',
        name='analysis_run_type',
    ).create(op.get_bind(), checkfirst=True)

    sa.Enum(
        'strategy_version',
        name='analysis_target_type',
    ).create(op.get_bind(), checkfirst=True)

    # PgEnum(create_type=False): enum이 위에서 이미 생성되었으므로 CREATE TYPE 생략
    op.create_table(
        'ai_analysis_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('analysis_type', PgEnum('strategy_performance', name='analysis_run_type', create_type=False), nullable=False),
        sa.Column('target_type', PgEnum('strategy_version', name='analysis_target_type', create_type=False), nullable=False),
        sa.Column('target_id', sa.Integer(), nullable=False),
        sa.Column('strategy_id', sa.Integer(), nullable=True),
        sa.Column('strategy_version_id', sa.Integer(), nullable=True),
        sa.Column('prompt_type', sa.String(length=50), nullable=False),
        sa.Column('provider', sa.String(length=30), nullable=False),
        sa.Column('model', sa.String(length=80), nullable=False),
        sa.Column('status', PgEnum('pending', 'running', 'succeeded', 'failed', name='analysis_run_status', create_type=False), nullable=False),
        sa.Column('input_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('prompt', sa.Text(), nullable=True),
        sa.Column('prompt_length', sa.Integer(), nullable=True),
        sa.Column('truncated', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('warnings', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['strategy_id'], ['strategies.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['strategy_version_id'], ['strategy_versions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ai_analysis_runs_strategy_version_id', 'ai_analysis_runs', ['strategy_version_id'])
    op.create_index('ix_ai_analysis_runs_status', 'ai_analysis_runs', ['status'])

    op.create_table(
        'ai_model_responses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=30), nullable=False),
        sa.Column('model', sa.String(length=80), nullable=False),
        sa.Column('role', sa.String(length=30), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True),
        sa.Column('completion_tokens', sa.Integer(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('finish_reason', sa.String(length=30), nullable=True),
        sa.Column('raw', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['ai_analysis_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ai_model_responses_run_id', 'ai_model_responses', ['run_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_ai_model_responses_run_id', table_name='ai_model_responses')
    op.drop_table('ai_model_responses')

    op.drop_index('ix_ai_analysis_runs_status', table_name='ai_analysis_runs')
    op.drop_index('ix_ai_analysis_runs_strategy_version_id', table_name='ai_analysis_runs')
    op.drop_table('ai_analysis_runs')

    sa.Enum(name='analysis_target_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='analysis_run_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='analysis_run_status').drop(op.get_bind(), checkfirst=True)
