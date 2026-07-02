"""백테스트 실행 기록 (C-6.1).

저장된 market_data 위에서 전략 신호 생성기를 히스토리컬 리플레이한 결과를 기록한다.
- **주문/브로커/KIS 호출 없음** — 순수 read-only 계산의 결과 저장.
- Trade/Position/SignalLog와 FK 미연결 (시뮬레이션 결과는 운영 데이터가 아니다).
- status는 String + CheckConstraint (enum 마이그레이션 불필요).
"""
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('succeeded', 'failed')",
            name="ck_backtest_runs_status",
        ),
        Index("ix_backtest_runs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    strategy_type: Mapped[str] = mapped_column(String(50), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    symbol_code: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    market: Mapped[str] = mapped_column(String(5), nullable=False, default="KR")

    start_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # 승률/기대값/MDD/거래수/수수료 합계 등 집계 지표
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # 시뮬레이션 체결 목록 (entry/exit ts·price·pnl)
    simulated_trades: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
