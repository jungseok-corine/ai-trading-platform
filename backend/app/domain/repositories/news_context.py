from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.domain.models.enums import MarketCode
from app.domain.models.news_context import NewsEvent, UsMarketSnapshot
from app.domain.repositories.base import BaseRepository


class NewsEventRepository(BaseRepository[NewsEvent]):
    model = NewsEvent

    async def existing_urls(self, urls: list[str]) -> set[str]:
        """주어진 url 중 이미 저장된 것들의 집합(중복 수집 방지)."""
        if not urls:
            return set()
        result = await self.session.execute(
            select(NewsEvent.url).where(NewsEvent.url.in_(urls))
        )
        return {row[0] for row in result.all() if row[0]}

    async def list_filtered(
        self,
        market: MarketCode | None = None,
        symbol_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[NewsEvent]:
        stmt = select(NewsEvent).order_by(
            NewsEvent.published_at.desc(), NewsEvent.id.desc()
        )
        if market is not None:
            stmt = stmt.where(NewsEvent.market == market)
        if symbol_code is not None:
            stmt = stmt.where(NewsEvent.symbol_code == symbol_code)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class UsMarketSnapshotRepository(BaseRepository[UsMarketSnapshot]):
    model = UsMarketSnapshot

    async def get_by_date(self, session_date: date) -> UsMarketSnapshot | None:
        result = await self.session.execute(
            select(UsMarketSnapshot).where(UsMarketSnapshot.session_date == session_date)
        )
        return result.scalar_one_or_none()

    async def get_latest(self) -> UsMarketSnapshot | None:
        result = await self.session.execute(
            select(UsMarketSnapshot).order_by(UsMarketSnapshot.session_date.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_before(self, before_date: date) -> UsMarketSnapshot | None:
        """before_date보다 엄격히 이전(session_date < before_date)인 최신 스냅샷.

        과거 거래일 분석 시 룩어헤드(미래 미국장)를 막기 위해 쓴다.
        """
        result = await self.session.execute(
            select(UsMarketSnapshot)
            .where(UsMarketSnapshot.session_date < before_date)
            .order_by(UsMarketSnapshot.session_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_recent(self, limit: int = 30) -> list[UsMarketSnapshot]:
        result = await self.session.execute(
            select(UsMarketSnapshot)
            .order_by(UsMarketSnapshot.session_date.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
