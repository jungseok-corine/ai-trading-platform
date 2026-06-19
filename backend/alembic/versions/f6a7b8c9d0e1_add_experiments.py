"""add experiments, experiment_variants, experiment_results

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-19 05:00:00.000000

C-2.26 Paper Experiment Framework:
- experiment_status / variant_role enum
- experiments: 전략 버전 비교 실험
- experiment_variants: 실험에 포함된 전략 버전 (챔피언/챌린저)
- experiment_results: variant 성과 지표 스냅샷
market_code enum은 기존 것을 재사용한다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    sa.Enum(
        "draft", "running", "completed", "archived", name="experiment_status"
    ).create(op.get_bind(), checkfirst=True)
    sa.Enum("champion", "challenger", name="variant_role").create(
        op.get_bind(), checkfirst=True
    )

    market_code = PgEnum("KR", "US", name="market_code", create_type=False)
    experiment_status = PgEnum(
        "draft", "running", "completed", "archived",
        name="experiment_status", create_type=False,
    )
    variant_role = PgEnum(
        "champion", "challenger", name="variant_role", create_type=False
    )

    op.create_table(
        "experiments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market", market_code, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", experiment_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "experiment_variants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("experiment_id", sa.Integer(), nullable=False),
        sa.Column("strategy_version_id", sa.Integer(), nullable=False),
        sa.Column("role", variant_role, nullable=False),
        sa.Column("label", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["strategy_version_id"], ["strategy_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("experiment_id", "strategy_version_id", name="uq_experiment_variant"),
    )

    op.create_table(
        "experiment_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("experiment_variant_id", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("trades_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("win_rate", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("avg_profit", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("avg_loss", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("profit_factor", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("expectancy", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("max_drawdown", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["experiment_variant_id"], ["experiment_variants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_experiment_results_variant", "experiment_results", ["experiment_variant_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_experiment_results_variant", table_name="experiment_results")
    op.drop_table("experiment_results")
    op.drop_table("experiment_variants")
    op.drop_table("experiments")
    sa.Enum(name="variant_role").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="experiment_status").drop(op.get_bind(), checkfirst=True)
