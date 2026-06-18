"""add investor_flows table

Revision ID: f3a2b1c9d8e7
Revises: e2b7f4a1c8d3
Create Date: 2026-06-18 00:00:00.000000

C-2.18: 종목별 일별 투자자 수급 데이터 (외국인/기관/개인 순매수 수량/금액).
KIS API FHPTJ04160001 (종목별 투자자매매동향 일별) 응답을 영속화한다.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3a2b1c9d8e7"
down_revision: Union[str, Sequence[str], None] = "e2b7f4a1c8d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "investor_flows",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol_code", sa.String(20), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("foreign_net_buy_quantity", sa.BigInteger(), nullable=True),
        sa.Column("foreign_net_buy_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("institution_net_buy_quantity", sa.BigInteger(), nullable=True),
        sa.Column("institution_net_buy_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("individual_net_buy_quantity", sa.BigInteger(), nullable=True),
        sa.Column("individual_net_buy_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source", sa.String(50), nullable=False, server_default="kis"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol_code", "trade_date", "source", name="uq_investor_flows_symbol_date_source"),
    )
    op.create_index(
        "ix_investor_flows_symbol_date",
        "investor_flows",
        ["symbol_code", "trade_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_investor_flows_symbol_date", table_name="investor_flows")
    op.drop_table("investor_flows")
