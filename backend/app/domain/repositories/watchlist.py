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

    async def list_enabled_symbol_codes(self, limit: int | None = None) -> list[str]:
        """enabled watchlist에 속한 enabled 종목 코드 목록(중복 제거)을 반환한다.

        유니버스/스캔/수집 등 여러 서비스가 공유하는 공통 조회.
        """
        stmt = (
            select(WatchlistSymbol.symbol_code)
            .join(Watchlist, Watchlist.id == WatchlistSymbol.watchlist_id)
            .where(Watchlist.enabled.is_(True), WatchlistSymbol.enabled.is_(True))
            .distinct()
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]

    async def get_by_symbol_code(self, watchlist_id: int, symbol_code: str) -> WatchlistSymbol | None:
        result = await self.session.execute(
            select(WatchlistSymbol).where(
                WatchlistSymbol.watchlist_id == watchlist_id,
                WatchlistSymbol.symbol_code == symbol_code,
            )
        )
        return result.scalar_one_or_none()
