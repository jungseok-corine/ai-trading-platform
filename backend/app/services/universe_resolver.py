from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from app.common.timezone import KST

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.enums import MarketCode
from app.domain.repositories.watchlist import WatchlistSymbolRepository

logger = logging.getLogger(__name__)


# 전략 파라미터 universe 필드에 허용되는 값.
SCANNER_CANDIDATES = "scanner_candidates"
WATCHLIST = "watchlist"
VALID_UNIVERSES = frozenset({SCANNER_CANDIDATES, WATCHLIST})


@dataclass(frozen=True)
class ResolvedSymbol:
    """유니버스 해석 결과의 종목 1개 — 종목코드 + 시장/거래소 정보를 함께 담는다.

    멀티마켓(KR/US)에서 종목마다 시장·거래소가 다를 수 있으므로(예: AAPL=NAS,
    JPM=NYS) 시세 조회 라우팅에 필요한 market/exchange를 종목 단위로 전달한다.
    exchange는 미국 종목에서만 의미가 있고 KR은 None이다.
    """

    symbol_code: str
    market: str = "KR"
    exchange: str | None = None


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
    ) -> list[ResolvedSymbol]:
        """universe 이름을 ResolvedSymbol 리스트로 해석한다.

        알 수 없는 universe는 빈 리스트를 반환하고 warning을 남긴다(예외 raise 안 함).
        """
        if universe == SCANNER_CANDIDATES:
            return await self._scanner_candidates(market, lookback_days, limit)
        if universe == WATCHLIST:
            return await self._watchlist_symbols(market, limit)
        logger.warning("알 수 없는 universe=%r — 빈 유니버스로 처리합니다.", universe)
        return []

    async def _scanner_candidates(
        self, market: MarketCode | None, lookback_days: int, limit: int
    ) -> list[ResolvedSymbol]:
        since = datetime.now(KST) - timedelta(days=lookback_days)
        stmt = (
            select(CandidateEvent.symbol_code, CandidateEvent.market)
            .where(CandidateEvent.triggered_at >= since)
            .distinct()
        )
        if market is not None:
            stmt = stmt.where(CandidateEvent.market == market)
        stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        # 스캐너 후보는 거래소 코드를 따로 갖지 않는다(현재 KR 중심) — exchange=None.
        return [
            ResolvedSymbol(symbol_code=code, market=mkt.value if mkt else "KR")
            for code, mkt in result.all()
        ]

    async def _watchlist_symbols(
        self, market: MarketCode | None, limit: int
    ) -> list[ResolvedSymbol]:
        rows = await WatchlistSymbolRepository(self._session).list_enabled_symbols(
            market=market.value if market is not None else None, limit=limit
        )
        return [
            ResolvedSymbol(symbol_code=code, market=mkt, exchange=exc)
            for code, mkt, exc in rows
        ]
