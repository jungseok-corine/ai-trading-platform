from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class InvestorFlow(Base):
    """종목별 일별 투자자 수급 데이터.

    KIS API FHPTJ04160001 (종목별 투자자매매동향 일별) 응답을 영속화한다.
    금액 단위: 백만원 (KIS 응답 그대로). 수량 단위: 주.
    음수는 순매도를 의미한다.
    """

    __tablename__ = "investor_flows"
    __table_args__ = (
        UniqueConstraint("symbol_code", "trade_date", "source", name="uq_investor_flows_symbol_date_source"),
        Index("ix_investor_flows_symbol_date", "symbol_code", "trade_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol_code: Mapped[str] = mapped_column(String(20), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)

    # 외국인 순매수 (frgn_ntby_qty, frgn_ntby_tr_pbmn)
    foreign_net_buy_quantity: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    foreign_net_buy_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)

    # 기관계 순매수 (orgn_ntby_qty, orgn_ntby_tr_pbmn)
    institution_net_buy_quantity: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    institution_net_buy_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)

    # 개인 순매수 (prsn_ntby_qty, prsn_ntby_tr_pbmn)
    individual_net_buy_quantity: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    individual_net_buy_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)

    # 원본 KIS 응답 보관 (디버깅 및 추후 필드 확장용)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # 데이터 출처 식별자 (확장 가능성 고려)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="kis")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
