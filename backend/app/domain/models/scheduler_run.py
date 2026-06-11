from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.domain.models._types import pg_enum
from app.domain.models.enums import SchedulerRunStatus


class SchedulerRun(Base):
    """scheduler job(strategy_runner, order_sync) 1회 실행에 대한 기록."""

    __tablename__ = "scheduler_runs"
    __table_args__ = (Index("ix_scheduler_runs_job_id_started_at", "job_id", "started_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[SchedulerRunStatus] = mapped_column(
        pg_enum(SchedulerRunStatus, "scheduler_run_status"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
