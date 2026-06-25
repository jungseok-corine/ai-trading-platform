from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.domain.models._types import pg_enum
from app.domain.models.enums import TradeAttemptStatus, TradeSide


class SignalLog(Base):
    """Strategy가 생성한 Signal의 기록. 아직 주문 실행과는 연결되지 않는다."""

    __tablename__ = "signal_logs"
    __table_args__ = (
        Index("ix_signal_logs_symbol_generated_at", "symbol_code", "generated_at"),
        UniqueConstraint(
            "strategy_version_id",
            "symbol_code",
            "signal_type",
            "candle_ts",
            name="uq_signal_logs_dedup",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol_code: Mapped[str] = mapped_column(String(20), nullable=False)
    # 시장 구분(KR/US) — 시장별 신호 집계/리포트/필터용. enum 없이 String(2).
    market: Mapped[str] = mapped_column(String(2), nullable=False, server_default="KR")
    # 신호가 사용한 분봉 단위(예: '1m','5m') — 신호 결과 조회 시 같은 timeframe의 market_data를 본다.
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False, server_default="1m")
    strategy_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="SET NULL")
    )
    # 이 신호를 만든 Paper Signal Session (있으면). 세션별 outcome 집계용 정확 추적.
    # 일반 strategy_runner 신호는 NULL. (SET NULL: 세션이 지워져도 신호 기록은 남긴다)
    paper_signal_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("paper_signal_sessions.id", ondelete="SET NULL")
    )
    signal_type: Mapped[TradeSide] = mapped_column(pg_enum(TradeSide, "signal_type"), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    candle_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)
    short_ma: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    long_ma: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    signal_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    quantity: Mapped[int | None] = mapped_column(Integer)
    indicators: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    context_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("market_context_snapshots.id", ondelete="SET NULL")
    )
    trade_id: Mapped[int | None] = mapped_column(ForeignKey("trades.id", ondelete="SET NULL"))
    trade_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trade_attempt_status: Mapped[TradeAttemptStatus] = mapped_column(
        pg_enum(TradeAttemptStatus, "trade_attempt_status"),
        nullable=False,
        default=TradeAttemptStatus.NOT_ATTEMPTED,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
