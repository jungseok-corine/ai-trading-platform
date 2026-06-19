from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.domain.models._types import pg_enum
from app.domain.models.enums import MarketCode


class PromotionCriteria(Base):
    """paper → 실전 승격 기준 (C-2.30).

    전략 버전이 실전 적용 후보로 승격되기 위한 최소 조건을 정의한다.
    ※ 이 기준 통과는 '실전 적용 가능 여부 판단'일 뿐, 실거래를 자동으로 켜지 않는다.
       실전 활성화는 항상 사람의 명시적 확인 + KIS_REAL_TRADING_ENABLED + TradingGuard 해제가 필요하다.
    """

    __tablename__ = "promotion_criteria"

    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[MarketCode] = mapped_column(
        pg_enum(MarketCode, "market_code"), nullable=False, default=MarketCode.KR
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    min_trade_count: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    min_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    min_expectancy: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    max_drawdown: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PromotionEvaluation(Base):
    """전략 버전에 대한 승격 기준 평가 결과 스냅샷."""

    __tablename__ = "promotion_evaluations"
    __table_args__ = (
        Index("ix_promotion_evaluations_version", "strategy_version_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_version_id: Mapped[int] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="CASCADE"), nullable=False
    )
    criteria_id: Mapped[int | None] = mapped_column(
        ForeignKey("promotion_criteria.id", ondelete="SET NULL")
    )
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    trades_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expectancy: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    max_drawdown: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    checks: Mapped[list | None] = mapped_column(JSONB)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
