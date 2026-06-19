from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.domain.models._types import pg_enum
from app.domain.models.enums import MarketCode


class NewsEvent(Base):
    """뉴스/공시 이벤트 (C-2.28).

    종목 단위(symbol_code 지정) 또는 시장 단위(symbol_code NULL) 뉴스를 저장한다.
    themes에 관련 테마 코드 목록을 담아 테마별 분석에 활용한다.
    """

    __tablename__ = "news_events"
    __table_args__ = (
        Index("ix_news_events_symbol_published", "symbol_code", "published_at"),
        Index("ix_news_events_market_published", "market", "published_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[MarketCode] = mapped_column(
        pg_enum(MarketCode, "market_code"), nullable=False, default=MarketCode.KR
    )
    symbol_code: Mapped[str | None] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    headline: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1000))
    sentiment: Mapped[str | None] = mapped_column(String(10))  # positive/neutral/negative
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    themes: Mapped[list | None] = mapped_column(JSONB)  # 관련 테마 코드 목록
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UsMarketSnapshot(Base):
    """미국장 일별 요약 스냅샷 (C-2.28).

    한국장 전략 분석 시 전일 미국장 흐름(나스닥/S&P500/SOX)·금리·VIX를 참고할 수 있도록
    일자별로 저장한다. session_date는 유일하다.
    """

    __tablename__ = "us_market_snapshots"
    __table_args__ = (
        UniqueConstraint("session_date", name="uq_us_market_snapshots_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    nasdaq_change_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    sp500_change_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    sox_change_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    treasury_10y: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    vix: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    major_news: Mapped[list | None] = mapped_column(JSONB)
    data: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
