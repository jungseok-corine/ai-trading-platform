from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.domain.models._types import pg_enum
from app.domain.models.enums import OrderStatus, TradeSide


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    strategy_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="SET NULL")
    )
    symbol_code: Mapped[str] = mapped_column(String(20), nullable=False)
    symbol_name: Mapped[str | None] = mapped_column(String(100))
    # 멀티마켓: 이 체결이 속한 시장(KR/US). 브로커 라우팅/회고용. enum 없이 String(2).
    market: Mapped[str] = mapped_column(String(2), nullable=False, server_default="KR")
    side: Mapped[TradeSide] = mapped_column(pg_enum(TradeSide, "trade_side"), nullable=False)

    entry_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    pnl_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    pnl_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))

    entry_reason: Mapped[str | None] = mapped_column(Text)
    exit_reason: Mapped[str | None] = mapped_column(Text)
    market_condition: Mapped[dict | None] = mapped_column(JSONB)
    context_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("market_context_snapshots.id", ondelete="SET NULL")
    )
    ai_analysis_id: Mapped[int | None] = mapped_column(Integer)

    order_status: Mapped[OrderStatus] = mapped_column(
        pg_enum(OrderStatus, "order_status"), nullable=False, default=OrderStatus.PENDING
    )
    broker_order_id: Mapped[str | None] = mapped_column(String(50))
    org_no: Mapped[str | None] = mapped_column(String(10))  # KRX_FWDG_ORD_ORGNO — 주문채번지점번호
    partial_fill: Mapped[dict | None] = mapped_column(JSONB)
    position_applied_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    commission: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    tax: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    slippage: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
