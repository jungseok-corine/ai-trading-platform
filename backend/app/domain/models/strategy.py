from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.domain.models._types import pg_enum
from app.domain.models.enums import StrategyVersionStatus


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    versions: Mapped[list["StrategyVersion"]] = relationship(
        back_populates="strategy", cascade="all, delete-orphan"
    )


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"
    __table_args__ = (UniqueConstraint("strategy_id", "version_no", name="uq_strategy_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    change_description: Mapped[str | None] = mapped_column(Text)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    win_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    avg_profit: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    avg_loss: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    mdd: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    status: Mapped[StrategyVersionStatus] = mapped_column(
        pg_enum(StrategyVersionStatus, "strategy_version_status"),
        nullable=False,
        default=StrategyVersionStatus.DRAFT,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    strategy: Mapped["Strategy"] = relationship(back_populates="versions")
