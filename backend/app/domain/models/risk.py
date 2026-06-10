from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.domain.models._types import pg_enum
from app.domain.models.enums import RiskEventResult


class RiskConfig(Base):
    __tablename__ = "risk_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    max_daily_loss_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    max_position_size: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    max_open_positions: Mapped[int] = mapped_column(Integer, nullable=False)
    max_trades_per_day: Mapped[int] = mapped_column(Integer, nullable=False)
    consecutive_loss_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    emergency_stop: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RiskEvent(Base):
    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    strategy_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="SET NULL")
    )
    signal_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    context_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result: Mapped[RiskEventResult] = mapped_column(
        pg_enum(RiskEventResult, "risk_event_result"), nullable=False
    )
    rule_name: Mapped[str | None] = mapped_column(String(50))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
