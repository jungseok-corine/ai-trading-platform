"""add paper_signal_recurring_runs table (M2.14A — inert pair-scoped recurring plans)

Revision ID: q1r2s3t4u5v6
Revises: p1q2r3s4t5u6
Create Date: 2026-06-27 00:00:00.000000

Additive only (D-20). 신규 테이블 `paper_signal_recurring_runs` 생성:
- pair-scoped 반복 신호 *계획*을 표현(D-24). M2.14A는 **계획만 관리**(inert):
  실행/디스패처/스케줄러 없음 · SignalLog/Trade/Order 없음.
- status 는 String 컬럼(prepared/active/stopped/completed/failed) — enum 마이그레이션 불필요.
- CheckConstraint: interval>0, max_runs>0, completed_runs>=0, baseline != challenger.
- 인덱스: status, baseline, challenger, (baseline,challenger), (status,next_run_at).

Downgrade: 테이블/인덱스/제약을 통째로 drop 한다(데이터 백필 없음).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "q1r2s3t4u5v6"
down_revision: str | None = "p1q2r3s4t5u6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paper_signal_recurring_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="prepared"
        ),
        sa.Column(
            "scope_type",
            sa.String(40),
            nullable=False,
            server_default="baseline_challenger_pair",
        ),
        sa.Column("baseline_session_id", sa.Integer(), nullable=False),
        sa.Column("challenger_session_id", sa.Integer(), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("max_runs", sa.Integer(), nullable=False),
        sa.Column("completed_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("stopped_by", sa.String(100), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["baseline_session_id"], ["paper_signal_sessions.id"],
            name="fk_psrr_baseline_session",
        ),
        sa.ForeignKeyConstraint(
            ["challenger_session_id"], ["paper_signal_sessions.id"],
            name="fk_psrr_challenger_session",
        ),
        sa.CheckConstraint("interval_seconds > 0", name="ck_psrr_interval_positive"),
        sa.CheckConstraint("max_runs > 0", name="ck_psrr_max_runs_positive"),
        sa.CheckConstraint("completed_runs >= 0", name="ck_psrr_completed_runs_nonneg"),
        sa.CheckConstraint(
            "baseline_session_id <> challenger_session_id",
            name="ck_psrr_distinct_sessions",
        ),
    )
    op.create_index("ix_psrr_status", "paper_signal_recurring_runs", ["status"])
    op.create_index(
        "ix_psrr_baseline_session_id",
        "paper_signal_recurring_runs",
        ["baseline_session_id"],
    )
    op.create_index(
        "ix_psrr_challenger_session_id",
        "paper_signal_recurring_runs",
        ["challenger_session_id"],
    )
    op.create_index(
        "ix_psrr_pair",
        "paper_signal_recurring_runs",
        ["baseline_session_id", "challenger_session_id"],
    )
    op.create_index(
        "ix_psrr_status_next_run_at",
        "paper_signal_recurring_runs",
        ["status", "next_run_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_psrr_status_next_run_at", table_name="paper_signal_recurring_runs")
    op.drop_index("ix_psrr_pair", table_name="paper_signal_recurring_runs")
    op.drop_index(
        "ix_psrr_challenger_session_id", table_name="paper_signal_recurring_runs"
    )
    op.drop_index(
        "ix_psrr_baseline_session_id", table_name="paper_signal_recurring_runs"
    )
    op.drop_index("ix_psrr_status", table_name="paper_signal_recurring_runs")
    op.drop_table("paper_signal_recurring_runs")
