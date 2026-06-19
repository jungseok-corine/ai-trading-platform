from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.domain.models._types import pg_enum
from app.domain.models.enums import MarketCode


class CandidateEvent(Base):
    """스캐너 룰에 걸린 종목 기록 (C-2.24).

    "왜 이 종목을 봤는가 / 어떤 조건 때문에 후보가 되었는가"에 답할 수 있도록,
    매칭된 조건(matched_conditions)과 당시 facts 스냅샷을 함께 저장한다.
    market_context_snapshot과 연결해 시장 맥락도 함께 기록할 수 있다.
    """

    __tablename__ = "candidate_events"
    __table_args__ = (
        Index("ix_candidate_events_version_triggered", "scanner_rule_version_id", "triggered_at"),
        Index("ix_candidate_events_symbol_triggered", "symbol_code", "triggered_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scanner_rule_version_id: Mapped[int] = mapped_column(
        ForeignKey("scanner_rule_versions.id", ondelete="CASCADE"), nullable=False
    )
    market: Mapped[MarketCode] = mapped_column(
        pg_enum(MarketCode, "market_code"), nullable=False, default=MarketCode.KR
    )
    symbol_code: Mapped[str] = mapped_column(String(20), nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 매칭된 조건 타입 목록 (예: ["volume_spike", "price_change_pct"])
    matched_conditions: Mapped[list | None] = mapped_column(JSONB)
    # 평가 당시 종목 facts 스냅샷 (왜 후보가 되었는지 추적용)
    facts: Mapped[dict | None] = mapped_column(JSONB)
    context_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("market_context_snapshots.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
