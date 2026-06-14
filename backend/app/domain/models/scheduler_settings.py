from datetime import datetime

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SchedulerSettings(Base):
    """strategy_runner/order_sync 스케줄러 주기 설정 (singleton row, id=1)."""

    __tablename__ = "scheduler_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_scheduler_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    order_sync_scheduler_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
