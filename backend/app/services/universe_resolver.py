from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.enums import MarketCode
from app.domain.models.watchlist import Watchlist, WatchlistSymbol

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

# 전략 파라미터 universe 필드에 허용되는 값.
SCANNER_CANDIDATES = "scanner_candidates"
WATCHLIST = "watchlist"
VALID_UNIVERSES = frozenset({SCANNER_CANDIDATES, WATCHLIST})


class UniverseResolver:
    """전략을 적용할 종목 유니버스를 해석한다.

    종목을 사람이 하나씩 지정하지 않아도, 스캐너가 포착한 후보(candidate_events)나
    관심종목(watchlist)의 종목 집합 전체에 전략을 신호 생성용으로 돌릴 수 있게 한다.
    모든 조회는 read-only이며 주문과 무관하다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve(
        self,
        universe: str,
        market: MarketCode | None = None,
        lookback_days: int = 5,
        limit: int = 200,
    ) -> list[str]:
        """universe 이름을 종목코드 리스트로 해석한다.

        알 수 없는 universe는 빈 리스트를 반환하고 warning을 남긴다(예외 raise 안 함).
        """
        if universe == SCANNER_CANDIDATES:
            return await self._scanner_candidates(market, lookback_days, limit)
        if universe == WATCHLIST:
            return await self._watchlist_symbols(limit)
        logger.warning("알 수 없는 universe=%r — 빈 유니버스로 처리합니다.", universe)
        return []

    async def _scanner_candidates(
        self, market: MarketCode | None, lookback_days: int, limit: int
    ) -> list[str]:
        since = datetime.now(KST) - timedelta(days=lookback_days)
        stmt = (
            select(CandidateEvent.symbol_code)
            .where(CandidateEvent.triggered_at >= since)
            .distinct()
        )
        if market is not None:
            stmt = stmt.where(CandidateEvent.market == market)
        stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all()]

    async def _watchlist_symbols(self, limit: int) -> list[str]:
        stmt = (
            select(WatchlistSymbol.symbol_code)
            .join(Watchlist, Watchlist.id == WatchlistSymbol.watchlist_id)
            .where(WatchlistSymbol.enabled.is_(True))
            .where(Watchlist.enabled.is_(True))
            .distinct()
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all()]
