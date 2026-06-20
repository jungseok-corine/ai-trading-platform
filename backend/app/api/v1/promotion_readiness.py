"""승격 준비 현황 보드 API (C-3.13).

활성/테스트 전략 버전을 승격 기준에 대해 평가(persist=False)해 근접도를 반환한다.
⚠️ 통과는 판단일 뿐 — 실거래 활성화는 사람만 한다. read-only 평가로 주문/외부 호출이 없다.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.promotion_readiness_service import PromotionReadinessService

router = APIRouter(prefix="/promotion-readiness", tags=["promotion-readiness"])


def get_service(session: AsyncSession = Depends(get_db)) -> PromotionReadinessService:
    return PromotionReadinessService(session)


@router.get("")
async def get_board(
    criteria_id: int | None = Query(None),
    service: PromotionReadinessService = Depends(get_service),
) -> dict:
    return await service.board(criteria_id=criteria_id)
