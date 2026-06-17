from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.domain.models.market_data import MarketData
from app.domain.repositories.base import BaseRepository


class MarketDataRepository(BaseRepository[MarketData]):
    model = MarketData

    async def list_candles(
        self,
        symbol_code: str,
        timeframe: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MarketData]:
        stmt = select(MarketData).where(MarketData.symbol_code == symbol_code)
        if timeframe is not None:
            stmt = stmt.where(MarketData.timeframe == timeframe)
        if start_at is not None:
            stmt = stmt.where(MarketData.ts >= start_at)
        if end_at is not None:
            stmt = stmt.where(MarketData.ts <= end_at)
        stmt = stmt.order_by(MarketData.ts.asc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_symbol_summary_by_timeframe(self, symbol_code: str) -> list[dict]:
        """symbol_code의 timeframe별 count/min_ts/max_ts를 집계한다."""
        stmt = (
            select(
                MarketData.timeframe,
                func.count().label("count"),
                func.min(MarketData.ts).label("oldest_ts"),
                func.max(MarketData.ts).label("latest_ts"),
            )
            .where(MarketData.symbol_code == symbol_code)
            .group_by(MarketData.timeframe)
            .order_by(MarketData.timeframe)
        )
        result = await self.session.execute(stmt)
        return [
            {
                "timeframe": row.timeframe,
                "count": row.count,
                "oldest_ts": row.oldest_ts,
                "latest_ts": row.latest_ts,
            }
            for row in result.all()
        ]

    async def get_global_summary(self) -> list[dict]:
        """symbol_code × timeframe 조합별 count/latest_ts를 집계한다."""
        stmt = (
            select(
                MarketData.symbol_code,
                MarketData.timeframe,
                func.count().label("count"),
                func.max(MarketData.ts).label("latest_ts"),
            )
            .group_by(MarketData.symbol_code, MarketData.timeframe)
            .order_by(MarketData.symbol_code, MarketData.timeframe)
        )
        result = await self.session.execute(stmt)
        return [
            {
                "symbol_code": row.symbol_code,
                "timeframe": row.timeframe,
                "count": row.count,
                "latest_ts": row.latest_ts,
            }
            for row in result.all()
        ]

    async def get_candles_between(
        self,
        symbol_code: str,
        timeframe: str,
        after_ts: datetime,
        until_ts: datetime,
    ) -> list[MarketData]:
        """after_ts(exclusive) ~ until_ts(inclusive) 범위의 캔들을 시간순으로 반환한다."""
        stmt = (
            select(MarketData)
            .where(
                MarketData.symbol_code == symbol_code,
                MarketData.timeframe == timeframe,
                MarketData.ts > after_ts,
                MarketData.ts <= until_ts,
            )
            .order_by(MarketData.ts.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_bulk(self, rows: list[dict]) -> int:
        """OHLCV 행을 bulk upsert한다. 동일 PK(symbol_code, timeframe, ts) 시 OHLCV 업데이트."""
        if not rows:
            return 0
        stmt = pg_insert(MarketData).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol_code", "timeframe", "ts"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
            },
        )
        await self.session.execute(stmt)
        await self.session.flush()
        return len(rows)
