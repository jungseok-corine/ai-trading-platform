from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.news_context import NewsEventRepository
from app.services.ai_analysis.factory import get_analysis_provider
from app.services.ai_analysis.schemas import AnalysisProviderError
from app.trading.analysis.disclosure_assessment import (
    build_disclosure_prompt,
    parse_disclosure_assessment,
)


class DisclosureAssessmentService:
    """공시 한 건의 보유 포지션 영향을 LLM으로 온디맨드 평가한다 (C-2.62).

    사람이 요청할 때만 호출된다(토큰 소모 지점). AI는 평가만 — 자동매매/주문은 없다.
    provider는 설정에서 읽으며(기본 fake), 테스트는 provider 주입으로 네트워크 없이 한다.
    """

    def __init__(self, session: AsyncSession, provider=None) -> None:
        self._session = session
        self._news_repo = NewsEventRepository(session)
        if provider is None:
            from app.core.config import get_settings

            provider = get_analysis_provider(get_settings().ai_analysis_provider)
        self._provider = provider

    async def assess(
        self, news_event_id: int, holding_note: str | None = None
    ) -> dict | None:
        event = await self._news_repo.get(news_event_id)
        if event is None:
            return None

        raw = event.raw_payload or {}
        prompt = build_disclosure_prompt(
            symbol_code=event.symbol_code or "",
            headline=event.headline,
            category=raw.get("category"),
            corp_name=raw.get("corp_name"),
            holding_note=holding_note,
        )

        result_meta = {
            "news_event_id": news_event_id,
            "symbol_code": event.symbol_code,
            "headline": event.headline,
        }
        try:
            result = await self._provider.analyze(prompt)
        except AnalysisProviderError as exc:
            return {**result_meta, "error": exc.message, "assessment": None}

        parsed = parse_disclosure_assessment(result.content or "")
        return {
            **result_meta,
            "provider": result.provider,
            "model": result.model,
            "assessment": parsed.to_dict() if parsed else None,
            "raw": None if parsed else (result.content or "")[:1000],
        }
