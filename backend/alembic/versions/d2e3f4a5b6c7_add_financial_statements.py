"""add financial_statements table (C-2.21.1)

Revision ID: d2e3f4a5b6c7
Revises: a4b5c6d7e8f9
Create Date: 2026-06-23
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "financial_statements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("corp_code", sa.String(length=8), nullable=False),
        sa.Column("stock_code", sa.String(length=10), nullable=True),
        sa.Column("corp_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("bsns_year", sa.String(length=4), nullable=False),
        sa.Column("reprt_code", sa.String(length=5), nullable=False),
        sa.Column("fs_div", sa.String(length=3), nullable=False),
        sa.Column("key_items", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "corp_code", "bsns_year", "reprt_code", "fs_div",
            name="uq_finstat_corp_period",
        ),
    )
    op.create_index("ix_finstat_stock_year", "financial_statements", ["stock_code", "bsns_year"])


def downgrade() -> None:
    op.drop_index("ix_finstat_stock_year", table_name="financial_statements")
    op.drop_table("financial_statements")
