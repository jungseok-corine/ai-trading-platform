from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import MarketCode
from app.domain.models.news_context import NewsEvent, UsMarketSnapshot
from app.domain.repositories.news_context import (
    NewsEventRepository,
    UsMarketSnapshotRepository,
)


class DuplicateUsSnapshotError(Exception):
    """동일 session_date의 미국장 스냅샷이 이미 존재할 때 발생."""


class NewsContextService:
    """뉴스 이벤트와 미국장 스냅샷을 저장·조회한다 (C-2.28).

    한국장 전략 분석 시 뉴스/미국장/환율 맥락을 함께 참고할 수 있는 데이터 기반을 제공한다.
    실제 뉴스/시세 수집은 외부 소스 연동(이후 단계)이 담당하며, 여기서는 저장/조회를 다룬다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._news_repo = NewsEventRepository(session)
        self._us_repo = UsMarketSnapshotRepository(session)

    # --- news ------------------------------------------------------------
    async def create_news(
        self,
        headline: str,
        published_at: datetime,
        market: MarketCode = MarketCode.KR,
        symbol_code: str | None = None,
        source: str = "manual",
        url: str | None = None,
        sentiment: str | None = None,
        themes: list[str] | None = None,
        raw_payload: dict | None = None,
    ) -> NewsEvent:
        news = await self._news_repo.create(
            headline=headline,
            published_at=published_at,
            market=market,
            symbol_code=symbol_code,
            source=source,
            url=url,
            sentiment=sentiment,
            themes=themes,
            raw_payload=raw_payload,
        )
        await self._session.commit()
        return news

    async def list_news(
        self,
        market: MarketCode | None = None,
        symbol_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[NewsEvent]:
        return await self._news_repo.list_filtered(
            market=market, symbol_code=symbol_code, limit=limit, offset=offset
        )

    # --- US market -------------------------------------------------------
    async def upsert_us_snapshot(
        self, session_date: date, **fields: Any
    ) -> UsMarketSnapshot:
        """미국장 스냅샷을 생성하거나, 같은 날짜가 있으면 갱신한다(멱등)."""
        existing = await self._us_repo.get_by_date(session_date)
        if existing is not None:
            await self._us_repo.update(existing, **_coerce_decimals(fields))
            await self._session.commit()
            return existing
        snapshot = await self._us_repo.create(
            session_date=session_date, **_coerce_decimals(fields)
        )
        await self._session.commit()
        return snapshot

    async def get_us_snapshot(self, session_date: date) -> UsMarketSnapshot | None:
        return await self._us_repo.get_by_date(session_date)

    async def get_latest_us_snapshot(self) -> UsMarketSnapshot | None:
        return await self._us_repo.get_latest()

    async def list_us_snapshots(self, limit: int = 30) -> list[UsMarketSnapshot]:
        return await self._us_repo.list_recent(limit=limit)


def _coerce_decimals(fields: dict) -> dict:
    """float/str 수치 입력을 Decimal로 변환한다 (None/list/dict는 그대로)."""
    numeric_keys = {
        "nasdaq_change_pct",
        "sp500_change_pct",
        "sox_change_pct",
        "treasury_10y",
        "vix",
    }
    out = {}
    for k, v in fields.items():
        if k in numeric_keys and v is not None and not isinstance(v, Decimal):
            out[k] = Decimal(str(v))
        else:
            out[k] = v
    return out
