from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.ai_analysis import AiAnalysisRun, AiModelResponse
from app.domain.models.strategy_proposal import StrategyProposal
from app.trading.analysis.model_pricing import estimate_cost


class AnalysisAuditService:
    """AI 분석 실행 감사 뷰 (C-3.4).

    최근 `ai_analysis_runs`를 실행 메타 + 토큰/추정비용 + 이 run이 만든 제안 수와 함께
    나열한다. "AI가 무엇을 분석했고, 얼마를 썼고, 제안으로 이어졌는가"를 한 줄씩 본다.
    read-only 집계 — 주문/외부 호출이 없다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def recent(self, limit: int = 20) -> list[dict]:
        runs = (
            await self._session.execute(
                select(AiAnalysisRun)
                .order_by(AiAnalysisRun.created_at.desc(), AiAnalysisRun.id.desc())
                .limit(limit)
            )
        ).scalars().all()
        if not runs:
            return []
        run_ids = [r.id for r in runs]

        # 토큰/비용: run별로 응답을 한 번에 모은다(N+1 회피).
        responses = (
            await self._session.execute(
                select(AiModelResponse).where(AiModelResponse.run_id.in_(run_ids))
            )
        ).scalars().all()
        tokens: dict[int, int] = {}
        cost: dict[int, float] = {}
        for resp in responses:
            ttok = resp.total_tokens
            if ttok is None:
                ttok = (resp.prompt_tokens or 0) + (resp.completion_tokens or 0)
            tokens[resp.run_id] = tokens.get(resp.run_id, 0) + ttok
            c, _ = estimate_cost(resp.model, resp.prompt_tokens, resp.completion_tokens)
            cost[resp.run_id] = round(cost.get(resp.run_id, 0.0) + c, 6)

        # 제안 연결 수: run별 카운트를 한 번에.
        prop_rows = (
            await self._session.execute(
                select(StrategyProposal.ai_analysis_run_id, func.count(StrategyProposal.id))
                .where(StrategyProposal.ai_analysis_run_id.in_(run_ids))
                .group_by(StrategyProposal.ai_analysis_run_id)
            )
        ).all()
        proposals = {rid: cnt for rid, cnt in prop_rows}

        return [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "analysis_type": r.analysis_type.value,
                "mode": r.mode.value,
                "provider": r.provider,
                "model": r.model,
                "prompt_type": r.prompt_type,
                "status": r.status.value,
                "strategy_version_id": r.strategy_version_id,
                "truncated": r.truncated,
                "warnings": len(r.warnings) if r.warnings else 0,
                "error_message": r.error_message,
                "total_tokens": tokens.get(r.id, 0),
                "est_cost_usd": cost.get(r.id, 0.0),
                "proposals_created": proposals.get(r.id, 0),
            }
            for r in runs
        ]
