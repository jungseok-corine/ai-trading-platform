from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.market_data import MarketData
from app.domain.models.news_context import NewsEvent, UsMarketSnapshot

# 소스별 신선도 임계(시간). 이 시간보다 오래된 최신 데이터면 stale로 본다.
# 데이터가 아예 없으면 present=False로 두고 stale로 보지 않는다(소스 미사용은 정상일 수 있음).
_THRESHOLDS_HOURS = {
    "market_data": 48,   # 영업일 기준 — 주말 포함 여유
    "us_market": 48,
    "news": 72,
    "dart": 72,
}


class DataFreshnessService:
    """데이터 소스 신선도 점검 (C-3.10).

    수집 파이프라인이 멈춰 데이터가 늙어가는 것을 운영자가 빨리 알도록, 핵심 소스의
    최신 타임스탬프와 경과 시간을 모은다. read-only 점검 — 아무것도 바꾸지 않는다.
    데이터가 아예 없는 소스(미사용일 수 있음)는 stale로 보지 않는다(거짓 경보 방지).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def status(self) -> dict:
        now = datetime.now(timezone.utc)
        sources = [
            await self._source("market_data", await self._max(MarketData.ts), now),
            await self._source("us_market", await self._max(UsMarketSnapshot.created_at), now),
            await self._source("news", await self._max(NewsEvent.created_at), now),
            await self._source(
                "dart",
                await self._max(NewsEvent.created_at, NewsEvent.source == "dart"),
                now,
            ),
        ]
        stale = [s for s in sources if s["stale"]]
        return {
            "checked_at": now.isoformat(),
            "sources": sources,
            "stale_count": len(stale),
            "stale_sources": [s["source"] for s in stale],
        }

    async def _max(self, column, where=None) -> datetime | None:
        stmt = select(func.max(column))
        if where is not None:
            stmt = stmt.where(where)
        return (await self._session.execute(stmt)).scalar()

    async def _source(self, name: str, last_at: datetime | None, now: datetime) -> dict:
        threshold = _THRESHOLDS_HOURS[name]
        present = last_at is not None
        age_hours = None
        stale = False
        if present:
            # tz-naive로 저장된 경우 UTC로 간주
            if last_at.tzinfo is None:
                last_at = last_at.replace(tzinfo=timezone.utc)
            age_hours = round((now - last_at).total_seconds() / 3600, 1)
            stale = age_hours > threshold
        return {
            "source": name,
            "present": present,
            "last_at": last_at.isoformat() if last_at else None,
            "age_hours": age_hours,
            "threshold_hours": threshold,
            "stale": stale,
        }
