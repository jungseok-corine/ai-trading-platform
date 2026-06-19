from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.domain.models._types import pg_enum
from app.domain.models.enums import MarketCode


class StrategyAssignmentRule(Base):
    """후보 종목에 어떤 전략을 붙일지 결정하는 규칙 (C-2.25).

    scanner_rule에 걸려 발견된 후보(candidate_event)에 대해, 어떤 strategy_type을
    배정할지 정의한다. scanner_rule_id가 지정되면 해당 스캐너 후보에만 적용되고,
    NULL이면 (해당 market의) 모든 후보에 적용 가능한 fallback 규칙이 된다.
    여러 규칙이 매칭되면 priority가 높은 규칙이 선택된다.
    """

    __tablename__ = "strategy_assignment_rules"
    __table_args__ = (
        Index("ix_strategy_assignment_rules_scanner", "scanner_rule_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[MarketCode] = mapped_column(
        pg_enum(MarketCode, "market_code"), nullable=False, default=MarketCode.KR
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    scanner_rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("scanner_rules.id", ondelete="CASCADE")
    )
    strategy_type: Mapped[str] = mapped_column(String(50), nullable=False)
    default_parameters: Mapped[dict | None] = mapped_column(JSONB)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StrategyAssignmentLog(Base):
    """후보 종목에 전략이 배정된 기록 (C-2.25).

    "왜 이 전략을 붙였는가"에 답할 수 있도록, 어떤 후보(candidate_event)에 어떤 규칙으로
    어떤 strategy_type과 파라미터가 배정되었는지 기록한다. 이 단계에서는 strategy_version을
    실제로 생성하지 않고, 배정 결정만 로그로 남긴다.
    """

    __tablename__ = "strategy_assignment_logs"
    __table_args__ = (
        Index("ix_strategy_assignment_logs_candidate", "candidate_event_id"),
        Index("ix_strategy_assignment_logs_symbol", "symbol_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_event_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_events.id", ondelete="CASCADE"), nullable=False
    )
    strategy_assignment_rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategy_assignment_rules.id", ondelete="SET NULL")
    )
    market: Mapped[MarketCode] = mapped_column(
        pg_enum(MarketCode, "market_code"), nullable=False, default=MarketCode.KR
    )
    symbol_code: Mapped[str] = mapped_column(String(20), nullable=False)
    strategy_type: Mapped[str] = mapped_column(String(50), nullable=False)
    assigned_parameters: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
