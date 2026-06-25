"""add paper_signal_session values to analysis enums + target index

Revision ID: o1p2q3r4s5t6
Revises: n1o2p3q4r5s6
Create Date: 2026-06-26 03:00:00.000000

Additive only:
- analysis_target_type += 'paper_signal_session'
- analysis_run_type    += 'paper_signal_session_analysis'
- index ai_analysis_runs(target_type, target_id) for session-run listing

기존 행/컬럼/테이블은 변경하지 않는다. ALTER TYPE ADD VALUE는 트랜잭션 밖에서
실행해야 하므로 autocommit_block을 사용한다.

Downgrade: PostgreSQL은 enum 값 제거를 지원하지 않는다(ALTER TYPE ... DROP VALUE 없음).
프로젝트 관례에 따라 enum 값 추가는 downgrade에서 되돌리지 않는다(인덱스만 제거).
추가된 enum 값은 사용되지 않으면 무해하므로 남겨둔다.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "o1p2q3r4s5t6"
down_revision: str | None = "n1o2p3q4r5s6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ADD VALUE는 트랜잭션 블록 안에서 실행 불가 → autocommit_block 사용.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE analysis_target_type ADD VALUE IF NOT EXISTS 'paper_signal_session'"
        )
        op.execute(
            "ALTER TYPE analysis_run_type ADD VALUE IF NOT EXISTS 'paper_signal_session_analysis'"
        )
    op.create_index(
        "ix_ai_analysis_runs_target",
        "ai_analysis_runs",
        ["target_type", "target_id"],
    )


def downgrade() -> None:
    # enum 값은 PostgreSQL에서 안전하게 제거할 수 없으므로 남겨둔다(미사용 시 무해).
    op.drop_index("ix_ai_analysis_runs_target", table_name="ai_analysis_runs")
