"""DART XBRL 재무제표 (C-2.21.1).

종목별 연간/반기 핵심 재무항목을 저장한다 — 매출액·영업이익·당기순이익·자산총계·자본총계.
DartFinanceProvider(fnlttSinglAcnt.json)가 수집하고 AI 분석 bundle에 주입된다.
주문과 무관한 read-only 데이터.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class FinancialStatement(Base):
    """종목 재무제표 요약 (DART XBRL, 연간/반기).

    bsns_year + reprt_code + fs_div 조합으로 한 기간의 핵심 재무항목을 저장한다.
    key_items: {revenue, operating_income, net_income, total_assets, total_equity} (단위: 원)
    """

    __tablename__ = "financial_statements"
    __table_args__ = (
        UniqueConstraint(
            "corp_code", "bsns_year", "reprt_code", "fs_div",
            name="uq_finstat_corp_period",
        ),
        Index("ix_finstat_stock_year", "stock_code", "bsns_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    corp_code: Mapped[str] = mapped_column(String(8), nullable=False)
    stock_code: Mapped[str | None] = mapped_column(String(10))
    corp_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    bsns_year: Mapped[str] = mapped_column(String(4), nullable=False)
    reprt_code: Mapped[str] = mapped_column(String(5), nullable=False)
    fs_div: Mapped[str] = mapped_column(String(3), nullable=False)
    # 핵심 재무항목 {revenue, operating_income, net_income, total_assets, total_equity}
    key_items: Mapped[dict | None] = mapped_column(JSONB)
    raw_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
