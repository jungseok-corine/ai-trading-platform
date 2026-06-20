from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.domain.models._types import pg_enum
from app.domain.models.enums import PauseSource


class TradingGuardState(Base):
    """계좌별 자동매매 pause 상태 (singleton per account).

    real mode에서 position reconciliation mismatch 등 정합성 문제가 발생하면
    auto_pause()로 is_paused=True로 전환되고 신규 주문이 차단된다.
    사람이 resume API로 수동 해제하기 전까지 pause 상태가 유지된다.
    """

    __tablename__ = "trading_guard_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    is_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pause_reason: Mapped[str | None] = mapped_column(Text)
    pause_source: Mapped[PauseSource | None] = mapped_column(
        pg_enum(PauseSource, "pause_source")
    )
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_by: Mapped[str | None] = mapped_column(String(20))  # "system" | "user"
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(100))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    related_risk_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("risk_events.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
