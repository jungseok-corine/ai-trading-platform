from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.domain.models.market_data import MarketData
from app.domain.repositories.base import BaseRepository


class MarketDataRepository(BaseRepository[MarketData]):
    model = MarketData

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
