from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.domain.models._types import pg_enum
from app.domain.models.enums import MarketCode


class MarketContextSnapshot(Base):
    """특정 시점의 시장/테마/수급/시간대 맥락 스냅샷 (C-2.22).

    signal/trade가 발생한 당시의 시장 상황을 함께 기록해, 전략 성과를
    시장/시간대/수급/뉴스 맥락별로 분석할 수 있게 한다. market 필드를 처음부터
    포함해 한국장/미국장 멀티마켓 확장에 대비한다.

    시장별로 의미가 다른 세부 데이터(지수 변화율, 미국 전일장, 환율 등)는
    JSONB 컬럼에 유연하게 저장한다.
    """

    __tablename__ = "market_context_snapshots"
    __table_args__ = (
        Index("ix_market_context_snapshots_market_captured", "market", "captured_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[MarketCode] = mapped_column(
        pg_enum(MarketCode, "market_code"), nullable=False, default=MarketCode.KR
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # premarket / morning / midday / afternoon / after_hours
    time_bucket: Mapped[str | None] = mapped_column(String(20))
    # up / down / flat
    index_trend: Mapped[str | None] = mapped_column(String(10))
    # net_buy / net_sell / neutral (한국장 수급; 미국장에서는 null일 수 있음)
    foreign_flow: Mapped[str | None] = mapped_column(String(10))
    institution_flow: Mapped[str | None] = mapped_column(String(10))
    individual_flow: Mapped[str | None] = mapped_column(String(10))
    # positive / neutral / negative
    news_sentiment: Mapped[str | None] = mapped_column(String(10))
    # 지수 변화율 등 시장별 지표: {"kospi_change_pct":..,"kosdaq_change_pct":..} 또는 {"nasdaq":..,"sox":..}
    indices: Mapped[dict | None] = mapped_column(JSONB)
    # 미국 전일장 요약: {"nasdaq_change_pct":..,"sox_change_pct":..,"major_news":[...]}
    us_previous_session: Mapped[dict | None] = mapped_column(JSONB)
    # 환율: {"usdkrw":..,"usdkrw_trend":".."}
    fx: Mapped[dict | None] = mapped_column(JSONB)
    # 확장용 catch-all
    data: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Theme(Base):
    """테마/섹터 정의 (예: 반도체, AI, 2차전지). market별로 코드가 유일하다."""

    __tablename__ = "themes"
    __table_args__ = (UniqueConstraint("market", "code", name="uq_themes_market_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[MarketCode] = mapped_column(
        pg_enum(MarketCode, "market_code"), nullable=False, default=MarketCode.KR
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SymbolThemeMembership(Base):
    """종목 ↔ 테마 매핑. 한 종목이 여러 테마에 속할 수 있다."""

    __tablename__ = "symbol_theme_memberships"
    __table_args__ = (
        UniqueConstraint("symbol_code", "theme_id", name="uq_symbol_theme"),
        Index("ix_symbol_theme_symbol", "symbol_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[MarketCode] = mapped_column(
        pg_enum(MarketCode, "market_code"), nullable=False, default=MarketCode.KR
    )
    symbol_code: Mapped[str] = mapped_column(String(20), nullable=False)
    theme_id: Mapped[int] = mapped_column(
        ForeignKey("themes.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
