"""add experiment link to candidate_strategy_proposals

Revision ID: l1m2n3o4p5q6
Revises: k1l2m3n4o5p6
Create Date: 2026-06-25 01:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "l1m2n3o4p5q6"
down_revision: str | None = "k1l2m3n4o5p6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 준비된 paper 실험(DRAFT) 연결 + 준비 시각. 둘 다 nullable(아직 준비 안 된 제안이 기본).
    op.add_column(
        "candidate_strategy_proposals",
        sa.Column("experiment_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "candidate_strategy_proposals",
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_candidate_strategy_proposals_experiment",
        "candidate_strategy_proposals",
        "experiments",
        ["experiment_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_candidate_strategy_proposals_experiment",
        "candidate_strategy_proposals",
        type_="foreignkey",
    )
    op.drop_column("candidate_strategy_proposals", "prepared_at")
    op.drop_column("candidate_strategy_proposals", "experiment_id")
