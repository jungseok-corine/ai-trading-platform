from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.domain.models._types import pg_enum
from app.domain.models.enums import TradeSide


class SignalLog(Base):
    """Strategy가 생성한 Signal의 기록. 아직 주문 실행과는 연결되지 않는다."""

    __tablename__ = "signal_logs"
    __table_args__ = (Index("ix_signal_logs_symbol_generated_at", "symbol_code", "generated_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol_code: Mapped[str] = mapped_column(String(20), nullable=False)
    strategy_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="SET NULL")
    )
    signal_type: Mapped[TradeSide] = mapped_column(pg_enum(TradeSide, "signal_type"), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    short_ma: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    long_ma: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    quantity: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
