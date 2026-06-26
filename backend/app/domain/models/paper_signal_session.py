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
        Index("ix_paper_signal_sessions_source", "source_type", "status"),
        Index("ix_paper_signal_sessions_source_strategy_proposal_id", "source_strategy_proposal_id"),
        Index("ix_paper_signal_sessions_baseline_session_id", "baseline_session_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # candidate-proposal 세션은 이 FK를 채운다. signal_challenger 세션(M2.5+)은 NULL이며
    # source_strategy_proposal_id로 추적한다. 런너/outcome/비교는 이 컬럼을 읽지 않는다(D-20).
    candidate_strategy_proposal_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidate_strategy_proposals.id", ondelete="CASCADE")
    )
    # 세션 출처. 'candidate_proposal'(기존 흐름) | 'signal_challenger'(challenger 흐름).
    source_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="candidate_proposal",
        server_default="candidate_proposal",
    )
    # challenger 세션의 출처 StrategyProposal(추적용, nullable). 기존 세션은 NULL.
    source_strategy_proposal_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategy_proposals.id", ondelete="SET NULL")
    )
    # 비교 대상 baseline 세션(추적용, nullable, self-FK). 런너 동작과 무관.
    baseline_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("paper_signal_sessions.id", ondelete="SET NULL")
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
    # prepared / active / stopped. DB enum 대신 문자열 — live_promotion_records 등 안전 기록과 동일 관례.
    # 'prepared'는 비실행(런너 비대상) 상태 — list_active는 'active'만 잡는다(D-20). 시작은 사람-게이트(M2.5+).
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
