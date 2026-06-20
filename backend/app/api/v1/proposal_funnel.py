"""연구 루프 제안 퍼널 API (C-3.2).

전략·스캐너 제안의 생성→승인/거절→버전생성 흐름 + 회고 결과를 집계해 반환한다.
read-only 집계로 주문/외부 호출이 없다.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.proposal_funnel_service import ProposalFunnelService

router = APIRouter(prefix="/proposal-funnel", tags=["proposal-funnel"])


def get_service(session: AsyncSession = Depends(get_db)) -> ProposalFunnelService:
    return ProposalFunnelService(session)


@router.get("")
async def get_funnel(
    days: int = Query(30, ge=1, le=365),
    service: ProposalFunnelService = Depends(get_service),
) -> dict:
    return await service.funnel(days=days)
