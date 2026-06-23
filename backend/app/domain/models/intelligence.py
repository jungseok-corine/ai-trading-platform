"""Market Intelligence 소스·이벤트 모델 (C-2.21.1b).

어댑터 패턴의 DB 계층. IntelligenceSource는 등록된 데이터 소스를,
IntelligenceEvent는 각 소스에서 수집된 정규화된 이벤트를 저장한다.

설계 원칙:
- 소스마다 어댑터(IntelligenceAdapter)가 하나씩 대응한다.
- 어댑터는 fetch → normalize → (IntelligenceEvent 저장) 흐름을 따른다.
- source-specific 로직은 어댑터 내부에만 존재한다; 이 모델은 공통 계층이다.
- dedup_hash로 중복 이벤트를 방지한다.
"""
from __future__ import annotations

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
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.domain.models._types import pg_enum
from app.domain.models.enums import (
    IntelligenceEventStatus,
    IntelligenceMarketScope,
    IntelligenceProvider,
    IntelligenceSourceType,
    MarketCode,
)


class IntelligenceSource(Base):
    """등록된 Market Intelligence 데이터 소스.

    source_key는 어댑터가 자신을 식별하는 유일 문자열이다(예: "dart_finance", "edgar_8k").
    enabled=False인 소스의 어댑터는 실행되지 않는다.
    config JSONB에 소스별 파라미터(API 엔드포인트, 필터 등)를 저장할 수 있다.
    """

    __tablename__ = "intelligence_sources"
    __table_args__ = (
        UniqueConstraint("source_key", name="uq_intelligence_source_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_key: Mapped[str] = mapped_column(String(100), nullable=False)
    source_type: Mapped[IntelligenceSourceType] = mapped_column(
        pg_enum(IntelligenceSourceType, "intelligence_source_type"), nullable=False
    )
    provider: Mapped[IntelligenceProvider] = mapped_column(
        pg_enum(IntelligenceProvider, "intelligence_provider"), nullable=False
    )
    market_scope: Mapped[IntelligenceMarketScope] = mapped_column(
        pg_enum(IntelligenceMarketScope, "intelligence_market_scope"), nullable=False,
        default=IntelligenceMarketScope.KR,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reliability_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))  # 0.000–1.000
    config: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    events: Mapped[list[IntelligenceEvent]] = relationship(
        "IntelligenceEvent", back_populates="source", lazy="noload"
    )


class IntelligenceEvent(Base):
    """소스에서 수집·정규화된 Market Intelligence 이벤트.

    dedup_hash로 동일 이벤트의 중복 수집을 방지한다. 어댑터가 수집 시점에
    이벤트 고유성을 보장하는 hash를 생성해야 한다.
    status로 처리 파이프라인 단계를 추적한다.
    """

    __tablename__ = "intelligence_events"
    __table_args__ = (
        UniqueConstraint("dedup_hash", name="uq_intelligence_event_dedup"),
        Index("ix_intelligence_events_source_collected", "source_id", "collected_at"),
        Index("ix_intelligence_events_market_occurred", "market", "occurred_at"),
        Index("ix_intelligence_events_symbol", "symbol_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("intelligence_sources.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    market: Mapped[MarketCode | None] = mapped_column(
        pg_enum(MarketCode, "market_code"), nullable=True
    )
    symbol_code: Mapped[str | None] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(2000))
    source_ref: Mapped[str | None] = mapped_column(String(1000))  # URL 또는 외부 ID
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[IntelligenceEventStatus] = mapped_column(
        pg_enum(IntelligenceEventStatus, "intelligence_event_status"),
        nullable=False,
        default=IntelligenceEventStatus.RAW,
    )
    importance_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))  # 0.000–1.000
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    dedup_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 hex
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    source: Mapped[IntelligenceSource] = relationship(
        "IntelligenceSource", back_populates="events", lazy="noload"
    )
