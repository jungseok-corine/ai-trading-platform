from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

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
