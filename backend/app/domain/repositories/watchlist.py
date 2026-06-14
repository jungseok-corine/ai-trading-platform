from sqlalchemy import func, select

from app.domain.models.watchlist import Watchlist, WatchlistSymbol
from app.domain.repositories.base import BaseRepository


class WatchlistRepository(BaseRepository[Watchlist]):
    model = Watchlist

    async def list_with_symbol_counts(self) -> list[tuple[Watchlist, int]]:
        """Watchlist 목록과 각 Watchlist의 종목 수를 함께 조회한다."""
        stmt = (
            select(Watchlist, func.count(WatchlistSymbol.id))
            .outerjoin(WatchlistSymbol, WatchlistSymbol.watchlist_id == Watchlist.id)
            .group_by(Watchlist.id)
            .order_by(Watchlist.id)
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]


class WatchlistSymbolRepository(BaseRepository[WatchlistSymbol]):
    model = WatchlistSymbol

    async def list_by_watchlist(self, watchlist_id: int) -> list[WatchlistSymbol]:
        result = await self.session.execute(
            select(WatchlistSymbol)
            .where(WatchlistSymbol.watchlist_id == watchlist_id)
            .order_by(WatchlistSymbol.id)
        )
        return list(result.scalars().all())

    async def get_by_symbol_code(self, watchlist_id: int, symbol_code: str) -> WatchlistSymbol | None:
        result = await self.session.execute(
            select(WatchlistSymbol).where(
                WatchlistSymbol.watchlist_id == watchlist_id,
                WatchlistSymbol.symbol_code == symbol_code,
            )
        )
        return result.scalar_one_or_none()
