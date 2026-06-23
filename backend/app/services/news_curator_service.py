from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import MarketCode
from app.services.ai_analysis.schemas import AnalysisProviderError
from app.services.news_context_service import NewsContextService
from app.trading.analysis.news_llm_score import build_news_scoring_prompt, parse_news_scores
from app.trading.analysis.news_materiality import score_materiality


class NewsCuratorService:
    """종목 뉴스/공시를 중요도로 큐레이션한다 (C-2.57).

    "주가에 영향 없는 뉴스는 분석할 필요 없다"는 원칙 — 룰 기반 중요도(materiality)로
    노이즈를 거르고 중요한 것만 상위로 올린다. 비싼 분석 모델엔 정제본만 넘긴다.
    (정밀 점수가 필요하면 이후 싼 모델 큐레이터로 보강 가능.)
    """

    def __init__(self, session: AsyncSession, llm_provider=None) -> None:
        self._news_svc = NewsContextService(session)
        self._llm_provider = llm_provider  # 주입되면 LLM 정밀화 사용(테스트/설정)

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

        # 룰 점수 (C-2.57). 수집 시 이미 매긴 중요도(raw_payload.materiality)가 있으면 그걸
        # 우선한다 — DART(KR 키워드)·EDGAR(미국 form type)는 소스별 채점기가 다르므로,
        # 영어 헤드라인을 한국어 키워드 채점기에 다시 넣어 떨어뜨리는 일을 막는다.
        rule_scores = [self._ingest_or_rule_score(n) for n in raw]
        # LLM 정밀화 (C-2.65, 옵션) — 룰이 놓친 중요 뉴스를 보강. 실패해도 룰로 진행.
        llm_scores = await self._maybe_llm_scores([n.headline for n in raw])

        scored: list[dict] = []
        for i, n in enumerate(raw):
            rscore, category = rule_scores[i]
            lscore = llm_scores[i] if llm_scores else None
            final = max(rscore, lscore) if lscore is not None else rscore
            if final < min_score:
                continue
            scored.append({
                "headline": n.headline,
                "source": n.source,
                "sentiment": n.sentiment,
                "published_at": n.published_at.isoformat() if n.published_at else None,
                "themes": n.themes,
                "materiality": round(final, 3),
                "rule_score": rscore,
                "llm_score": lscore,
                "category": category,
            })
        scored.sort(key=lambda x: (x["materiality"], x["published_at"] or ""), reverse=True)
        return scored[:limit]

    @staticmethod
    def _ingest_or_rule_score(news) -> tuple[float, str]:
        """수집 시 저장한 중요도가 있으면 (score, category)로 쓰고, 없으면 룰 채점."""
        raw = news.raw_payload or {}
        score = raw.get("materiality")
        if isinstance(score, (int, float)):
            category = raw.get("category") or "low"
            return float(score), category
        return score_materiality(news.headline, news.themes)

    async def _maybe_llm_scores(self, headlines: list[str]) -> list[float | None] | None:
        """설정/주입된 LLM provider가 있으면 헤드라인별 점수를 반환, 없으면 None."""
        provider = self._llm_provider
        if provider is None:
            from app.core.config import get_settings

            s = get_settings()
            if not s.news_curator_llm_enabled:
                return None
            from app.services.ai_analysis.factory import get_analysis_provider

            provider = get_analysis_provider(s.news_curator_provider)
        if not headlines:
            return None
        try:
            result = await provider.analyze(build_news_scoring_prompt(headlines))
        except AnalysisProviderError:
            return None
        return parse_news_scores(result.content or "", len(headlines))
