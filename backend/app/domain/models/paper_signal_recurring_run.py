"""Paper Signal Recurring Run Plan — pair-scoped 반복 신호 기록 *계획* (M2.14A, inert).

D-24를 따른다: 상시 신호 운영은 **명시한 baseline+challenger 페어**에 한정된, `max_runs`로 상한된,
**SignalLog-only** 반복 *계획*부터 시작한다. 전역 런너 활성은 V1이 아니다.

핵심 안전 불변식 (M2.14A 범위):
- 이 단계는 **계획만 만든다(inert).** 생성된 계획은 **실행되지 않는다**:
  - 어떤 잡/스케줄러도 켜지 않는다 · 어떤 SignalLog/Trade/Order도 만들지 않는다.
  - 디스패처/run-loop/APScheduler 통합은 M2.14B(별도 승인)에서만.
- 계획은 항상 `status="prepared"`로 생성된다. `active`는 미래 예약값이며 M2.14A에서는 만들지 않는다.
- `next_run_at`은 M2.14A에서 항상 NULL이다(스케줄 없음 → inert).
- 연결된 PaperSignalSession/StrategyVersion/StrategyProposal status를 바꾸지 않는다.
"""
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PaperSignalRecurringRun(Base):
    __tablename__ = "paper_signal_recurring_runs"
    __table_args__ = (
        CheckConstraint("interval_seconds > 0", name="ck_psrr_interval_positive"),
        CheckConstraint("max_runs > 0", name="ck_psrr_max_runs_positive"),
        CheckConstraint("completed_runs >= 0", name="ck_psrr_completed_runs_nonneg"),
        CheckConstraint(
            "baseline_session_id <> challenger_session_id",
            name="ck_psrr_distinct_sessions",
        ),
        Index("ix_psrr_status", "status"),
        Index("ix_psrr_baseline_session_id", "baseline_session_id"),
        Index("ix_psrr_challenger_session_id", "challenger_session_id"),
        Index("ix_psrr_pair", "baseline_session_id", "challenger_session_id"),
        Index("ix_psrr_status_next_run_at", "status", "next_run_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # prepared(생성 기본) | active(미래 예약 — M2.14A 미생성) | stopped | completed | failed.
    # 비종료(non-terminal) = prepared/active. 종료(terminal) = stopped/completed/failed.
    # DB enum 대신 문자열 — 안전 기록 테이블 관례(paper_signal_sessions와 동일).
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="prepared", server_default="prepared"
    )
    scope_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="baseline_challenger_pair",
        server_default="baseline_challenger_pair",
    )
    baseline_session_id: Mapped[int] = mapped_column(
        ForeignKey("paper_signal_sessions.id"), nullable=False
    )
    challenger_session_id: Mapped[int] = mapped_column(
        ForeignKey("paper_signal_sessions.id"), nullable=False
    )
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    max_runs: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_runs: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # M2.14A에서는 항상 NULL(스케줄 없음). M2.14B 디스패처가 채운다.
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    stopped_by: Mapped[str | None] = mapped_column(String(100))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
