"""AI 분석 비용·사용량 관제 API (C-3.1).

`ai_model_responses`의 토큰 기록을 provider/model별·일자별로 집계해 반환한다.
read-only 집계로 주문/외부 호출이 없다. '비용 가드' 화면의 데이터 소스.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.ai_cost_service import AiCostService

router = APIRouter(prefix="/ai-cost", tags=["ai-cost"])


def get_service(session: AsyncSession = Depends(get_db)) -> AiCostService:
    return AiCostService(session)


@router.get("/summary")
async def get_summary(
    days: int = Query(30, ge=1, le=365),
    service: AiCostService = Depends(get_service),
) -> dict:
    return await service.summary(days=days)
