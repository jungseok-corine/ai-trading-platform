"""add archived to strategy_version_status enum

Revision ID: a1b2c3d4e5f6
Revises: f3a2b1c9d8e7
Create Date: 2026-06-19 00:00:00.000000

C-2.21: strategy_version 아카이브 정책 도입.
status enum에 'archived' 값을 추가한다. archived는 "수명종료(retired)"와 구분되는
"목록에서 숨겨진 보관 상태"로, TESTING/ACTIVE 또는 참조 데이터가 있어 hard delete가
불가능한 버전을 안전하게 정리하기 위해 사용한다.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f3a2b1c9d8e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL 12+ 에서는 트랜잭션 안에서 enum 값 추가가 가능하다(같은 트랜잭션에서
    # 사용만 불가). 마이그레이션은 값 추가만 하므로 안전하다.
    op.execute("ALTER TYPE strategy_version_status ADD VALUE IF NOT EXISTS 'archived'")


def downgrade() -> None:
    # PostgreSQL은 enum 값 제거를 직접 지원하지 않는다(타입 재생성 필요).
    # 'archived' 값을 그대로 두는 것은 안전하므로 downgrade는 no-op으로 둔다.
    pass
