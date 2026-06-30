"""Leader Trend research candidate observation record (M2.15G-2).

**연구 관찰 기록**이다. 특정 시점에 leader trend research candidate가 관찰되었다는 사실을 영구 기록한다.
**매수 신호가 아니다.** Order/Trade/SignalLog/broker/KIS/StrategyRunner/StrategyVersion/Account/Portfolio와
**어떤 FK도 갖지 않는다**(research observation record ≠ strategy execution record).

기존 `candidate_events`(C-2.24 스캐너 룰 후보)와는 **다른 테이블**(`leader_trend_candidate_events`)이다 —
이름 충돌/기존 운영 데이터 영향을 피하기 위해 분리한다.

⚠ M2.15G-2는 **model + migration only**. 저장 service/API/repository 없음 · record 생성 없음.
"""
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

# 허용 값(DB enum 대신 String + CheckConstraint — migration/downgrade 단순화).
CANDIDATE_BUCKETS = ("A", "B", "none")
WINDOW_BASES = ("last_252_trading_rows", "calendar_52_weeks", "source_reported")
VALIDATION_STATUSES = (
    "matched", "minor_diff", "explained_major_diff", "unresolved_major_diff", "not_validated",
)


class LeaderTrendCandidateEvent(Base):
    """Leader trend research candidate가 관찰된 시점을 기록하는 연구 이벤트(매수 신호 아님)."""

    __tablename__ = "leader_trend_candidate_events"
    __table_args__ = (
        UniqueConstraint(
            "symbol", "scanner_name", "scanner_version", "reference_date",
            "timeframe", "window_basis", "universe_scope",
            name="uq_ltce_symbol_scanner_reference_window_scope",
        ),
        CheckConstraint(
            "candidate_bucket in ('A','B','none')", name="ck_ltce_candidate_bucket"
        ),
        CheckConstraint(
            "window_basis in ('last_252_trading_rows','calendar_52_weeks','source_reported')",
            name="ck_ltce_window_basis",
        ),
        CheckConstraint(
            "validation_status in "
            "('matched','minor_diff','explained_major_diff','unresolved_major_diff','not_validated')",
            name="ck_ltce_validation_status",
        ),
        CheckConstraint("research_only = true", name="ck_ltce_research_only_true"),
        CheckConstraint("not_buy_signal = true", name="ck_ltce_not_buy_signal_true"),
        Index("ix_ltce_reference_date_scanner", "reference_date", "scanner_name"),
        Index("ix_ltce_symbol_reference_date", "symbol", "reference_date"),
        Index("ix_ltce_bucket_reference_date", "candidate_bucket", "reference_date"),
        Index("ix_ltce_validation_status_reference_date", "validation_status", "reference_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reference_date: Mapped[date] = mapped_column(Date, nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    universe_scope: Mapped[str] = mapped_column(String(40), nullable=False)
    scanner_name: Mapped[str] = mapped_column(String(80), nullable=False)
    scanner_version: Mapped[str] = mapped_column(String(40), nullable=False)
    candidate_bucket: Mapped[str] = mapped_column(String(20), nullable=False)
    is_operational_candidate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    strategy_extreme: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    current_price: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    low_52w: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    high_52w: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    low_52w_gain_pct: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    drawdown_from_52w_high_pct: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    window_basis: Mapped[str] = mapped_column(String(40), nullable=False)
    data_source: Mapped[str] = mapped_column(
        String(40), nullable=False, default="local_market_data", server_default="local_market_data"
    )
    validation_source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    validation_status: Mapped[str] = mapped_column(String(40), nullable=False)
    validation_report_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    research_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    not_buy_signal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # 선택 메타.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_basis_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance_warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    safety_warning: Mapped[str | None] = mapped_column(Text, nullable=True)
