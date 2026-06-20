from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class OperationsSnapshot(Base):
    """일자별 운영 종합 스냅샷 (C-3.17).

    운영 종합(C-3.5)의 헤드라인을 매일 한 행으로 적재해 추세(비용·손익·검토 대기·승격 후보)를
    본다. 헤드라인 수치는 인덱스 가능한 컬럼으로 빼고, 전체 본문은 data(JSONB)에 보존한다.
    read-only 집계의 적재 — 주문과 무관하다.
    """

    __tablename__ = "operations_snapshots"
    __table_args__ = (UniqueConstraint("snapshot_date", name="uq_operations_snapshots_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)

    invariants_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    pending_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    promotion_ready: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    est_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
