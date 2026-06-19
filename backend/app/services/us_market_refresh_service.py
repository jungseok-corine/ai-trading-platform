from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.news_context import UsMarketSnapshot
from app.services.news_context_service import NewsContextService
from app.services.us_market.base import UsMarketProvider
from app.services.us_market.factory import get_us_market_provider


@dataclass
class RefreshResult:
    """미국장 스냅샷 갱신 1회 결과."""

    provider: str
    updated: bool  # provider가 데이터를 줘서 스냅샷을 upsert했는가
    session_date: date | None
    reason: str | None = None  # updated=False일 때의 사유

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "updated": self.updated,
            "session_date": self.session_date.isoformat() if self.session_date else None,
            "reason": self.reason,
        }


class UsMarketRefreshService:
    """provider에서 미국장 스냅샷을 가져와 DB에 upsert한다 (C-2.44).

    provider가 None을 반환하면(manual 등) 아무것도 덮어쓰지 않는다(no-op). 사람이 직접
    입력한 데이터를 보존하기 위함이다. 실거래/주문과 무관한 read-only 수집이다.
    """

    def __init__(
        self, session: AsyncSession, provider: UsMarketProvider | None = None
    ) -> None:
        self._session = session
        self._news_service = NewsContextService(session)
        if provider is None:
            from app.core.config import get_settings

            provider = get_us_market_provider(get_settings().us_market_provider)
        self._provider = provider

    async def refresh(self, session_date: date | None = None) -> RefreshResult:
        name = self._provider.provider_name()
        data = await self._provider.fetch_snapshot(session_date)
        if data is None:
            return RefreshResult(
                provider=name,
                updated=False,
                session_date=session_date,
                reason="provider returned no data (manual mode)",
            )
        await self._news_service.upsert_us_snapshot(
            data.session_date, **data.to_upsert_fields()
        )
        return RefreshResult(provider=name, updated=True, session_date=data.session_date)

    async def latest(self) -> UsMarketSnapshot | None:
        return await self._news_service.get_latest_us_snapshot()
