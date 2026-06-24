"""IntelligenceEvent 기반 관심 후보 모델 (C-2.24).

CandidateEvent(스캐너 룰 기반)와 분리된 별도 개념.
  - CandidateEvent  = 스캐너 조건을 통과한 후보 (scanner_rule_version_id NOT NULL)
  - IntelligenceCandidate = 뉴스/공시/시장 이벤트 기반 관심 후보 (스캐너 무관)

실전 매매·전략 배정과 직접 연결하지 않는다.
C-2.26 이후 단계에서 IntelligenceCandidate가 StrategyAssignment 흐름으로 승격 가능.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.domain.models._types import pg_enum
from app.domain.models.enums import IntelligenceCandidateStatus, MarketCode


class IntelligenceCandidate(Base):
    __tablename__ = "intelligence_candidates"
    __table_args__ = (
        UniqueConstraint("dedup_hash", name="uq_intelligence_candidate_dedup"),
        Index("ix_intelligence_candidates_symbol_created", "symbol_code", "created_at"),
        Index("ix_intelligence_candidates_market_status", "market", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # SET NULL on delete: 이벤트가 삭제되어도 후보 기록은 남긴다
    intelligence_event_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("intelligence_events.id", ondelete="SET NULL"), nullable=True
    )
    symbol_code: Mapped[str] = mapped_column(String(20), nullable=False)
    market: Mapped[MarketCode] = mapped_column(
        pg_enum(MarketCode, "market_code"), nullable=False, default=MarketCode.KR
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    why_text: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[IntelligenceCandidateStatus] = mapped_column(
        pg_enum(IntelligenceCandidateStatus, "intelligence_candidate_status"),
        nullable=False,
        default=IntelligenceCandidateStatus.PENDING,
    )
    source_type: Mapped[str | None] = mapped_column(String(50))
    # 매칭된 활성 테마 코드 목록 (예: ["semiconductor", "ai"])
    matched_themes: Mapped[list | None] = mapped_column(JSONB)
    # 점수 계산 근거 (예: {"base_importance": 70, "theme_bonus": 10, ...})
    score_components: Mapped[dict | None] = mapped_column(JSONB)
    dedup_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
