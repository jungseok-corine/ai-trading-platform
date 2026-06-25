from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from app.domain.models.enums import TradeSide
from app.domain.models.signal_log import SignalLog
from app.domain.repositories.base import BaseRepository


class SignalLogRepository(BaseRepository[SignalLog]):
    model = SignalLog

    async def list(self, limit: int = 100, offset: int = 0) -> list[SignalLog]:
        result = await self.session.execute(
            select(SignalLog)
            .order_by(SignalLog.generated_at.desc(), SignalLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_filtered(
        self,
        limit: int = 50,
        offset: int = 0,
        signal_type: TradeSide | None = None,
        symbol_code: str | None = None,
        strategy_version_id: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[SignalLog]:
        stmt = select(SignalLog).order_by(SignalLog.generated_at.desc(), SignalLog.id.desc())
        if signal_type is not None:
            stmt = stmt.where(SignalLog.signal_type == signal_type)
        if symbol_code is not None:
            stmt = stmt.where(SignalLog.symbol_code == symbol_code)
        if strategy_version_id is not None:
            stmt = stmt.where(SignalLog.strategy_version_id == strategy_version_id)
        if date_from is not None:
            stmt = stmt.where(SignalLog.generated_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(SignalLog.generated_at <= date_to)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_paper_signal_session(
        self, paper_signal_session_id: int, limit: int = 1000
    ) -> list[SignalLog]:
        """해당 Paper Signal Session이 만든 신호를 최신순으로 조회한다(세션 outcome 집계용)."""
        stmt = (
            select(SignalLog)
            .where(SignalLog.paper_signal_session_id == paper_signal_session_id)
            .order_by(SignalLog.generated_at.desc(), SignalLog.id.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_strategy_version(self, strategy_version_id: int) -> int:
        """해당 strategy_version_id를 참조하는 signal_log 개수를 반환한다."""
        result = await self.session.execute(
            select(func.count(SignalLog.id)).where(
                SignalLog.strategy_version_id == strategy_version_id
            )
        )
        return result.scalar() or 0

    async def exists_for_candle(
        self,
        strategy_version_id: int | None,
        symbol_code: str,
        signal_type: TradeSide,
        candle_ts: datetime | None,
    ) -> bool:
        """동일 (strategy_version_id, symbol_code, signal_type, candle_ts)에 대한
        Signal이 이미 저장되어 있는지 확인한다 (중복 생성 방지)."""
        if candle_ts is None:
            return False

        result = await self.session.execute(
            select(SignalLog.id).where(
                SignalLog.strategy_version_id == strategy_version_id,
                SignalLog.symbol_code == symbol_code,
                SignalLog.signal_type == signal_type,
                SignalLog.candle_ts == candle_ts,
            )
        )
        return result.scalar_one_or_none() is not None
