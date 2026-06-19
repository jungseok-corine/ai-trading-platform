"""add scanner_rules and scanner_rule_versions tables

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-19 02:00:00.000000

C-2.23 Scanner Rule Foundation:
- scanner_rule_status enum (draft/testing/active/archived)
- scanner_rules: 시장 감시 룰의 원형 (market-aware)
- scanner_rule_versions: 감시 조건(JSONB) 버전
market_code enum은 C-2.22(b2c3d4e5f6a7)에서 이미 생성되어 있어 재사용한다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    sa.Enum(
        "draft", "testing", "active", "archived", name="scanner_rule_status"
    ).create(op.get_bind(), checkfirst=True)

    # market_code는 C-2.22에서 이미 생성됨 → create_type=False로 참조
    market_code = PgEnum("KR", "US", name="market_code", create_type=False)
    scanner_status = PgEnum(
        "draft", "testing", "active", "archived",
        name="scanner_rule_status", create_type=False,
    )

    op.create_table(
        "scanner_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market", market_code, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "scanner_rule_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scanner_rule_id", sa.Integer(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", scanner_status, nullable=False),
        sa.Column("change_description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["scanner_rule_id"], ["scanner_rules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scanner_rule_id", "version_no", name="uq_scanner_rule_version"),
    )


def downgrade() -> None:
    op.drop_table("scanner_rule_versions")
    op.drop_table("scanner_rules")
    sa.Enum(name="scanner_rule_status").drop(op.get_bind(), checkfirst=True)
