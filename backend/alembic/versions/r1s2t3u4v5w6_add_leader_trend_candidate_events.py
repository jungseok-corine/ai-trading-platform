"""add leader_trend_candidate_events table (M2.15G-2 — research observation record only)

Revision ID: r1s2t3u4v5w6
Revises: q1r2s3t4u5v6
Create Date: 2026-06-30 00:00:00.000000

Additive only. 신규 테이블 `leader_trend_candidate_events` 생성:
- Leader trend research candidate가 관찰된 시점을 기록하는 **연구 관찰 기록**(매수 신호 아님).
- 기존 `candidate_events`(C-2.24 스캐너 룰 후보)와 **다른 테이블**(이름 충돌/운영 데이터 영향 회피).
- **FK 없음**: Order/Trade/SignalLog/broker/KIS/StrategyRunner/StrategyVersion/Account/Portfolio 미연결.
- status/bucket/window_basis 는 String + CheckConstraint(enum 마이그레이션 불필요).
- research_only=true, not_buy_signal=true 를 CheckConstraint로 강제.
- unique: (symbol, scanner_name, scanner_version, reference_date, timeframe, window_basis, universe_scope).

M2.15G-2는 **schema + model only** — record insert/seed 없음. Downgrade: 테이블/인덱스/제약 통째 drop.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "r1s2t3u4v5w6"
down_revision: str | None = "q1r2s3t4u5v6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "leader_trend_candidate_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reference_date", sa.Date(), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("universe_scope", sa.String(40), nullable=False),
        sa.Column("scanner_name", sa.String(80), nullable=False),
        sa.Column("scanner_version", sa.String(40), nullable=False),
        sa.Column("candidate_bucket", sa.String(20), nullable=False),
        sa.Column(
            "is_operational_candidate", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("strategy_extreme", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("current_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("low_52w", sa.Numeric(18, 4), nullable=False),
        sa.Column("high_52w", sa.Numeric(18, 4), nullable=False),
        sa.Column("low_52w_gain_pct", sa.Numeric(14, 4), nullable=True),
        sa.Column("drawdown_from_52w_high_pct", sa.Numeric(14, 4), nullable=True),
        sa.Column("window_basis", sa.String(40), nullable=False),
        sa.Column(
            "data_source", sa.String(40), nullable=False, server_default="local_market_data"
        ),
        sa.Column("validation_source", sa.String(40), nullable=True),
        sa.Column("validation_status", sa.String(40), nullable=False),
        sa.Column("validation_report_path", sa.String(255), nullable=True),
        sa.Column("research_only", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("not_buy_signal", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_basis_note", sa.Text(), nullable=True),
        sa.Column("provenance_warning", sa.Text(), nullable=True),
        sa.Column("safety_warning", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "symbol", "scanner_name", "scanner_version", "reference_date",
            "timeframe", "window_basis", "universe_scope",
            name="uq_ltce_symbol_scanner_reference_window_scope",
        ),
        sa.CheckConstraint(
            "candidate_bucket in ('A','B','none')", name="ck_ltce_candidate_bucket"
        ),
        sa.CheckConstraint(
            "window_basis in ('last_252_trading_rows','calendar_52_weeks','source_reported')",
            name="ck_ltce_window_basis",
        ),
        sa.CheckConstraint(
            "validation_status in "
            "('matched','minor_diff','explained_major_diff','unresolved_major_diff','not_validated')",
            name="ck_ltce_validation_status",
        ),
        sa.CheckConstraint("research_only = true", name="ck_ltce_research_only_true"),
        sa.CheckConstraint("not_buy_signal = true", name="ck_ltce_not_buy_signal_true"),
    )
    op.create_index(
        "ix_ltce_reference_date_scanner",
        "leader_trend_candidate_events", ["reference_date", "scanner_name"],
    )
    op.create_index(
        "ix_ltce_symbol_reference_date",
        "leader_trend_candidate_events", ["symbol", "reference_date"],
    )
    op.create_index(
        "ix_ltce_bucket_reference_date",
        "leader_trend_candidate_events", ["candidate_bucket", "reference_date"],
    )
    op.create_index(
        "ix_ltce_validation_status_reference_date",
        "leader_trend_candidate_events", ["validation_status", "reference_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ltce_validation_status_reference_date", table_name="leader_trend_candidate_events"
    )
    op.drop_index("ix_ltce_bucket_reference_date", table_name="leader_trend_candidate_events")
    op.drop_index("ix_ltce_symbol_reference_date", table_name="leader_trend_candidate_events")
    op.drop_index("ix_ltce_reference_date_scanner", table_name="leader_trend_candidate_events")
    op.drop_table("leader_trend_candidate_events")
