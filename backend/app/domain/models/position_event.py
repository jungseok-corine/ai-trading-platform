from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.domain.models._types import pg_enum
from app.domain.models.enums import PositionEventType


class PositionEvent(Base):
    __tablename__ = "position_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.id", ondelete="CASCADE"), nullable=False)
    trade_id: Mapped[int | None] = mapped_column(ForeignKey("trades.id", ondelete="SET NULL"))

    event_type: Mapped[PositionEventType] = mapped_column(
        pg_enum(PositionEventType, "position_event_type"), nullable=False
    )
    quantity_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    realized_pnl_delta: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    """수수료/세금을 차감하기 전 실현손익(gross)."""
    realized_pnl_delta_net: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    """수수료/세금을 차감한 실현손익(net). positions.realized_pnl에 누적되는 값."""

    commission: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    tax: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))

    before_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    after_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    before_avg_entry_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    after_avg_entry_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))

    raw: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
