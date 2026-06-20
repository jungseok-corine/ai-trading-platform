from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.ai_analysis import AiModelResponse
from app.trading.analysis.model_pricing import estimate_cost


class AiCostService:
    """AI 분석 토큰 사용량·추정비용 집계 (C-3.1, '비용 가드' 관제).

    `ai_model_responses`의 토큰 기록을 provider/model별·일자별로 모아 운영자가 비용 급증을
    한눈에 보도록 한다. read-only 집계 — 주문/외부 호출이 없고 어떤 상태도 바꾸지 않는다.

    단가는 추정치(`model_pricing`)이며, 단가 미상 모델은 비용 0 + `unpriced`에 표시해
    과소계상을 숨기지 않는다. 토큰 사용량 자체는 항상 정확하므로 이상 급증 탐지엔 충분하다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def summary(self, days: int = 30) -> dict:
        """최근 `days`일 사용량/비용 요약(고정 구조)을 반환한다."""
        since = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        rows = (
            await self._session.execute(
                select(AiModelResponse).where(AiModelResponse.created_at >= since)
            )
        ).scalars().all()

        by_model: dict[tuple[str, str], dict] = {}
        by_day: dict[str, dict] = {}
        unpriced: set[str] = set()
        total = {
            "responses": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "est_cost_usd": 0.0,
        }

        for r in rows:
            cost, priced = estimate_cost(r.model, r.prompt_tokens, r.completion_tokens)
            if not priced and r.model:
                unpriced.add(r.model)

            ptok = r.prompt_tokens or 0
            ctok = r.completion_tokens or 0
            ttok = r.total_tokens if r.total_tokens is not None else ptok + ctok

            key = (r.provider, r.model)
            m = by_model.setdefault(
                key,
                {
                    "provider": r.provider,
                    "model": r.model,
                    "responses": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "est_cost_usd": 0.0,
                    "priced": priced,
                },
            )
            m["responses"] += 1
            m["prompt_tokens"] += ptok
            m["completion_tokens"] += ctok
            m["total_tokens"] += ttok
            m["est_cost_usd"] = round(m["est_cost_usd"] + cost, 6)

            day = r.created_at.date().isoformat() if r.created_at else "unknown"
            d = by_day.setdefault(
                day, {"date": day, "responses": 0, "total_tokens": 0, "est_cost_usd": 0.0}
            )
            d["responses"] += 1
            d["total_tokens"] += ttok
            d["est_cost_usd"] = round(d["est_cost_usd"] + cost, 6)

            total["responses"] += 1
            total["prompt_tokens"] += ptok
            total["completion_tokens"] += ctok
            total["total_tokens"] += ttok
            total["est_cost_usd"] = round(total["est_cost_usd"] + cost, 6)

        models = sorted(by_model.values(), key=lambda x: x["est_cost_usd"], reverse=True)
        daily = sorted(by_day.values(), key=lambda x: x["date"])
        return {
            "days": days,
            "total": total,
            "by_model": models,
            "by_day": daily,
            "unpriced_models": sorted(unpriced),
        }
