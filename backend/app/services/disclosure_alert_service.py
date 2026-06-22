from __future__ import annotations

from datetime import datetime, timedelta
from app.common.timezone import KST

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.news_context import NewsEventRepository



class DisclosureAlertService:
    """수집된 DART 공시(C-2.59)를 '알림'으로 띄운다 (C-2.61).

    보유/관심 종목의 최근 중요 공시를 최신순으로 모아 관제탑·알림 화면에 노출한다.
    read-only 집계이며 자동매매와 무관하다(감지·표시만, 대응은 사람).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._repo = NewsEventRepository(session)

    async def recent(
        self,
        hours: int = 48,
        symbols: list[str] | None = None,
        min_score: float = 0.5,
        limit: int = 50,
    ) -> list[dict]:
        since = datetime.now(KST) - timedelta(hours=hours)
        events = await self._repo.list_by_source_since(
            "dart", since, symbols=symbols, limit=limit
        )
        alerts: list[dict] = []
        for e in events:
            raw = e.raw_payload or {}
            score = raw.get("materiality")
            if score is not None and score < min_score:
                continue
            alerts.append({
                "symbol_code": e.symbol_code,
                "headline": e.headline,
                "category": raw.get("category"),
                "materiality": score,
                "corp_name": raw.get("corp_name"),
                "published_at": e.published_at.isoformat() if e.published_at else None,
                "url": e.url,
            })
        return alerts

    async def count_recent(self, hours: int = 48, min_score: float = 0.6) -> int:
        """관제탑 배지용: 최근 중요(>=min_score) 공시 수."""
        return len(await self.recent(hours=hours, min_score=min_score, limit=200))
