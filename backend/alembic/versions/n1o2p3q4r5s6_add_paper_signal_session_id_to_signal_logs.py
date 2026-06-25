"""add paper_signal_session_id to signal_logs

Revision ID: n1o2p3q4r5s6
Revises: m1n2o3p4q5r6
Create Date: 2026-06-26 02:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "n1o2p3q4r5s6"
down_revision: str | None = "m1n2o3p4q5r6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 세션별 outcome 집계용 정확 추적. nullable(일반 strategy_runner 신호는 NULL).
    op.add_column(
        "signal_logs",
        sa.Column("paper_signal_session_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_signal_logs_paper_signal_session",
        "signal_logs",
        "paper_signal_sessions",
        ["paper_signal_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_signal_logs_paper_signal_session",
        "signal_logs",
        ["paper_signal_session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_signal_logs_paper_signal_session", table_name="signal_logs")
    op.drop_constraint(
        "fk_signal_logs_paper_signal_session", "signal_logs", type_="foreignkey"
    )
    op.drop_column("signal_logs", "paper_signal_session_id")
