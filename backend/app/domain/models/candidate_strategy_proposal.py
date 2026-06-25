"""후보 종목 기반 전략 배정 제안 (Candidate Strategy Proposal).

스캐너 후보(candidate_event)에 대해 "어떤 전략 템플릿을 실험해볼지"를 사람이 검토용으로
저장하는 PENDING 제안이다. 제안일 뿐 실행과 무관하다:

- 생성 시 항상 status="pending".
- StrategyVersion / StrategyAssignmentLog / Experiment / 주문을 만들지 않는다.
- 승인(approve)해도 이 단계에서는 status만 바뀐다(실행/버전 생성/실험 연결 없음).
- auto_trade_enabled 를 절대 건드리지 않는다.

기존 제안 테이블(StrategyAssignmentLog=확정 로그, IntelligenceStrategyProposal=
intelligence_candidates 종속, StrategyProposal=strategies 종속)이 candidate_event에
맞지 않아 별도 테이블로 둔다.
"""
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CandidateStrategyProposal(Base):
    __tablename__ = "candidate_strategy_proposals"
    __table_args__ = (
        Index(
            "ix_candidate_strategy_proposals_candidate_status",
            "candidate_event_id",
            "status",
        ),
        Index("ix_candidate_strategy_proposals_symbol", "symbol_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_event_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_events.id", ondelete="CASCADE"), nullable=False
    )
    symbol_code: Mapped[str] = mapped_column(String(20), nullable=False)
    suggested_strategy_type: Mapped[str] = mapped_column(String(50), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    # 제안 파라미터. auto_trade_enabled 등 실행 토글은 포함하지 않는다.
    suggested_parameters: Mapped[dict | None] = mapped_column(JSONB)
    # pending / approved / rejected (ProposalStatus 값과 동일). 항상 pending에서 시작.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(100))
    review_note: Mapped[str | None] = mapped_column(Text)
    # APPROVED 제안에서 사람 명시 액션으로 준비된 paper 실험(DRAFT) 연결 + 시각.
    # 준비는 실행이 아니다 — Experiment/StrategyVersion 모두 DRAFT, auto_trade=False.
    # (SET NULL: 실험이 삭제돼도 제안 기록은 남긴다)
    experiment_id: Mapped[int | None] = mapped_column(
        ForeignKey("experiments.id", ondelete="SET NULL")
    )
    prepared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
