"""LLM 전략 리서처 API (C-7.3). 수동 트리거 전용 — LLM 비용 발생 주의.

기본 provider는 settings.ai_default_provider (기본 fake — 실수 유료호출 방지).
통과 스펙은 pending 제안 — 승인은 사람.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.strategy_researcher import StrategyResearcherService

router = APIRouter(prefix="/strategy-researcher", tags=["strategy-researcher"])


@router.post("/run")
async def run_researcher(
    count: int = Query(3, ge=1, le=10),
    provider: str | None = Query(None, description="미지정 시 ai_default_provider"),
    session: AsyncSession = Depends(get_db),
) -> dict:
    return await StrategyResearcherService(session).research(
        count=count, provider_name=provider
    )
