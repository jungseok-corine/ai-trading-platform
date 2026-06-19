from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.domain.models._types import pg_enum
from app.domain.models.enums import MarketCode


class DailyResearchReport(Base):
    """일일 AI 리서치 리포트 (C-2.29).

    매일 장마감 후 시장/전략/스캐너/체결 활동을 집계한 리포트를 저장한다.
    sections에 구조화된 집계 데이터를, summary에 사람이 읽는 요약을 담는다.
    (market, report_date)는 유일하며, 재생성 시 갱신된다.
    """

    __tablename__ = "daily_research_reports"
    __table_args__ = (
        UniqueConstraint("market", "report_date", name="uq_daily_report_market_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[MarketCode] = mapped_column(
        pg_enum(MarketCode, "market_code"), nullable=False, default=MarketCode.KR
    )
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    sections: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
