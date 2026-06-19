from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import MarketCode
from app.domain.models.market_context import MarketContextSnapshot
from app.domain.repositories.news_context import UsMarketSnapshotRepository
from app.services.market_context_service import MarketContextService
from app.trading.scanner.facts import time_bucket

KST = ZoneInfo("Asia/Seoul")


class MarketContextCaptureService:
    """현재 시점의 시장 맥락을 스냅샷으로 캡처한다 (C-2.37).

    C-2.22의 market_context_snapshots를 실제 흐름에서 채우는 역할이다. 지금은 시간대와
    최근 미국장 요약을 담고, 지수/수급 등 추가 소스는 이후 단계에서 보강한다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._context_service = MarketContextService(session)
        self._us_repo = UsMarketSnapshotRepository(session)

    async def capture(
        self, market: MarketCode = MarketCode.KR, now: datetime | None = None
    ) -> MarketContextSnapshot:
        now = now or datetime.now(KST)

        us = await self._us_repo.get_latest()
        us_prev = None
        if us is not None:
            us_prev = {
                "session_date": us.session_date.isoformat(),
                "nasdaq_change_pct": str(us.nasdaq_change_pct)
                if us.nasdaq_change_pct is not None
                else None,
                "sox_change_pct": str(us.sox_change_pct)
                if us.sox_change_pct is not None
                else None,
            }

        return await self._context_service.create_snapshot(
            market=market,
            time_bucket=time_bucket(now),
            us_previous_session=us_prev,
        )
