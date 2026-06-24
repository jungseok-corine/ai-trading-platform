"""Intelligence 후보 기반 전략 배정 제안 모델 (C-2.26).

IntelligenceCandidate에 어울리는 strategy_type과 파라미터를 heuristic으로 제안한다.
사람이 승인하기 전까지 실행 대상이 아니며, 승인 후에도 실전/자동매매와 연결되지 않는다.

- 승인 시: status → APPROVED, IntelligenceCandidate.status → PROMOTED
- 거절 시: status → REJECTED (StrategyVersion/StrategyAssignmentLog 미생성)
- StrategyVersion 자동 생성 금지
- StrategyAssignmentLog 자동 생성 금지
- auto_trade_enabled = True 금지
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.domain.models._types import pg_enum
from app.domain.models.enums import IntelligenceStrategyProposalStatus, MarketCode


class IntelligenceStrategyProposal(Base):
    """IntelligenceCandidate → 전략 배정 제안.

    heuristic 매칭으로 생성되며 항상 PENDING에서 시작한다.
    사람이 approve/reject 할 때까지 실행과 무관하다.
    """

    __tablename__ = "intelligence_strategy_proposals"
    __table_args__ = (
        UniqueConstraint("dedup_hash", name="uq_intelligence_strategy_proposal_dedup"),
        Index(
            "ix_intelligence_strategy_proposals_candidate_status",
            "intelligence_candidate_id",
            "status",
        ),
        Index("ix_intelligence_strategy_proposals_symbol", "symbol_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    intelligence_candidate_id: Mapped[int] = mapped_column(
        ForeignKey("intelligence_candidates.id", ondelete="CASCADE"), nullable=False
    )
    symbol_code: Mapped[str] = mapped_column(String(20), nullable=False)
    market: Mapped[MarketCode] = mapped_column(
        pg_enum(MarketCode, "market_code"), nullable=False, default=MarketCode.KR
    )
    suggested_strategy_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # auto_trade_enabled는 포함 시 항상 False. 포함하지 않는 것을 권장.
    suggested_parameters: Mapped[dict | None] = mapped_column(JSONB)
    rationale: Mapped[str | None] = mapped_column(Text)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    # heuristic 매칭 근거 (어떤 신호가 어떤 가중치로 결정에 기여했는지)
    score_components: Mapped[dict | None] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="heuristic")
    status: Mapped[IntelligenceStrategyProposalStatus] = mapped_column(
        pg_enum(IntelligenceStrategyProposalStatus, "intelligence_strategy_proposal_status"),
        nullable=False,
        default=IntelligenceStrategyProposalStatus.PENDING,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    dedup_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # materialize 시 연결된 Experiment (SET NULL: 실험이 삭제되어도 제안 기록은 남긴다)
    experiment_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True
    )
    materialized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # AI Evolution 분석 추적 (C-2.28)
    evolution_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evolution_strategy_proposal_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("strategy_proposals.id", ondelete="SET NULL"), nullable=True
    )
    # not_analyzed / analyzed_no_proposal / proposal_created / failed
    evolution_status: Mapped[str | None] = mapped_column(String(50))
    evolution_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
