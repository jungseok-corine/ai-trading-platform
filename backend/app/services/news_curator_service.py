from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import MarketCode
from app.services.news_context_service import NewsContextService
from app.trading.analysis.news_materiality import score_materiality


class NewsCuratorService:
    """종목 뉴스/공시를 중요도로 큐레이션한다 (C-2.57).

    "주가에 영향 없는 뉴스는 분석할 필요 없다"는 원칙 — 룰 기반 중요도(materiality)로
    노이즈를 거르고 중요한 것만 상위로 올린다. 비싼 분석 모델엔 정제본만 넘긴다.
    (정밀 점수가 필요하면 이후 싼 모델 큐레이터로 보강 가능.)
    """

    def __init__(self, session: AsyncSession) -> None:
        self._news_svc = NewsContextService(session)

    async def curate(
        self,
        market: MarketCode = MarketCode.KR,
        symbol_code: str | None = None,
        limit: int = 8,
        min_score: float = 0.5,
        candidate_pool: int = 50,
    ) -> list[dict]:
        """중요도 임계 이상 뉴스를 중요도순으로 limit개 반환한다(고정 구조).

        candidate_pool: 점수 매길 후보 풀 크기(최근 N개를 가져와 필터링).
        """
        raw = await self._news_svc.list_news(
            market=market, symbol_code=symbol_code, limit=candidate_pool
        )
        scored: list[dict] = []
        for n in raw:
            score, category = score_materiality(n.headline, n.themes)
            if score < min_score:
                continue
            scored.append({
                "headline": n.headline,
                "source": n.source,
                "sentiment": n.sentiment,
                "published_at": n.published_at.isoformat() if n.published_at else None,
                "themes": n.themes,
                "materiality": score,
                "category": category,
            })
        scored.sort(key=lambda x: (x["materiality"], x["published_at"] or ""), reverse=True)
        return scored[:limit]
