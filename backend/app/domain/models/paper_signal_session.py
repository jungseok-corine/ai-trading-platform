"""Paper Signal Session — paper 신호 기록 세션 (signal-only).

사람이 명시적으로 시작한 '신호 기록 세션'을 표현한다. 전용 signal-only 스케줄러 잡이
active 세션의 DRAFT 전략 버전으로 **SignalLog만** 생성한다.

핵심 안전 불변식:
- 연결된 StrategyVersion은 **DRAFT 그대로** 유지된다 → 기존 trade-capable runner(list_active=
  ACTIVE/TESTING)는 절대 보지 못한다.
- 세션 잡은 SignalService.generate_and_log_signal만 호출한다 — TradeService/주문 클라이언트
  미구성, 주문/체결/Trade 없음.
- 세션을 stop하면 더 이상 SignalLog가 쌓이지 않는다.
"""
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PaperSignalSession(Base):
    __tablename__ = "paper_signal_sessions"
    __table_args__ = (
        Index("ix_paper_signal_sessions_proposal_status", "candidate_strategy_proposal_id", "status"),
        Index("ix_paper_signal_sessions_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_strategy_proposal_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_strategy_proposals.id", ondelete="CASCADE"), nullable=False
    )
    # 실험/버전이 지워져도 세션 기록은 남긴다(SET NULL). 버전이 null이면 run에서 건너뛴다.
    experiment_id: Mapped[int | None] = mapped_column(
        ForeignKey("experiments.id", ondelete="SET NULL")
    )
    strategy_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="SET NULL")
    )
    candidate_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidate_events.id", ondelete="SET NULL")
    )
    symbol_code: Mapped[str] = mapped_column(String(20), nullable=False)
    # active / stopped (V1). DB enum 대신 문자열 — live_promotion_records 등 안전 기록과 동일 관례.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    started_by: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stopped_by: Mapped[str | None] = mapped_column(String(100))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
