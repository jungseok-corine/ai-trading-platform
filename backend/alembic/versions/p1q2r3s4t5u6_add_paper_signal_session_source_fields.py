"""add source fields to paper_signal_sessions (Option A, M2.5 Phase 1)

Revision ID: p1q2r3s4t5u6
Revises: o1p2q3r4s5t6
Create Date: 2026-06-26 04:00:00.000000

Additive / constraint-relaxing only (D-20). 기존 candidate-proposal 세션은 그대로 동작한다:
- candidate_strategy_proposal_id 를 nullable 로 푼다(런너는 이 컬럼을 읽지 않으므로 선택 로직 무변경).
- source_type (기본 'candidate_proposal') — 기존 행은 server_default 로 backfill 된다.
- source_strategy_proposal_id (nullable FK → strategy_proposals, SET NULL) — challenger 추적용.
- baseline_session_id (nullable self-FK → paper_signal_sessions, SET NULL) — 비교 baseline 추적용.
- 인덱스: (source_type, status), source_strategy_proposal_id, baseline_session_id.

status 는 String 컬럼이라 'prepared' 값은 enum 마이그레이션 없이 표현된다(런너의 list_active 는
status=='active' 만 잡으므로 prepared 세션은 런너 비대상).

Downgrade: NULL candidate_strategy_proposal_id 행(=challenger 세션)이 있으면 NOT NULL 복원이
데이터를 깨므로 **중단**한다. challenger 행을 먼저 제거한 뒤 다운그레이드할 것.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p1q2r3s4t5u6"
down_revision: str | None = "o1p2q3r4s5t6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) candidate FK 를 nullable 로 (런너/outcome/비교는 이 컬럼에 무관 → 런타임 선택 무변경).
    op.alter_column(
        "paper_signal_sessions",
        "candidate_strategy_proposal_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    # 2) source_type — server_default 로 기존 행 backfill('candidate_proposal').
    op.add_column(
        "paper_signal_sessions",
        sa.Column(
            "source_type",
            sa.String(30),
            nullable=False,
            server_default="candidate_proposal",
        ),
    )
    # 3) challenger 추적 컬럼(둘 다 nullable, additive).
    op.add_column(
        "paper_signal_sessions",
        sa.Column("source_strategy_proposal_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "paper_signal_sessions",
        sa.Column("baseline_session_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_paper_signal_sessions_source_strategy_proposal",
        "paper_signal_sessions",
        "strategy_proposals",
        ["source_strategy_proposal_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_paper_signal_sessions_baseline_session",
        "paper_signal_sessions",
        "paper_signal_sessions",
        ["baseline_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # 4) 인덱스.
    op.create_index(
        "ix_paper_signal_sessions_source",
        "paper_signal_sessions",
        ["source_type", "status"],
    )
    op.create_index(
        "ix_paper_signal_sessions_source_strategy_proposal_id",
        "paper_signal_sessions",
        ["source_strategy_proposal_id"],
    )
    op.create_index(
        "ix_paper_signal_sessions_baseline_session_id",
        "paper_signal_sessions",
        ["baseline_session_id"],
    )


def downgrade() -> None:
    # 안전장치: NULL candidate_strategy_proposal_id 행(=challenger 세션)이 있으면 NOT NULL 복원이
    # 데이터를 깨므로 중단한다(조용한 손상 방지). challenger 행을 먼저 제거한 뒤 다운그레이드할 것.
    conn = op.get_bind()
    null_count = conn.execute(
        sa.text(
            "SELECT count(*) FROM paper_signal_sessions "
            "WHERE candidate_strategy_proposal_id IS NULL"
        )
    ).scalar()
    if null_count and null_count > 0:
        raise RuntimeError(
            f"cannot downgrade: {null_count} paper_signal_sessions rows have NULL "
            "candidate_strategy_proposal_id (challenger sessions). Remove them before downgrade."
        )

    op.drop_index(
        "ix_paper_signal_sessions_baseline_session_id",
        table_name="paper_signal_sessions",
    )
    op.drop_index(
        "ix_paper_signal_sessions_source_strategy_proposal_id",
        table_name="paper_signal_sessions",
    )
    op.drop_index(
        "ix_paper_signal_sessions_source", table_name="paper_signal_sessions"
    )
    op.drop_constraint(
        "fk_paper_signal_sessions_baseline_session",
        "paper_signal_sessions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_paper_signal_sessions_source_strategy_proposal",
        "paper_signal_sessions",
        type_="foreignkey",
    )
    op.drop_column("paper_signal_sessions", "baseline_session_id")
    op.drop_column("paper_signal_sessions", "source_strategy_proposal_id")
    op.drop_column("paper_signal_sessions", "source_type")
    op.alter_column(
        "paper_signal_sessions",
        "candidate_strategy_proposal_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
